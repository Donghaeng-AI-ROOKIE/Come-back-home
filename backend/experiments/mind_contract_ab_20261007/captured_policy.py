"""Prepared actual-app synthetic source -> D4/D12 policies; no authored gold in prompts."""
import argparse
import fcntl
import json
from pathlib import Path
from experiments.mind_contract_ab_20261007 import run_v2 as r, contract_d4 as d4, contract_d12 as d12
from experiments.mind_contract_ab_20261007 import resume_concise8 as guarded, condition_probe, audit_repair8
from app.llm import mind_policy as m


def reference(personal):
    """Explicit author interpretation of this frozen fixture, never fed to K."""
    def atom(f, v=True, op='eq'): return {'fact': f, 'op': op, 'value': v}
    def rule(rid, action, when, note, **kw):
        return dict(id=rid, action=action, when=when, goal_label=None, feature=None,
                    place_labels=[], hold_minutes=None, supersedes=[], evidence=[{'note_id': note}], **kw)
    wait = rule('author_wait', 'wait', [[atom('lost_awareness'), atom('family_present', False)]], 'N4')
    rest = rule('author_rest', 'rest', [
        [atom('is_walking'), atom('continuous_walk_minutes', 6, 'gte')],
        [atom('is_walking'), atom('distance_since_rest_m', 280, 'gte')]], 'N9')
    rest['hold_minutes'] = 5
    avoid = rule('author_avoid', 'avoid', [[atom('market.noisy')]], 'N5')
    avoid.update(feature='market', place_labels=['해든상가'])
    return m.validate({'rules': [wait, rest, avoid], 'unrepresented': [
        {'note_id': 'N7', 'reason': '이름을 부르면 쳐다보는 반응은 현재 보행 명령에 없음.'}]}, personal)


def score_response(public, personal, compiler, ref):
    # run_v2.judge returns (problem, error kind, compiled policy).
    problem, kind, policy = r.judge(public, personal, compiler) if public else ('no_response', 'no_response', None)
    probe = condition_probe.compare(policy, ref) if policy is not None else {'status': 'unusable_output'}
    return {'problem': problem, 'error_kind': kind,
            'policy': policy.model_dump(mode='json') if policy is not None else None,
            'condition_probe': probe}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    p.add_argument('--ledger', type=Path, required=True); p.add_argument('--execute', action='store_true')
    a = p.parse_args(); personal = r.read(a.source); ref = reference(personal)
    jobs = {}
    candidates = {'d4': (d4, d4.compile_d4), 'd12': (d12, d12.compile_d12)}
    for name, (mod, _) in candidates.items():
        x = {'id': 'actual_app_synthetic_person', 'personal': personal}
        jobs[name] = [{'job': f'captured_{name}_{rep}', 'input': x, 'rep': rep,
                       'body': mod.request(personal, r.transport.MODEL)} for rep in (1, 2)]
    manifest = {'source_sha256': r.digest(a.source), 'source_is_synthetic_actual_app_qa': True,
        'source_notes': len(personal['notes']), 'jobs': jobs, 'max_calls': 8,
        'max_output_tokens_total': 131072, 'input_bytes_per_call': 40000,
        'automatic_retries': False, 'concurrency': 2,
        'unit_price': None, 'actual_cost': None, 'support_round': None,
        'authorization': '2026-10-08 user same-goal iterative improvement standing approval',
        'reference_NOT_MODEL_INPUT': ref.model_dump(mode='json'),
        'limits': 'author reference, no clinician approval; one synthetic person; source integration diagnostic only',
        'source_files': {str(Path(f).resolve()): r.digest(Path(f)) for f in
                         (__file__, d4.__file__, d12.__file__, r.__file__, guarded.__file__, condition_probe.__file__)}}
    path = a.out / 'manifest.json'
    if path.exists() and r.read(path) != manifest: raise SystemExit('frozen manifest differs')
    if any(len(json.dumps(j['body'], ensure_ascii=False).encode()) > 40000 for batch in jobs.values() for j in batch):
        raise SystemExit('source too long; not silently truncated')
    r.write(path, manifest)
    if not a.execute: return
    if not r.os.environ.get('CBH_K_BRIDGE_SSH'): raise SystemExit('no bridge')
    lock = (a.out / 'runner.lock').open('a'); fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    results = []
    for name, (mod, compiler) in candidates.items():
        out = a.out / name; stage = 'captured_' + name
        r.write(out / 'manifest.json', manifest)
        r.write(a.out / 'status.json', {'state': 'calling', 'candidate': name})
        stopped = guarded.execute_guarded(r.execute, stage, out, jobs[name], mod, compiler, a.ledger, 4)
        for job in jobs[name]:
            folder = out / job['input']['id'] / str(job['rep'])
            public = r.read(folder / 'fix/response.public.json') or r.read(folder / 'first/response.public.json')
            fix_result = r.read(folder / 'fix/result.json')
            if fix_result and not fix_result.get('response_saved'): public = None
            row = {'candidate': name, 'rep': job['rep'], **score_response(public, personal, compiler, ref)}
            results.append(row)
            r.write(a.out / 'scored.json', {'results': results, 'author_reference': ref.model_dump(mode='json'),
                'clinical_accuracy': False, 'release_qualified': False})
        r.write(out / 'usage_summary.json', audit_repair8.usage(a.ledger, stage))
        if stopped:
            r.write(a.out / 'status.json', {'state': 'needs_transport_diagnosis'}); raise SystemExit(2)
    r.write(a.out / 'status.json', {'state': 'source_comparison_complete', 'outputs': len(results),
        'condition_equivalent_in_probes': sum(x['condition_probe']['status'] == 'no_difference_in_probes' for x in results),
        'release_qualified': False})


if __name__ == '__main__': main()
