"""Offline summary of a completed D6/D7 batch, preserving original scores."""
import argparse
from collections import Counter
import json
from pathlib import Path

from experiments.mind_contract_ab_20261007 import condition_probe, run_repair8, run_v2


def usage(ledger, stage):
    events = []
    run_id = 'MIND_contract_ab_20261007_' + stage
    with ledger.open() as f:
        for line in f:
            row = json.loads(line)
            if row.get('run_id') == run_id:
                events.append(row)
    starts = {e['attempt_id']: e for e in events if e['event_type'] == 'api_attempt_started'}
    ends = {e['attempt_id']: e for e in events if e['event_type'] == 'api_attempt_finished'}
    totals = {}
    for name in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
        values = [(e.get('usage') or {}).get(name) for e in ends.values()]
        totals[name] = sum(values) if values and all(isinstance(v, int) for v in values) else None
    return {'run_id': run_id, 'started': len(starts), 'finished': len(ends),
            'balanced_attempt_ids': set(starts) == set(ends),
            'missing_finish': sorted(set(starts) - set(ends)),
            'response_received': sum(e.get('outcome') == 'response_received' for e in ends.values()),
            'failed_attempts': sum(e.get('outcome') != 'response_received' for e in ends.values()),
            'api_duration_seconds_sum': sum(e.get('duration_seconds', 0) for e in ends.values()),
            'usage': totals, 'unit_price': None, 'actual_cost': None, 'support_round': None,
            'ledger': str(ledger),
            'note': 'API elapsed time is not GPU billed time. Unknown prices are not zero.'}


def paired(before, after):
    a = {(r['input_id'], r['rep']): r for r in before['rows']}
    b = {(r['input_id'], r['rep']): r for r in after['rows']}
    if len(a) != len(before['rows']) or len(b) != len(after['rows']) or set(a) != set(b):
        raise ValueError('paired denominator differs')
    out = []
    for key in a:
        x, y = a[key], b[key]
        if {s['id'] for s in x['scenes']} != {s['id'] for s in y['scenes']}:
            raise ValueError('paired scenes differ')
        bx = {s['id']: s['pass'] for s in x['scenes']}
        ay = {s['id']: s['pass'] for s in y['scenes']}
        out.append({'input_id': key[0], 'rep': key[1],
                    'before_passed': sum(bx.values()), 'after_passed': sum(ay.values()),
                    'fixed_scenes': [k for k in bx if not bx[k] and ay[k]],
                    'regressed_scenes': [k for k in bx if bx[k] and not ay[k]],
                    'before_usable': x['policy'] is not None, 'after_usable': y['policy'] is not None})
    return {'rows': out, 'fixed_scenes': sum(len(r['fixed_scenes']) for r in out),
            'regressed_scenes': sum(len(r['regressed_scenes']) for r in out),
            'responses_with_regression': sum(bool(r['regressed_scenes']) for r in out)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--stage', choices=('d6_dev8', 'd7_dev8', 'd8_dev8', 'd8plain_dev8'), required=True)
    p.add_argument('--ledger', type=Path, required=True)
    p.add_argument('--before', type=Path)
    a = p.parse_args()
    source = a.out / 'scored.json'
    scored = run_v2.read(source)
    if not scored or not scored['summary']['complete']:
        raise SystemExit('batch incomplete')
    expected = {(k, rep) for k in run_repair8.IDS for rep in (1, 2)}
    if len(scored['rows']) != len(expected) or {(r['input_id'], r['rep']) for r in scored['rows']} != expected:
        raise ValueError('repair8 denominator differs')
    _, _, refs, _ = run_repair8.repair_dataset()
    probes = condition_probe.audit(scored, refs)
    probes['scored_sha256'] = run_v2.digest(source)
    run_v2.write(a.out / 'condition_probes.json', probes)
    costs = usage(a.ledger, a.stage)
    run_v2.write(a.out / 'usage_summary.json', costs)
    report = {'scope': 'development failures only; source review is not human or clinical validation',
              'scored_sha256': run_v2.digest(source), 'scenes': scored['summary']['passed'],
              'total_scenes': scored['summary']['decisions'], 'valid': scored['summary']['final_valid'],
              'total_responses': scored['summary']['responses'], 'probes': probes['summary'],
              'costs': costs, 'source_reference_dispute': ['DEV_P08_preserve'],
              'deployment_qualified': False}
    if a.before:
        report['paired'] = paired(run_v2.read(a.before), scored)
        report['before_sha256'] = run_v2.digest(a.before)
    run_v2.write(a.out / 'iteration_audit.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'paired'}, ensure_ascii=False))
    if a.before:
        print(json.dumps({k: v for k, v in report['paired'].items() if k != 'rows'}))


if __name__ == '__main__':
    main()
