"""Handwritten contract fixtures for candidates A/B (2026-10-07).

These outputs were written by hand to test the compiler, scorer and completion
classifier. Passing them is not evidence of model interpretation quality.
"""
import json

import pytest

from experiments.mind_contract_ab_20261007 import completion, contracts, scoring

PEOPLE, SCENES, REFERENCE = scoring.load()


def personal(pid):
    return PEOPLE[pid]['personal']


def scenes_pass(policy, pid):
    from experiments.mind_policy_candidates import note_policy_eval as ev
    return {s['id']: scoring.scene_pass(ev.decide(policy, personal(pid), s['scene']), s)
            for s in SCENES if s['person_id'] == pid}


def a_rule(action, condition, note='N1', goal='', scope=(), hold=0):
    return {'action': action, 'goal_place': goal, 'applies_only_at': list(scope),
            'condition': condition, 'hold_minutes': hold, 'note_ids': [note]}


def a_out(rules, non_action=('N0',)):
    return {'source_assessment': '수기 계약 fixture', 'rules': rules,
            'non_action_note_ids': list(non_action)}


def unit(note, quote, kind='other_information', subject='patient', action='none',
         start='', end='', goal='', scope=(), hold=0):
    return {'note_id': note, 'quote': quote, 'subject': subject, 'kind': kind, 'action': action,
            'goal_place': goal, 'applies_only_at': list(scope), 'start_condition': start,
            'end_condition': end, 'hold_minutes': hold}


N0 = unit('N0', '질문에 나온 후보 이름이에요')

A_CORRECT = {
    'P05': a_out([a_rule('rest', 'is_walking and (continuous_walk_minutes >= 8 or distance_since_rest_m >= 450)')]),
    'P14': a_out([a_rule('seek', 'target_recognized', goal='느티공원')]),
    'P21': a_out([a_rule('walk', 'lost_awareness')]),
    'P25': a_out([a_rule('wait', 'clock_hour >= 8 and clock_hour < 9 and not family_present')]),
    'P29': a_out([a_rule('rest', 'is_walking and (continuous_walk_minutes >= 6 or distance_since_rest_m >= 280)'),
                  a_rule('wait', 'lost_awareness and not family_present', note='N2')]),
    'P06': a_out([], non_action=('N0', 'N1')),
    'P13': a_out([], non_action=('N0', 'N1')),
    'P24': a_out([], non_action=('N0', 'N1')),
}

B_CORRECT = {
    'P05': {'units': [N0, unit('N1', '무릎 때문에 앉아 쉬어야 해요', 'functional_need', action='rest',
                               start='is_walking and (continuous_walk_minutes >= 8 or distance_since_rest_m >= 450)')]},
    'P14': {'units': [N0, unit('N1', '그쪽으로 걸어 출발했어요', 'observed_response', action='seek',
                               start='target_recognized', goal='느티공원'),
                      unit('N1', '알아보지 못했을 때의 행동은 아직 본 적 없어요', 'unobserved')]},
    'P21': {'units': [N0,
                      unit('N1', '어머니가 아니라 아버지 이야기였어요', 'corrected_away', subject='other_person'),
                      unit('N1', '실제로 멈추지 않고 계속 걸었어요', 'observed_response', action='walk',
                           start='lost_awareness'),
                      unit('N1', '기다리는지는 어머니에게서 본 적 없어요', 'unobserved')]},
    'P25': {'units': [N0, unit('N1', '현관에서 기다렸어요', 'observed_response', action='wait',
                               start='clock_hour >= 8 and not family_present', end='clock_hour >= 9')]},
    'P29': {'units': [N0,
                      unit('N1', '먼저 도달한 쪽에서 쉬어야 해요', 'functional_need', action='rest',
                           start='is_walking and (continuous_walk_minutes >= 6 or distance_since_rest_m >= 280)'),
                      unit('N2', '그 자리에서 기다렸어요', 'observed_response', action='wait',
                           start='lost_awareness and not family_present', end='family_present')]},
    'P06': {'units': [N0, unit('N1', '쉬지 않고 이십오 분은 걸을 수 있어요', 'capacity_only')]},
    'P13': {'units': [N0, unit('N1', '느티공원에 가야 한다는 말은 매일 하세요', 'stated_goal'),
                      unit('N1', '실제로 일어나 출발한 적은 확인하지 못했어요', 'unobserved')]},
    'P24': {'units': [N0, unit('N1', '기다리는 모습은 관찰하지 못했어요', 'unobserved'),
                      unit('N1', '다른 가족이 돌보는 분 이야기였어요', 'other_information', subject='other_person')]},
}


