from experiments.mind_contract_ab_20261007 import captured_policy as c
from app.llm.mind_policy import Policy


def test_compiled_policy_not_error_kind_is_compared(monkeypatch):
    ref = Policy(rules=[], unrepresented=[])
    monkeypatch.setattr(c.r, 'judge', lambda *args: (None, None, ref))
    result = c.score_response({'content': 'synthetic'}, {}, None, ref)
    assert result['policy'] == ref.model_dump(mode='json')
    assert result['condition_probe']['status'] == 'no_difference_in_probes'


def test_invalid_and_missing_output_stay_in_denominator(monkeypatch):
    ref = Policy(rules=[], unrepresented=[])
    monkeypatch.setattr(c.r, 'judge', lambda *args: ('bad condition', 'validation', None))
    for public in ({'content': 'synthetic'}, None):
        result = c.score_response(public, {}, None, ref)
        assert result['policy'] is None
        assert result['problem'] is not None
        assert result['condition_probe']['status'] == 'unusable_output'
