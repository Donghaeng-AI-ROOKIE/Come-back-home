"""Semantic-to-engine invariants; these tests do not measure model accuracy."""
import copy
import json
from datetime import datetime, timedelta

import pytest

from app.llm import initial_behavior, person_evidence, person_scope
from app.llm.exaone import ExaoneClient
from app.phase2 import guardrail
from app.phase2.person_projection import compile_person
from app.schemas.common import GeoPoint
from app.schemas.persona import Persona, AttractionPoint
from app.schemas.report import MissingReport


@pytest.fixture
def sample():
    p = Persona(id='meaning-person', type='dementia', name='비공개 이름', age=80,
        home=GeoPoint(lat=37.6, lng=127.),
        attraction_points=[AttractionPoint(label='공원', location=GeoPoint(lat=37.61, lng=127.01)),
                           AttractionPoint(label='시장', location=GeoPoint(lat=37.62, lng=127.02))],
        onboarding_quotes={'lost_behavior':['낯선 길에서 보호자를 기다렸다.'],
                           'capacity':['다리는 건강하여 45분 산책한다.'],
                           'destination':['새 동네 공원에 가고 싶으나 가 본 적 없다.']},
        axis_scores={'mobility_transport_capacity': .5}, behavior_tendency='stay')
    r = MissingReport(id='meaning-report', persona_id=p.id, missing_type='dementia', lkp=p.home,
        lkp_time=datetime.now()-timedelta(hours=1), situation='아침 외출 후 미복귀')
    client = ExaoneClient()
    default = client._default_prior(p, r)
    sar = guardrail.apply_axis_scores(default, p.axis_scores, p, default.radius_lognormal)
    sar = sar.model_copy(update={'strategy_before_behavior': dict(default.strategy_probs)})
    payload = initial_behavior.build_payload(p, r, [], sar)
    leaf = lambda v='unknown': {'value': v, 'note_ids': [], 'explanation': '관련 개인 관찰 정보 미확인.'}
    core = {'goals': {x.label: {**leaf(), 'period': 'unspecified'} for x in p.attraction_points},
            'routes': {x.label: leaf() for x in p.attraction_points},
            'found_history': {x.label: leaf('not_reported') for x in p.attraction_points},
            'environment': {x: leaf() for x in ['water','forest','park','market']},
            **{x:leaf() for x in ['persistence','direction','mobility','emotion']},
            'other_traits': []}
    scope = {'persistence': {'evidence':'missing','pattern':'unresolved','value':'unknown',
                            'note_ids':[], 'explanation':'관련 선택 관찰 미확인.'},
             'environment':{x:{'response':'unknown','scope':'unknown','condition':'미확인',
                               'note_ids':[], 'explanation':'환경 반응 미확인.'}
                            for x in ['water','forest','park','market']}}
    return p,r,sar,default,payload,core,scope


def compile_sample(x):
    p,r,sar,default,payload,core,scope=x
    environment={}
    for k,v in scope['environment'].items():
        environment[k]={'note_ids':v['note_ids'], 'basis':'reaction' if v['response']!='unknown' else 'unknown',
            'scope':{'place_specific':'one_place','conditional_category':'category','explicit_category':'category','unknown':'unknown'}[v['scope']],
            'condition':'required' if v['scope']=='conditional_category' else 'none_stated' if v['response']!='unknown' else 'unknown',
            'response':v['response']}
    return compile_person(core,scope,payload,p,sar,default,environment=environment)


def supported_wait(x):
    x[-1]['persistence'].update(evidence='supported',pattern='consistent',value='wait_for_help',
                              note_ids=['N0'],explanation='과거 유사 상황의 대기를 초기 가설에 사용.')


def test_wait_not_counted_twice(sample):
    supported_wait(sample)
    final=compile_sample(sample)
    assert final.strategy_probs==pytest.approx(sample[2].strategy_probs)
    # Exact pre-tilt snapshot matters even near epsilon flooring.
    base={'route_following':.7,'direction_keeping':.2,'random_walk':.04,
          'backtracking':.04,'staying_put':.01,'landmark_seeking':.01}
    sample[2].strategy_before_behavior=base
    final=compile_sample(sample)
    expected=guardrail.sanitize_strategy_probs(guardrail._boost_strategies(base,{'staying_put':3.},floor=0),base)
    assert final.strategy_probs==pytest.approx(expected)


