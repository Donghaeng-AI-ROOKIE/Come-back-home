"""Expanded development run for the dev8-selected candidate (PLAN_dev128.md).

Refuses unless dev8 advanced. Same freezing, ledger and no-resubmission rules
as run_stage.py. Without --execute: build requests, freeze the manifest, stop.
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

from experiments.mind_contract_ab_20261007 import contracts, scoring, transport
from experiments.mind_contract_ab_20261007.run_stage import BACKEND, HERE, SOURCES, digest, write

STAGE = 'dev128'
DATA = HERE / 'dataset' / 'dev128'
FILES = ('dev128_inputs.jsonl', 'dev128_scenes.NOT_MODEL_INPUT.json', 'dev128_reference.NOT_MODEL_INPUT.json')
OWN_SOURCES = SOURCES + [HERE / 'PLAN_dev128.md', HERE / 'run_dev128.py']


def load():
    inputs = [json.loads(x) for x in (DATA / FILES[0]).read_text().splitlines() if x.strip()]
    scenes = json.loads((DATA / FILES[1]).read_text())
    reference = json.loads((DATA / FILES[2]).read_text())
    return inputs, scenes, reference


def jobs_for(candidate):
    inputs, _, _ = load()
    return [{'job': f'{STAGE}_{candidate}_{r["id"]}_{rep}', 'input': r, 'rep': rep,
             'body': contracts.CANDIDATES[candidate][1](r['personal'], transport.MODEL, thinking=True)}
            for r in inputs for rep in (1, 2)]


def folder(out, j):
    return out / j['input']['id'] / str(j['rep'])


def score(out, candidate):
    inputs, scenes, reference = load()
    rows = []
    for j in jobs_for(candidate):
        r = j['input']
        f = folder(out, j)
        public = (json.loads((f / 'response.public.json').read_text()) if (f / 'response.public.json').exists()
                  else {'finish_reason': None, 'final_content': None})
        # Originals keep the root ID so the authored withheld-action list applies.
        key = r['root_id'] if r['form'] == 'original' else r['id']
        row = scoring.evaluate(candidate, public, r['personal'], [s for s in scenes if s['input_id'] == r['id']],
                               reference[r['id']], key)
        row.update(input_id=r['id'], root_id=r['root_id'], form=r['form'], rep=j['rep'],
                   family=next(s['family'] for s in scenes if s['input_id'] == r['id']))
        for s, scene in zip(row['scenes'], (s for s in scenes if s['input_id'] == r['id'])):
            s['expected_status'] = scene['expected_status']
        rows.append(row)
    decisions = [s | {'family': r['family'], 'form': r['form']} for r in rows for s in r['scenes']]
    by = lambda key: {k: {'passed': sum(d['pass'] for d in decisions if d[key] == k),  # noqa: E731
                          'total': sum(d[key] == k for d in decisions)} for k in sorted({d[key] for d in decisions})}
    status = by('expected_status')
    policies = {}
    for r in rows:
        policies.setdefault(r['input_id'], []).append(json.dumps(r['policy'] and r['policy']['rules'], sort_keys=True))
    summary = scoring.summarize(rows)
    summary.update(by_family=by('family'), by_form=by('form'), by_expected_status=status,
                   repeat_identical_policy=sum(len(set(v)) == 1 and v[0] != 'null' for v in policies.values()),
                   inputs=len(policies))
    total = summary['decisions']
    gate = {'decisions': summary['passed'] >= ceil(.9 * total),
            'families': all(v['passed'] >= ceil(.8 * v['total']) for v in summary['by_family'].values()),
            'supported': status['supported']['passed'] >= ceil(.9 * status['supported']['total']),
            'unknown': status['unknown']['passed'] >= ceil(.9 * status['unknown']['total']),
            'complete': summary['completion'].get('complete_json', 0) >= ceil(.95 * summary['responses']),
            'no_critical': sum(summary['critical'].values()) == 0}
    return rows, summary, {'checks': gate, 'advance_to_evaluation': all(gate.values()),
                           'meaning': 'draft development data; 32 root lineages, not 128 people'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--score-only', action='store_true')
    args = parser.parse_args()
    dev8 = json.loads((args.run_dir / 'dev8' / 'scored.json').read_text())['gate']
    if not dev8['advance_to_expanded_development']:
        raise SystemExit('dev8 did not advance: expanded development is not run')
    candidate = dev8['selected']
    out = args.run_dir / STAGE
    jobs = jobs_for(candidate)
    manifest = {'stage': STAGE, 'candidate': candidate, 'model': transport.MODEL,
                'source_sha256': {str(p.relative_to(BACKEND)): digest(p) for p in OWN_SOURCES},
                'data_sha256': {n: digest(DATA / n) for n in FILES},
                'jobs': [{'job': j['job'], 'request_sha256': hashlib.sha256(json.dumps(
                    j['body'], ensure_ascii=False, sort_keys=True).encode()).hexdigest()} for j in jobs],
                'planned_calls': len(jobs), 'automatic_retries': False, 'concurrency': 2}
    path = out / 'manifest.json'
    if path.exists():
        if json.loads(path.read_text()) != manifest:
            raise SystemExit('frozen manifest differs: code, data or request changed')
    else:
        write(path, manifest)
    print(json.dumps({'stage': STAGE, 'candidate': candidate, 'planned_calls': len(jobs)}))
    if args.execute:
        approval = json.loads((args.run_dir / 'authorization.json').read_text())
        limit = approval.get('stages', {}).get(STAGE)
        if approval.get('status') != 'approved' or not limit or limit['max_calls'] < len(jobs):
            raise SystemExit('stage not authorized')
        with (out / 'runner.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            pending = [j for j in jobs if not (folder(out, j) / 'result.json').exists()]
            orphan = [j['job'] for j in pending if (folder(out, j) / 'request.json').exists()]
            if orphan:
                raise SystemExit('submitted without result, recover explicitly: ' + ', '.join(orphan))
            stop = threading.Event()

            def one(j):
                f = folder(out, j)
                result = {'job': j['job'], 'submitted': False, 'error_type': None}
                if stop.is_set():
                    result['error_type'] = 'not_submitted_after_transport_error'
                    write(f / 'result.json', result)
                    return
                write(f / 'request.json', j['body'])
                try:
                    result['submitted'] = True
                    response = transport.invoke(j['body'], j['job'], run_id='MIND_contract_ab_20261007_' + STAGE,
                                                role='mind_contract_ab_' + STAGE, ledger_path=args.ledger,
                                                max_started=limit['max_calls'])
                    write(f / 'response.public.json', transport.public(response))
                except Exception as error:  # noqa: BLE001 - recorded, never retried
                    result['error_type'] = type(error).__name__ + ':' + str(error)[:120]
                    if 'transport' in str(error) or 'K_API_' in str(error) or 'Timeout' in type(error).__name__:
                        stop.set()
                write(f / 'result.json', result)
                print(json.dumps(result, ensure_ascii=False), flush=True)

            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(one, pending))
    if args.execute or args.score_only:
        rows, summary, gate = score(out, candidate)
        write(out / 'scored.json', {'rows': rows, 'summary': summary, 'gate': gate})
        print(json.dumps({'summary': summary, 'gate': gate}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
