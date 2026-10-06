"""Run a candidate module (first call + at most one validator-feedback correction).

Candidates: c (contract_c), d (contract_d), d2 (contract_d2; adds per-response
trait accounting). Stages: <cand>_dev8 (the eight dev8
profiles), <cand>_dev128 (dataset/dev128). Without
--execute it freezes the manifest only. Every call goes to the ledger; a job
submitted without a saved result stops the run for explicit recovery. Scores
are reported both for the first call alone and for the final (corrected)
output; the gate uses the final output, as pre-registered in the candidate PLAN file.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from math import ceil
from pathlib import Path

from experiments.mind_contract_ab_20261007 import completion, contract_c, contract_d, contract_d2, contract_d3, scoring, transport
from app.llm.initial_behavior import decode_json_content
from experiments.mind_contract_ab_20261007.run_stage import BACKEND, HERE, digest, write
from experiments.mind_policy_candidates import note_policy_eval as ev

CANDIDATES = {'c': (contract_c, contract_c.compile_c, 'PLAN_c.md'), 'd': (contract_d, contract_d.compile_d, 'PLAN_d.md'),
              'd2': (contract_d2, contract_d2.compile_d2, 'PLAN_d2.md'),
              'd3': (contract_d3, contract_d3.compile_d3, 'PLAN_d3.md')}
COMMON = [HERE / n for n in ('contract_c.py', 'contracts.py', 'completion.py', 'scoring.py',
                             'transport.py', 'run_candidate.py')] + [
    BACKEND / p for p in ('experiments/mind_policy_candidates/condition_program.py',
                          'experiments/mind_policy_candidates/note_policy_eval.py',
                          'app/llm/mind_policy.py', 'app/llm/initial_behavior.py', 'app/llm/usage_ledger.py')]
DEV8 = ['P05', 'P06', 'P13', 'P14', 'P21', 'P24', 'P25', 'P29']


def sources(cand):
    module, _, plan = CANDIDATES[cand]
    extra = {'d2': [HERE / 'contract_d.py'], 'd3': [HERE / 'contract_d.py', HERE / 'contract_d2.py']}.get(cand, [])
    return [HERE / plan, Path(module.__file__)] + extra + [p for p in COMMON if p != Path(module.__file__)]


def traits(module, public):
    """Unit counts by kind for candidates that report them; None otherwise."""
    if not hasattr(module, 'trait_accounting') or not public:
        return None
    if completion.classify(public)[0] != 'complete_json':
        return None
    return module.trait_accounting(decode_json_content(public['final_content']))


def dataset(stage):
    stage = stage.split('_', 1)[1]
    if stage == 'dev8':
        people, scenes, reference = scoring.load()
        inputs = [{'id': p, 'root_id': p, 'form': 'original', 'personal': people[p]['personal'],
                   'family': people[p]['family']} for p in DEV8]
        rows = [dict(s, input_id=s['person_id']) for s in scenes if s['person_id'] in DEV8]
        files = [scoring.ROOT / n for n in ('profiles.json', 'scenes.json', 'reference_policies.NOT_MODEL_INPUT.json')]
        return inputs, rows, {p: reference[p] for p in DEV8}, files
    if stage == 'dev128':
        d = HERE / 'dataset' / 'dev128'
        inputs = [json.loads(x) for x in (d / 'dev128_inputs.jsonl').read_text().splitlines() if x.strip()]
        rows = json.loads((d / 'dev128_scenes.NOT_MODEL_INPUT.json').read_text())
        family = {r['input_id']: r['family'] for r in rows}
        for r in inputs:
            r['family'] = family[r['id']]
        reference = json.loads((d / 'dev128_reference.NOT_MODEL_INPUT.json').read_text())
        files = [d / n for n in ('dev128_inputs.jsonl', 'dev128_scenes.NOT_MODEL_INPUT.json',
                                 'dev128_reference.NOT_MODEL_INPUT.json')]
        return inputs, rows, reference, files
    raise ValueError(stage)


def jobs_for(stage):
    inputs, _, _, _ = dataset(stage)
    module = CANDIDATES[stage.split('_')[0]][0]
    return [{'job': f'{stage}_{r["id"]}_{rep}', 'input': r, 'rep': rep,
             'body': module.request(r['personal'], transport.MODEL)} for r in inputs for rep in (1, 2)]


def judge(public, personal, compile_fn):
    """(problem or None, policy). problem is a completion class or compile error."""
    status, value = completion.classify(public or {'finish_reason': None, 'final_content': None})
    if status != 'complete_json':
        return status, None
    try:
        return None, compile_fn(value, personal)
    except Exception as error:  # noqa: BLE001 - recorded and fed back, never repaired
        return str(error).splitlines()[0][:200], None


def read(path):
    return json.loads(path.read_text()) if path.exists() else None


def score(stage, out):
    module, compile_fn, _ = CANDIDATES[stage.split('_')[0]]
    inputs, scenes, reference, _ = dataset(stage)
    rows = []
    for j in jobs_for(stage):
        r = j['input']
        f = out / r['id'] / str(j['rep'])
        first_problem, first_policy = judge(read(f / 'first' / 'response.public.json'), r['personal'], compile_fn)
        final_problem, final_policy = first_problem, first_policy
        final_public = read(f / 'first' / 'response.public.json')
        if first_problem is not None:
            final_public = read(f / 'fix' / 'response.public.json')
            final_problem, final_policy = judge(final_public, r['personal'], compile_fn)
        key = r['root_id'] if r.get('form') == 'original' else r['id']
        mine = [s for s in scenes if s['input_id'] == r['id']]
        row = {'input_id': r['id'], 'root_id': r['root_id'], 'form': r.get('form'), 'family': r['family'],
               'rep': j['rep'], 'first_problem': first_problem, 'final_problem': final_problem,
               'corrected': first_problem is not None, 'scenes': []}
        for s in mine:
            d1 = ev.decide(first_policy, r['personal'], s['scene']) if first_policy else None
            d2 = ev.decide(final_policy, r['personal'], s['scene']) if final_policy else None
            row['scenes'].append({'id': s['id'], 'expected': s['expected_commands'],
                                  'expected_status': s['expected_status'],
                                  'first_pass': scoring.scene_pass(d1, s), 'pass': scoring.scene_pass(d2, s),
                                  'decision': d2})
        row['critical'] = scoring.critical(final_policy, r['personal'], reference[r['id']], key)
        row['traits'] = traits(module, final_public) if final_problem is None else None
        row['policy'] = final_policy.model_dump() if final_policy else None
        rows.append(row)
    decisions = [s | {'family': r['family'], 'form': r['form']} for r in rows for s in r['scenes']]

    def by(key):
        return {k: {'passed': sum(d['pass'] for d in decisions if d[key] == k),
                    'total': sum(d[key] == k for d in decisions)} for k in sorted({str(d[key]) for d in decisions})}

    critical = {}
    for r in rows:
        for c in r['critical']:
            critical[c] = critical.get(c, 0) + 1
    problems = {}
    for r in rows:
        for k in ('first_problem', 'final_problem'):
            if r[k]:
                problems.setdefault(k, {}).setdefault(r[k], 0)
                problems[k][r[k]] += 1
    policies = {}
    for r in rows:
        policies.setdefault(r['input_id'], []).append(json.dumps(r['policy'] and r['policy']['rules'], sort_keys=True))
    summary = {'responses': len(rows), 'decisions': len(decisions),
               'first_pass_passed': sum(d['first_pass'] for d in decisions),
               'passed': sum(d['pass'] for d in decisions),
               'first_valid': sum(r['first_problem'] is None for r in rows),
               'final_valid': sum(r['final_problem'] is None for r in rows),
               'corrections': sum(r['corrected'] for r in rows), 'problems': problems, 'critical': critical,
               'by_family': by('family'), 'by_form': by('form'), 'by_expected_status': by('expected_status'),
               'by_input': {i: {'passed': sum(s['pass'] for r in rows if r['input_id'] == i for s in r['scenes']),
                                'total': sum(len(r['scenes']) for r in rows if r['input_id'] == i)}
                            for i in sorted({r['input_id'] for r in rows})},
               'trait_accounting': {
                   'responses_counted': sum(r['traits'] is not None for r in rows),
                   'by_kind': {k: sum((r['traits'] or {}).get('by_kind', {}).get(k, 0) for r in rows)
                               for k in getattr(module, 'KINDS', ())},
                   'responses_with_trait_loss': sum(bool((r['traits'] or {}).get('trait_loss_sentence_ids'))
                                                    for r in rows),
                   'trait_loss_sentences': sum(len((r['traits'] or {}).get('trait_loss_sentence_ids', []))
                                               for r in rows),
                   'note': 'not_representable = guardian-observed trait the engine cannot express (trait loss)'},
               'repeat_identical_policy': sum(len(set(v)) == 1 and v[0] != 'null' for v in policies.values()),
               'inputs': len(policies)}
    total = summary['decisions']
    if stage.endswith('_dev8'):
        checks = {'decisions': summary['passed'] >= ceil(.9 * total),
                  'final_valid': summary['final_valid'] >= 15, 'no_critical': not critical}
    else:
        status = summary['by_expected_status']
        checks = {'decisions': summary['passed'] >= ceil(.9 * total),
                  'families': all(v['passed'] >= ceil(.8 * v['total']) for v in summary['by_family'].values()),
                  'supported': status['supported']['passed'] >= ceil(.9 * status['supported']['total']),
                  'unknown': status['unknown']['passed'] >= ceil(.9 * status['unknown']['total']),
                  'final_valid': summary['final_valid'] >= ceil(.95 * summary['responses']),
                  'no_critical': not critical}
    return rows, summary, {'checks': checks, 'advance': all(checks.values()),
                           'meaning': 'synthetic development data; not location accuracy or clinical validity'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', required=True, choices=[f'{c}_{s}' for c in CANDIDATES for s in ('dev8', 'dev128')])
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--score-only', action='store_true')
    args = parser.parse_args()
    stage, run_id = args.stage, 'MIND_contract_ab_20261007_' + args.stage
    out = args.run_dir / stage
    cand = stage.split('_')[0]
    module, compile_fn, _ = CANDIDATES[cand]
    if stage.endswith('_dev128'):
        gate = read(args.run_dir / f'{cand}_dev8' / 'scored.json')
        if not gate or not gate['gate']['advance']:
            raise SystemExit(f'{cand}_dev8 did not advance; {stage} is not run')
    jobs = jobs_for(stage)
    _, _, _, files = dataset(stage)
    manifest = {'stage': stage, 'version': module.VERSION, 'model': transport.MODEL,
                'sampling': module.SAMPLING, 'correction_rounds_max': 1,
                'source_sha256': {str(p.relative_to(BACKEND)): digest(p) for p in sources(cand)},
                'data_sha256': {p.name: digest(p) for p in files},
                'jobs': [{'job': j['job'], 'request_sha256': hashlib.sha256(json.dumps(
                    j['body'], ensure_ascii=False, sort_keys=True).encode()).hexdigest()} for j in jobs],
                'first_calls': len(jobs), 'max_calls': 2 * len(jobs), 'automatic_retries': False,
                'concurrency': 2}
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
    if args.execute:
        approval = read(args.run_dir / 'authorization.json') or {}
        limit = approval.get('stages', {}).get(stage)
        if approval.get('status') != 'approved' or not limit or limit['max_calls'] < 2 * len(jobs):
            raise SystemExit('stage not authorized')
        with (out / 'runner.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            stop = threading.Event()

            def call(body, job, folder):
                if (folder / 'result.json').exists():
                    return read(folder / 'response.public.json')
                if (folder / 'request.json').exists():
                    raise SystemExit('submitted without result, recover explicitly: ' + job)
                if stop.is_set():
                    write(folder / 'result.json', {'job': job, 'submitted': False,
                                                   'error_type': 'not_submitted_after_transport_error'})
                    return None
                write(folder / 'request.json', body)
                result = {'job': job, 'submitted': True, 'error_type': None}
                public = None
                try:
                    response = transport.invoke(body, job, run_id=run_id, role='mind_contract_' + stage,
                                                ledger_path=args.ledger, max_started=limit['max_calls'])
                    public = transport.public(response)
                    write(folder / 'response.public.json', public)
                except Exception as error:  # noqa: BLE001 - recorded, never retried
                    result['error_type'] = type(error).__name__ + ':' + str(error)[:120]
                    if 'transport' in str(error) or 'Timeout' in type(error).__name__:
                        stop.set()
                write(folder / 'result.json', result)
                print(json.dumps(result, ensure_ascii=False), flush=True)
                return public

            def one(j):
                f = out / j['input']['id'] / str(j['rep'])
                first = call(j['body'], j['job'], f / 'first')
                problem, _ = judge(first, j['input']['personal'], compile_fn)
                if problem is not None and not stop.is_set():
                    write(f / 'first' / 'problem.json', {'problem': problem})
                    call(module.correction(j['body'], first, problem), j['job'] + '_fix', f / 'fix')

            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(one, jobs))
    if args.execute or args.score_only:
        rows, summary, gate = score(stage, out)
        write(out / 'scored.json', {'rows': rows, 'summary': summary, 'gate': gate})
        print(json.dumps({'summary': {k: v for k, v in summary.items() if k != 'by_input'}, 'gate': gate},
                         ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
