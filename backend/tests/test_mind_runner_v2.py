"""Offline tests for run_v2 / scoring_v2 (2026-10-07 runner defects, code_review_d3.json).

transport.invoke is replaced by a fake in every test and an autouse guard fails
any test that reaches the real transport or SSH; CBH_K_BRIDGE_SSH is set to a
placeholder so the runner's own preflight passes (nothing can use it). Run folders live in tmp_path;
the real experiment folder and the dataset are only read. Model outputs here
are handwritten; passing them says nothing about K's interpretation quality.
"""
import ast
import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.llm import mind_policy as m
from app.llm import usage_ledger
from experiments.mind_contract_ab_20261007 import contract_d3, contracts, run_v2, scoring, scoring_v2, transport
from experiments.mind_contract_ab_20261007.fixtures import a_out, a_rule
from experiments.mind_policy_candidates import note_policy_eval as ev
from tests.test_mind_contract_ab import D_CORRECT, cl, du, to_d3

PEOPLE, SCENES, REFERENCE = scoring.load()
DEV8_JOBS = [f'd3_dev8_{p}_{rep}' for p in run_v2.DEV8 for rep in (1, 2)]
PLACEHOLDER = 'offline-test-placeholder-never-used'


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('real transport or SSH reached in an offline test')
    monkeypatch.setattr(transport, 'invoke', refuse)
    monkeypatch.setattr(transport.subprocess, 'run', refuse)
    monkeypatch.setattr(run_v2, 'CONCURRENCY', 1)  # deterministic order unless a test sets 2
    monkeypatch.setenv(run_v2.BRIDGE_ENV, PLACEHOLDER)


# ------------------------------------------------------------------ helpers

def split(part):
    return run_v2._split(run_v2.DEV128 if part == 'dev128' else run_v2.EVAL64, part)


def behavior(ids, action, start, goal='', scope=(), end=(), hold=0, kind='observed_response'):
    return {'sentence_ids': list(ids), 'kind': kind, 'action': action, 'goal_place': goal,
            'applies_only_at': list(scope), 'start_when_any': list(start), 'end_when_any': list(end),
            'hold_minutes': hold}


def d3_output(personal, behaviors, others=None):
    """Behaviors plus every remaining sentence as other_information (or the given others)."""
    cited = {s for b in behaviors for s in b['sentence_ids']}
    if others is None:
        others = [{'sentence_ids': [s['id']], 'subject': 'patient', 'kind': 'other_information'}
                  for s in contract_d3.sentences(personal) if s['id'] not in cited]
    return {'behaviors': behaviors, 'other_sentences': others}


def public(value):
    return {'final_content': value if isinstance(value, str) else json.dumps(value, ensure_ascii=False),
            'finish_reason': 'stop', 'usage': None}


