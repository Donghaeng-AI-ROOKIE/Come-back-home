"""Runner v2: a candidate's first call + at most one validator-feedback correction.

Built from run_candidate.py, which stays unchanged because running stages are
frozen to it by manifest hashes. v2 fixes the runner defects confirmed in
code_review_d3.json (runner lens):

1. Critical checks use scoring_v2 (reference-aware goal_scope_swap).
2. A correction is requested only when a RECEIVED response fails validation.
   An API error or transport failure leaves that call as a recorded failure
   ('no_response'); nothing more is sent for the job (no retry) and the run
   stops before submitting further jobs.
3. Resume: a call marked not submitted was never sent and is submitted on the
   next run. A call that was submitted without a saved result stops the run
   for explicit recovery before anything is sent.
4. <cand>_dev128 runs only if the same candidate's dev8 manifest froze the same
   source hashes (and version, model, sampling), and the dev8 scored.json was
   written by run_v2 from that manifest and advanced. <cand>_eval64 needs the
   same against dev128 plus the human review signature
   dataset/eval64/HUMAN_REVIEW_APPROVED.json.
5. Validator errors keep the field path and cause (pydantic multi-line errors
   included), up to 800 characters, for the correction request and tables.
6. A policy whose scene enumeration exceeds the evaluator cap is recorded as a
   'policy_too_complex' output failure instead of aborting scoring.
7. Trait accounting counts every parseable final response, compiled or not,
   with a 'compiled' flag.
8. Candidates are imported lazily by module name (d4 may not exist yet).
9. --rescore <stage>: read-only re-scoring of saved responses with scoring_v2
   into scored_v2.json; no manifest check, scored.json untouched, no call.
10. <cand>_eval64 stage on dataset/eval64.

Review of run_v2 (2026-10-07):
- A request that cannot leave the machine (CBH_K_BRIDGE_SSH unset, model
  other than transport.MODEL) is refused before the ledger or SSH is touched:
  --execute checks every first call before anything is written, and each call
  is checked again right before transport.invoke and, if refused, marked
  not_submitted so a later run sends it. Any error raised once
  transport.invoke has started stays a submitted failure: transport polls
  through SSH after launching, so its errors cannot prove nothing was sent.
- Gates report how many responses each critical type could be revealed on
  (scoring_v2.measurable). A type the data cannot reveal at all (on eval64:
  withheld_action_injected and action_without_reference) blocks automatic
  advance and is left to a human judgment; commands_not_in_reference lists
  typed candidates for that judgment.
- HUMAN_REVIEW_APPROVED.json needs reviewer, reviewed_on (ISO date) and a
  sha256 map that binds the three eval64 files the runner reads.

Without --execute it freezes the manifest only. Scores are reported for the
first call alone and for the final (corrected) output; gates use the final
output. Synthetic development/evaluation data; not location accuracy.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from math import ceil
from pathlib import Path
from types import FunctionType, ModuleType

from pydantic import ValidationError

from app.llm import usage_ledger
from experiments.mind_contract_ab_20261007 import completion, scoring_v2, transport
from experiments.mind_contract_ab_20261007.run_stage import BACKEND, HERE, digest
from experiments.mind_policy_candidates import note_policy_eval as ev

PACKAGE = 'experiments.mind_contract_ab_20261007'
# Module names only: a candidate is imported when it is used, never at import.
CANDIDATES = {'c': ('contract_c', 'compile_c', 'PLAN_c.md'),
              'd': ('contract_d', 'compile_d', 'PLAN_d.md'),
              'd2': ('contract_d2', 'compile_d2', 'PLAN_d2.md'),
              'd3': ('contract_d3', 'compile_d3', 'PLAN_d3.md'),
              'd4': ('contract_d4', 'compile_d4', 'PLAN_d4.md')}
PARTS = ('dev8', 'dev128', 'eval64')
PREVIOUS = {'dev128': 'dev8', 'eval64': 'dev128'}
DEV8 = ['P05', 'P06', 'P13', 'P14', 'P21', 'P24', 'P25', 'P29']
DEV128 = HERE / 'dataset' / 'dev128'
EVAL64 = HERE / 'dataset' / 'eval64'
APPROVAL = 'HUMAN_REVIEW_APPROVED.json'
EVAL64_FILES = ('eval64_inputs.jsonl', 'eval64_scenes.NOT_MODEL_INPUT.json', 'eval64_reference.NOT_MODEL_INPUT.json')
BRIDGE_ENV = 'CBH_K_BRIDGE_SSH'  # transport's SSH target; without it nothing can be sent
REPS = (1, 2)
CONCURRENCY = 2
ERROR_CHARS = 800
TOO_COMPLEX = 'policy_too_complex'
UNMEASURED_WHY = {'goal_scope_swap': 'no reference seek rule',
                  'explicit_rest_deleted': 'no reference rest rule with a walking limit',
                  'action_without_reference': 'every reference has its own rules',
                  'withheld_action_injected': 'no typed WITHHELD list for these ids'}
COMMON = [HERE / n for n in ('contracts.py', 'completion.py', 'scoring.py', 'scoring_v2.py', 'transport.py',
                             'run_stage.py', 'run_v2.py')] + [
    BACKEND / p for p in ('experiments/mind_policy_candidates/condition_program.py',
                          'experiments/mind_policy_candidates/note_policy_eval.py',
                          'app/llm/mind_policy.py', 'app/llm/initial_behavior.py', 'app/llm/usage_ledger.py')]


# ------------------------------------------------------------------ files

def read(path):
    return json.loads(path.read_text()) if path.exists() else None


def write(path, value):
    """Atomic JSON write, so a concurrent read (e.g. --rescore) never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1) + '\n')
    os.replace(tmp, path)


