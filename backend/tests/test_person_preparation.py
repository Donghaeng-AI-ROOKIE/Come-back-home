"""Background lifecycle and emergency reporting, with no model/network calls."""
import copy
import json
from datetime import datetime, timezone, timedelta
import pytest
from fastapi import HTTPException
from app import storage
from app.config import settings
from app.api import phase0, phase1
from app.llm import initial_behavior, person_scope
from app.phase0 import person_preparation as prep, persona_events
from app.phase2 import initial_person
from app.schemas.case import Case, CaseStatus
from tests.test_person_evidence_projection import sample

@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    storage.reset_for_tests()
    for name in ('kexaone_api_key','kexaone_base_url','kexaone_model'):
        monkeypatch.setattr(settings,name,'offline-test')
    monkeypatch.setattr(prep,'_dispatch',lambda *args: None)
    monkeypatch.setattr(persona_events,'notify_persona_updated',lambda *args: None)
    yield
    storage.reset_for_tests()

def queue(sample):
    p=sample[0];storage.personas.save(p.id,p)
    return prep.enqueue(p.id)

def make_ready(sample):
    p=sample[0];key=prep.fingerprint(p)
    p.initial_preparation_status={'state':'ready','fingerprint':key}
    p.prepared_initial={'fingerprint':key,'core':copy.deepcopy(sample[-2]),'scope':copy.deepcopy(sample[-1]),'profile_snapshot_at':'2026-01-01T12:00:00'}
    return p

def test_enqueues_once_without_calling_model(sample,monkeypatch):
    calls=[]
    monkeypatch.setattr(prep,'_dispatch',lambda *x:calls.append(x))
    monkeypatch.setattr(initial_person,'interpret',lambda *x:pytest.fail('synchronous model call'))
    p=queue(sample)
    assert p.initial_preparation_status['state']=='queued'
    assert prep.enqueue(p.id) is None
    assert len(calls)==1

def test_job_prepares_without_fabricated_incident(sample,monkeypatch):
    p=queue(sample);seen=[]
    monkeypatch.setattr(initial_person,'cached_research',lambda p,r: [])
    def interpret(payload):
        seen.append(payload)
        return {'core':sample[-2],'context':sample[-1]}
    monkeypatch.setattr(initial_person,'interpret',interpret)
    prep.run_job(p.id,p.initial_preparation_status['job_id'])
    ready=storage.personas.get(p.id)
    assert ready.initial_preparation_status['state']=='ready'
    assert seen[0]['incident']['status']=='not_reported'
    assert seen[0]['incident']['last_seen_time'] is None
    assert seen[0]['SAR_reference']['status']=='not_generated_before_incident'
    assert ready.prepared_initial['core']==sample[-2]

@pytest.mark.parametrize('action',['delete','edit'])
def test_late_completion_cannot_resurrect_or_overwrite(sample,monkeypatch,action):
    p=queue(sample)
    monkeypatch.setattr(initial_person,'cached_research',lambda *a: [])
    def interpret(payload):
        if action=='delete':storage.personas.delete(p.id)
        else:
            current=storage.personas.get(p.id).model_copy(deep=True)
            current.version+=1;current.onboarding_quotes={'new':['새 관찰']}
            storage.personas.save(p.id,current);prep.enqueue(p.id)
        return {'core':sample[-2],'context':sample[-1]}
    monkeypatch.setattr(initial_person,'interpret',interpret)
    prep.run_job(p.id,p.initial_preparation_status['job_id'])
    current=storage.personas.get(p.id)
    assert current is None if action=='delete' else current.prepared_initial=={}

