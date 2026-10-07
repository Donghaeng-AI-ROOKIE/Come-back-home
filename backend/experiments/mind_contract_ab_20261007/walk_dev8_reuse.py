"""Walk the 16 dev8 outputs, reusing verified identical reference walks.

An efficiency change only: same 150 walkers, KINTEX graph, three six-hour
scenarios, seeds and per-input tolerances as engine_outputs_v2. Compare all
dev8 responses, including invalid outputs. No model/network calls. Refuse
reuse if inputs, reference policies, app/walker sources or a replay differ.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import socket
import time

from app.llm.mind_policy import Policy
from experiments.mind_contract_ab_20261007 import engine_outputs_v2 as e, run_v2


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_sources(current, frozen):
    names = {str(p.relative_to(current)) for p in (current / 'app').rglob('*.py')}
    other = {str(p.relative_to(frozen)) for p in (frozen / 'app').rglob('*.py')}
    if names != other:
        raise ValueError('app file inventory differs from cached reference backend')
    names.update(('experiments/mind_contract_ab_20261007/engine_outputs_v2.py',
                  'tests/test_mind_upgrade.py'))
    mismatched = [n for n in names if not (frozen / n).exists() or sha(current / n) != sha(frozen / n)]
    if mismatched:
        raise ValueError('reference source differs: ' + ', '.join(sorted(mismatched)))
    return {n: sha(current / n) for n in sorted(names)}


def check_inputs(inputs, refs, frozen):
    original = run_v2.DEV128.relative_to(run_v2.BACKEND)
    folder = frozen / original
    old = {r['id']: r for r in map(json.loads, (folder / 'dev128_inputs.jsonl').read_text().splitlines())}
    oldrefs = json.loads((folder / 'dev128_reference.NOT_MODEL_INPUT.json').read_text())
    mapping = {}
    for row in inputs:
        key = row['id']; oldkey = 'DEV_' + key + '_original'
        if row['personal'] != old[oldkey]['personal']:
            raise ValueError('personal input differs: ' + key)
        if e.rule_set(Policy.model_validate(refs[key])) != e.rule_set(Policy.model_validate(oldrefs[oldkey])):
            raise ValueError('reference policy differs: ' + key)
        mapping[key] = oldkey
    return mapping


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scored', type=Path, required=True)
    p.add_argument('--reference-walks', type=Path, required=True)
    p.add_argument('--frozen-backend', type=Path, required=True)
    p.add_argument('--map', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        p.error('refusing to overwrite output')
    started = time.monotonic()
    scored = json.loads(args.scored.read_text())
    if not scored['summary']['complete']:
        p.error('wait for all dev8 responses')
    inputs, _, refs, _ = run_v2.dataset('d3_dev8')  # fixed shared inputs; no candidate execution
    expected = {(r['id'], rep) for r in inputs for rep in (1, 2)}
    rows = scored['rows']
    if len(rows) != len(expected) or {(r['input_id'], r['rep']) for r in rows} != expected:
        p.error('dev8 denominator differs')
    source_hashes = check_sources(run_v2.BACKEND, args.frozen_backend)
    mapping = check_inputs(inputs, refs, args.frozen_backend)
    cached = json.loads(args.reference_walks.read_text())
    if (cached['version'] != 'engine_outputs_v2' or cached['walkers'] != 150 or
            cached['seed'] != e.SEED or cached['site'] != e.SITE or
            cached['map_sha256'] != e.MAP_SHA256 or sha(args.map) != e.MAP_SHA256 or
            set(cached['scenarios']) != set(e.SCENARIOS)):
        p.error('reference walk configuration differs')
    site = next(s for s in json.loads((e.scoring.ROOT / 'sites.json').read_text())['sites'] if s['site_id'] == e.SITE)
    old_site = args.frozen_backend / e.scoring.ROOT.relative_to(run_v2.BACKEND) / 'sites.json'
    if sha(e.scoring.ROOT / 'sites.json') != sha(old_site):
        p.error('site definition differs')
    socket.socket.connect = e._offline
    net = e.verified_network(args.map)
    people = {r['id']: r['personal'] for r in inputs}
    key = inputs[0]['id']; names = list(e.SCENARIOS)
    checks, env = e.support_equivalence(net, site, people[key],
        [('reference', Policy.model_validate(refs[key]))], names[0], 10, e.SEED)
    if not all(x['identical'] for x in checks):
        p.error('network snapshot differs')
    replay = e.walk(env, site, people[key], Policy.model_validate(refs[key]), e.SCENARIOS[names[0]],
                    walkers=150, seed=e.SEED)
    # Replay same source/inputs at production-sized diagnostic population, not
    # just a file hash, before accepting cached tolerances and reference paths.
    if replay != cached['reference_walks'][mapping[key]][names[0]]:
        p.error('reference replay differs; cached values must not be reused')
    runner = e.Runner(env, site, 150, 2)
    try:
        valid = [r for r in rows if r['policy'] is not None]
        plan = [(r['input_id'], r['rep'], s) for r in valid for s in names]
        walked = runner.run([(people[r['input_id']], Policy.model_validate(r['policy']), s, e.SEED)
                             for r in valid for s in names], 'dev8_saved_outputs')
    finally:
        runner.close()
    actual = {(r['input_id'], r['rep']): None for r in rows}
    for (key, rep, scene), metric in zip(plan, walked):
        actual[key, rep] = (actual[key, rep] or {}) | {scene: metric}
    results = []
    for r in rows:
        key = r['input_id']; oldkey = mapping[key]
        judged = e.judge(actual[key, r['rep']], cached['reference_walks'][oldkey],
                         cached['tolerance']['per_input_by_scenario'][oldkey])
        judged['discriminable'] = any(x['discriminable'] for x in cached['discrimination']['per_input'][oldkey].values())
        results.append({'input_id': key, 'rep': r['rep'], 'family': r['family'],
                        'k_walks': actual[key, r['rep']], 'per_input': judged})
    counted = [r for r in results if r['per_input']['discriminable']]
    summary = {'responses': len(results), 'discriminable': len(counted),
               'preserved': sum(r['per_input']['preserved'] for r in counted),
               'not_walkable': sum(not r['per_input']['walkable'] for r in counted),
               'engine_errors': sum(r['per_input']['engine_error'] for r in counted),
               'not_discriminable': len(results) - len(counted)}
    out = {'scope': 'dev8 diagnostic only, synthetic people/observations on KINTEX roads; not deployment or clinical accuracy',
           'model_calls': 0, 'network_calls': 0, 'map_sha256': e.MAP_SHA256, 'walkers': 150, 'seed': e.SEED,
           'checks': {'source_hashes': source_hashes, 'identical_inputs_mapping': mapping,
                      'snapshot': checks, 'reference_replay_identical': True},
           'inputs': {str(p): sha(p) for p in (args.scored, args.reference_walks)},
           'reference_walks_reused_from': str(args.reference_walks),
           'reference_source_assumption': 'frozen backend of the prior run; identical local runtime; replay checked',
           'summary': summary, 'results': results, 'seconds': round(time.monotonic() - started, 1)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    from experiments.mind_contract_ab_20261007.walk_dev8_reuse import main as _main
    _main()