def save(folder, value=None, job='saved'):
    """A submitted call with (value) or without (None) a saved response, as run_v2 leaves it."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'request.json').write_text('{}')
    if value is not None:
        run_v2.write(folder / 'response.public.json', public(value))
    run_v2.write(folder / 'result.json', {'job': job, 'submitted': True, 'response_saved': value is not None,
                                          'error_type': None if value is not None else 'RuntimeError:K_API_HTTPError'})


def all_other(body):
    """A valid D3 answer for any request: every sentence classified, no behavior."""
    payload = json.loads(body['messages'][1]['content'])
    return json.dumps({'behaviors': [], 'other_sentences': [
        {'sentence_ids': [s['id']], 'subject': 'patient', 'kind': 'other_information'}
        for s in payload['answer_sentences']]}, ensure_ascii=False)


class FakeK:
    """Stands in for transport.invoke; plan maps a job to content, a raw response or an exception."""

    def __init__(self, plan=None):
        self.plan, self.calls, self.bodies = plan or {}, [], {}

    def __call__(self, body, job, *, run_id, role, ledger_path, max_started):
        self.calls.append(job)
        self.bodies[job] = body
        answer = self.plan.get(job, all_other)
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, dict):
            return answer
        content = answer(body) if callable(answer) else answer
        return {'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}], 'usage': {'total_tokens': 1}}


def authorize(run_dir, stage='d3_dev8', max_calls=32):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / 'authorization.json').write_text(json.dumps(
        {'status': 'approved', 'stages': {stage: {'max_calls': max_calls}}}))


def run(run_dir, *extra, stage='d3_dev8'):
    return run_v2.main(['--stage', stage, '--run-dir', str(run_dir), '--ledger', str(run_dir / 'ledger.jsonl'),
                        *extra])


def read(path):
    return json.loads(path.read_text())


def sign_scored(run_dir, stage, advance=True):
    """A scored.json as run_v2 writes it, bound to the frozen manifest."""
    path = run_dir / stage / 'manifest.json'
    run_v2.write(run_dir / stage / 'scored.json',
                 {'manifest_sha256': run_v2.digest(path), 'gate': {'advance': advance}})


def freeze(run_dir, stage):
    run_v2.main(['--stage', stage, '--run-dir', str(run_dir)])


def tree_digest(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def p16_hard(extra=()):
    personal = next(r for r in split('dev128')[0] if r['id'] == 'DEV_P16_hard')['personal']
    return personal, d3_output(personal, [
        behavior(['N1.s1'], 'seek', [cl(['target_recognized'], ['physical_arrival'])], goal='솔빛쉼터'),
        behavior(['N2.s1'], 'wait', [cl(['physical_arrival', 'target_recognized'])], scope=['솔빛쉼터']),
        *extra])


# ------------------------------------------------------------------ 1. goal_scope_swap

@pytest.mark.parametrize('part,count', [('dev128', 128), ('eval64', 64)])
def test_every_reference_policy_is_free_of_critical_errors(part, count):
    inputs, _, reference, _ = split(part)
    assert len(inputs) == len(reference) == count
    flagged = {}
    for r in inputs:
        key = r['root_id'] if r.get('form') == 'original' else r['id']
        policy = m.validate(reference[r['id']], r['personal'])
        found = scoring_v2.critical(policy, r['personal'], reference[r['id']], key)
        extra = scoring_v2.commands_not_in_reference(policy, r['personal'], reference[r['id']])
        if found or extra:
            flagged[r['id']] = found + extra
    assert flagged == {}


def p16_rule(rid, action, feature=None):
    """A rule limited to 솔빛쉼터 (DEV_P16_hard's seek goal, a park) under a crowd condition."""
    evidence = split('dev128')[2]['DEV_P16_hard']['rules'][1]['evidence']
    return {'id': rid, 'when': [[{'fact': 'park.crowded', 'op': 'eq', 'value': True}]], 'action': action,
            'goal_label': None, 'feature': feature, 'place_labels': ['솔빛쉼터'], 'hold_minutes': None,
            'supersedes': [], 'evidence': evidence}


def test_reference_exemption_needs_the_same_action_and_target_not_only_the_same_place():
    personal = next(r for r in split('dev128')[0] if r['id'] == 'DEV_P16_hard')['personal']
    base = split('dev128')[2]['DEV_P16_hard']
    reference = copy.deepcopy(base)
    reference['rules'].append(p16_rule('k_2', 'avoid', 'park'))
    m.validate(reference, personal)

    def own(rule):
        policy = copy.deepcopy(base)
        policy['rules'].append(rule)
        return m.validate(policy, personal)
    assert scoring_v2.critical(own(p16_rule('x', 'avoid', 'park')), personal, reference, 'DEV_P16_hard') == []
    for other in (p16_rule('x', 'avoid', 'water'), p16_rule('x', 'avoid', 'market'), p16_rule('x', 'rest')):
        assert scoring_v2.critical(own(other), personal, reference, 'DEV_P16_hard') == ['goal_scope_swap']


def test_the_10_06_reference_policies_stay_free_of_critical_errors():
    assert {p: scoring_v2.critical(m.validate(REFERENCE[p], PEOPLE[p]['personal']), PEOPLE[p]['personal'],
                                   REFERENCE[p], p) for p in PEOPLE} == {p: [] for p in PEOPLE}


def test_v1_flagged_exactly_the_two_place_limited_references():
    flagged = {}
    for part in ('dev128', 'eval64'):
        inputs, _, reference, _ = split(part)
        for r in inputs:
            key = r['root_id'] if r.get('form') == 'original' else r['id']
            found = scoring.critical(m.validate(reference[r['id']], r['personal']), r['personal'],
                                     reference[r['id']], key)
            if found:
                flagged[r['id']] = found
    assert flagged == {'DEV_P16_hard': ['goal_scope_swap'], 'R_lost_reaction_03': ['goal_scope_swap']}


def test_place_limited_wait_from_the_reference_is_not_a_swap_but_a_scoped_walk_still_is():
    personal, out = p16_hard()
    reference = split('dev128')[2]['DEV_P16_hard']
    policy = contract_d3.compile_d3(out, personal)
    scenes = [s for s in split('dev128')[1] if s['input_id'] == 'DEV_P16_hard']
    assert all(scoring_v2.scene_pass(ev.decide(policy, personal, s['scene']), s) for s in scenes)
    assert scoring.critical(policy, personal, reference, 'DEV_P16_hard') == ['goal_scope_swap']
    assert scoring_v2.critical(policy, personal, reference, 'DEV_P16_hard') == []
    _, swapped = p16_hard([behavior(['N1.s1'], 'walk', [cl(['target_recognized'])], scope=['솔빛쉼터'])])
    policy = contract_d3.compile_d3(swapped, personal)
    assert scoring_v2.critical(policy, personal, reference, 'DEV_P16_hard') == ['goal_scope_swap']
    p14 = PEOPLE['P14']['personal']
    walk = contracts.compile_a(a_out([a_rule('walk', 'target_recognized', scope=['느티공원'])]), p14)
    assert scoring_v2.critical(walk, p14, REFERENCE['P14'], 'P14') == ['goal_scope_swap']


# ------------------------------------------------------------------ 2. no correction without a response

def test_api_error_is_recorded_without_correction_and_stops_the_run(tmp_path, monkeypatch):
    authorize(tmp_path)
    fake = FakeK({'d3_dev8_P05_1': RuntimeError('K_API_HTTPError')})
    monkeypatch.setattr(transport, 'invoke', fake)
    with pytest.raises(SystemExit, match='stopped'):
        run(tmp_path, '--execute')
    assert fake.calls == ['d3_dev8_P05_1']
    out = tmp_path / 'd3_dev8'
    first = out / 'P05' / '1' / 'first'
    assert read(first / 'result.json')['error_type'] == 'RuntimeError:K_API_HTTPError'
    assert not (first / 'response.public.json').exists() and not (first / 'problem.json').exists()
    assert not (out / 'P05' / '1' / 'fix').exists()
    later = out / 'P05' / '2' / 'first'
    assert read(later / 'not_submitted.json')['submitted'] is False and not (later / 'request.json').exists()
    scored = read(out / 'scored.json')
    row = scored['rows'][0]
    assert (row['final_problem'], row['correction_needed'], row['corrected']) == ('no_response', False, False)
    summary = scored['summary']
    assert (summary['corrections'], summary['no_response'], summary['not_submitted'], summary['final_valid']) == (0, 1, 15, 0)
    assert 'unexpected_finish' not in json.dumps(summary['problems'])
    assert scored['gate']['checks']['complete'] is False and scored['gate']['advance'] is False


@pytest.mark.parametrize('failure', [
    RuntimeError('K_API_TimeoutError'), RuntimeError('K_bridge_transport_failure'),
    json.JSONDecodeError('Expecting value', 'Warning: banner', 0),
    {'error': {'message': 'upstream'}},  # a body without choices is no response either
])
def test_no_correction_after_any_failed_call_with_two_workers(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(run_v2, 'CONCURRENCY', 2)
    authorize(tmp_path)
    fake = FakeK({'d3_dev8_P05_1': failure})
    monkeypatch.setattr(transport, 'invoke', fake)
    with pytest.raises(SystemExit, match='stopped'):
        run(tmp_path, '--execute')
    assert 'd3_dev8_P05_1' in fake.calls and len(fake.calls) < len(DEV8_JOBS)
    assert not any(job.endswith('_fix') for job in fake.calls)
    assert not (tmp_path / 'd3_dev8' / 'P05' / '1' / 'fix').exists()


def test_a_received_invalid_response_gets_exactly_one_correction_with_the_validator_text(tmp_path, monkeypatch):
    authorize(tmp_path)
    p14 = to_d3(D_CORRECT['P14'])
    p14['behaviors'][0]['hold_minutes'] = 5  # seek with a duration: rejected by Policy
    fake = FakeK({'d3_dev8_P05_1': '{"behaviors": [', 'd3_dev8_P14_1': json.dumps(p14, ensure_ascii=False)})
    monkeypatch.setattr(transport, 'invoke', fake)
    run(tmp_path, '--execute')
    assert [j for j in fake.calls if j.endswith('_fix')] == ['d3_dev8_P05_1_fix', 'd3_dev8_P14_1_fix']
    assert len(fake.calls) == len(DEV8_JOBS) + 2
    assert 'invalid_json' in fake.bodies['d3_dev8_P05_1_fix']['messages'][-1]['content']
    feedback = fake.bodies['d3_dev8_P14_1_fix']['messages'][-1]['content']
    assert '1 validation error for Policy: rules.' in feedback
    assert 'only a sourced rest/wait duration is allowed' in feedback
    rows = {(r['input_id'], r['rep']): r for r in read(tmp_path / 'd3_dev8' / 'scored.json')['rows']}
    assert rows['P05', 1]['corrected'] and rows['P05', 1]['first_problem'] == 'invalid_json'
    assert rows['P05', 1]['final_problem'] is None
    assert rows['P14', 1]['first_problem_kind'] == 'validation:Policy:rules:value_error'


# ------------------------------------------------------------------ 2b. a call that cannot leave the machine

def test_missing_bridge_target_refuses_execute_before_anything_is_written(tmp_path, monkeypatch):
    monkeypatch.setattr(run_v2, 'CONCURRENCY', 2)
    monkeypatch.delenv(run_v2.BRIDGE_ENV)
    authorize(tmp_path)
    fake = FakeK()
    monkeypatch.setattr(transport, 'invoke', fake)
    with pytest.raises(SystemExit, match='CBH_K_BRIDGE_SSH is not set'):
        run(tmp_path, '--execute')
    assert fake.calls == [] and not (tmp_path / 'ledger.jsonl').exists()
    assert not [p for p in (tmp_path / 'd3_dev8').iterdir() if p.name in run_v2.DEV8]


def test_unsendable_calls_are_not_submitted_and_sent_on_resume(tmp_path, monkeypatch):
    """Review repro (two workers): the bridge target is gone when the calls start."""
    monkeypatch.setattr(run_v2, 'CONCURRENCY', 2)
    authorize(tmp_path)
    freeze(tmp_path, 'd3_dev8')
    module, compile_fn, _ = run_v2.load_candidate('d3')
    jobs = run_v2.jobs_for('d3_dev8', module, run_v2.dataset('d3_dev8')[0])
    fake = FakeK()
    monkeypatch.setattr(transport, 'invoke', fake)
    monkeypatch.delenv(run_v2.BRIDGE_ENV)
    out, ledger = tmp_path / 'd3_dev8', tmp_path / 'ledger.jsonl'
    assert run_v2.execute('d3_dev8', out, jobs, module, compile_fn, ledger, 32) is True
    assert fake.calls == [] and not ledger.exists()
    folders = [out / j['input']['id'] / str(j['rep']) / 'first' for j in jobs]
    assert {run_v2.call_state(f) for f in folders} == {'not_submitted'}
    assert not any((f / 'result.json').exists() or (f / 'request.json').exists() for f in folders)
    reasons = {read(f / 'not_submitted.json')['reason'] for f in folders}
    assert 'unsendable:CBH_K_BRIDGE_SSH is not set' in reasons
    assert reasons <= {'unsendable:CBH_K_BRIDGE_SSH is not set', 'run stopped before submission'}
    monkeypatch.setenv(run_v2.BRIDGE_ENV, PLACEHOLDER)
    run(tmp_path, '--execute')
    assert sorted(fake.calls) == sorted(DEV8_JOBS)
    summary = read(out / 'scored.json')['summary']
    assert summary['complete'] and (summary['final_valid'], summary['no_response'], summary['not_submitted']) == (16, 0, 0)


def test_a_correction_for_another_model_is_not_submitted_and_sent_once_fixed(tmp_path, monkeypatch):
    authorize(tmp_path)
    real = contract_d3.correction
    monkeypatch.setattr(contract_d3, 'correction', lambda *a: real(*a) | {'model': 'another-model'})
    fake = FakeK({'d3_dev8_P05_1': '{"behaviors": ['})
    monkeypatch.setattr(transport, 'invoke', fake)
    with pytest.raises(SystemExit, match='stopped'):
        run(tmp_path, '--execute')
    assert fake.calls == ['d3_dev8_P05_1']
    fix = tmp_path / 'd3_dev8' / 'P05' / '1' / 'fix'
    assert run_v2.call_state(fix) == 'not_submitted' and not (fix / 'request.json').exists()
    assert "'another-model' is not transport.MODEL" in read(fix / 'not_submitted.json')['reason']
    monkeypatch.setattr(contract_d3, 'correction', real)
    run(tmp_path, '--execute')
    assert fake.calls[:2] == ['d3_dev8_P05_1', 'd3_dev8_P05_1_fix'] and fake.calls.count('d3_dev8_P05_1') == 1
    assert read(tmp_path / 'd3_dev8' / 'scored.json')['rows'][0]['corrected'] is True


def test_an_error_inside_transport_stays_a_submitted_failure(tmp_path, monkeypatch):
    """transport polls through SSH after launching, so its errors never prove nothing was sent."""
    authorize(tmp_path)
    fake = FakeK({'d3_dev8_P05_1': RuntimeError('CBH_K_BRIDGE_SSH is not set; no request submitted')})
    monkeypatch.setattr(transport, 'invoke', fake)
    with pytest.raises(SystemExit, match='stopped'):
        run(tmp_path, '--execute')
    first = tmp_path / 'd3_dev8' / 'P05' / '1' / 'first'
    assert run_v2.call_state(first) == 'done' and read(first / 'result.json')['submitted'] is True
    second = FakeK()
    monkeypatch.setattr(transport, 'invoke', second)
    run(tmp_path, '--execute')
    assert 'd3_dev8_P05_1' not in second.calls


# ------------------------------------------------------------------ 3. resume

def test_resume_submits_never_sent_first_calls_and_never_resends_a_failure(tmp_path, monkeypatch):
    authorize(tmp_path)
    first = FakeK({'d3_dev8_P06_1': RuntimeError('K_bridge_transport_failure')})
    monkeypatch.setattr(transport, 'invoke', first)
    with pytest.raises(SystemExit, match='stopped'):
        run(tmp_path, '--execute')
    assert first.calls == DEV8_JOBS[:3]
    second = FakeK()
    monkeypatch.setattr(transport, 'invoke', second)
    run(tmp_path, '--execute')
    assert second.calls == DEV8_JOBS[3:]  # first calls only: no correction, no resend of P06_1
    out = tmp_path / 'd3_dev8'
    assert (out / 'P06' / '2' / 'first' / 'unsent' / '1' / 'not_submitted.json').exists()
    assert read(out / 'P06' / '2' / 'first' / 'result.json')['submitted'] is True
    summary = read(out / 'scored.json')['summary']
    assert summary['complete'] and summary['not_submitted'] == 0
    assert (summary['corrections'], summary['no_response'], summary['final_valid']) == (0, 1, 15)
    third = FakeK()
    monkeypatch.setattr(transport, 'invoke', third)
    run(tmp_path, '--execute')
    assert third.calls == []


def test_legacy_not_submitted_result_marker_is_submitted_as_a_first_call(tmp_path, monkeypatch):
    authorize(tmp_path)
    freeze(tmp_path, 'd3_dev8')
    folder = tmp_path / 'd3_dev8' / 'P05' / '1' / 'first'
    run_v2.write(folder / 'result.json', {'job': 'd3_dev8_P05_1', 'submitted': False,
                                          'error_type': 'not_submitted_after_transport_error'})
    assert run_v2.call_state(folder) == 'not_submitted'
    fake = FakeK()
    monkeypatch.setattr(transport, 'invoke', fake)
    run(tmp_path, '--execute')
    assert fake.calls == DEV8_JOBS
    assert read(folder / 'unsent' / '1' / 'result.json')['submitted'] is False
    assert read(folder / 'result.json')['submitted'] is True


def test_submitted_without_result_stops_before_anything_is_sent(tmp_path, monkeypatch):
    authorize(tmp_path)
    freeze(tmp_path, 'd3_dev8')
    folder = tmp_path / 'd3_dev8' / 'P13' / '1' / 'first'
    folder.mkdir(parents=True)
    (folder / 'request.json').write_text('{}')
    fake = FakeK()
    monkeypatch.setattr(transport, 'invoke', fake)
    with pytest.raises(SystemExit, match='recover explicitly: d3_dev8_P13_1'):
        run(tmp_path, '--execute')
    assert fake.calls == []
    (folder / 'result.json').write_text('{"job": "d3_dev8_P13_1", "subm')  # half-written by a non-atomic writer
    assert run_v2.call_state(folder) == 'submitted_without_result'


def test_budget_refusal_is_not_a_submission_and_resume_sends_the_pending_correction(tmp_path, monkeypatch):
    authorize(tmp_path)
    fake = FakeK({'d3_dev8_P05_1': '{"behaviors": [',
                  'd3_dev8_P05_1_fix': usage_ledger.CallBudgetExceeded('approved call budget exhausted')})
    monkeypatch.setattr(transport, 'invoke', fake)
    with pytest.raises(SystemExit, match='stopped'):
        run(tmp_path, '--execute')
    assert fake.calls == ['d3_dev8_P05_1', 'd3_dev8_P05_1_fix']
    fix = tmp_path / 'd3_dev8' / 'P05' / '1' / 'fix'
    assert not (fix / 'result.json').exists() and run_v2.call_state(fix) == 'not_submitted'
    second = FakeK()
    monkeypatch.setattr(transport, 'invoke', second)
    run(tmp_path, '--execute')
    assert second.calls[0] == 'd3_dev8_P05_1_fix' and 'd3_dev8_P05_1' not in second.calls
    row = read(tmp_path / 'd3_dev8' / 'scored.json')['rows'][0]
    assert row['corrected'] and row['final_problem'] is None


# ------------------------------------------------------------------ 4. dev128 entry gate

def test_dev128_runs_only_on_the_sources_dev8_was_gated_with(tmp_path):
    with pytest.raises(SystemExit, match='d3_dev8 has no frozen manifest'):
        freeze(tmp_path, 'd3_dev128')
    freeze(tmp_path, 'd3_dev8')
    path = tmp_path / 'd3_dev8' / 'manifest.json'
    original = path.read_text()
    run_v2.write(tmp_path / 'd3_dev8' / 'scored.json', {'gate': {'advance': True}})  # run_candidate style
    with pytest.raises(SystemExit, match='not written by run_v2'):
        freeze(tmp_path, 'd3_dev128')
    tampered = json.loads(original)
    tampered['source_sha256']['experiments/mind_contract_ab_20261007/contract_d3.py'] = '0' * 64
    path.write_text(json.dumps(tampered))
    sign_scored(tmp_path, 'd3_dev8')
    with pytest.raises(SystemExit, match='code differs .*contract_d3.py'):
        freeze(tmp_path, 'd3_dev128')
    path.write_text(original)
    sign_scored(tmp_path, 'd3_dev8', advance=False)
    with pytest.raises(SystemExit, match='d3_dev8 did not advance'):
        freeze(tmp_path, 'd3_dev128')
    assert not (tmp_path / 'd3_dev128').exists()
    sign_scored(tmp_path, 'd3_dev8')
    freeze(tmp_path, 'd3_dev128')
    manifest = read(tmp_path / 'd3_dev128' / 'manifest.json')
    assert manifest['source_sha256'] == json.loads(original)['source_sha256']
    assert manifest['first_calls'] == 256 and manifest['runner'] == 'run_v2'


# ------------------------------------------------------------------ 5. validator error text

def test_validator_error_keeps_field_path_and_cause_within_800_chars():
    from experiments.mind_contract_ab_20261007 import run_candidate
    personal = PEOPLE['P14']['personal']
    out = to_d3(D_CORRECT['P14'])
    out['behaviors'][0]['hold_minutes'] = 5
    saved = public(out)
    problem, kind, policy = run_v2.judge(saved, personal, contract_d3.compile_d3)
    assert policy is None and kind == 'validation:Policy:rules:value_error'
    assert problem.startswith('1 validation error for Policy: rules.')
    assert 'only a sourced rest/wait duration is allowed' in problem
    assert run_candidate.judge(saved, personal, contract_d3.compile_d3)[0] == '1 validation error for Policy'
    fix = contract_d3.correction(contract_d3.request(personal, 'model-x'), saved, problem)
    assert problem in fix['messages'][-1]['content']
    with pytest.raises(ValidationError) as many:
        m.Policy.model_validate({'rules': [{'id': ''}] * 20, 'unrepresented': []})
    text, _ = run_v2.describe(many.value)
    assert len(text) == run_v2.ERROR_CHARS and text.startswith(str(many.value).splitlines()[0] + ': rules.0.id: ')
    assert run_v2.describe(ValueError('sentence_not_classified:N1.s3')) == ('sentence_not_classified:N1.s3',
                                                                            'sentence_not_classified')
    assert run_v2.describe(KeyError('behaviors')) == ("KeyError: 'behaviors'", 'KeyError')
    with pytest.raises(ValidationError) as atom:
        m.Atom.model_validate({'fact': 'clock_hour', 'op': 'gte', 'value': 25})
    assert run_v2.describe(atom.value)[0] == '1 validation error for Atom: (root): Value error, clock hour out of range'


# ------------------------------------------------------------------ 6. scene enumeration cap

TOO_COMPLEX = d3_output(PEOPLE['P14']['personal'], [
    behavior(['N1.s1'], 'wait', [cl([f]) for f in ('market.noisy', 'market.crowded', 'park.noisy', 'park.crowded')]),
    behavior(['N1.s1'], 'wait', [cl([f]) for f in ('forest.noisy', 'forest.crowded', 'water.noisy', 'water.crowded')]),
    behavior(['N1.s1'], 'walk', [cl(['target_recognized'])])])


def test_policy_beyond_the_enumeration_cap_is_a_recorded_failure_not_a_crash(tmp_path):
    from experiments.mind_contract_ab_20261007 import run_candidate
    out = tmp_path / 'd3_dev8'
    save(out / 'P14' / '1' / 'first', TOO_COMPLEX)
    with pytest.raises(ValueError, match='too many unresolved'):
        run_candidate.score('d3_dev8', out)
    rows, summary, verdict = run_v2.score('d3_dev8', out)
    row = next(r for r in rows if (r['input_id'], r['rep']) == ('P14', 1))
    assert row['first_problem'] == row['final_problem'] == 'policy_too_complex'
    assert 'too many unresolved' in row['decision_error'] and row['policy'] is None
    assert not row['correction_needed'] and row['critical'] == []
    assert not any(s['pass'] or s['first_pass'] for s in row['scenes']) and len(row['scenes']) == 4
    assert row['traits']['compiled'] is True
    assert summary['policy_too_complex'] == 1
    assert summary['problems']['final_problem'] == {'policy_too_complex': 1, 'not_submitted': 15}
    assert verdict['advance'] is False


# ------------------------------------------------------------------ 7. trait loss of rejected responses

def test_trait_loss_of_a_parseable_rejected_response_is_counted(tmp_path):
    from experiments.mind_contract_ab_20261007 import run_candidate
    units = D_CORRECT['P21'][:3] + [du(['N1.s3'], 'not_representable')]
    valid = to_d3(units)
    rejected = to_d3(units)
    rejected['behaviors'].append(behavior(['N1.s2'], 'walk', [cl(['is_walking'])]))
    out = tmp_path / 'd3_dev8'
    save(out / 'P21' / '1' / 'first', rejected)
    save(out / 'P21' / '1' / 'fix', rejected)
    save(out / 'P21' / '2' / 'first', valid)
    rows, summary, _ = run_v2.score('d3_dev8', out)
    r1, r2 = [r for r in rows if r['input_id'] == 'P21']
    assert r1['final_problem'] == 'degenerate_condition_only_is_walking' and r1['corrected']
    assert r1['traits']['compiled'] is False and r1['traits']['trait_loss_sentence_ids'] == ['N1.s3']
    assert r2['traits']['compiled'] is True and r2['traits']['trait_loss_sentence_ids'] == ['N1.s3']
    acct = summary['trait_accounting']
    assert (acct['responses_counted'], acct['responses_counted_rejected'], acct['responses_with_trait_loss']) == (2, 1, 2)
    assert acct['rejected'] == {'responses_with_trait_loss': 1, 'trait_loss_sentences': 1}
    assert acct['by_kind']['not_representable'] == 2
    v1 = run_candidate.score('d3_dev8', out)[1]['trait_accounting']
    assert (v1['responses_counted'], v1['responses_with_trait_loss']) == (1, 1)


# ------------------------------------------------------------------ 8. lazy candidate registry

def test_candidates_are_registered_by_name_and_imported_only_when_used(tmp_path, monkeypatch):
    assert run_v2.CANDIDATES['d4'][:2] == ('contract_d4', 'compile_d4')
    assert all(isinstance(name, str) for name, _, _ in run_v2.CANDIDATES.values())
    tree = ast.parse(Path(run_v2.__file__).read_text())
    imported = [a.name for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom)) for a in node.names]
    assert not [name for name in imported if name.startswith('contract')]
    monkeypatch.setitem(run_v2.CANDIDATES, 'zz', ('contract_zz_absent', 'compile_zz', 'PLAN_zz.md'))
    with pytest.raises(SystemExit, match='contract_zz_absent.py not found'):
        run_v2.main(['--stage', 'zz_dev8', '--run-dir', str(tmp_path)])
    monkeypatch.setitem(run_v2.CANDIDATES, 'zz', ('contract_c', 'compile_zz', 'PLAN_c.md'))
    with pytest.raises(SystemExit, match='compile_zz is missing'):
        run_v2.load_candidate('zz')
    assert not (tmp_path / 'zz_dev8').exists()
    assert run_v2.load_candidate('d3')[1] is contract_d3.compile_d3