# ------------------------------------------------------------------ candidates and data

def load_candidate(cand):
    """(module, compile_fn, plan file name), imported on first use."""
    if cand not in CANDIDATES:
        raise SystemExit(f'unknown candidate: {cand}')
    name, compile_name, plan = CANDIDATES[cand]
    try:
        module = importlib.import_module(f'{PACKAGE}.{name}')
    except ModuleNotFoundError as error:
        if error.name != f'{PACKAGE}.{name}':
            raise
        raise SystemExit(f'candidate {cand}: {name}.py not found; nothing built or sent') from None
    compile_fn = getattr(module, compile_name, None)
    if compile_fn is None:
        raise SystemExit(f'candidate {cand}: {name}.{compile_name} is missing; nothing built or sent')
    return module, compile_fn, plan


def _local_dependencies(module):
    """Files of the experiment-package modules a candidate uses, transitively."""
    found, todo, seen = [], [module], {module.__name__}
    while todo:
        for value in vars(todo.pop()).values():
            if isinstance(value, ModuleType):
                name = value.__name__
            elif isinstance(value, (type, FunctionType)):
                name = getattr(value, '__module__', None)
            else:
                continue
            if isinstance(name, str) and name.startswith(PACKAGE + '.') and name not in seen:
                seen.add(name)
                dep = sys.modules.get(name) or importlib.import_module(name)
                found.append(Path(dep.__file__))
                todo.append(dep)
    return found


def sources(cand):
    module, _, plan = load_candidate(cand)
    out = []
    for p in [HERE / plan, Path(module.__file__)] + sorted(_local_dependencies(module)) + COMMON:
        p = Path(p).resolve()
        if p not in out:
            out.append(p)
    missing = [str(p.relative_to(BACKEND)) for p in out if not p.exists()]
    if missing:
        raise SystemExit('source file missing (write and freeze it before running): ' + ', '.join(missing))
    return out


def source_sha256(cand):
    return {str(p.relative_to(BACKEND)): digest(p) for p in sources(cand)}


def _split(folder, part):
    inputs = [json.loads(x) for x in (folder / f'{part}_inputs.jsonl').read_text().splitlines() if x.strip()]
    rows = json.loads((folder / f'{part}_scenes.NOT_MODEL_INPUT.json').read_text())
    family = {r['input_id']: r['family'] for r in rows}
    for r in inputs:
        if r.get('family', family[r['id']]) != family[r['id']]:
            raise ValueError('family differs between inputs and scenes: ' + r['id'])
        r['family'] = family[r['id']]
    reference = json.loads((folder / f'{part}_reference.NOT_MODEL_INPUT.json').read_text())
    files = [folder / n for n in (f'{part}_inputs.jsonl', f'{part}_scenes.NOT_MODEL_INPUT.json',
                                  f'{part}_reference.NOT_MODEL_INPUT.json')]
    return inputs, rows, reference, files