@pytest.mark.parametrize('pid', sorted(A_CORRECT))
def test_a_correct_fixture_compiles_and_matches_every_scene(pid):
    policy = contracts.compile_a(A_CORRECT[pid], personal(pid))
    assert all(scenes_pass(policy, pid).values())
    assert scoring.critical(policy, personal(pid), REFERENCE[pid], pid) == []


@pytest.mark.parametrize('pid', sorted(B_CORRECT))
def test_b_correct_fixture_compiles_and_matches_every_scene(pid):
    policy = contracts.compile_b(B_CORRECT[pid], personal(pid))
    assert all(scenes_pass(policy, pid).values())
    assert scoring.critical(policy, personal(pid), REFERENCE[pid], pid) == []


def test_b_end_condition_releases_wait_at_nine_and_on_family_arrival():
    p25 = contracts.compile_b(B_CORRECT['P25'], personal('P25'))
    from app.llm import mind_policy as m
    when = p25.rules[0].when
    assert m.truth(when, {'clock_hour': 8.99, 'family_present': False}) is True
    assert m.truth(when, {'clock_hour': 9, 'family_present': False}) is False
    assert m.truth(when, {'clock_hour': 8.5, 'family_present': True}) is False
    p29 = contracts.compile_b(B_CORRECT['P29'], personal('P29'))
    wait = next(r for r in p29.rules if r.action == 'wait')
    assert m.truth(wait.when, {'lost_awareness': True, 'family_present': True}) is False


# P14: the goal and the scope are separate fields; mixing them is rejected, not repaired.
@pytest.mark.parametrize('rule,error', [
    (a_rule('walk', 'target_recognized', goal='느티공원'), 'goal_on_non_seek'),
    (a_rule('seek', 'target_recognized', goal='느티공원', scope=['느티공원']), 'goal_used_as_scope'),
    (a_rule('seek', 'target_recognized'), 'seek_without_registered_goal'),
    (a_rule('seek', 'target_recognized', goal='없는공원'), 'unknown enum'),
])
def test_a_rejects_goal_scope_mixing(rule, error):
    with pytest.raises(ValueError, match=error):
        contracts.compile_a(a_out([rule]), personal('P14'))


def test_saved_p14_walk_scoped_to_goal_compiles_but_is_flagged_and_fails():
    # The 2026-10-06 output shape. Scope is a legitimate field, so the compiler
    # cannot know the intent; the reference comparison must catch it.
    out = a_out([a_rule('walk', 'target_recognized', scope=['느티공원'])])
    policy = contracts.compile_a(out, personal('P14'))
    assert scoring.critical(policy, personal('P14'), REFERENCE['P14'], 'P14') == ['goal_scope_swap']
    assert not scenes_pass(policy, 'P14')['P14_S1']


def test_b_judged_behavior_without_action_is_an_omission_not_an_empty_policy():
    out = {'units': [N0, unit('N1', '무릎 때문에 앉아 쉬어야 해요', 'functional_need')]}
    with pytest.raises(ValueError, match='behavior_unit_without_action'):
        contracts.compile_b(out, personal('P05'))


@pytest.mark.parametrize('u,error', [
    (unit('N1', '아버지 이야기였어요', 'corrected_away', subject='other_person', action='wait',
          start='lost_awareness'), 'non_behavior_unit_with_action'),
    (unit('N1', '아버지 이야기였어요', 'observed_response', subject='other_person', action='wait',
          start='lost_awareness'), 'behavior_unit_not_about_patient'),
    (unit('N1', '어머니는 기다렸어요', 'observed_response', action='walk', start='lost_awareness'),
     'quote_not_in_original_answer'),
    (unit('N1', '계속 걸었어요', 'observed_response', action='walk'), 'behavior_unit_without_condition'),
])
def test_b_rejects_subject_quote_and_condition_violations(u, error):
    with pytest.raises(ValueError, match=error):
        contracts.compile_b({'units': [N0, u]}, personal('P21'))