# ------------------------------------------------------------------ 9. offline rescore

def test_rescore_is_read_only_and_marks_scoring_v2(tmp_path):
    from experiments.mind_contract_ab_20261007 import run_candidate
    out = tmp_path / 'd3_dev128'
    run_v2.write(out / 'manifest.json', {'stage': 'd3_dev128', 'frozen_by': 'run_candidate (differs from v2)'})
    run_v2.write(out / 'scored.json', {'gate': {'advance': False}, 'scored_by': 'run_candidate'})
    _, faithful = p16_hard()
    save(out / 'DEV_P16_hard' / '1' / 'first', faithful)
    save(out / 'DEV_P16_hard' / '2' / 'first', faithful)
    p01 = next(r for r in split('dev128')[0] if r['id'] == 'DEV_P01_original')['personal']
    save(out / 'DEV_P01_original' / '1' / 'first')  # API error, no response
    save(out / 'DEV_P01_original' / '1' / 'fix', d3_output(p01, []))  # the run_candidate retry
    run_v2.write(out / 'DEV_P01_original' / '2' / 'first' / 'result.json',
                 {'job': 'x', 'submitted': False, 'error_type': 'not_submitted_after_transport_error'})
    before = tree_digest(out)
    run_v2.main(['--rescore', 'd3_dev128', '--run-dir', str(tmp_path)])
    after = tree_digest(out)
    assert after.pop('scored_v2.json') and after == before
    result = read(out / 'scored_v2.json')
    assert result['rescored_with'] == 'scoring_v2' and result['manifest_checked'] is False
    rows = {(r['input_id'], r['rep']): r for r in result['rows']}
    for rep in (1, 2):
        assert rows['DEV_P16_hard', rep]['critical'] == [] and rows['DEV_P16_hard', rep]['final_problem'] is None
        assert all(s['pass'] for s in rows['DEV_P16_hard', rep]['scenes'])
    assert rows['DEV_P01_original', 1]['final_problem'] == 'no_response'
    assert rows['DEV_P01_original', 1]['ignored_fix_after_no_response'] is True
    assert rows['DEV_P01_original', 2]['first_state'] == 'not_submitted'
    assert result['summary']['critical'] == {}
    v1 = {(r['input_id'], r['rep']): r for r in run_candidate.score('d3_dev128', out)[0]}
    assert v1['DEV_P16_hard', 1]['critical'] == ['goal_scope_swap']