def dataset(stage):
    """(inputs, scenes, reference, data files). Only inputs[i]['personal'] reaches the model."""
    part = stage.split('_', 1)[1]
    if part == 'dev8':
        people, scenes, reference = scoring_v2.load()
        inputs = [{'id': p, 'root_id': p, 'form': 'original', 'personal': people[p]['personal'],
                   'family': people[p]['family']} for p in DEV8]
        rows = [dict(s, input_id=s['person_id']) for s in scenes if s['person_id'] in DEV8]
        files = [scoring_v2.ROOT / n for n in ('profiles.json', 'scenes.json', 'reference_policies.NOT_MODEL_INPUT.json')]
        return inputs, rows, {p: reference[p] for p in DEV8}, files
    if part == 'dev128':
        return _split(DEV128, 'dev128')
    if part == 'eval64':
        return _split(EVAL64, 'eval64')
    raise ValueError(stage)


def jobs_for(stage, module, inputs):
    return [{'job': f'{stage}_{r["id"]}_{rep}', 'input': r, 'rep': rep,
             'body': module.request(r['personal'], transport.MODEL)} for r in inputs for rep in REPS]


# ------------------------------------------------------------------ judging

def describe(error):
    """(text, kind) of a rejection. Keeps every field path and cause, <= 800 chars."""
    if isinstance(error, ValidationError):
        items = error.errors(include_url=False)
        text = str(error).splitlines()[0] + ': ' + '; '.join(
            f"{'.'.join(str(x) for x in e.get('loc', ())) or '(root)'}: {e.get('msg')}" for e in items)
        first = items[0] if items else {}
        kind = ':'.join(['validation', error.title,
                         '.'.join(str(x) for x in first.get('loc', ()) if not isinstance(x, int)) or '(root)',
                         str(first.get('type', ''))])
    else:
        text = ' | '.join(x.strip() for x in str(error).splitlines() if x.strip())
        if not isinstance(error, ValueError) or not text:
            text = type(error).__name__ + (': ' + text if text else '')
        kind = text.split(':', 1)[0].split('(', 1)[0].strip()[:80]
    return text[:ERROR_CHARS], kind


def judge(public, personal, compile_fn):
    """(problem, kind, policy) of a received response; problem None means valid."""
    status, value = completion.classify(public)
    if status != 'complete_json':
        return status, status, None
    try:
        return None, None, compile_fn(value, personal)
    except Exception as error:  # noqa: BLE001 - recorded and fed back, never repaired
        text, kind = describe(error)
        return text, kind, None


def decide_all(policy, personal, scenes):
    """(decisions, error). The evaluator's enumeration cap is an output failure, not a crash."""
    if policy is None:
        return [None] * len(scenes), None
    try:
        return [ev.decide(policy, personal, s['scene']) for s in scenes], None
    except ValueError as error:
        if 'too many unresolved' not in str(error):
            raise
        return [None] * len(scenes), str(error)


def traits(module, public, compiled):
    """Trait accounting of any parseable response; compiled tells whether it also compiled."""
    if not hasattr(module, 'trait_accounting') or not public:
        return None
    status, value = completion.classify(public)
    if status != 'complete_json':
        return None
    try:
        return dict(module.trait_accounting(value), compiled=compiled)
    except Exception as error:  # noqa: BLE001 - an unreadable shape is reported, not guessed
        return {'compiled': compiled, 'unreadable': describe(error)[0]}


# ------------------------------------------------------------------ call folders

def _never_sent(result):
    return result.get('submitted') is False or str(result.get('error_type') or '').startswith('CallBudgetExceeded')


def call_state(folder):
    """done | not_submitted | pending | submitted_without_result."""
    try:
        result = read(folder / 'result.json')
    except ValueError:  # being written by a runner without atomic writes: not a usable result yet
        return 'submitted_without_result'
    if result is not None and not _never_sent(result):
        return 'done'
    if result is not None or (folder / 'not_submitted.json').exists():
        return 'not_submitted'
    if (folder / 'request.json').exists():
        return 'submitted_without_result'
    return 'pending'


def _archive_unsent(folder):
    """Move markers of a never-sent attempt aside so a crash during resubmission is an orphan."""
    names = [n for n in ('not_submitted.json', 'result.json', 'request.json') if (folder / n).exists()]
    if not names:
        return
    k = 1
    while (folder / 'unsent' / str(k)).exists():
        k += 1
    target = folder / 'unsent' / str(k)
    target.mkdir(parents=True)
    for n in names:
        os.replace(folder / n, target / n)