def test_body_limit_changes_radius_not_wait_choice(sample):
    a=compile_sample(sample)
    sample[-2]['mobility'].update(value='B',note_ids=['N1'])
    b=compile_sample(sample)
    assert a.strategy_probs==b.strategy_probs
    assert b.radius_lognormal.mu==pytest.approx(a.radius_lognormal.mu-.4)


def test_goal_and_route_independent_and_original_unchanged(sample):
    p,*_=sample; before=copy.deepcopy(p.model_dump());supported_wait(sample)
    core=sample[-2]
    core['goals']['공원'].update(value='current_statement',note_ids=['N2'],explanation='공원에 갈 의도는 현재 발언으로 확인.')
    core['routes']['공원'].update(value='new_route',note_ids=['N2'],explanation='새 동네 길은 아직 경험 없음.')
    final=compile_sample(sample);effective=initial_behavior.simulation_persona(p,final)
    assert final.attraction_weights['공원']>final.attraction_weights['시장']
    assert effective.route_familiarity[0].score==.1
    assert effective.env_responses==[]
    assert p.model_dump()==before
    assert initial_behavior.simulation_persona(effective,final)==effective
    assert '경로 경험 없음' in final.reasoning


@pytest.mark.parametrize('scope',['place_specific','conditional_category'])
def test_scoped_environment_not_expanded_to_all_places(sample,scope):
    sample[-1]['environment']['market'].update(response='avoid',scope=scope,condition='소음 있을 때',note_ids=['N0'])
    final=compile_sample(sample)
    assert final.persona_adjustments['env_responses']==[]
    assert final.initial_interpretation['environment_contract']['market']['scope']==('one_place' if scope=='place_specific' else 'category')
    assert final.initial_interpretation['unrepresented'][0]['feature']=='environment.market'


def test_explicit_type_response_reaches_engine(sample):
    sample[-1]['environment']['water'].update(response='approach',scope='explicit_category',note_ids=['N0'])
    final=compile_sample(sample)
    assert initial_behavior.simulation_persona(sample[0],final).env_responses[0].feature=='water'


def test_context_environment_applies_only_unconditional_category(sample):
    p,r,sar,default,payload,core,scope=sample
    scope['environment']['water'].update(response='approach',scope='explicit_category',
        condition='추가 조건 없음',note_ids=['N0'])
    scope['environment']['market'].update(response='avoid',scope='conditional_category',
        condition='추가 조건 필요',note_ids=['N1'])
    scope['environment']['park'].update(response='avoid',scope='place_specific',
        condition='추가 조건 없음',note_ids=['N2'])
    final=compile_person(core,scope,payload,p,sar,default)
    assert [e['feature'] for e in final.persona_adjustments['env_responses']]==['water']
    assert {x['feature'] for x in final.initial_interpretation['unrepresented']}=={'environment.market','environment.park'}
    assert final.initial_interpretation['environment_method']=='single_context_contract'


def test_conflict_kept_distinct_without_behavior_boost(sample):
    before=compile_sample(sample)
    sample[-1]['persistence'].update(evidence='conflicting',note_ids=['N0'])
    after=compile_sample(sample)
    assert before.strategy_probs==after.strategy_probs
    assert after.initial_interpretation['semantic_contract']['persistence']['value']=='conflict'
    assert after.initial_interpretation['context_scope']['persistence']['evidence']=='conflicting'


def test_raw_evidence_and_provider_response_not_exported(sample):
    final=compile_sample(sample)
    data=json.dumps(final.model_dump(mode='json'),ensure_ascii=False)
    assert all(n['text'] not in data for n in sample[4]['notes'])
    assert 'evidence_notes' not in data and 'SAR_reference' not in data


def test_missing_snapshot_rejected_instead_of_inverting_floored_prior(sample):
    sample[2].strategy_before_behavior={}
    with pytest.raises(ValueError,match='missing_pre_behavior'):
        compile_sample(sample)


def test_unavailable_current_context_cannot_resolve_conflict(sample):
    sample[-1]['persistence'].update(evidence='conflicting',value='keep_moving',note_ids=['N0'])
    with pytest.raises(ValueError,match='unsupported_resolution'):
        compile_sample(sample)