def test_failures_require_explicit_retry_and_recovery_does_not_retry_running(sample,monkeypatch):
    p=queue(sample);dispatched=[]
    monkeypatch.setattr(initial_person,'cached_research',lambda *a: [])
    def fail(*a):raise RuntimeError('secret must not persist')
    monkeypatch.setattr(initial_person,'interpret',fail)
    prep.run_job(p.id,p.initial_preparation_status['job_id'])
    failed=storage.personas.get(p.id)
    assert failed.initial_preparation_status['state']=='failed'
    assert 'secret' not in json.dumps(failed.initial_preparation_status)
    assert prep.enqueue(p.id) is None
    fresh=prep.enqueue(p.id,retry=True)
    fresh.initial_preparation_status['state']='running';storage.personas.save(p.id,fresh)
    monkeypatch.setattr(prep,'_dispatch',lambda *a:dispatched.append(a))
    prep.recover()
    assert storage.personas.get(p.id).initial_preparation_status['state']=='interrupted'
    assert dispatched==[]

def test_saved_traits_reused_without_k_and_goal_not_assumed_current(sample,monkeypatch):
    p=make_ready(sample);p.prepared_initial['core']['goals']['공원'].update(value='current_statement',note_ids=['N2'])
    p.created_at=datetime(2026,1,1,9)
    monkeypatch.setattr(initial_person,'interpret',lambda *a:pytest.fail('K on prediction'))
    r=sample[1].model_copy(update={'lkp_time':datetime(2026,9,25,10)})
    for _ in range(2):
        out=prep.apply_prepared(p,r,sample[2],sample[3])
        assert out.initial_interpretation['K_called_during_prediction'] is False
        assert out.initial_interpretation['semantic_contract']['goals']['공원']['value']=='historical_only'
    assert p.prepared_initial['core']['goals']['공원']['value']=='current_statement'

def test_time_rules_select_incident_period_without_losing_other_branch(sample):
    p=make_ready(sample)
    p.prepared_initial['scope']['behavior_rules']=[
        {'period':'clock_day','dimension':'persistence','value':'keep_moving','note_ids':['N0']},
        {'period':'clock_night','dimension':'persistence','value':'wait_for_help','note_ids':['N0']}]
    values=[]
    for hour in (10,22):
        r=type(sample[1]).model_validate({**sample[1].model_dump(), 'lkp_time':datetime(2026,9,25,hour,tzinfo=timezone(timedelta(hours=9)))})
        out=prep.apply_prepared(p,r,sample[2],sample[3])
        values.append(out.initial_interpretation['semantic_contract']['persistence']['value'])
    assert values==['keep_moving','wait_for_help']
    assert len(p.prepared_initial['scope']['behavior_rules'])==2

def test_no_profile_pending_and_stale_have_explicit_status(sample):
    _,r,sar,default,*_=sample
    assert prep.apply_prepared(None,r,sar,default).initial_interpretation['status']=='no_persona'
    p=queue(sample)
    assert prep.apply_prepared(p,r,sar,default).initial_interpretation['status']=='preparation_queued'
    p=make_ready(sample);p.age+=1
    assert prep.apply_prepared(p,r,sar,default).initial_interpretation['status']=='preparation_stale'

def test_emergency_profile_link_is_idempotent_and_preserves_case(sample,monkeypatch):
    p,r,*_=sample;storage.personas.save(p.id,p)
    r=r.model_copy(update={'persona_id':None})
    case=Case(id='urgent',report=r,lkp=r.lkp,lkp_time=r.lkp_time,current_poa={'cell':1})
    storage.cases.save(case.id,case);events=[]
    monkeypatch.setattr(persona_events,'notify_persona_updated',lambda *a:events.append(a))
    for _ in range(2):out=phase1.link_persona(case.id,phase1.LinkPersonaIn(persona_id=p.id))
    assert out.report.persona_id==p.id and out.current_poa=={'cell':1}
    assert len(storage.cases.list())==1 and len(events)==1
    out.status=CaseStatus.closed
    with pytest.raises(HTTPException) as err:phase1.link_persona(case.id,phase1.LinkPersonaIn(persona_id=p.id))
    assert err.value.status_code==409

def test_emergency_without_persona_does_not_schedule_k(sample,monkeypatch):
    from app.phase1 import intake
    monkeypatch.setattr(prep,'enqueue',lambda *a:pytest.fail('no facts to interpret'))
    monkeypatch.setattr(settings,'reflex_alert_on_intake',False)
    monkeypatch.setattr(settings,'roadnet_preload',False)
    case=intake.create_report(missing_type='dementia',lkp=sample[1].lkp,lkp_time=sample[1].lkp_time)
    assert case.report.persona_id is None and case.status==CaseStatus.intake