def outcome(folder, personal, compile_fn):
    state = call_state(folder)
    out = {'state': state, 'public': None, 'problem': None, 'kind': None, 'policy': None, 'error': None}
    if state != 'done':
        problem = 'submitted_without_result' if state == 'submitted_without_result' else 'not_submitted'
        return out | {'problem': problem, 'kind': problem}
    public = read(folder / 'response.public.json')
    if public is None:
        return out | {'problem': 'no_response', 'kind': 'no_response',
                      'error': read(folder / 'result.json').get('error_type')}
    problem, kind, policy = judge(public, personal, compile_fn)
    return out | {'public': public, 'problem': problem, 'kind': kind, 'policy': policy}


# ------------------------------------------------------------------ scoring

def score_response(module, compile_fn, folder, r, mine, reference, key):
    first = outcome(folder / 'first', r['personal'], compile_fn)
    received = first['public'] is not None
    needs_fix = received and first['problem'] is not None
    fix_state = call_state(folder / 'fix')
    final = first
    if needs_fix and fix_state == 'done':
        final = outcome(folder / 'fix', r['personal'], compile_fn)
    first_decisions, first_error = decide_all(first['policy'], r['personal'], mine)
    if final is first:
        final_decisions, final_error = first_decisions, first_error
    else:
        final_decisions, final_error = decide_all(final['policy'], r['personal'], mine)
    first_problem, first_kind = (TOO_COMPLEX, TOO_COMPLEX) if first_error else (first['problem'], first['kind'])
    final_problem, final_kind = (TOO_COMPLEX, TOO_COMPLEX) if final_error else (final['problem'], final['kind'])
    final_policy = final['policy'] if final_problem is None else None
    row = {'input_id': r['id'], 'root_id': r['root_id'], 'form': r.get('form'), 'family': r['family'],
           'rep': None, 'complete': first['state'] == 'done' and (not needs_fix or fix_state == 'done'),
           'first_state': first['state'], 'fix_state': fix_state,
           'first_problem': first_problem, 'first_problem_kind': first_kind,
           'final_problem': final_problem, 'final_problem_kind': final_kind,
           'correction_needed': needs_fix, 'corrected': needs_fix and fix_state == 'done',
           'transport_error': first['error'] or final['error'],
           # A correction sent after an API failure (run_candidate defect) is not scored.
           'ignored_fix_after_no_response': not received and fix_state == 'done',
           'decision_error': final_error, 'scenes': []}
    for s, d1, d2 in zip(mine, first_decisions, final_decisions):
        row['scenes'].append({'id': s['id'], 'expected': s['expected_commands'],
                              'expected_status': s['expected_status'],
                              'first_pass': scoring_v2.scene_pass(d1, s), 'pass': scoring_v2.scene_pass(d2, s),
                              'decision': d2})
    row['critical'] = scoring_v2.critical(final_policy, r['personal'], reference[r['id']], key)
    row['critical_measurable'] = scoring_v2.measurable(reference[r['id']], key)
    row['commands_not_in_reference'] = scoring_v2.commands_not_in_reference(final_policy, r['personal'],
                                                                            reference[r['id']])
    row['traits'] = traits(module, final['public'], compiled=final['policy'] is not None)
    row['policy'] = final_policy.model_dump() if final_policy else None
    return row


