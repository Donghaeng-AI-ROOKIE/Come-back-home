"""Resume frozen D8 requests; oversized correction is a terminal output failure.

Does not change the candidate, source, requests, gold or paid-call policy.
A supplementary execution manifest records this repair to orchestration.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
from experiments.mind_contract_ab_20261007 import run_v2, run_concise8

CAP_ERROR = 'input byte cap; original evidence is not truncated'


def execute_guarded(original, stage, out, jobs, module, compile_fn, ledger, max_calls):
    run_v2.write(out / 'execution_repair.json', {
        'runner': 'resume_concise8', 'sha256': run_v2.digest(Path(__file__)),
        'candidate_manifest_sha256': run_v2.digest(out / 'manifest.json'),
        'change': 'oversized correction recorded as terminal failure; original response retained',
        'automatic_paid_retries': False})
    stopped = threading.Event()
    def one(job):
        if stopped.is_set():
            return
        folder = out / job['input']['id'] / str(job['rep'])
        if (folder / 'correction_unavailable.json').exists():
            return
        try:
            if original(stage, out, [job], module, compile_fn, ledger, max_calls):
                stopped.set()
        except ValueError as error:
            if str(error) != CAP_ERROR:
                stopped.set()
                raise
            first = run_v2.read(folder / 'first' / 'response.public.json')
            if first is None:
                raise RuntimeError('cap failure without recorded first response') from error
            problem, _, _ = run_v2.judge(first, job['input']['personal'], compile_fn)
            if problem is None or run_v2.call_state(folder / 'fix') != 'pending':
                raise RuntimeError('unexpected correction state; needs diagnosis') from error
            run_v2.write(folder / 'correction_unavailable.json', {
                'reason': CAP_ERROR, 'submitted': False, 'terminal': True,
                'original_problem': problem,
                'first_response_sha256': run_v2.digest(folder / 'first' / 'response.public.json')})
    with ThreadPoolExecutor(max_workers=run_v2.CONCURRENCY) as pool:
        list(pool.map(one, jobs))
    return stopped.is_set()


def score_with_unavailable(original, stage, out):
    rows, _, _ = original(stage, out)
    for row in rows:
        folder = out / row['input_id'] / str(row['rep'])
        marker = run_v2.read(folder / 'correction_unavailable.json')
        if marker:
            if (row['first_state'] != 'done' or not row['first_problem'] or
                row['fix_state'] != 'pending' or row['policy'] is not None):
                raise RuntimeError('inconsistent terminal correction failure')
            row.update(complete=True, correction_unavailable=marker['reason'], corrected=False)
    module, _, _ = run_v2.load_candidate(stage.split('_')[0])
    summary = run_v2.summarize(module, rows)
    summary['corrections_unavailable'] = sum('correction_unavailable' in r for r in rows)
    return rows, summary, run_v2.gate(stage, summary)


def main():
    old_execute, old_score = run_v2.execute, run_v2.score
    run_v2.execute = lambda *args: execute_guarded(old_execute, *args)
    run_v2.score = lambda *args: score_with_unavailable(old_score, *args)
    run_concise8.main()


if __name__ == '__main__':
    main()