def test_rescore_needs_a_saved_stage_folder(tmp_path):
    with pytest.raises(SystemExit, match='no saved stage folder'):
        run_v2.main(['--rescore', 'd3_dev8', '--run-dir', str(tmp_path)])


# ------------------------------------------------------------------ 10. eval64 stage

@pytest.fixture
def eval_copy(tmp_path, monkeypatch):
    """A copy of eval64 so a test signature never touches the real dataset folder."""
    folder = tmp_path / 'eval64_copy'
    shutil.copytree(run_v2.EVAL64, folder)
    (folder / run_v2.APPROVAL).unlink(missing_ok=True)
    monkeypatch.setattr(run_v2, 'EVAL64', folder)
    return folder


def test_eval64_refuses_without_the_human_review_signature(tmp_path, eval_copy):
    run_dir = tmp_path / 'run'
    authorize(run_dir, 'd3_eval64', 128)
    with pytest.raises(SystemExit, match='HUMAN_REVIEW_APPROVED.json'):
        run(run_dir, '--execute', stage='d3_eval64')
    with pytest.raises(SystemExit, match='HUMAN_REVIEW_APPROVED.json'):
        run(run_dir, '--score-only', stage='d3_eval64')
    assert not (run_dir / 'd3_eval64').exists()


def signed(folder, **change):
    """A well-formed test signature (not a review) bound to the copied files, with fields changed."""
    value = {'reviewer': 'test fixture, not a review', 'reviewed_on': '2026-10-07',
             'sha256': {n: run_v2.digest(folder / n) for n in run_v2.EVAL64_FILES}} | change
    (folder / run_v2.APPROVAL).write_text(json.dumps(value, ensure_ascii=False))
    return value


