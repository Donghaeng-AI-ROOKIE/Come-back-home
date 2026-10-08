import pytest
from experiments.mind_contract_ab_20261007 import contract_d12 as c
from app.llm import mind_policy as m

SOURCE = {'notes': [{'id': 'N0', 'text': '답변: 연속 여섯 분이나 280미터를 걸으면 오 분 쉬어요.'}],
          'places': [], 'prepared_initial': {}}


def output(condition, action='rest'):
    return {'source_assessment': '합성 테스트 입력', 'rules': [{'action': action,
        'goal_place': '', 'applies_only_at': [], 'condition': condition,
        'hold_minutes': 5 if action == 'rest' else 0, 'note_ids': ['N0']}], 'non_action_note_ids': []}


def test_compact_expression_preserves_or_and_walking_guard():
    policy = c.compile_d12(output('is_walking and (continuous_walk_minutes >= 6 or distance_since_rest_m >= 280)'), SOURCE)
    assert len(policy.rules[0].when) == 2
    assert m.truth(policy.rules[0].when, {'is_walking': True, 'continuous_walk_minutes': 5, 'distance_since_rest_m': 280}) is True
    assert m.truth(policy.rules[0].when, {'is_walking': False, 'continuous_walk_minutes': 6, 'distance_since_rest_m': 0}) is False


@pytest.mark.parametrize('condition,action', [
    ('is_walking and continuous_walk_minutes >= 0', 'rest'),
    ('is_walking and pain_observed and not pain_observed', 'rest'),
    ('is_walking and lost_awareness', 'wait'),
    ('is_walking or distance_since_rest_m >= 280', 'rest'),
    ('__import__("os").system("echo no")', 'rest'),
])
def test_invalid_or_unrestricted_conditions_are_rejected(condition, action):
    with pytest.raises((ValueError, SyntaxError)):
        c.compile_d12(output(condition, action), SOURCE)


def test_trait_coverage_is_unknown_not_zero_loss():
    assert c.trait_accounting({})['available'] is False
