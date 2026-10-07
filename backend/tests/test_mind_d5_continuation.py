"""No-network checks for the paid-stage continuation gates."""
from pathlib import Path
import pytest

from experiments.mind_contract_ab_20261007 import continue_d5 as c


def test_completed_failed_d4_can_be_baseline_but_partial_or_unbound_cannot(tmp_path):
    assert c.prior_complete(tmp_path) is False
    c.run_v2.write(tmp_path / 'manifest.json', {'stage': 'd4_dev128'})
    result = {'manifest_sha256': c.run_v2.digest(tmp_path / 'manifest.json'),
              'summary': {'complete': False, 'responses': 256}, 'gate': {'advance': False}}
    c.run_v2.write(tmp_path / 'scored.json', result)
    with pytest.raises(ValueError, match='incomplete'):
        c.prior_complete(tmp_path)
    result['summary']['complete'] = True
    c.run_v2.write(tmp_path / 'scored.json', result)
    assert c.prior_complete(tmp_path) is True
    c.run_v2.write(tmp_path / 'manifest.json', {'stage': 'different'})
    with pytest.raises(ValueError, match='not bound'):
        c.prior_complete(tmp_path)


def _review(tmp_path, monkeypatch, *, gate=True, valid=13, passes=4, overrides=0, silent=False):
    new, old = tmp_path / 'new', tmp_path / 'old'
    monkeypatch.setattr(c.run_v2, 'dataset', lambda stage: ([{'id': 'P', 'personal': {}}], [], {'P': {}}, []))
    monkeypatch.setattr(c.contract_d5, 'diagnostics', lambda *a: {'overrides': overrides, 'silent_collapse': silent})
    def scored(valid, passes, advance):
        return {'summary': {'first_valid': valid, 'responses': 16,
                            'by_input': {'P': {'passed': passes, 'total': 4}}},
                'gate': {'advance': advance},
                'rows': [{'input_id': 'P', 'rep': 1, 'corrected': False,
                          'scenes': [{'pass': x < passes} for x in range(4)]}]}
    c.run_v2.write(new / 'd5_dev8/scored.json', scored(valid, passes, gate))
    for candidate in ('d3', 'd4'):
        c.run_v2.write(old / f'{candidate}_dev8/scored.json', scored(13, 4, True))
    c.run_v2.write(new / 'd5_dev8/P/1/first/response.public.json',
                   {'finish_reason': 'stop', 'final_content': '{}'})
    return c.inspect_stage(new, old, 'd5_dev8')


def test_failed_stage_never_authorizes_expansion(tmp_path, monkeypatch):
    result = _review(tmp_path, monkeypatch, gate=False)
    assert result['advance'] is False
    assert 'registered_stage_gate_failed' in result['reasons']


def test_validity_regression_holds_even_when_aggregate_gate_passes(tmp_path, monkeypatch):
    result = _review(tmp_path, monkeypatch, valid=12)
    assert result['advance'] is False
    assert result['first_valid_drop_percentage_points'] == 6.25


def test_previously_correct_input_and_new_priority_regression_require_review(tmp_path, monkeypatch):
    result = _review(tmp_path, monkeypatch, passes=3, overrides=1)
    assert result['advance'] is False
    assert result['watch_regressions'] == ['P']
    assert result['override_regressions'] == [['P', 1]]


def test_unchanged_pass_can_advance(tmp_path, monkeypatch):
    assert _review(tmp_path, monkeypatch)['advance'] is True
