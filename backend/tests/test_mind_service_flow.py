"""Saved synthetic onboarding -> actual worker/API/pipeline -> DB restore/closure.

External model and map replies are captured/reused. This is an integration test,
not new model accuracy, a live chatbot test, or a production deployment test.
"""
from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
import json
import os
import pytest
from fastapi.testclient import TestClient
from app import storage
from app.config import settings
from app.llm import mind_policy as m
from app.main import app
from app.phase0 import person_preparation as pp, mind_preparation, interview
from app.phase2 import pipeline, initial_person, claim_check
from app.schemas.case import Case
from app.schemas.persona import Persona
from tests.test_place_bound_walk import cached

FIXTURE=Path(__file__).parent/'fixtures/service_connection'

def read(name):return json.loads((FIXTURE/name).read_text())


@pytest.mark.parametrize('report_first',[False,True],ids=['onboard_before_incident','urgent_report_then_onboard'])
@pytest.mark.parametrize('candidate_kind',['extended','guarded_core','guarded_partial'])
def test_saved_onboarding_preparation_actual_api_hourly_restore_and_found(cached,monkeypatch,tmp_path,report_first,candidate_kind):
    storage.reset_for_tests()
    for key,value in {'mind_policy_deployment':'staging','persist_storage':True,
        'storage_db_path':str(tmp_path/'state.db'),'privacy_audit_path':str(tmp_path/'audit.jsonl'),
        'privacy_admin_key':'synthetic-test-only','mc_num_walkers':8,'axis_scoring_enabled':False,
        'reflex_alert_on_intake':False,'reverse_geocode_on_intake':False,'roadnet_preload':False,
        'kexaone_model':'saved-synthetic-replay','kexaone_api_key':'offline','kexaone_base_url':'https://offline.invalid/v1'}.items():
        monkeypatch.setattr(settings,key,value)
    assert not m.RELEASE_QUALIFIED # test the real staging boundary, not a gate monkeypatch
    net,_,_=cached
    original=Persona.model_validate(read('persona.json'))
    original.prepared_initial={};original.prepared_mind={};original.initial_preparation_status={};original.mind_preparation_status={}
    jobs=[];http_calls=[];numeric_calls=[]
    monkeypatch.setattr(pp,'_dispatch',lambda *a:jobs.append(a))
    monkeypatch.setattr(interview,'ensure_axis_scores',lambda *a:None)
    monkeypatch.setattr(initial_person,'cached_research',lambda *a:[])
    monkeypatch.setattr(initial_person,'interpret',lambda payload:deepcopy(read('initial.json')))
    monkeypatch.setattr(claim_check,'verify',lambda parsed,payload:parsed)
    raw=json.loads(read('mind_public.json')['final_content'])
    if candidate_kind=='extended':
        for row in raw['rules']:row['after_wait']=[] # explicit schema migration only
    else:
        monkeypatch.setattr(settings,'mind_policy_contract','guarded_core')
    if candidate_kind=='guarded_partial':
        bad=deepcopy(raw['rules'][0]);bad.update(action='seek',goal_place='',applies_only_at=[],hold_minutes=0)
        raw['rules'].append(bad)
    expected_calls=2  # guarded core also re-reads unrepresented source notes
    def replay_http(url,body,**kw):
        http_calls.append(body)
        assert json.loads(body['messages'][1]['content'])['original_notes']
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(raw,ensure_ascii=False)}}]}
    monkeypatch.setattr(mind_preparation,'logged_json_request',replay_http)
    monkeypatch.setattr(pipeline,'_load_roadnet',lambda *a,**kw:(net,''))
    monkeypatch.setattr(pipeline.situation_link,'cached',lambda *a:[])
    # Keep real prepared-initial projection; substitute only external SAR numeric response.
    monkeypatch.setattr(pipeline.exaone,'generate_prior',lambda persona,report:numeric_calls.append(1) or pipeline.exaone._default_prior(persona,report))
    def no_legacy(*a,**kw):pytest.fail('ready policy bypassed new continuous executor')
    monkeypatch.setattr(pipeline.simulation,'run_monte_carlo',no_legacy)
    monkeypatch.setattr(settings,'layer2_periodic_minutes',60)
    client=TestClient(app)
    start=datetime(2026,10,9,8)
    body={'missing_type':'dementia','lkp':original.home.model_dump(),'lkp_time':start.isoformat()}
    if report_first:
        response=client.post('/phase1/reports',json=body);assert response.status_code==200
        case_id=response.json()['id']
    storage.personas.save(original.id,original)
    pp.enqueue(original.id);assert len(jobs)==1
    pp.run_job(*jobs.pop())
    saved=storage.personas.get(original.id)
    assert saved.initial_preparation_status['state']=='ready'
    assert saved.mind_preparation_status['state']=='ready'
    assert saved.prepared_mind['interpretation_contract']==mind_preparation.selected().VERSION
    assert saved.prepared_mind['public_output_count']==expected_calls
    assert saved.prepared_mind['invalid_first_output_corrected'] is False
    if candidate_kind in ('guarded_core','guarded_partial'):
        assert saved.prepared_mind['semantic_review']=='not_independently_validated'
    assert mind_preparation.ready(saved)[1]==('ready_partial' if candidate_kind=='guarded_partial' else 'ready')
    if candidate_kind=='guarded_partial':
        assert saved.prepared_mind['policy_quality']=='partial'
        assert saved.prepared_mind['quarantined_rule_count']==1
    assert len(http_calls)==expected_calls
    if report_first:
        # Linking triggers only this case; suppress thread scheduling so test
        # drives the same predict API at deterministic times below.
        from app.phase0 import persona_events
        monkeypatch.setattr(persona_events,'notify_persona_updated',lambda *a:None)
        response=client.patch('/phase1/cases/'+case_id+'/persona',json={'persona_id':saved.id})
        assert response.status_code==200
    else:
        body['persona_id']=saved.id
        response=client.post('/phase1/reports',json=body);assert response.status_code==200
        case_id=response.json()['id']
    assert not jobs # report/link must reuse completed preparation
    class Clock:
        value=start
        @classmethod
        def now(cls):return cls.value
    monkeypatch.setattr(pipeline,'datetime',Clock)
    evidence=[]
    for hour in (1,2,4,6):
        Clock.value=start+timedelta(hours=hour)
        if candidate_kind=='guarded_core' and hour>1:
            from app.phase2.refresher import refresh_due_cases
            assert refresh_due_cases(now=Clock.value)
            q=storage.cases.get(case_id).prediction_quality
        else:
            response=client.post('/phase2/cases/'+case_id+'/predict?seed=17')
            assert response.status_code==200,response.text
            q=response.json()['quality']
        from app.phase2.persistent_context_walk import VERSION as CONTEXT_EXECUTOR
        assert q['context_executor']==CONTEXT_EXECUTOR
        assert q['deployment_scope']=='staging' and q['policy_contract']==m.VERSION
        assert q['unresolved_mass']==0 and q['resolved_mass']==pytest.approx(1)
        if candidate_kind=='guarded_partial':
            assert q['personal_policy_status']=='ready_partial'
            assert q['personal_policy_quality']=='partial'
            assert q['quarantined_rule_count']==1 and q['unrepresented_note_count']>=1
        assert q['statistical']['context_executor']==q['context_executor']
        assert q['checkpoint_reused']==(hour!=1)
        # Reload from SQLite through new repository instances, not an in-memory copy.
        monkeypatch.setattr(storage,'cases',storage.Repository(Case,'cases'))
        monkeypatch.setattr(storage,'personas',storage.Repository(Persona,'personas'))
        restored=storage.cases.get(case_id)
        assert all(p['minute']==pytest.approx(hour*60) for p in restored.continuous_state['checkpoint']['particles'])
        assert all(p['minute']==pytest.approx(hour*60) for p in restored.continuous_state['statistical']['checkpoint']['particles'])
        evidence.append({'hour':hour,'quality':q,'cell_count':len(restored.current_poa)})
    assert len(http_calls)==expected_calls and len(numeric_calls)==1
    public=client.get('/phase1/cases/'+case_id).json()
    assert 'continuous_state' not in public
    response=client.post('/privacy/cases/'+case_id+'/close',json={'reason':'found'},headers={'x-privacy-admin-key':'synthetic-test-only'})
    assert response.status_code==200,response.text
    assert client.post('/phase2/cases/'+case_id+'/predict').status_code==409
    assert client.get('/phase3/cases/'+case_id+'/poa?elapsed_hours=6').status_code==409
    if os.environ.get('CBH_SERVICE_EVIDENCE'):
        out=Path(os.environ['CBH_SERVICE_EVIDENCE']);out.mkdir(parents=True,exist_ok=True)
        (out/(candidate_kind+('_urgent.json' if report_first else '_preregistered.json'))).write_text(json.dumps({
            'scope':'saved synthetic model response replay, not new model accuracy',
            'onboarding_source':'captured synthetic guardian Q&A',
            'hourly':evidence,'model_transport_replay_calls':len(http_calls),'numeric_prior_replay_calls':len(numeric_calls),
            'sqlite_restore':True,'found_blocks_prediction':True},ensure_ascii=False,indent=2))
    storage.reset_for_tests()