def test_edit_invalidates_ready_result_and_prefers_explicit_guardian_correction(sample):
    p=make_ready(sample);storage.personas.save(p.id,p)
    updated=phase0.update_persona(p.id,phase0.UpdatePersonaIn(behavior_notes=['정정: 보호자를 기다리지 않고 계속 걷는다.']))
    assert updated.version==1 and updated.prepared_initial=={}
    payload=initial_behavior.build_payload(updated,None,[],None)
    assert [n['text'] for n in initial_behavior.evidence_notes(payload)]==updated.behavior_notes
    assert updated.onboarding_quotes==p.onboarding_quotes

def test_spatial_scope_and_or_condition_are_independent(sample):
    z={'persistence':{'evidence':'missing','pattern':'unresolved','value':'unknown','note_ids':[]},
       'environment':{f:{'response':'unknown','spatial_scope':'unknown','condition':'unknown','condition_clauses':[],'note_ids':[]} for f in ('water','forest','park','market')}}
    clauses=[[{'signal':'crowded','state':'present'}],[{'signal':'noisy','state':'present'}]]
    for spatial in ('category','place_specific'):
        z['environment']['market'].update(response='avoid',spatial_scope=spatial,condition='present',condition_clauses=clauses,note_ids=['N0'])
        parsed=person_scope.validate({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(z)}}]},sample[4])
        assert parsed['environment']['market']['condition_clauses']==clauses
        assert parsed['environment']['market']['scope']==('conditional_category' if spatial=='category' else 'place_specific')

def test_emergency_link_http_contract(sample):
    from fastapi.testclient import TestClient
    from app.main import app
    p,r,*_=sample;storage.personas.save(p.id,p)
    c=Case(id='http-emergency',report=r.model_copy(update={'persona_id':None}),lkp=r.lkp,lkp_time=r.lkp_time)
    storage.cases.save(c.id,c)
    response=TestClient(app).patch(f'/phase1/cases/{c.id}/persona',json={'persona_id':p.id})
    assert response.status_code==200,response.text
    assert response.json()['report']['persona_id']==p.id


def test_preparation_survives_disk_reload(sample,tmp_path,monkeypatch):
    p=make_ready(sample)
    monkeypatch.setattr(settings,'persist_storage',True)
    monkeypatch.setattr(settings,'storage_db_path',str(tmp_path/'test.sqlite'))
    storage.personas.save(p.id,p)
    storage.reset_for_tests()
    restored=storage.personas.get(p.id)
    assert restored.prepared_initial==p.prepared_initial
    out=prep.apply_prepared(restored,sample[1],sample[2],sample[3])
    assert out.initial_interpretation['prepared_outside_prediction'] is True


def test_scoring_cannot_overwrite_newer_profile_or_prepared_output(sample,monkeypatch):
    from app.phase0 import interview, axis_scoring
    p=make_ready(sample);storage.personas.save(p.id,p)
    def score(snapshot):
        assert snapshot is not p
        newer=p.model_copy(deep=True,update={'version':p.version+1,'name':'수정 후 이름'})
        storage.personas.save(p.id,newer)
        return {'mobility_transport_capacity':.9},{}
    monkeypatch.setattr(axis_scoring,'score_axes_for',score)
    interview._score_and_save(p.id)
    current=storage.personas.get(p.id)
    assert current.name=='수정 후 이름'
    assert current.axis_scores==p.axis_scores
    assert current.prepared_initial==p.prepared_initial


def test_corrupt_saved_result_does_not_block_prediction(sample):
    p=make_ready(sample);p.prepared_initial['core']={}
    result=prep.apply_prepared(p,sample[1],sample[2],sample[3])
    assert result.initial_interpretation['status']=='preparation_invalid'
    assert result.strategy_probs==sample[2].strategy_probs