def test_human_review_signature_must_name_reviewer_date_and_bind_the_three_files(tmp_path, eval_copy):
    full = signed(eval_copy)['sha256']
    outside = tmp_path / 'outside.json'
    outside.write_text('{}')
    cases = [({'ok': True}, 'needs reviewer'),
             ({'reviewer': ' '}, 'needs reviewer'),
             ({'reviewed_on': None}, 'reviewed_on'),
             ({'reviewed_on': '10월 7일'}, 'reviewed_on'),
             ({'sha256': 'all good'}, 'sha256 map'),
             ({'sha256': {n: h for n, h in full.items() if 'scenes' not in n}}, 'sha256 map'),
             ({'sha256': full | {'eval64_inputs.jsonl': '0' * 64}}, 'differ.*eval64_inputs.jsonl'),
             ({'sha256': full | {'eval64_review.NOT_MODEL_INPUT.jsonl': '0' * 64}}, 'differ.*eval64_review'),
             ({'sha256': full | {'../outside.json': run_v2.digest(outside)}}, 'differ.*outside.json')]
    for change, message in cases:
        if 'ok' in change:
            (eval_copy / run_v2.APPROVAL).write_text(json.dumps(change))
        else:
            signed(eval_copy, **change)
        with pytest.raises(SystemExit, match=message):
            run_v2.require_human_review()
    review = eval_copy / 'eval64_review.NOT_MODEL_INPUT.jsonl'
    signed(eval_copy, sha256=full | {review.name: run_v2.digest(review)})
    assert run_v2.require_human_review() == run_v2.digest(eval_copy / run_v2.APPROVAL)