def summarize(module, rows):
    decisions = [s | {'family': r['family'], 'form': r['form']} for r in rows for s in r['scenes']]

    def by(key):
        return {k: {'passed': sum(d['pass'] for d in decisions if str(d[key]) == k),
                    'total': sum(str(d[key]) == k for d in decisions)} for k in sorted({str(d[key]) for d in decisions})}

    def count(field):
        out = {}
        for r in rows:
            for k in ('first', 'final'):
                if r[f'{k}_{field}']:
                    bucket = out.setdefault(f'{k}_problem', {})
                    bucket[r[f'{k}_{field}']] = bucket.get(r[f'{k}_{field}'], 0) + 1
        return out

    critical = {}
    for r in rows:
        for c in r['critical']:
            critical[c] = critical.get(c, 0) + 1
    policies = {}
    for r in rows:
        policies.setdefault(r['input_id'], []).append(json.dumps(r['policy'] and r['policy']['rules'], sort_keys=True))
    counted = [r['traits'] for r in rows if r['traits'] and 'by_kind' in r['traits']]

    def loss(items):
        return {'responses_with_trait_loss': sum(bool(t.get('trait_loss_sentence_ids')) for t in items),
                'trait_loss_sentences': sum(len(t.get('trait_loss_sentence_ids', [])) for t in items)}

    return {'responses': len(rows), 'decisions': len(decisions),
            'complete': all(r['complete'] for r in rows),
            'incomplete_responses': [f"{r['input_id']}_{r['rep']}" for r in rows if not r['complete']],
            'first_pass_passed': sum(d['first_pass'] for d in decisions),
            'passed': sum(d['pass'] for d in decisions),
            'first_valid': sum(r['first_problem'] is None for r in rows),
            'final_valid': sum(r['final_problem'] is None for r in rows),
            'corrections': sum(r['corrected'] for r in rows),
            'no_response': sum(r['final_problem'] == 'no_response' for r in rows),
            'not_submitted': sum(r['first_state'] in ('pending', 'not_submitted') for r in rows),
            'policy_too_complex': sum(r['final_problem'] == TOO_COMPLEX for r in rows),
            'ignored_fix_after_no_response': sum(r['ignored_fix_after_no_response'] for r in rows),
            'problems': count('problem'), 'problem_kinds': count('problem_kind'), 'critical': critical,
            # Responses on which each critical type could be revealed at all (not how many passed).
            'critical_coverage': {k: sum(k in r['critical_measurable'] for r in rows) for k in scoring_v2.CRITICAL},
            'responses_with_commands_not_in_reference': sum(bool(r['commands_not_in_reference']) for r in rows),
            'by_family': by('family'), 'by_form': by('form'), 'by_expected_status': by('expected_status'),
            'by_input': {i: {'passed': sum(s['pass'] for r in rows if r['input_id'] == i for s in r['scenes']),
                             'total': sum(len(r['scenes']) for r in rows if r['input_id'] == i)}
                         for i in sorted({r['input_id'] for r in rows})},
            'trait_accounting': {
                'responses_counted': len(counted),
                'responses_counted_compiled': sum(t['compiled'] for t in counted),
                'responses_counted_rejected': sum(not t['compiled'] for t in counted),
                'responses_unreadable': sum(bool(r['traits']) and 'unreadable' in r['traits'] for r in rows),
                'by_kind': {k: sum(t.get('by_kind', {}).get(k, 0) for t in counted) for k in getattr(module, 'KINDS', ())},
                **loss(counted),
                'rejected': loss([t for t in counted if not t['compiled']]),
                'note': 'not_representable = guardian-observed trait the engine cannot express (trait loss); '
                        'counted for every parseable final response, compiled or rejected'},
            'repeat_identical_policy': sum(len(set(v)) == 1 and v[0] != 'null' for v in policies.values()),
            'inputs': len(policies)}


def gate(stage, summary):
    part = stage.split('_', 1)[1]
    total = summary['decisions']
    checks = {'complete': summary['complete'], 'decisions': summary['passed'] >= ceil(.9 * total)}
    if part == 'dev8':
        checks.update(final_valid=summary['final_valid'] >= 15, no_critical=not summary['critical'])
    else:
        status = summary['by_expected_status']

        def share(name):
            v = status.get(name, {'passed': 0, 'total': 0})
            return v['passed'] >= ceil(.9 * v['total'])
        checks.update(families=all(v['passed'] >= ceil(.8 * v['total']) for v in summary['by_family'].values()),
                      supported=share('supported'), unknown=share('unknown'),
                      final_valid=summary['final_valid'] >= ceil(.95 * summary['responses']),
                      no_critical=not summary['critical'])
    meaning = {'dev8': 'synthetic development data; not location accuracy or clinical validity',
               'dev128': 'synthetic development data; not location accuracy or clinical validity',
               'eval64': 'research-based evaluation personas, human-reviewed per HUMAN_REVIEW_APPROVED.json; '
                         'synthetic behavior agreement, not location accuracy or clinical validity'}[part]
    coverage = summary['critical_coverage']
    # no_critical says nothing about a type this data cannot reveal; a human judges it instead.
    unmeasured = [k for k in scoring_v2.CRITICAL if not coverage.get(k)]
    verdict = {'checks': checks, 'machine_checks_passed': all(checks.values()),
               'advance': all(checks.values()) and not unmeasured, 'meaning': meaning,
               'critical_coverage': coverage, 'critical_unmeasured': unmeasured}
    if unmeasured:
        verdict['human_judgment_required'] = (
            'no_critical covers only the measured types. Not revealable by the typed checks on this data: '
            + '; '.join(f'{k} ({UNMEASURED_WHY[k]})' for k in unmeasured)
            + '. advance stays False until a human judges them; rows list commands_not_in_reference '
              'as typed candidates.')
    return verdict