def test_embedding_records_usage_without_personal_input(tmp_path,monkeypatch):
    from app.phase0.retrieval import OpenAICompatEmbedder
    from app.llm import usage_ledger
    ledger_path=tmp_path/'usage.jsonl'
    monkeypatch.setattr(settings,'research_usage_ledger_path',str(ledger_path))
    class Response:
        status=200
        headers={}
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return json.dumps({'data':[{'index':0,'embedding':[3,4]}],
            'usage':{'prompt_tokens':7,'total_tokens':7}}).encode()
    monkeypatch.setattr(usage_ledger,'urlopen',lambda *a,**kw:Response())
    result=OpenAICompatEmbedder('https://example.invalid/v1','embed-test','private-key').encode(['private guardian phrase'])
    assert result==[[.6,.8]]
    rows=[json.loads(s) for s in ledger_path.read_text().splitlines()]
    assert [r['event_type'] for r in rows]==['api_attempt_started','api_attempt_finished']
    assert rows[-1]['usage']['total_tokens']==7
    assert 'private-key' not in ledger_path.read_text() and 'private guardian phrase' not in ledger_path.read_text()

def test_final_audit_receives_context_draft_and_original_evidence(sample,monkeypatch):
    payload=initial_behavior.build_payload(sample[0],None,[],None)
    calls=[]
    def fake(url,body,**kwargs):
        calls.append((kwargs['role'],body))
        parsed=sample[-1] if kwargs['role'] in ('initial_person_context','initial_person_context_review') else sample[-2]
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(parsed)}}]}
    monkeypatch.setattr(initial_person,'logged_json_request',fake)
    result=initial_person.interpret(payload)
    assert result['core']==sample[-2]
    assert len(calls)==4
    audit=next(body for role,body in calls if role=='initial_person_semantic_audit')
    visible=json.loads(audit['messages'][-1]['content'])
    assert visible['incident']['status']=='not_reported'
    assert visible['context_draft']['status']=='unverified_model_interpretation'
    assert visible['context_draft']['content']==sample[-1]
    assert visible['notes'][0]['provenance']=='guardian_original'

def test_preincident_core_has_no_competing_behavior_owner(sample):
    from app.llm import person_evidence, person_audit
    payload=initial_behavior.build_payload(sample[0],None,[],None)
    schema=person_evidence.request_schema(payload)
    assert set(schema['properties'])=={'goals','routes','found_history','mobility','emotion','other_traits'}
    body=person_audit.request(payload,sample[-2],'test',context=sample[-1])
    draft=json.loads(body['messages'][-1]['content'])['draft']['content']
    assert 'direction' not in draft and 'persistence' not in draft


def test_unconditional_direction_is_consumed_without_clock_rules(sample):
    p=make_ready(sample)
    p.prepared_initial['core']['direction']={'value':'unknown','note_ids':[],'explanation':'조건 과업 담당'}
    p.prepared_initial['scope']['baseline_direction']={'value':'retrace','note_ids':['N0']}
    out=prep.apply_prepared(p,sample[1],sample[2],sample[3])
    assert out.initial_interpretation['semantic_contract']['direction']['value']=='retrace'


def test_missing_clock_branch_cannot_inherit_other_period_heading(sample):
    p=make_ready(sample)
    p.prepared_initial['scope']['baseline_direction']={'value':'unknown','note_ids':[]}
    p.prepared_initial['scope']['behavior_rules']=[{'period':'clock_day','dimension':'direction','value':'retrace','note_ids':['N0']}]
    p.prepared_initial['core']['direction']={'value':'unknown','note_ids':[],'explanation':'조건 과업 담당'}
    r=type(sample[1]).model_validate({**sample[1].model_dump(),'lkp_time':datetime(2026,9,25,21,tzinfo=timezone(timedelta(hours=9)))})
    out=prep.apply_prepared(p,r,sample[2],sample[3])
    assert out.initial_interpretation['semantic_contract']['direction']['value']=='unknown'