def test_b_capacity_cannot_become_rest_and_need_must_be_rest():
    with pytest.raises(ValueError, match='non_behavior_unit_with_action'):
        contracts.compile_b({'units': [N0, unit('N1', '이십오 분은 걸을 수 있어요', 'capacity_only', action='rest',
                                                start='is_walking and continuous_walk_minutes >= 25')]}, personal('P06'))
    with pytest.raises(ValueError, match='functional_need_not_rest'):
        contracts.compile_b({'units': [N0, unit('N1', '무릎 때문에 앉아 쉬어야 해요', 'functional_need', action='wait',
                                                start='is_walking')]}, personal('P05'))


@pytest.mark.parametrize('compile_fn,out', [
    (contracts.compile_a, a_out([a_rule('rest', 'continuous_walk_minutes >= 8')])),
    (contracts.compile_b, {'units': [N0, unit('N1', '무릎 때문에 앉아 쉬어야 해요', 'functional_need', action='rest',
                                              start='continuous_walk_minutes >= 8 or is_walking and distance_since_rest_m >= 450')]}),
])
def test_walking_limited_rest_needs_is_walking_in_every_branch(compile_fn, out):
    with pytest.raises(ValueError, match='walking_limited_rest_unguarded'):
        compile_fn(out, personal('P05'))


@pytest.mark.parametrize('compile_fn,out', [
    (contracts.compile_a, a_out([], non_action=('N0',))),
    (contracts.compile_b, {'units': [N0]}),
])
def test_unclassified_source_is_rejected(compile_fn, out):
    with pytest.raises(ValueError, match='source_omitted_without_classification'):
        compile_fn(out, personal('P05'))


def test_critical_checks_on_typed_policies():
    no_rest = contracts.compile_a(a_out([], non_action=('N0', 'N1')), personal('P05'))
    assert scoring.critical(no_rest, personal('P05'), REFERENCE['P05'], 'P05') == ['explicit_rest_deleted']
    injected = contracts.compile_a(a_out([a_rule('wait', 'lost_awareness')]), personal('P21'))
    assert 'withheld_action_injected' in scoring.critical(injected, personal('P21'), REFERENCE['P21'], 'P21')
    invented = contracts.compile_a(a_out([a_rule('rest', 'is_walking and continuous_walk_minutes >= 25')]), personal('P06'))
    assert scoring.critical(invented, personal('P06'), REFERENCE['P06'], 'P06') == ['action_without_reference']


@pytest.mark.parametrize('public,status', [
    ({'finish_reason': 'length', 'final_content': '{"units": ['}, 'incomplete_length'),
    ({'finish_reason': 'stop', 'final_content': '  '}, 'empty'),
    ({'finish_reason': 'stop', 'final_content': '{"a": 1}'}, 'complete_json'),
    ({'finish_reason': 'stop', 'final_content': '```json\n{"a": 1}\n```'}, 'complete_json'),
    ({'finish_reason': 'stop', 'final_content': '.\n{"a": {"b": 2}}'}, 'boundary_single_object'),
    ({'finish_reason': 'stop', 'final_content': '{"a": 1}\n{"a": 2}'}, 'multiple_objects'),
    ({'finish_reason': 'stop', 'final_content': '{"a": 1, "a": 2}'}, 'duplicate_keys'),
    ({'finish_reason': 'stop', 'final_content': '. {"a": 1, "a": 2}'}, 'duplicate_keys'),
    ({'finish_reason': 'stop', 'final_content': '{"a": [1, 2'}, 'invalid_json'),
    ({'finish_reason': 'content_filter', 'final_content': '{"a": 1}'}, 'unexpected_finish'),
    ({'finish_reason': 'stop', 'final_content': '이 사람은 쉬어야 합니다. ' * 10 + '{"a": 1}'}, 'invalid_json'),
])
def test_completion_classes_are_separate_and_unrepaired(public, status):
    got, value = completion.classify(public)
    assert got == status
    assert (value is not None) == (status == 'complete_json')


def test_requests_carry_whole_source_and_no_labels():
    for pid in ('P05', 'P14', 'P29'):
        for build in (contracts.request_a, contracts.request_b):
            body = build(personal(pid), 'model-x')
            text = json.dumps(body, ensure_ascii=False)
            assert body['chat_template_kwargs']['enable_thinking'] is True
            user = json.loads(body['messages'][1]['content'])
            assert user['original_notes'] == personal(pid)['notes']
            for leaked in ('expected', 'reference', 'rationale', pid, '"family": '):
                assert leaked not in text
