"""Bounded D5 continuation after the existing D4 job; no final evaluation.

Runs only the two explicitly authorized D5 development stages. The existing
runner still enforces attempt budgets, one correction, and frozen manifests.
No experiment is started if D4 is incomplete or its saved result is unbound.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

from experiments.mind_contract_ab_20261007 import completion, contract_d5, run_d5, run_v2


def prior_complete(folder):
    result = run_v2.read(folder / 'scored.json')
    if result is None:
        return False
    manifest = folder / 'manifest.json'
    if not manifest.exists() or result.get('manifest_sha256') != run_v2.digest(manifest):
        raise ValueError('D4 result is not bound to its frozen manifest')
    if not result['summary'].get('complete'):
        raise ValueError('D4 stopped incomplete; do not launch D5 automatically')
    if result['summary'].get('responses') != 256:
        raise ValueError('D4 response denominator differs')
    return True  # A completed but failed D4 is still a valid development baseline.


def inspect_stage(run_dir, previous, stage):
    scored = run_v2.read(run_dir / stage / 'scored.json')
    old = run_v2.read(previous / stage.replace('d5_', 'd4_') / 'scored.json')
    d3 = run_v2.read(previous / stage.replace('d5_', 'd3_') / 'scored.json')
    inputs, _, refs, _ = run_v2.dataset(stage)
    personal = {p['id']: p['personal'] for p in inputs}
    rows = []
    for row in scored['rows']:
        folder = run_dir / stage / row['input_id'] / str(row['rep'])
        final = folder / ('fix' if row['corrected'] else 'first') / 'response.public.json'
        public = run_v2.read(final)
        status, value = completion.classify(public) if public else ('not_received', None)
        diag = (contract_d5.diagnostics(value, personal[row['input_id']], refs[row['input_id']])
                if value is not None else {'readable': False, 'completion': status})
        rows.append({'input_id': row['input_id'], 'rep': row['rep'], 'diagnostics': diag})
    reasons = []
    summary = scored['summary']
    if not scored.get('gate', {}).get('advance'):
        reasons.append('registered_stage_gate_failed')
    old_summary = old['summary']
    first_drop = old_summary['first_valid'] / old_summary['responses'] - summary['first_valid'] / summary['responses']
    if first_drop > .03 + 1e-9:
        reasons.append('first_valid_drop_exceeds_3_percentage_points')
    silent = sum(r['diagnostics'].get('silent_collapse') is True for r in rows)
    if silent > 3:
        reasons.append('silent_collapse_exceeds_3')
    watch = []
    if d3 is not None:
        for iid, current in summary['by_input'].items():
            a, b = old_summary['by_input'].get(iid), d3['summary']['by_input'].get(iid)
            if a and b and a['passed'] == a['total'] and b['passed'] == b['total'] and current['passed'] < current['total']:
                watch.append(iid)
    if watch:
        reasons.append('previously_perfect_watch_inputs_regressed')
    # Semantic priority judgments cannot be established by the model's own
    # citations. If a new precedence accompanies a regression, inspect it
    # rather than letting a good aggregate score authorize expansion.
    old_rows = {(r['input_id'], r['rep']): r for r in old['rows']}
    override_regression = []
    for row, diagnosis in zip(scored['rows'], rows):
        other = old_rows[(row['input_id'], row['rep'])]
        if (diagnosis['diagnostics'].get('overrides', 0)
                and sum(s['pass'] for s in row['scenes']) < sum(s['pass'] for s in other['scenes'])):
            override_regression.append([row['input_id'], row['rep']])
    if override_regression:
        reasons.append('precedence_with_regression_needs_semantic_review')
    return {'advance': not reasons, 'reasons': reasons,
            'first_valid_drop_percentage_points': round(first_drop * 100, 4),
            'silent_collapse': silent, 'watch_regressions': watch,
            'override_regressions': override_regression, 'rows': rows,
            'meaning': 'development checks; not clinical validity or deployment approval'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    run_dir, previous = Path(config['run_dir']), Path(config['previous_run_dir'])
    run_d5.register_candidate()
    run_dir.mkdir(parents=True, exist_ok=True)

    def status(phase, **details):
        record = {'phase': phase, 'time': datetime.now(timezone.utc).isoformat(), 'pid': os.getpid(), **details}
        run_v2.write(run_dir / 'continuation_status.json', record)
        print(json.dumps(record, ensure_ascii=False), flush=True)

    def frozen():
        if run_v2.source_sha256('d5') != config['source_sha256']:
            raise ValueError('D5 source differs from the authorized frozen preparation')
        if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != config['continuation_sha256']:
            raise ValueError('continuation source changed')
        if run_v2.digest(run_dir / 'authorization.json') != config['authorization_sha256']:
            raise ValueError('authorization changed during continuation')

    def execute(module, arguments, logfile):
        frozen()
        with logfile.open('a') as out:
            proc = subprocess.run([sys.executable, '-m', module, *map(str, arguments)],
                                  cwd=run_v2.BACKEND, stdout=out, stderr=subprocess.STDOUT, check=False)
        if proc.returncode:
            raise RuntimeError(f'{module} exited {proc.returncode}; inspect {logfile.name}; no automatic retry')

    with (run_dir / 'continuation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            frozen()
            status('waiting_for_d4')
            deadline = time.monotonic() + 12 * 3600
            while not prior_complete(previous / 'd4_dev128'):
                if time.monotonic() > deadline:
                    raise TimeoutError('D4 not complete after 12 hours; no D5 call submitted')
                time.sleep(30)
            for stage in ('d5_dev8', 'd5_dev128'):
                status('running', stage=stage)
                execute('experiments.mind_contract_ab_20261007.run_d5',
                        ['--stage', stage, '--run-dir', run_dir, '--ledger', config['ledger'], '--execute'],
                        run_dir / (stage + '.log'))
                review = inspect_stage(run_dir, previous, stage)
                run_v2.write(run_dir / stage / 'continuation_review.json', review)
                if not review['advance'] and stage == 'd5_dev8':
                    status('needs_review', stage=stage, reasons=review['reasons'])
                    return
            # Diagnostic walking is useful even for a failed expanded candidate;
            # failures stay in the denominator. It is never a deployment gate.
            status('walking_saved_d5_outputs')
            execute('experiments.mind_contract_ab_20261007.engine_outputs_v2',
                    ['--scored', run_dir / 'd5_dev128/scored.json', '--map', config['map'],
                     '--output', run_dir / 'd5_dev128/engine_outputs_v2.json', '--workers', '2'],
                    run_dir / 'd5_engine_v2.log')
            status('development_comparison_finished', expansion_gate=review['advance'],
                   reasons=review['reasons'], deployment_approved=False, eval64_executed=False)
        except Exception as error:
            status('stopped', error_type=type(error).__name__, error=str(error)[:500])
            raise


if __name__ == '__main__':
    main()