def test_unknown_source_rejected(sample):
    sample[-2]['mobility'].update(value='C',note_ids=['N999'])
    with pytest.raises(ValueError):compile_sample(sample)


def test_empty_prose_only_allowed_for_unknown_without_evidence(sample):
    sample[-2]['environment']['water']['explanation']=''
    final=compile_sample(sample)
    assert final.initial_interpretation['semantic_contract']['direction']['value']=='unknown'
    assert not final.persona_adjustments['env_responses']
    sample[-2]['direction'].update(value='same_heading',note_ids=['N0'],explanation='')
    with pytest.raises(ValueError,match='missing_explanation:direction'):
        compile_sample(sample)


def test_core_does_not_read_candidate_tags_or_numeric_sar_as_facts(sample):
    payload=sample[4];req=person_evidence.request(payload,'fixture')
    visible=json.loads(req['messages'][1]['content'])
    assert 'SAR_reference' not in visible
    assert all(set(p)=={'label','status'} for p in visible['places'])
    assert all('sources' not in n for n in visible['notes'])
    assert 'strategy_probs' not in req['response_format']['json_schema']['schema']['properties']


def test_source_precedence_reaches_every_interpretation_task(sample):
    from app.llm import person_environment
    p,r,sar,*_=sample
    p.behavior_notes=['길을 잃으면 계속 이동한다.', p.onboarding_quotes['lost_behavior'][0]]
    payload=initial_behavior.build_payload(p,r,[],sar)
    for contract in [person_evidence, person_scope, person_environment]:
        request=contract.request(payload,'fixture')
        notes=json.loads(request['messages'][1]['content'])['notes']
        by_text={n['text']:n for n in notes}
        assert '길을 잃으면 계속 이동한다.' not in by_text
        assert by_text[p.onboarding_quotes['lost_behavior'][0]]['provenance']=='guardian_original'
        assert len(notes)==len({n['text'] for n in notes})
        assert initial_behavior.SOURCE_PRECEDENCE in request['messages'][0]['content']
    assert any(n['text']=='길을 잃으면 계속 이동한다.' for n in payload['notes'])


def test_compact_context_retains_choice_and_condition(sample):
    payload=sample[4]
    compact={'persistence':{'evidence':'supported','pattern':'consistent','value':'wait_for_help','note_ids':['N0']},
        'environment':{f:{'response':'unknown','scope':'unknown','condition':'unknown','note_ids':[]}
                       for f in ['water','forest','park','market']}}
    response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(compact)}}]}
    parsed=person_scope.validate(response,payload)
    assert parsed['persistence']['value']=='wait_for_help'
    assert parsed['persistence']['note_ids']==['N0']
    assert parsed['environment']['market']['condition']=='조건 미확인'
    assert 'explanation' not in person_scope.request_schema(payload)['properties']['persistence']['properties']


def test_no_source_is_not_promoted_to_guardian_observation():
    notes=initial_behavior.evidence_notes({'notes':[{'id':'N0','text':'미검증 요약'}]})
    assert notes[0]['provenance']=='model_extracted_unverified'


def test_final_json_envelope_does_not_repair_or_select_between_answers():
    decode=initial_behavior.decode_json_content
    assert decode('analysis</think>Final output:\n```json\n{"value":"unknown"}\n```')=={'value':'unknown'}
    assert decode('```json\n{"value":"unknown"}\n```')=={'value':'unknown'}
    for text in ['```json\n{"a":1}\n```\n```json\n{"a":2}\n```',
                 'prefix {"a":1}', '{"a":1,"a":2}',
                 '```json\n{"a":1}\n``` trailing answer', '{"a":']:
        with pytest.raises(ValueError):decode(text)


def test_compact_core_preserves_semantics_without_free_prose(sample):
    core=copy.deepcopy(sample[-2]);core.pop('environment')
    for section in ['goals','routes','found_history']:
        for leaf in core[section].values():leaf.pop('explanation')
    for field in ['persistence','direction','mobility','emotion']:core[field].pop('explanation')
    core['direction'].update(value='retrace',note_ids=['N0'])
    parsed=person_evidence.validate({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(core)}}]},sample[4])
    assert parsed['direction']['value']=='retrace' and parsed['direction']['note_ids']==['N0']
    assert all(e['value']=='unknown' for e in parsed['environment'].values())