def score(stage, out):
    module, compile_fn, _ = load_candidate(stage.split('_')[0])
    inputs, scenes, reference, _ = dataset(stage)
    rows = []
    for r in inputs:
        mine = [s for s in scenes if s['input_id'] == r['id']]
        key = r['root_id'] if r.get('form') == 'original' else r['id']
        for rep in REPS:
            row = score_response(module, compile_fn, out / r['id'] / str(rep), r, mine, reference, key)
            row['rep'] = rep
            rows.append(row)
    summary = summarize(module, rows)
    return rows, summary, gate(stage, summary)


# ------------------------------------------------------------------ entry gates

def require_human_review():
    """sha256 of the human review signature; refuses without it, if malformed, or if it binds other data.

    Format: {"reviewer": "<who reviewed>", "reviewed_on": "YYYY-MM-DD",
             "sha256": {"eval64_inputs.jsonl": ..., "eval64_scenes.NOT_MODEL_INPUT.json": ...,
                        "eval64_reference.NOT_MODEL_INPUT.json": ..., <optional further eval64 files>}}
    Every listed file must match; the three files the runner reads must be listed.
    """
    path = EVAL64 / APPROVAL
    if not path.exists():
        raise SystemExit(f'{APPROVAL} (human review signature) is missing; eval64 is not run')
    try:
        value = json.loads(path.read_text())
    except ValueError:
        raise SystemExit(f'{APPROVAL} is not valid JSON; eval64 is not run') from None
    if not isinstance(value, dict):
        raise SystemExit(f'{APPROVAL} must be a JSON object; eval64 is not run')
    reviewer, reviewed_on, bound = value.get('reviewer'), value.get('reviewed_on'), value.get('sha256')
    problems = []
    if not isinstance(reviewer, str) or not reviewer.strip():
        problems.append('reviewer (non-empty string)')
    try:
        date.fromisoformat(reviewed_on)
    except (TypeError, ValueError):
        problems.append('reviewed_on (YYYY-MM-DD)')
    if not isinstance(bound, dict) or not all(isinstance(bound.get(n), str) for n in EVAL64_FILES):
        problems.append('sha256 map with ' + ', '.join(EVAL64_FILES))
    if problems:
        raise SystemExit(f'{APPROVAL} needs ' + '; '.join(problems) + '; eval64 is not run')
    changed = [n for n, h in bound.items()
               if Path(n).name != n or not (EVAL64 / n).is_file() or digest(EVAL64 / n) != h]
    if changed:
        raise SystemExit('eval64 files differ from the human-reviewed version: ' + ', '.join(changed))
    return digest(path)


def entry_gate(run_dir, stage, identity):
    """dev128/eval64 run only on the code the previous stage was gated with, and only if it advanced."""
    cand, part = stage.split('_', 1)
    previous = PREVIOUS.get(part)
    if previous is None:
        return
    name = f'{cand}_{previous}'
    path = run_dir / name / 'manifest.json'
    manifest, scored = read(path), read(run_dir / name / 'scored.json')
    if manifest is None or scored is None:
        raise SystemExit(f'{name} has no frozen manifest or scored result; {stage} is not run')
    if scored.get('manifest_sha256') != digest(path):
        raise SystemExit(f'{name}/scored.json was not written by run_v2 from its frozen manifest; {stage} is not run')
    old, new = manifest.get('source_sha256', {}), identity['source_sha256']
    changed = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
    changed += [k for k in ('version', 'model', 'sampling') if manifest.get(k) != identity[k]]
    if changed:
        raise SystemExit(f'{stage} refused: code differs from the code {name} was gated with: ' + ', '.join(changed))
    if not (scored.get('gate') or {}).get('advance'):
        raise SystemExit(f'{name} did not advance; {stage} is not run')


