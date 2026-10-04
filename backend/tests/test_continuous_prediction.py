import copy
from datetime import timedelta
import pytest
from app import storage
from app.config import settings
from app.llm import mind_policy
from app.phase0 import mind_preparation
from app.phase2 import pipeline,continuous_prediction
from app.schemas.report import MissingReport
from app.schemas.case import Case
from tests.test_mind_upgrade import geography,person,prior,START
from tests.test_person_policy import policy,rule,obs

@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    storage.reset_for_tests();monkeypatch.setattr(settings,'mc_num_walkers',6)
    # These test authored executor mechanics, not model release qualification.
    monkeypatch.setattr(mind_policy,'RELEASE_QUALIFIED',True)
    yield
    storage.reset_for_tests()

def prepared(center):
    p=person(center);key=mind_policy.revision(p)
    p.prepared_mind={'revision':key,'policy':policy(rule()).model_dump()}
    p.mind_preparation_status={'state':'ready'}
    return p

def case_for(p):
    r=MissingReport(id='report',persona_id=p.id,missing_type='dementia',lkp=p.home,lkp_time=START)
    return Case(id='case',report=r,lkp=r.lkp,lkp_time=r.lkp_time)

def test_product_hourly_update_reuses_preparation_prior_and_walkers(geography,monkeypatch):
    net,center=geography;p=prepared(center);storage.personas.save(p.id,p);case=case_for(p);calls=[]
    monkeypatch.setattr(pipeline,'_load_roadnet',lambda *a,**k:(net,''))
    monkeypatch.setattr(pipeline.situation_link,'cached',lambda *a:[])
    monkeypatch.setattr(pipeline,'_initial_prior',lambda *a:calls.append('prior') or prior())
    def mc(*args,**kw):
        assert kw['mode']=='statistical'
        return {'stat':1.}
    monkeypatch.setattr(pipeline.simulation,'run_monte_carlo',mc)
    a=pipeline.run_prediction(case,now=START+timedelta(hours=1),seed=42)
    assert a.quality['continuous_clock'] and not a.quality['checkpoint_reused']
    b=pipeline.run_prediction(case,now=START+timedelta(hours=2),seed=42)
    assert b.quality['checkpoint_reused'] and calls==['prior']
    assert all(x['minute']==pytest.approx(120) for x in case.continuous_state['checkpoint']['particles'])
    assert b.quality['new_model_calls_during_walk']==0

def test_preview_does_not_mutate_live_case(geography,monkeypatch):
    net,center=geography;p=prepared(center);c=case_for(p);c.prior=prior()
    continuous_prediction.run(c,p,c.prior,net,1,seed=42)
    before=c.model_dump(mode='json')
    for hour in (.5,2):continuous_prediction.run(c,p,c.prior,net,hour,seed=42,persist=False)
    assert c.model_dump(mode='json')==before

def test_profile_revision_invalidates_policy_before_simulation(geography):
    net,center=geography;p=prepared(center);c=case_for(p)
    p.onboarding_turns[0]['answer']='전혀 다른 새 관찰'
    cells,q=continuous_prediction.run(c,p,prior(),net,1)
    assert cells is None and q['personal_policy_status']=='stale'

def test_report_change_resets_checkpoint(geography):
    net,center=geography;p=prepared(center);c=case_for(p)
    continuous_prediction.run(c,p,prior(),net,1,seed=42)
    c.report.behavior_observations=[obs('lost_awareness',True)]
    _,q=continuous_prediction.run(c,p,prior(),net,1,seed=42)
    assert not q['checkpoint_reused']

def test_preparation_failure_is_visible_does_not_erase_initial(geography,monkeypatch):
    _,center=geography;p=person(center);p.prepared_initial={'core':{'sentinel':1}};storage.personas.save(p.id,p)
    for name in ('kexaone_api_key','kexaone_model','kexaone_base_url'):monkeypatch.setattr(settings,name,'offline')
    def fail(*a):raise RuntimeError('sensitive input')
    monkeypatch.setattr(mind_preparation,'interpret',fail)
    mind_preparation.prepare(p.id)
    got=storage.personas.get(p.id)
    assert got.prepared_initial==p.prepared_initial and got.mind_preparation_status['state']=='failed'
    assert 'sensitive' not in str(got.mind_preparation_status)
    monkeypatch.setattr(mind_preparation,'interpret',lambda *a:pytest.fail('automatic retry'))
    mind_preparation.prepare(p.id)

def test_late_mind_result_cannot_overwrite_edited_person(geography,monkeypatch):
    _,center=geography;p=person(center);storage.personas.save(p.id,p)
    for name in ('kexaone_api_key','kexaone_model','kexaone_base_url'):monkeypatch.setattr(settings,name,'offline')
    def interpret(*a):
        current=storage.personas.get(p.id);current.version+=1;storage.personas.save(p.id,current)
        return policy(rule()).model_dump(),[]
    monkeypatch.setattr(mind_preparation,'interpret',interpret);mind_preparation.prepare(p.id)
    assert storage.personas.get(p.id).prepared_mind=={}