def test_eval64_runs_on_reviewed_data_after_an_advanced_dev128(tmp_path, eval_copy):
    run_dir = tmp_path / 'run'
    signature = eval_copy / run_v2.APPROVAL
    names = run_v2.EVAL64_FILES
    signed(eval_copy, sha256={n: run_v2.digest(eval_copy / n) for n in names} | {names[0]: '0' * 64})
    with pytest.raises(SystemExit, match='differ from the human-reviewed'):
        freeze(run_dir, 'd3_eval64')
    signed(eval_copy)
    with pytest.raises(SystemExit, match='d3_dev128 has no frozen manifest'):
        freeze(run_dir, 'd3_eval64')
    freeze(run_dir, 'd3_dev8')
    sign_scored(run_dir, 'd3_dev8')
    freeze(run_dir, 'd3_dev128')
    sign_scored(run_dir, 'd3_dev128', advance=False)
    with pytest.raises(SystemExit, match='d3_dev128 did not advance'):
        freeze(run_dir, 'd3_eval64')
    sign_scored(run_dir, 'd3_dev128')
    freeze(run_dir, 'd3_eval64')
    manifest = read(run_dir / 'd3_eval64' / 'manifest.json')
    assert manifest['first_calls'] == 128 and manifest['human_review_sha256'] == run_v2.digest(signature)
    assert manifest['rows_marked_draft_unreviewed'] == 64  # recorded only; re-marking rows is the user's call
    assert sorted(manifest['data_sha256']) == sorted(names)
    assert manifest['jobs'][0]['job'] == 'd3_eval64_R_rest_endurance_01_1'
    inputs, scenes, reference, _ = run_v2.dataset('d3_eval64')
    assert (len(inputs), len(scenes), len(reference)) == (64, 256, 64)
    text = json.dumps(contract_d3.request(inputs[0]['personal'], transport.MODEL), ensure_ascii=False)
    assert inputs[0]['id'] not in text and 'expected_commands' not in text


