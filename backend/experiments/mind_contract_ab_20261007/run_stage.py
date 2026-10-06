"""Staged K-EXAONE comparison of contract candidates A/B.

Without --execute: build every request, freeze hashes in manifest.json and stop.
With --execute: requires authorization.json for this stage, unchanged hashes,
and no previously submitted job without a saved result (those need explicit
recovery, never resubmission). No automatic retry. Concurrency 2.
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

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
SOURCES = [HERE / n for n in ('PLAN.md', 'contracts.py', 'completion.py', 'scoring.py', 'transport.py', 'run_stage.py')] + [
    BACKEND / p for p in ('experiments/mind_policy_candidates/condition_program.py',
                          'experiments/mind_policy_candidates/note_policy_eval.py',
                          'app/llm/mind_policy.py', 'app/llm/initial_behavior.py', 'app/llm/usage_ledger.py')]
STAGES = {
    # Five named failures plus three over-reach counterexamples (capacity,
    # stated goal, negated/other-person). Chosen before any new model call.
    'dev8': {'people': ['P05', 'P06', 'P13', 'P14', 'P21', 'P24', 'P25', 'P29'],
             'candidates': ['A', 'B'], 'repetitions': [1, 2], 'thinking': True, 'data': 'diverse_20261006'},
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + '\n')


def data_files(stage):
    root = scoring.ROOT
    return {n: root / n for n in ('profiles.json', 'scenes.json', 'reference_policies.NOT_MODEL_INPUT.json')}


def jobs_for(stage):
    spec = STAGES[stage]
    people, _, _ = scoring.load()
    jobs = []
    for pid in spec['people']:
        for cand in spec['candidates']:
            for rep in spec['repetitions']:
                body = contracts.CANDIDATES[cand][1](people[pid]['personal'], transport.MODEL,
                                                     thinking=spec['thinking'])
                jobs.append({'job': f'{stage}_{cand}_{pid}_{rep}', 'candidate': cand, 'person_id': pid,
                             'rep': rep, 'body': body})
    return jobs


def manifest_for(stage, jobs):
    return {'stage': stage, 'spec': STAGES[stage], 'model': transport.MODEL,
            'source_sha256': {str(p.relative_to(BACKEND)): digest(p) for p in SOURCES},
            'data_sha256': {n: digest(p) for n, p in data_files(stage).items()},
            'jobs': [{'job': j['job'], 'request_sha256': hashlib.sha256(
                json.dumps(j['body'], ensure_ascii=False, sort_keys=True).encode()).hexdigest()} for j in jobs],
            'planned_calls': len(jobs),
            'max_request_utf8_bytes': max(len(json.dumps(j['body'], ensure_ascii=False).encode()) for j in jobs),
            'automatic_retries': False, 'concurrency': 2}


def score_stage(stage, out):
    people, scenes, reference = scoring.load()
    spec = STAGES[stage]
    by = {c: [] for c in spec['candidates']}
    for j in jobs_for(stage):
        folder = out / j['candidate'] / j['person_id'] / str(j['rep'])
        result = json.loads((folder / 'result.json').read_text())
        pid = j['person_id']
        if (folder / 'response.public.json').exists():
            public = json.loads((folder / 'response.public.json').read_text())
        else:  # a failed or unsubmitted call is an output failure in the denominator
            public = {'finish_reason': None, 'final_content': None}
        row = scoring.evaluate(j['candidate'], public, people[pid]['personal'],
                               [s for s in scenes if s['person_id'] == pid], reference[pid], pid)
        row.update(job=j['job'], person_id=pid, rep=j['rep'], transport_error=result.get('error_type'))
        by[j['candidate']].append(row)
    summary = {}
    for cand, rows in by.items():
        s = scoring.summarize(rows)
        s['by_person'] = {pid: {'passed': sum(x['pass'] for r in rows if r['person_id'] == pid for x in r['scenes']),
                                'total': sum(len(r['scenes']) for r in rows if r['person_id'] == pid)}
                          for pid in spec['people']}
        summary[cand] = s
    return by, summary


def gate_dev8(summary):
    """Pre-registered in PLAN.md before any call. Development selection only."""
    def key(c):
        s = summary[c]
        return (s['passed'], -sum(s['critical'].values()), s['completion'].get('complete_json', 0), c == 'A')
    chosen = max(summary, key=key)
    s = summary[chosen]
    checks = {'decisions': s['passed'] >= ceil(.9 * s['decisions']),
              'complete_json': s['completion'].get('complete_json', 0) >= 15,
              'no_critical': sum(s['critical'].values()) == 0}
    return {'selected': chosen, 'selection_key': list(key(chosen)), 'required_decisions': ceil(.9 * s['decisions']),
            'checks': checks, 'advance_to_expanded_development': all(checks.values()),
            'meaning': 'development direction only; dev8 profiles were already seen; not performance evidence'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', required=True, choices=sorted(STAGES))
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--score-only', action='store_true')
    args = parser.parse_args()
    stage, run_id = args.stage, 'MIND_contract_ab_20261007_' + args.stage
    out = args.run_dir / stage
    jobs = jobs_for(stage)
    manifest = manifest_for(stage, jobs)
    path = out / 'manifest.json'
    if path.exists():
        if json.loads(path.read_text()) != manifest:
            raise SystemExit('frozen manifest differs: code, data or request changed')
    else:
        write(path, manifest)
        for source in SOURCES:
            target = out / 'source_snapshot' / source.relative_to(BACKEND)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    print(json.dumps({k: manifest[k] for k in ('stage', 'planned_calls', 'max_request_utf8_bytes')}))
    if args.score_only:
        by, summary = score_stage(stage, out)
        write(out / 'scored.json', {'rows': by, 'summary': summary, 'gate': gate_dev8(summary)})
        print(json.dumps({'summary': summary, 'gate': gate_dev8(summary)}, ensure_ascii=False, indent=1))
        return
    if not args.execute:
        return
    approval = json.loads((args.run_dir / 'authorization.json').read_text())
    limit = approval.get('stages', {}).get(stage)
    if approval.get('status') != 'approved' or not limit or limit['max_calls'] < len(jobs):
        raise SystemExit('stage not authorized: no SSH or model submission')
    with (out / 'runner.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pending = [j for j in jobs if not (out / j['candidate'] / j['person_id'] / str(j['rep']) / 'result.json').exists()]
        orphan = [j['job'] for j in pending
                  if (out / j['candidate'] / j['person_id'] / str(j['rep']) / 'request.json').exists()]
        if orphan:
            raise SystemExit('submitted without result, recover explicitly: ' + ', '.join(orphan))
        stop = threading.Event()

        def one(j):
            folder = out / j['candidate'] / j['person_id'] / str(j['rep'])
            result = {'job': j['job'], 'submitted': False, 'error_type': None}
            if stop.is_set():
                result['error_type'] = 'not_submitted_after_transport_error'
                write(folder / 'result.json', result)
                return result
            write(folder / 'request.json', j['body'])
            try:
                result['submitted'] = True
                response = transport.invoke(j['body'], j['job'], run_id=run_id, role='mind_contract_ab_' + stage,
                                            ledger_path=args.ledger, max_started=limit['max_calls'])
                write(folder / 'response.public.json', transport.public(response))
            except Exception as error:  # noqa: BLE001 - every rejection is recorded, none repaired
                result['error_type'] = type(error).__name__ + ':' + str(error)[:120]
                if 'transport' in str(error) or 'K_API_' in str(error) or 'Timeout' in type(error).__name__:
                    stop.set()
            write(folder / 'result.json', result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            return result

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(one, pending))
    by, summary = score_stage(stage, out)
    write(out / 'scored.json', {'rows': by, 'summary': summary, 'gate': gate_dev8(summary)})
    print(json.dumps({'summary': summary, 'gate': gate_dev8(summary)}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