def test_refine_uses_four_logged_tasks_and_failure_is_visible(sample,monkeypatch,tmp_path):
    from app.phase2 import initial_person
    from app.config import settings
    p,r,sar,default,payload,core,scope=sample
    for k,v in [('kexaone_base_url','https://fixture.invalid/v1'),('kexaone_api_key','test'),
                ('kexaone_model','K'),('research_usage_ledger_path',str(tmp_path/'ledger'))]:
        monkeypatch.setattr(settings,k,v)
    monkeypatch.setattr(initial_person,'cached_research',lambda *a:[])
    environment={f:{'note_ids':[],'basis':'unknown','scope':'unknown','condition':'unknown','response':'unknown'}
                 for f in ['water','forest','park','market']}
    calls=[]
    def request(url,body,**kw):
        calls.append(kw)
        obj={'initial_person_core':core,'initial_person_context':scope,'initial_person_environment':environment,
             'initial_person_semantic_audit':core,'initial_person_context_review':scope}[kw['role']]
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(obj)}}]}
    monkeypatch.setattr(initial_person,'logged_json_request',request)
    result=initial_person.refine(p,r,sar,default)
    assert result.initial_interpretation['status']=='applied'
    assert len(calls)==4 and all(c['max_started']==4 for c in calls)
    assert len({c['run_id'] for c in calls})==1 and len({c['logical_request_id'] for c in calls})==4
    assert result.initial_interpretation['environment_method']=='single_context_contract'
    calls.clear()
    def fail(*a,**kw):
        calls.append(kw)
        raise ValueError('provider content must not be logged')
    monkeypatch.setattr(initial_person,'logged_json_request',fail)
    result=initial_person.refine(p,r,sar,default)
    assert result.initial_interpretation['status']=='fallback_to_sar'
    assert result.strategy_probs==sar.strategy_probs
    assert len(calls)<=4
    assert 'provider content' not in json.dumps(result.initial_interpretation)


def test_empty_person_does_not_trigger_retrieval_or_k(sample,monkeypatch):
    from app.phase2 import initial_person
    from app.config import settings
    p,r,sar,default,*_=sample
    p=p.model_copy(update={'onboarding_quotes':{},'axis_quotes':{},'axis_evidence':{},'behavior_notes':[]})
    for k in ['kexaone_base_url','kexaone_api_key','kexaone_model']:monkeypatch.setattr(settings,k,'fixture')
    def fail(*a,**kw):pytest.fail('No evidence should not generate a paid call')
    monkeypatch.setattr(initial_person,'cached_research',fail)
    monkeypatch.setattr(initial_person,'logged_json_request',fail)
    assert initial_person.refine(p,r,sar,default).initial_interpretation['status']=='no_person_evidence'


def test_new_projection_shared_by_initial_and_time_preview(sample,monkeypatch):
    from app import storage
    from app.phase2 import initial_person, pipeline
    from app.schemas.case import Case, CaseStatus
    p,r,sar,default,*_=sample
    supported_wait(sample)
    sample[-2]['routes']['공원'].update(value='new_route',note_ids=['N2'])
    final=compile_sample(sample)
    storage.personas.save(p.id,p)
    case=Case(id='new-person-pipeline',report=r,status=CaseStatus.intake,lkp=r.lkp,lkp_time=r.lkp_time)
    seen=[]
    monkeypatch.setattr(pipeline.exaone,'generate_prior',lambda *a:sar)
    monkeypatch.setattr(pipeline,'apply_prepared',lambda *a:final)
    monkeypatch.setattr(pipeline,'_load_roadnet',lambda *a:(None,'off'))
    monkeypatch.setattr(pipeline.topdown,'topdown_poa',lambda *a:{'cell':1.})
    def simulate(lkp,prior,person,elapsed,**kw):
        seen.append((kw['mode'],prior.strategy_probs.copy(),[x.model_dump() for x in person.route_familiarity]))
        return {'cell':1.}
    monkeypatch.setattr(pipeline.simulation,'run_monte_carlo',simulate)
    pipeline.run_prediction(case,seed=1)
    pipeline.poa_at_elapsed(case,3)
    assert len(seen)==4 and seen[0]==seen[2] and seen[1]==seen[3]
    assert seen[0][2]==[{'route':'공원','score':.1}]
    assert storage.personas.get(p.id).route_familiarity==p.route_familiarity