# ------------------------------------------------------------------ execution

def unsendable(body):
    """Why this request cannot leave the machine (None if it can); checked before the ledger or SSH."""
    if not os.environ.get(BRIDGE_ENV):
        return f'{BRIDGE_ENV} is not set'
    if body.get('model') != transport.MODEL:
        return f"model {body.get('model')!r} is not transport.MODEL {transport.MODEL!r}"
    return None


def execute(stage, out, jobs, module, compile_fn, ledger, max_calls):
    """Submit pending calls; returns True when the run stopped early."""
    run_id = 'MIND_contract_ab_20261007_' + stage
    orphans = [job for j in jobs for job, folder in ((j['job'], out / j['input']['id'] / str(j['rep']) / 'first'),
                                                     (j['job'] + '_fix', out / j['input']['id'] / str(j['rep']) / 'fix'))
               if call_state(folder) == 'submitted_without_result']
    if orphans:
        raise SystemExit('submitted without result, recover explicitly: ' + ', '.join(orphans))
    stop = threading.Event()

    def log(value):
        print(json.dumps(value, ensure_ascii=False), flush=True)

    def call(body, job, folder):
        state = call_state(folder)
        if state == 'done':
            return read(folder / 'response.public.json')  # None: a recorded failure, never resent
        if state == 'submitted_without_result':
            raise SystemExit('submitted without result, recover explicitly: ' + job)
        if stop.is_set():
            write(folder / 'not_submitted.json', {'job': job, 'submitted': False,
                                                  'reason': 'run stopped before submission'})
            return None
        reason = unsendable(body)
        if reason:  # nothing reached the ledger or SSH: a later run sends it
            stop.set()
            write(folder / 'not_submitted.json', {'job': job, 'submitted': False, 'reason': 'unsendable:' + reason})
            log({'job': job, 'submitted': False, 'error_type': 'unsendable:' + reason})
            return None
        _archive_unsent(folder)
        write(folder / 'request.json', body)
        try:
            response = transport.invoke(body, job, run_id=run_id, role='mind_contract_' + stage,
                                        ledger_path=ledger, max_started=max_calls)
            public = transport.public(response)
        except usage_ledger.CallBudgetExceeded as error:  # refused by the ledger before any submission
            stop.set()
            write(folder / 'not_submitted.json', {'job': job, 'submitted': False,
                                                  'reason': 'CallBudgetExceeded:' + str(error)[:300]})
            log({'job': job, 'submitted': False, 'error_type': 'CallBudgetExceeded'})
            return None
        except Exception as error:  # noqa: BLE001 - recorded, never retried; the run stops
            # Submitted on purpose: transport launches first and then polls through SSH, so an
            # error raised inside invoke (even one saying 'no request submitted') may follow a launch.
            stop.set()
            result = {'job': job, 'submitted': True, 'response_saved': False,
                      'error_type': type(error).__name__ + ':' + str(error)[:300]}
            write(folder / 'result.json', result)
            log(result)
            return None
        write(folder / 'response.public.json', public)
        result = {'job': job, 'submitted': True, 'response_saved': True, 'error_type': None}
        write(folder / 'result.json', result)
        log(result)
        return public

    def one(j):
        try:
            f = out / j['input']['id'] / str(j['rep'])
            first = call(j['body'], j['job'], f / 'first')
            if first is None:
                return  # no response received: nothing to correct, no retry
            problem, _, _ = judge(first, j['input']['personal'], compile_fn)
            if problem is None:
                return
            write(f / 'first' / 'problem.json', {'problem': problem})
            call(module.correction(j['body'], first, problem), j['job'] + '_fix', f / 'fix')
        except BaseException:
            stop.set()
            raise

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        list(pool.map(one, jobs))
    return stop.is_set()


def rescore(stage, run_dir):
    out = run_dir / stage
    if not out.is_dir():
        raise SystemExit(f'no saved stage folder: {out}')
    rows, summary, verdict = score(stage, out)
    write(out / 'scored_v2.json', {
        'rescored_with': 'scoring_v2', 'runner': 'run_v2', 'stage': stage, 'manifest_checked': False,
        'note': 'offline re-scoring of saved responses; no model call; scored.json and responses unchanged',
        'rows': rows, 'summary': summary, 'gate': verdict})
    print(json.dumps({'rescored_with': 'scoring_v2', 'summary': {k: v for k, v in summary.items() if k != 'by_input'},
                      'gate': verdict}, ensure_ascii=False, indent=1))