def test_eval64_gate_uses_the_preregistered_shares(tmp_path, eval_copy):
    rows, summary, verdict = run_v2.score('d3_eval64', tmp_path / 'empty')
    assert len(rows) == 128 and summary['decisions'] == 512 and summary['not_submitted'] == 128
    assert set(verdict['checks']) == {'complete', 'decisions', 'families', 'supported', 'unknown',
                                      'final_valid', 'no_critical'}
    assert verdict['advance'] is False and 'human-reviewed' in verdict['meaning']


# ------------------------------------------------------------------ gate thresholds (preregistered counts)

SIZES = {'dev8': (16, 64, 8), 'dev128': (256, 1024, 128), 'eval64': (128, 512, 64)}  # responses, decisions, per family
STATUS_TOTALS = {'dev8': (18, 4), 'dev128': (292, 186), 'eval64': (190, 116)}  # supported, unknown decisions
# dev8: 90% of 64 decisions, 15/16 valid. dev128: 90% / 80% per family / 95% valid / 90% per status.
# eval64 = EVAL64_설계.md: 461/512, 52/64 per family, 122/128 valid, 90% per status.
BOUNDS = {'dev8': {'decisions': 58, 'final_valid': 15},
          'dev128': {'decisions': 922, 'families': 103, 'final_valid': 244, 'supported': 263, 'unknown': 168},
          'eval64': {'decisions': 461, 'families': 52, 'final_valid': 122, 'supported': 171, 'unknown': 105}}