def test_environment_scope_disagreement_is_visible_and_not_injected(sample):
    from app.phase2.person_projection import agreed_environment
    proposal={'park':{'response':'approach','basis':'reaction','scope':'category',
                      'condition':'none_stated','note_ids':['N2']}}
    scope={'environment':{'park':{'response':'approach','scope':'place_specific','note_ids':['N2']}}}
    accepted,disagreements=agreed_environment(proposal,scope)
    assert accepted=={} and disagreements[0]['context_scope']=='place_specific'
    # Positive control: actually agreeing type-wide evidence must still pass.
    scope['environment']['park']['scope']='explicit_category'
    accepted,disagreements=agreed_environment(proposal,scope)
    assert accepted=={'park':'approach'} and disagreements==[]


def test_condition_contract_reaches_persona_without_becoming_unconditional(sample):
    p,r,sar,default,payload,core,scope=sample
    scope['environment']['market'].update(response='avoid',scope='conditional_category',
        condition='추가 조건 필요',note_ids=['N0'],condition_clauses=[[
            {'signal':'crowded','state':'present'},{'signal':'noisy','state':'present'}]])
    final=compile_person(core,scope,payload,p,sar,default)
    effective=initial_behavior.simulation_persona(p,final)
    response=effective.env_responses[0]
    assert response.feature=='market' and len(response.condition_clauses[0])==2
    assert 'market' in final.initial_interpretation['conditional_environment']
    assert final.initial_interpretation['semantic_contract']['environment']['market']['value']=='unknown'
    assert not final.initial_interpretation['unrepresented']
    from app.phase2.gauges import env_response_weight
    assert env_response_weight({'market_m':10},effective)==1
    assert env_response_weight({'market_m':10},effective,conditions={'market':{'crowded':True,'noisy':True}})<1
    assert not p.env_responses


def test_compact_context_validates_typed_conditions_and_legacy(sample):
    _,_,_,_,payload,_,scope=sample
    scope['persistence'].pop('explanation')
    for e in scope['environment'].values():
        e.pop('explanation');e['condition']='unknown';e['condition_clauses']=[]
    scope['environment']['market'].update(response='avoid',scope='conditional_category',
        condition='present',note_ids=['N0'],condition_clauses=[[{'signal':'noisy','state':'present'}]])
    wrap=lambda z:{'choices':[{'finish_reason':'stop','message':{'content':json.dumps(z)}}]}
    parsed=person_scope.validate(wrap(scope),payload)
    assert parsed['environment']['market']['condition_clauses'][0][0]['signal']=='noisy'
    scope['environment']['market']['condition_clauses']=[[]]
    with pytest.raises(ValueError):person_scope.validate(wrap(scope),payload)
    scope['environment']['market']['condition_clauses']=[[{'signal':'crowded','state':'present'},{'signal':'crowded','state':'absent'}]]
    with pytest.raises(ValueError):person_scope.validate(wrap(scope),payload)


def test_sar_prompt_shows_korean_clock_even_on_utc_server():
    import importlib
    import os
    import time
    exaone_module=importlib.import_module('app.llm.exaone')
    old=os.environ.get('TZ')
    os.environ['TZ']='UTC'
    time.tzset()
    try:
        r=MissingReport(id='tz',missing_type='dementia',lkp=GeoPoint(lat=37.6,lng=127.),
            lkp_time='2026-10-19T18:20:00+09:00',situation='저녁 외출')
        assert r.lkp_time.hour==9
        assert '18:20 마지막 목격' in exaone_module._build_prior_input(None,r)
        payload=initial_behavior.build_payload(Persona(id='tz',type='dementia',name='비공개',age=80,
            home=GeoPoint(lat=37.6,lng=127.)),r,[],None)
        assert payload['incident']['last_seen_time'].startswith('2026-10-19T18:20:00+09:00')
    finally:
        if old is None:
            os.environ.pop('TZ',None)
        else:
            os.environ['TZ']=old
        time.tzset()