def ready_with_goal(sample, value, period='unspecified', created=datetime(2026,1,1,9)):
    p=make_ready(sample).model_copy(deep=True)
    p.created_at=created
    p.prepared_initial['core']['goals']['공원'].update(value=value,period=period,note_ids=['N2'])
    return p


def at_hour(sample, hour):
    return type(sample[1]).model_validate({**sample[1].model_dump(),
        'lkp_time':datetime(2026,9,25,hour,tzinfo=timezone(timedelta(hours=9)))})


def test_habitual_goal_reaches_engine_only_in_its_clock_period(sample):
    p=ready_with_goal(sample,'habitual_visit','clock_day')
    day=prep.apply_prepared(p,at_hour(sample,10),sample[2],sample[3])
    night=prep.apply_prepared(p,at_hour(sample,22),sample[2],sample[3])
    assert day.initial_interpretation['semantic_contract']['goals']['공원']['value']=='habitual_visit'
    assert night.initial_interpretation['semantic_contract']['goals']['공원']['value']=='historical_only'
    assert day.attraction_weights['공원']>night.attraction_weights['공원']
    assert day.strategy_probs['landmark_seeking']>night.strategy_probs['landmark_seeking']


def test_habit_near_the_period_boundary_stays_active(sample):
    """최종 게이트 1회차 P03: '새벽마다' 밭에 가는 습관(clock_night)이 07:07 사건에서 꺼졌다.
    보호자의 새벽·저녁은 정확한 시각이 아니라 경계 앞뒤 GOAL_PERIOD_MARGIN_H 시간은 살려 둔다."""
    p=ready_with_goal(sample,'habitual_visit','clock_night')
    goal=lambda hour: prep.apply_prepared(p,at_hour(sample,hour),sample[2],sample[3]) \
        .initial_interpretation['semantic_contract']['goals']['공원']['value']
    assert prep.GOAL_PERIOD_MARGIN_H==2
    assert [goal(h) for h in (7,9,16,22)]==['habitual_visit','historical_only','habitual_visit','habitual_visit']


def test_unspecified_habit_applies_at_any_hour_and_single_report_is_demoted(sample):
    habit=ready_with_goal(sample,'repeated_statement')
    single=ready_with_goal(sample,'current_statement')
    for hour in (10,22):
        r=at_hour(sample,hour)
        kept=prep.apply_prepared(habit,r,sample[2],sample[3]).initial_interpretation['semantic_contract']
        demoted=prep.apply_prepared(single,r,sample[2],sample[3]).initial_interpretation['semantic_contract']
        assert kept['goals']['공원']['value']=='repeated_statement'
        assert demoted['goals']['공원']['value']=='historical_only'


def test_profile_created_after_incident_keeps_incident_time_statement(sample):
    p=ready_with_goal(sample,'current_statement',created=datetime(2026,9,25,11))
    out=prep.apply_prepared(p,at_hour(sample,10),sample[2],sample[3])
    assert out.initial_interpretation['registered_before_incident'] is False
    assert out.initial_interpretation['semantic_contract']['goals']['공원']['value']=='current_statement'


def test_found_history_sets_weight_without_onboarding_tag(sample):
    p=make_ready(sample)
    p.prepared_initial['core']['found_history']['시장'].update(value='found_here',note_ids=['N0'])
    out=prep.apply_prepared(p,sample[1],sample[2],sample[3])
    assert all(ap.evidence.value=='mention_only' for ap in p.attraction_points)
    assert out.attraction_weights['시장']>out.attraction_weights['공원']
    assert '과거 실종 때 발견된 곳' in out.reasoning


def test_other_traits_are_preserved_with_type_and_source(sample):
    p=make_ready(sample)
    p.prepared_initial['core']['other_traits']=[{'type':'transport_use','period':'unspecified','note_ids':['N1']}]
    out=prep.apply_prepared(p,sample[1],sample[2],sample[3])
    kept=[u for u in out.initial_interpretation['unrepresented'] if u['feature']=='trait.transport_use']
    assert kept==[{'feature':'trait.transport_use','period':'unspecified','note_ids':['N1'],'reason':'no_engine_consumer_yet'}]
    assert 'trait.transport_use' in out.initial_interpretation['coverage']['N1']


