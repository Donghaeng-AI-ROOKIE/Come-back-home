import copy
import os
from pathlib import Path
from datetime import timedelta
import pytest
from app import storage
from app.config import settings
from app.llm import mind_policy
from app.phase0 import mind_preparation
from app.phase2 import pipeline,continuous_prediction
from app.schemas.report import MissingReport
from app.schemas.case import Case
from tests.kintex_fixtures import geography,person,prior,START
from tests.test_person_policy import policy,rule,obs


@pytest.fixture(scope='module')
def full_geography():
    from app.geo.roadnet import verified_network
    from app.schemas.common import GeoPoint
    # Six hours of walking requires the already acquired wide KINTEX cache.
    # Do not enlarge the small fixture's declared coverage or fetch a new map.
    path=Path(os.environ.get('CBH_FULL_KINTEX_FIXTURE',str(
        Path(__file__).resolve().parents[4]/'실험/MIND_completion_20261004/map_full_support/kintex_walk.graphml')))
    if not path.exists():pytest.skip('wide KINTEX cache required for long-horizon integration')
    return verified_network(path),GeoPoint(lat=37.6652142,lng=126.7483258)

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

def test_product_hourly_update_reuses_preparation_prior_and_walkers(full_geography,monkeypatch):
    net,center=full_geography;p=prepared(center);storage.personas.save(p.id,p);case=case_for(p);calls=[]
    monkeypatch.setattr(pipeline,'_load_roadnet',lambda *a,**k:(net,''))
    monkeypatch.setattr(pipeline.situation_link,'cached',lambda *a:[])
    monkeypatch.setattr(pipeline,'_initial_prior',lambda *a:calls.append('prior') or prior())
    def mc(*args,**kw):pytest.fail('continuous pair must not call legacy terminal-distance sampling')
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
    valid={'source_assessment':'합성 검사: 실행 반응 없음','rules':[],'non_action_note_ids':[n['id'] for n in src['notes']]}
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


def test_partial_walk_does_not_replace_last_complete_checkpoint(full_geography,monkeypatch):
    net,center=full_geography;p=prepared(center);c=case_for(p)
    continuous_prediction.run(c,p,prior(),net,1,seed=42)
    previous=copy.deepcopy(c.continuous_state)
    original=continuous_prediction.Population
    class PartiallyBlocked(original):
        def advance_to(self,minute):
            self.particles[0].blocked=True
            self._event(self.particles[0],'map_boundary')
            return super().advance_to(minute)
    monkeypatch.setattr(continuous_prediction,'Population',PartiallyBlocked)
    cells,quality=continuous_prediction.run(c,p,prior(),net,2,seed=42)
    assert quality['unresolved_mass']==pytest.approx(1/6)
    assert sum(cells.values())==pytest.approx(5/6)
    assert c.continuous_state==previous


def test_both_channels_continue_after_four_hours(full_geography):
    net,center=full_geography;p=prepared(center);c=case_for(p)
    a,stat_a,qa=continuous_prediction.run_pair(c,p,prior(),net,4,seed=42)
    before=copy.deepcopy(c.continuous_state)
    b,stat_b,qb=continuous_prediction.run_pair(c,p,prior(),net,6,seed=42)
    assert qb['checkpoint_reused'] and qb['statistical']['checkpoint_reused']
    assert all(x['minute']==pytest.approx(360) for x in c.continuous_state['statistical']['checkpoint']['particles'])
    assert all(y['distance']>x['distance'] for x,y in zip(
        before['statistical']['checkpoint']['particles'],c.continuous_state['statistical']['checkpoint']['particles']))
    assert stat_a!=stat_b


def test_pair_preview_and_split_execution_preserve_both_random_streams(full_geography):
    net,center=full_geography;p=prepared(center);whole=case_for(p);split=whole.model_copy(deep=True)
    continuous_prediction.run_pair(whole,p,prior(),net,2,seed=42)
    continuous_prediction.run_pair(split,p,prior(),net,1,seed=42)
    before=copy.deepcopy(split.continuous_state)
    for hour in (.5,3):continuous_prediction.run_pair(split,p,prior(),net,hour,seed=42,persist=False)
    assert split.continuous_state==before
    continuous_prediction.run_pair(split,p,prior(),net,2,seed=42)
    assert split.continuous_state==whole.continuous_state


def test_statistical_failure_rolls_back_personal_checkpoint(full_geography,monkeypatch):
    net,center=full_geography;p=prepared(center);c=case_for(p)
    continuous_prediction.run_pair(c,p,prior(),net,1,seed=42)
    before=copy.deepcopy(c.continuous_state);original=continuous_prediction.Population
    constructed=[]
    class BlockStatistical(original):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            constructed.append(self)
        def advance_to(self,minute):
            if len(constructed)==2:
                self.particles[0].blocked=True
                self._event(self.particles[0],'map_boundary')
            return super().advance_to(minute)
    monkeypatch.setattr(continuous_prediction,'Population',BlockStatistical)
    a,b,q=continuous_prediction.run_pair(c,p,prior(),net,2,seed=42)
    assert q['unresolved_mass']==pytest.approx(.3/6)
    assert not q['checkpoint_committed'] and not q['statistical']['checkpoint_committed']
    assert c.continuous_state==before


def test_personal_wait_is_not_diluted_by_policy_free_thirty_percent(geography):
    from app.phase2 import combine
    net,center=geography;p=prepared(center);c=case_for(p)
    wait=rule('wait',when=[[dict(fact='lost_awareness',op='eq',value=True),
                           dict(fact='family_present',op='eq',value=False)]])
    p.prepared_mind['policy']=policy(wait).model_dump()
    c.report.behavior_observations=[obs('lost_awareness',True),obs('family_present',False,0,90),
                                    obs('family_present',True,90)]
    a,b,q=continuous_prediction.run_pair(c,p,prior(),net,1,seed=42)
    assert q['personal_policy_shared_between_channels']
    assert not q['policy_free_ablation_included_in_mixture']
    for checkpoint in (c.continuous_state['checkpoint'],c.continuous_state['statistical']['checkpoint']):
        assert all(x['waiting']==pytest.approx(60) and x['distance']==0 for x in checkpoint['particles'])
    assert a==b
    assert combine.alpha_pool([a,b],alphas=[.7,.3],mode='linear')==pytest.approx(a)
    continuous_prediction.run_pair(c,p,prior(),net,1.55,seed=42)
    for checkpoint in (c.continuous_state['checkpoint'],c.continuous_state['statistical']['checkpoint']):
        assert all(x['waiting']==pytest.approx(90) and x['distance']>0 for x in checkpoint['particles'])


def test_pair_only_removes_updated_mind_not_prepared_reactions(geography):
    from app.schemas.prediction import MindState
    net,center=geography;p=prepared(center);c=case_for(p)
    c.mind=MindState(confusion=.2,changed=True)
    _,_,quality=continuous_prediction.run_pair(c,p,prior(),net,.1,seed=42)
    assert quality['direction_state_source']=='updated_mind_state'
    assert quality['statistical']['direction_state_source']=='unobserved_default_0.5'
    assert c.continuous_state['checkpoint']['policy_digest']==c.continuous_state['statistical']['checkpoint']['policy_digest']
