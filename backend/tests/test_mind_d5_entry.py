from pathlib import Path

import pytest

from experiments.mind_contract_ab_20261007 import run_d5, run_v2


def test_registration_is_hashed_and_retains_the_existing_runner(monkeypatch):
    monkeypatch.setattr(run_v2, 'CANDIDATES', dict(run_v2.CANDIDATES))
    monkeypatch.setattr(run_v2, 'COMMON', list(run_v2.COMMON))
    d4 = run_v2.CANDIDATES['d4']
    run_d5.register_candidate()
    run_d5.register_candidate()
    assert run_v2.CANDIDATES['d4'] == d4
    assert run_v2.COMMON.count(Path(run_d5.__file__).resolve()) == 1
    assert 'experiments/mind_contract_ab_20261007/run_d5.py' in run_v2.source_sha256('d5')


@pytest.mark.parametrize('args', [['--stage', 'd4_dev128'], ['--rescore=d3_dev128']])
def test_other_candidates_are_rejected_before_runner_or_transport(monkeypatch, args):
    monkeypatch.setattr(run_v2, 'main', lambda _: pytest.fail('runner must not start'))
    with pytest.raises(SystemExit, match='only accepts D5'):
        run_d5.main(args)


def test_d5_delegates_to_unchanged_authorization_gate(monkeypatch):
    monkeypatch.setattr(run_v2, 'CANDIDATES', dict(run_v2.CANDIDATES))
    monkeypatch.setattr(run_v2, 'COMMON', list(run_v2.COMMON))
    captured = []
    monkeypatch.setattr(run_v2, 'main', lambda args: captured.append(args))
    args = ['--stage', 'd5_dev8', '--run-dir', 'unused', '--execute']
    run_d5.main(args)
    assert captured == [args]