def test_context_review_addition_is_not_injected_without_agreement(sample,monkeypatch):
    payload=initial_behavior.build_payload(sample[0],None,[],None)
    reviewed=copy.deepcopy(sample[-1])
    reviewed['environment']['water'].update(response='approach',scope='explicit_category',
        condition='추가 조건 없음',note_ids=['N0'])
    seen={}
    def fake(url,body,**kwargs):
        seen[kwargs['role']]=body
        parsed={'initial_person_context':sample[-1],'initial_person_context_review':reviewed}.get(kwargs['role'],sample[-2])
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(parsed)}}]}
    monkeypatch.setattr(initial_person,'logged_json_request',fake)
    result=initial_person.interpret(payload)
    assert result['context']['environment']['water']['response']=='unknown'
    assert result['audit']['context_disagreements'][0]['field']=='environment.water'
    draft=json.loads(seen['initial_person_context_review']['messages'][-1]['content'])['draft']
    assert draft['status']=='unverified_model_interpretation'
    assert draft['content']['environment']['water']['spatial_scope']=='unknown'


def test_sanitize_prior_keeps_only_real_sar_levels(sample):
    from app.phase2 import guardrail
    data={'attraction_levels':{'공원':'상','없는 장소':'상','시장':'매우 높음'},'reasoning':'r'}
    prior=guardrail.sanitize_prior(data,sample[0],sample[3])
    assert prior.attraction_levels=={'공원':'상'}


def test_sar_incident_levels_tilt_prepared_weights(sample):
    p=make_ready(sample)
    neutral=prep.apply_prepared(p,sample[1],sample[2],sample[3])
    assert neutral.attraction_weights['공원']==pytest.approx(neutral.attraction_weights['시장'])
    sar=sample[2].model_copy(update={'attraction_levels':{'공원':'상','시장':'하'}})
    tilted=prep.apply_prepared(p,sample[1],sar,sample[3])
    assert tilted.attraction_weights['공원']>tilted.attraction_weights['시장']
    trace=tilted.initial_interpretation['projection_trace']
    assert {'consumer':'attraction_weights','incident_levels_from_sar':{'공원':'상','시장':'하'}} in trace



def respond(obj,finish='stop'):
    return {'choices':[{'finish_reason':finish,'message':{'content':json.dumps(obj) if finish=='stop' else ' '*50}}]}


def test_uncited_core_claim_is_dropped_not_fatal(sample):
    from app.llm import person_evidence
    payload=initial_behavior.build_payload(sample[0],None,[],None)
    core=person_evidence.request_schema(payload)
    z={'goals':{'공원':{'value':'habitual_visit','period':'unspecified','note_ids':['N2']},'시장':{'value':'unknown','period':'unspecified','note_ids':[]}},
       'routes':{'공원':{'value':'routine_independent','note_ids':[]},'시장':{'value':'unknown','note_ids':[]}},
       'found_history':{'공원':{'value':'found_here','note_ids':['N9']},'시장':{'value':'not_reported','note_ids':[]}},
       'mobility':{'value':'C','note_ids':['N1']},'emotion':{'value':'unknown','note_ids':[]},
       'other_traits':[{'type':'transport_use','period':'unspecified','note_ids':[]}]}
    assert set(z)==set(core['properties'])
    cleaned,dropped=person_evidence.soft_clean(z,payload)
    parsed=person_evidence.validate(respond(cleaned),payload)
    assert parsed['goals']['공원']['value']=='habitual_visit'
    assert parsed['routes']['공원']['value']=='unknown' and parsed['found_history']['공원']['value']=='not_reported'
    assert parsed['other_traits']==[]
    assert {d['field'] for d in dropped}=={'routes.공원','found_history.공원','other_traits'}


