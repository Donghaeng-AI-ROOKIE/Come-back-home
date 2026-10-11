"""Interface/execution regressions, not model accuracy or patient validation."""
from copy import deepcopy
import json

import pytest
from app.llm import mind_handoff as handoff
from app.phase0.person_preparation import fingerprint
from experiments.mind_person_handoff.session import create_session
from experiments.mind_upgrade.runtime import RuntimePolicy
from tests.test_mind_upgrade import person, prior, state, START, geography


def prepared_person(location=None):
    p = person() if location is None else person(location)
    p.onboarding_turns = [{'slot': 'environment', 'question': '시장이 시끄러우면 어떻게 하나요?',
                          'answer': '혼자면 돌아서고 가족과 있으면 계속 가요.'}]
    p.behavior_notes = ['시장은 언제나 좋아한다']
    key = fingerprint(p)
    p.initial_preparation_status = {'state': 'ready', 'fingerprint': key}
    # Synthetic persisted contract, not a newly generated model response.
    p.prepared_initial = {'fingerprint': key, 'profile_snapshot_at': '2026-09-01T08:00:00',
        'core': {'other_traits': [{'condition': '가족 동행 여부', 'note_ids': ['N0']}],
                 'goals': {'등록 목적지': {'value': 'current_statement', 'note_ids': ['N0']}}},
        'scope': {'environment': {'market': {'response': 'conditional',
                                           'condition': '혼자면 회피, 가족 동행이면 계속 이동', 'note_ids': ['N0']}},
                  'behavior_rules': [{'period': 'clock_day'}, {'period': 'clock_night'}]}}
    return p


def context(p=None, **kwargs):
    return handoff.context_for(p or prepared_person(), prior(), state(), case_id='synthetic',
        started_at=START, trigger='environment_changed', env={'market_m':20},
        observations={'market': {'noisy': True}}, **kwargs)


def envelope(c, action='avoid', **fields):
    return {'evidence': [{'note_id':'N0', 'quote':'혼자면 돌아서고 가족과 있으면 계속 가요.'}],
            'state_check': handoff.state_facts(c),
            'assessment': '고정된 검사용 응답. 개인 조건의 의미 정확도를 측정하지 않음.',
            'confusion_level':'unknown', 'decision': {'action': action, **fields}}


def test_saved_k_conditions_unrepresented_traits_and_raw_answer_reach_request():
    p = prepared_person(); before = deepcopy(p.prepared_initial)
    c = context(p); body = handoff.request_spec(c, model='offline', provider='kexaone')
    sent = json.loads(body['messages'][1]['content'])
    interpretation = sent['person']['prepared_person_interpretation']
    assert interpretation['core'] == before['core']
    assert interpretation['scope'] == before['scope']
    assert interpretation['profile_snapshot_at'] == '2026-09-01T08:00:00'
    assert sent['person']['interpretation_is_not_new_observation'] is True
    assert sent['person']['preparation_status'] == 'ready'
    assert '혼자면 돌아서고' in sent['person']['evidence_notes'][0]['text']
    assert '시장은 언제나 좋아한다' not in str(sent['person']['evidence_notes'])
    assert sent['person']['initial_interpretation']['unrepresented']
    assert p.prepared_initial == before


@pytest.mark.parametrize('change', ['answer', 'version', 'queued', 'malformed'])
def test_changed_or_pending_preparation_is_not_used(change):
    p = prepared_person()
    if change == 'answer': p.onboarding_turns[0]['answer'] = '보호자가 정정한 내용'
    elif change == 'version': p.version += 1
    elif change == 'queued': p.initial_preparation_status['state'] = 'queued'
    else: p.prepared_initial['scope'] = None
    c = context(p)
    assert c['person']['prepared_person_interpretation'] == {}
    assert c['person']['preparation_status'] in {'stale', 'queued', 'invalid'}
    assert c['person']['evidence_notes']


@pytest.mark.parametrize('minute', [None, -1, 61, float('nan'), float('inf'), True])
def test_missing_invalid_or_future_event_time_rejected(minute):
    with pytest.raises(ValueError):
        handoff.State(**{**state().model_dump(), 'recent_events':[{'elapsed_minutes':minute}]})


def test_unknown_noise_cannot_be_reported_as_false():
    c = context(); value = envelope(c, avoid_feature='market')
    value['state_check']['observed_signals']['market']['crowded'] = False
    with pytest.raises(ValueError, match='mismatch'): handoff.decode_decision(value,c)


def test_false_and_zero_are_not_same_observation():
    c = context(); value = envelope(c, avoid_feature='market')
    value['state_check']['observed_signals']['market']['noisy'] = 1
    with pytest.raises(ValueError, match='mismatch'): handoff.decode_decision(value,c)


def test_continue_requires_actual_previous_movement():
    c = context()
    with pytest.raises(ValueError, match='previous movement'):
        handoff.decode_decision(envelope(c, 'continue'), c)