def test_public_api_excludes_private_checkpoint_and_policy(geography):
    from fastapi.testclient import TestClient
    from app.main import app
    _,center=geography;p=prepared(center);storage.personas.save(p.id,p);c=case_for(p)
    c.continuous_state={'private_marker':'rng-and-path'};storage.cases.save(c.id,c)
    client=TestClient(app)
    result=client.get('/phase1/cases/case')
    assert result.status_code==200 and 'continuous_state' not in result.json()
    result=client.get('/phase0/personas/'+p.id)
    assert result.status_code==200 and 'prepared_mind' not in result.json()
    assert storage.cases.get(c.id).continuous_state['private_marker']=='rng-and-path'


def test_checkpoint_persists_with_case_and_is_removed_on_delete(geography,tmp_path,monkeypatch):
    from app.schemas.case import Case
    _,center=geography;p=prepared(center);c=case_for(p);c.continuous_state={'private_marker':'SYNTHETIC_CHECKPOINT_20261004'}
    monkeypatch.setattr(settings,'persist_storage',True)
    monkeypatch.setattr(settings,'storage_db_path',str(tmp_path/'case.db'))
    store=storage.Repository(Case,'checkpoint_test');store.save(c.id,c)
    fresh=storage.Repository(Case,'checkpoint_test')
    assert fresh.get(c.id).continuous_state==c.continuous_state
    fresh.delete(c.id);storage.vacuum()
    assert b'SYNTHETIC_CHECKPOINT_20261004' not in (tmp_path/'case.db').read_bytes()

def test_failed_candidate_is_not_activated_or_called(geography,monkeypatch):
    _,center=geography;p=prepared(center);storage.personas.save(p.id,p)
    monkeypatch.setattr(mind_policy,'RELEASE_QUALIFIED',False)
    for name in ('kexaone_api_key','kexaone_model','kexaone_base_url'):monkeypatch.setattr(settings,name,'offline')
    monkeypatch.setattr(mind_preparation,'interpret',lambda *a:pytest.fail('unqualified candidate called'))
    mind_preparation.prepare(p.id)
    assert mind_preparation.ready(storage.personas.get(p.id))==(None,'candidate_not_qualified')

def test_incomplete_prediction_keeps_previous_map_and_reports_503(geography,monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    net,center=geography;p=prepared(center);storage.personas.save(p.id,p);c=case_for(p)
    c.current_poa={'previous-published-cell':1.};storage.cases.save(c.id,c)
    monkeypatch.setattr(pipeline,'_load_roadnet',lambda *a,**k:(net,''))
    monkeypatch.setattr(pipeline.situation_link,'cached',lambda *a:[])
    monkeypatch.setattr(pipeline,'_initial_prior',lambda *a:prior())
    monkeypatch.setattr(continuous_prediction,'run',lambda *a,**k:({'partial-cell':.8},{'unresolved_mass':.2,'unresolved_reasons':{'map_boundary':1}}))
    result=TestClient(app).post('/phase2/cases/case/predict')
    assert result.status_code==503,result.text
    assert result.json()['detail']['quality']['unresolved_mass']==.2
    assert storage.cases.get(c.id).current_poa=={'previous-published-cell':1.}

def test_second_source_review_runs_after_malformed_draft(monkeypatch):
    import json
    from app.llm import mind_policy_candidate
    src=mind_policy.source(person());calls=[]
    valid={'rules':[],'unused_note_ids':[n['id'] for n in src['notes']]}
    def request(url,body,**kw):
        calls.append(body)
        if len(calls)==1:content='{broken public JSON'
        else:
            assert json.loads(body['messages'][1]['content'])['draft_to_review']=='{broken public JSON'
            content=json.dumps(valid)
        return {'choices':[{'finish_reason':'stop','message':{'content':content}}]}
    monkeypatch.setattr(mind_preparation,'logged_json_request',request)
    policy,audit=mind_preparation.interpret(src,'offline-test')
    assert len(calls)==2 and [x['schema_valid'] for x in audit]==[False,True]
    assert policy['rules']==[]

def test_unsupported_execution_preserves_checkpoint_and_unresolved_mass(geography,monkeypatch):
    net,center=geography;p=prepared(center);c=case_for(p)
    continuous_prediction.run(c,p,prior(),net,1,seed=42)
    previous=copy.deepcopy(c.continuous_state)
    def bad(*a,**k):raise ValueError('private source must not appear in quality')
    monkeypatch.setattr(continuous_prediction,'Population',bad)
    cells,q=continuous_prediction.run(c,p,prior(),net,2,seed=42)
    assert cells=={} and q['unresolved_mass']==1
    assert c.continuous_state==previous and 'private source' not in str(q)