def test_uncited_context_claims_and_unknown_rules_are_dropped(sample):
    payload=initial_behavior.build_payload(sample[0],None,[],None)
    z={'persistence':{'evidence':'conflicting','pattern':'unresolved','value':'unknown','note_ids':[]},
       'environment':{f:{'response':'unknown','condition':'unknown','note_ids':[],'condition_clauses':[],'spatial_scope':'unknown'} for f in ('water','forest','park','market')},
       'baseline_direction':{'value':'retrace','note_ids':[]},
       'behavior_rules':[{'period':'clock_day','dimension':'direction','value':'unknown','note_ids':[]},
                         {'period':'clock_night','dimension':'persistence','value':'keep_moving','note_ids':['N0']},
                         {'period':'clock_night','dimension':'persistence','value':'same_heading','note_ids':['N0']}]}
    z['environment']['market'].update(response='avoid',spatial_scope='category',condition='none',note_ids=[])
    cleaned,dropped=person_scope.soft_clean(z,payload)
    parsed=person_scope.validate(respond(cleaned),payload)
    assert parsed['persistence']['evidence']=='missing' and parsed['environment']['market']['response']=='unknown'
    assert parsed['baseline_direction']['value']=='unknown'
    assert parsed['behavior_rules']==[{'period':'clock_night','dimension':'persistence','value':'keep_moving','note_ids':['N0']}]
    assert [d['field'] for d in dropped]==['persistence','environment.market','baseline_direction','behavior_rules']


def test_context_agreement_keeps_shared_claims_and_blocks_changes(sample):
    draft=copy.deepcopy(sample[-1])
    draft['persistence'].update(evidence='supported',pattern='conditional',value='unknown',note_ids=['N0'])
    draft['baseline_direction']={'value':'unknown','note_ids':[]}
    draft['behavior_rules']=[{'period':'clock_night','dimension':'persistence','value':'keep_moving','note_ids':['N0']},
                             {'period':'clock_day','dimension':'persistence','value':'wait_for_help','note_ids':['N0']}]
    draft['environment']['water'].update(response='approach',scope='explicit_category',condition='추가 조건 없음',note_ids=['N1'])
    review=copy.deepcopy(draft)
    review['behavior_rules']=draft['behavior_rules'][:1]
    review['baseline_direction']={'value':'same_heading','note_ids':['N0']}
    out,dis=person_scope.agree(draft,review)
    assert out['behavior_rules']==draft['behavior_rules'][:1]
    assert out['environment']['water']['response']=='approach'
    assert out['baseline_direction']['value']=='unknown'
    assert {d['field'] for d in dis}=={'behavior_rules','baseline_direction'}


def test_failed_core_draft_falls_back_to_review_without_extra_request(sample,monkeypatch):
    payload=initial_behavior.build_payload(sample[0],None,[],None)
    calls=[]
    def fake(url,body,**kwargs):
        calls.append(kwargs['role'])
        if kwargs['role']=='initial_person_core':
            return respond(None,finish='length')
        parsed=sample[-1] if 'context' in kwargs['role'] else sample[-2]
        return respond(parsed)
    monkeypatch.setattr(initial_person,'logged_json_request',fake)
    result=initial_person.interpret(payload)
    assert result['core']==sample[-2] and len(calls)==4
    assert result['audit']['fallbacks']==['core_draft_failed:ValueError']


def test_failed_context_review_keeps_draft_claims_out_of_engine(sample,monkeypatch):
    payload=initial_behavior.build_payload(sample[0],None,[],None)
    drafted=copy.deepcopy(sample[-1])
    drafted['environment']['water'].update(response='approach',scope='explicit_category',condition='추가 조건 없음',note_ids=['N1'])
    def fake(url,body,**kwargs):
        if kwargs['role']=='initial_person_context_review':
            return respond(None,finish='length')
        return respond(drafted if kwargs['role']=='initial_person_context' else sample[-2])
    monkeypatch.setattr(initial_person,'logged_json_request',fake)
    result=initial_person.interpret(payload)
    assert result['context']['environment']['water']['response']=='unknown'
    assert result['audit']['fallbacks']==['context_review_failed:ValueError']
    assert result['audit']['context_disagreements'][0]['cause']=='no_second_reading'