def test_action_is_not_parsed_from_explanation_and_cannot_set_second_destination():
    c = context(); value = envelope(c, avoid_feature='market')
    value['assessment'] = '문장에 rest, seek가 있어도 문자열로 행동을 바꾸지 않는다.'
    d = handoff.decode_decision(value,c)
    assert d.action == 'avoid' and d.goal_operation == 'keep'
    value['decision']['goal_label'] = '등록 목적지'
    with pytest.raises(ValueError, match='incompatible'): handoff.decode_decision(value,c)


def test_question_cannot_be_quoted_as_guardian_observation():
    c = context(); value = envelope(c, avoid_feature='market')
    value['evidence'][0]['quote'] = '시장이 시끄러우면'
    with pytest.raises(ValueError, match='source answer'): handoff.decode_decision(value,c)


def test_provider_failure_calls_once_and_does_not_invent_fallback():
    calls = []
    def request(body):
        calls.append(body)
        raise RuntimeError('synthetic transport failure')
    provider = handoff.DecisionProvider(request, model='offline', provider='kexaone')
    with pytest.raises(RuntimeError): provider(context())
    assert len(calls) == 1


def test_complete_handoff_rest_then_movement_on_kintex(geography):
    net, center = geography; seen = []
    def request(body):
        c = json.loads(body['messages'][1]['content']); seen.append(c)
        return envelope(c, 'rest' if len(seen) == 1 else 'roam')
    s = create_session(net, prepared_person(center), prior(), center, START,
        request=request, model='offline', provider='kexaone',
        policy=RuntimePolicy(rest_minutes=5,reassess_minutes=20))
    s.target = '등록 목적지'
    a = s.advance_to(3)
    assert a['state']['distance_m'] == 0 and a['state']['target_label'] == '등록 목적지'
    b = s.advance_to(6)
    assert b['state']['distance_m'] > 0
    assert seen[1]['trigger'] == 'rest_complete'
    assert seen[1]['state']['current_action'] == 'rest'
    assert seen[1]['engine_state_facts']['rest_phase'] == 'completed'
    assert seen[1]['state']['last_rest_end_minutes'] == 5
    assert seen[1]['person']['prepared_person_interpretation']['scope']['environment']['market']
    assert seen[1]['state']['recent_events'][-1]['kind'] == 'rest_complete'


def test_continue_retains_avoidance_target_and_destination(geography):
    net, center = geography
    s = create_session(net, prepared_person(center), prior(), center, START,
        request=lambda body: envelope(json.loads(body['messages'][1]['content']), 'continue'),
        model='offline', provider='kexaone', policy=RuntimePolicy(5,20))
    s.action = s.travel_action = 'avoid'; s.avoid_feature = 'market'; s.target = '등록 목적지'
    s._decide('scheduled_review')
    assert s.action == 'avoid' and s.avoid_feature == 'market'
    assert s.target == '등록 목적지'
    assert s.history[-1]['requested_action'] == 'continue'
    assert s.decisions[-1]['context']['execution']['previous_avoid_feature'] == 'market'


def test_candidate_hourly_snapshots_match_continuous_execution(geography):
    net, center = geography
    def make():
        return create_session(net, prepared_person(center), prior(), center, START,
            request=lambda body: envelope(json.loads(body['messages'][1]['content']), 'roam'),
            model='offline',provider='kexaone',policy=RuntimePolicy(5,20),seed=42)
    split = make(); whole = make()
    a = split.advance_to(60); b = split.advance_to(120); expected = whole.advance_to(120)
    assert a['state']['distance_m'] < b['state']['distance_m']
    assert b['state']['distance_m'] == pytest.approx(expected['state']['distance_m'])
    assert [x['node'] for x in b['path']] == [x['node'] for x in expected['path']]
    assert [x['minute'] for x in b['path']] == pytest.approx([x['minute'] for x in expected['path']])


def test_stale_compiled_prior_cannot_reintroduce_removed_personal_claim():
    p = prepared_person(); old = prior()
    old.initial_interpretation['preparation_fingerprint'] = fingerprint(p)
    p.onboarding_turns[0]['answer'] = '다른 보호자 정정'
    c = handoff.context_for(p, old, state(), case_id='synthetic', started_at=START,
        trigger='update', env={}, observations={})
    assert c['person']['initial_interpretation'] == {}
    assert c['person']['initial_interpretation_status'] == 'stale'
    assert c['known_places'][0]['attraction_weight'] is None
    assert c['person']['prepared_person_interpretation'] == {}


def test_equivalent_json_number_is_not_a_false_state_failure():
    c = context(); c['state']['fatigue'] = 0.0
    value = envelope(c, avoid_feature='market')
    value['state_check']['fatigue'] = 0
    assert handoff.decode_decision(value, c).action == 'avoid'