def main(argv=None):
    stages = [f'{c}_{p}' for c in CANDIDATES for p in PARTS]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--stage', choices=stages)
    parser.add_argument('--rescore', choices=stages, metavar='STAGE',
                        help='re-score saved responses of STAGE with scoring_v2 into scored_v2.json (read-only)')
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--ledger', type=Path)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--score-only', action='store_true')
    args = parser.parse_args(argv)
    if args.rescore:
        if args.stage or args.execute or args.score_only:
            parser.error('--rescore runs alone')
        return rescore(args.rescore, args.run_dir)
    if not args.stage:
        parser.error('--stage or --rescore is required')
    if args.execute and not args.ledger:
        parser.error('--execute needs --ledger')
    stage = args.stage
    cand, part = stage.split('_', 1)
    module, compile_fn, _ = load_candidate(cand)
    review = require_human_review() if part == 'eval64' else None
    identity = {'version': module.VERSION, 'model': transport.MODEL, 'sampling': module.SAMPLING,
                'source_sha256': source_sha256(cand)}
    entry_gate(args.run_dir, stage, identity)
    inputs, _, _, files = dataset(stage)
    jobs = jobs_for(stage, module, inputs)
    out = args.run_dir / stage
    manifest = {'stage': stage, 'runner': 'run_v2', 'scoring': scoring_v2.VERSION, **identity,
                'correction_rounds_max': 1,
                'correction_policy': 'only when a received response fails validation; none after an API error',
                'judge_error_chars': ERROR_CHARS,
                'data_sha256': {p.name: digest(p) for p in files},
                'jobs': [{'job': j['job'], 'request_sha256': hashlib.sha256(json.dumps(
                    j['body'], ensure_ascii=False, sort_keys=True).encode()).hexdigest()} for j in jobs],
                'first_calls': len(jobs), 'max_calls': 2 * len(jobs), 'automatic_retries': False,
                'concurrency': CONCURRENCY}
    if review is not None:
        manifest['human_review_sha256'] = review
        # Recorded, not enforced: whether rows must also be re-marked after review is the user's call.
        manifest['rows_marked_draft_unreviewed'] = sum(r.get('review_status') == 'draft_unreviewed' for r in inputs)
    path = out / 'manifest.json'
    if path.exists():
        if read(path) != manifest:
            raise SystemExit('frozen manifest differs: code, data or request changed')
    else:
        write(path, manifest)
        for source in sources(cand):
            target = out / 'source_snapshot' / source.relative_to(BACKEND)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    print(json.dumps({'stage': stage, 'first_calls': len(jobs), 'max_calls': 2 * len(jobs)}))
    stopped = False
    if args.execute:
        approval = read(args.run_dir / 'authorization.json') or {}
        limit = approval.get('stages', {}).get(stage)
        if approval.get('status') != 'approved' or not limit or limit['max_calls'] < 2 * len(jobs):
            raise SystemExit('stage not authorized')
        blocked = sorted({unsendable(j['body']) for j in jobs} - {None})
        if blocked:
            raise SystemExit('nothing sent or marked: ' + '; '.join(blocked))
        out.mkdir(parents=True, exist_ok=True)
        with (out / 'runner.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            stopped = execute(stage, out, jobs, module, compile_fn, args.ledger, limit['max_calls'])
    if args.execute or args.score_only:
        rows, summary, verdict = score(stage, out)
        write(out / 'scored.json', {'scored_with': 'scoring_v2', 'runner': 'run_v2', 'manifest_sha256': digest(path),
                                    'rows': rows, 'summary': summary, 'gate': verdict})
        print(json.dumps({'summary': {k: v for k, v in summary.items() if k != 'by_input'}, 'gate': verdict},
                         ensure_ascii=False, indent=1))
    if stopped:
        raise SystemExit(f'{stage} stopped after a failed or refused call; scored.json marks it incomplete. '
                         'Rerun to submit the calls marked not_submitted; failed calls are not resent.')


if __name__ == '__main__':
    main()