def summary_at(part, coverage=None, **values):
    """A synthetic summary sitting exactly on every preregistered bound of the stage."""
    responses, decisions, per_family = SIZES[part]
    v = {'families': per_family, 'supported': STATUS_TOTALS[part][0], 'unknown': STATUS_TOTALS[part][1]}
    v |= BOUNDS[part] | values
    families = {f'family_{i}': {'passed': per_family, 'total': per_family} for i in range(7)}
    families['family_7'] = {'passed': v['families'], 'total': per_family}
    status = {k: {'passed': v[k], 'total': t} for k, t in zip(('supported', 'unknown'), STATUS_TOTALS[part])}
    status['no_personal_reaction'] = {'passed': 0, 'total': 10}  # not a gated share
    return {'responses': responses, 'decisions': decisions, 'passed': v['decisions'], 'complete': True,
            'final_valid': v['final_valid'], 'critical': {}, 'by_family': families, 'by_expected_status': status,
            'critical_coverage': coverage or {k: 1 for k in scoring_v2.CRITICAL}}


@pytest.mark.parametrize('part,check', [(p, c) for p in BOUNDS for c in BOUNDS[p]])
def test_gate_passes_exactly_at_the_preregistered_count(part, check):
    bound = BOUNDS[part][check]
    at = run_v2.gate(f'd3_{part}', summary_at(part, **{check: bound}))
    below = run_v2.gate(f'd3_{part}', summary_at(part, **{check: bound - 1}))
    assert at['checks'][check] is True and at['advance'] is True
    assert below['checks'][check] is False and below['advance'] is False


def test_gate_fails_on_any_critical_or_an_incomplete_stage():
    for part in BOUNDS:
        verdict = run_v2.gate(f'd3_{part}', summary_at(part) | {'critical': {'goal_scope_swap': 1}})
        assert verdict['checks']['no_critical'] is False and verdict['advance'] is False
        verdict = run_v2.gate(f'd3_{part}', summary_at(part) | {'complete': False})
        assert verdict['checks']['complete'] is False and verdict['advance'] is False


# ------------------------------------------------------------------ critical types eval64 cannot reveal

def inject(pid, extra):
    """The review repro: an eval64 reference plus one rule under lost_awareness (not from any sentence)."""
    inputs, _, reference, _ = split('eval64')
    personal = next(r for r in inputs if r['id'] == pid)['personal']
    policy = copy.deepcopy(reference[pid])
    policy['rules'].append({'id': 'injected', 'when': [[{'fact': 'lost_awareness', 'op': 'eq', 'value': True}]],
                            'goal_label': None, 'feature': None, 'place_labels': [], 'hold_minutes': None,
                            'supersedes': [], 'evidence': reference[pid]['rules'][0]['evidence']} | extra)
    return m.validate(policy, personal), personal, reference[pid]


def test_eval64_leaves_unrevealable_critical_types_to_a_human(tmp_path, eval_copy):
    for pid, extra, added in (('R_source_certainty_06', {'action': 'avoid', 'feature': 'market'}, 'avoid_market'),
                              ('R_multiple_behaviors_05', {'action': 'wait'}, 'wait')):
        policy, personal, reference = inject(pid, extra)
        assert scoring_v2.critical(policy, personal, reference, pid) == []  # the typed checks cannot see it
        assert not {'withheld_action_injected', 'action_without_reference'} & set(scoring_v2.measurable(reference, pid))
        assert scoring_v2.commands_not_in_reference(policy, personal, reference) == [added]
    assert scoring_v2.measurable(REFERENCE['P22'], 'P22')[-1] == 'withheld_action_injected'  # contrast
    _, summary, verdict = run_v2.score('d3_eval64', tmp_path / 'empty')
    assert summary['critical_coverage'] == {'goal_scope_swap': 38, 'explicit_rest_deleted': 32,
                                            'action_without_reference': 0, 'withheld_action_injected': 0}
    assert verdict['critical_unmeasured'] == ['action_without_reference', 'withheld_action_injected']
    passing = run_v2.gate('d3_eval64', summary_at('eval64', coverage=summary['critical_coverage']))
    assert passing['machine_checks_passed'] is True and passing['advance'] is False
    assert 'withheld_action_injected (no typed WITHHELD list' in passing['human_judgment_required']
    assert 'action_without_reference (every reference has its own rules)' in passing['human_judgment_required']
    assert 'human_judgment_required' not in run_v2.gate('d3_eval64', summary_at('eval64'))


def test_rows_list_commands_the_reference_lacks_for_the_human_judgment(tmp_path):
    """N3.s1 '그건 못 봤어요' turned into a walk: the typed critical checks miss it, the row shows it."""
    personal, out = p16_hard([behavior(['N3.s1'], 'walk', [cl(['lost_awareness'])])])
    _, faithful = p16_hard()
    stage = tmp_path / 'd3_dev128'
    save(stage / 'DEV_P16_hard' / '1' / 'first', out)
    save(stage / 'DEV_P16_hard' / '2' / 'first', faithful)
    rows, summary, _ = run_v2.score('d3_dev128', stage)
    r1, r2 = [r for r in rows if r['input_id'] == 'DEV_P16_hard']
    assert (r1['final_problem'], r1['critical'], r1['commands_not_in_reference']) == (None, [], ['walk'])
    assert r2['commands_not_in_reference'] == [] and r1['critical_measurable'] == ['goal_scope_swap']
    assert summary['responses_with_commands_not_in_reference'] == 1


def test_development_stages_measure_every_critical_type(tmp_path):
    _, dev8, verdict8 = run_v2.score('d3_dev8', tmp_path / 'empty8')
    _, dev128, verdict128 = run_v2.score('d3_dev128', tmp_path / 'empty128')
    assert dev8['critical_coverage'] == {'goal_scope_swap': 2, 'explicit_rest_deleted': 4,
                                         'action_without_reference': 6, 'withheld_action_injected': 4}
    # WITHHELD is keyed by the 10-06 person, so only the original forms of P04/P21/P22/P24 (v1 behavior).
    assert dev128['critical_coverage']['withheld_action_injected'] == 8
    assert verdict8['critical_unmeasured'] == verdict128['critical_unmeasured'] == []
