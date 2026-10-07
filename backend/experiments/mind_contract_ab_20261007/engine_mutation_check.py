"""Can the walking check tell a wrong personal interpretation apart? No model call.

For every dev128 input whose authored reference has personal rules, three
deliberately wrong policies are walked next to the reference:
  delete   all personal rules removed (an output that dropped the person)
  flip     the first condition atom negated (True<->False, >= <-> <, > <-> <=)
  swap     the first rule's action replaced (wait->walk, rest->walk, walk->wait,
           avoid->walk, seek->wait)
A mutant is DETECTED when, in any scenario, any snapshot metric (1, 2, 4, 6 h)
differs from the reference beyond that input's own noise tolerance. The same
tolerance applied to the reference walked with another seed / reversed rule
order gives the FALSE ALARM rate. Snapshots also count walkers who waited or
rested under a PERSONAL rule and later walked again (release then re-walk);
population fatigue rests are not counted.

Uses the synthetic environment layer of engine_outputs_v2 (experiment-only
facilities, not real KINTEX environment data). Measures the detector, not K.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import statistics
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path

from app.geo.roadnet import verified_network
from app.llm.mind_policy import Policy
from app.phase2.person_walk import Population
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint
from experiments.mind_contract_ab_20261007 import engine_outputs_v2 as v2
from experiments.mind_contract_ab_20261007 import scoring
from tests.test_mind_upgrade import person, prior

HOURS = (60, 120, 240, 360)
SWAP = {'wait': 'walk', 'rest': 'walk', 'walk': 'wait', 'avoid': 'walk', 'seek': 'wait'}
_STATE = {}


def personal_rules(policy, personal):
    fixed_ids = {r['id'] for r in v2.empty_policy(personal).model_dump()['rules']}
    return [r for r in policy['rules'] if r['id'] not in fixed_ids]


def mutants(policy, personal):
    """Typed edits of the authored reference; never derived from guardian text."""
    rules = policy['rules']
    own = personal_rules(policy, personal)
    if not own:
        return {}
    first = own[0]
    out = {'delete': {**policy, 'rules': [r for r in rules if r not in own]}}
    flipped = json.loads(json.dumps(first))
    atom = flipped['when'][0][0]
    if isinstance(atom['value'], bool):
        atom['value'] = not atom['value']
    else:
        atom['op'] = {'gte': 'lt', 'lt': 'gte', 'gt': 'lte', 'lte': 'gt', 'eq': 'eq'}[atom['op']]
    out['flip'] = {**policy, 'rules': [flipped if r is first else r for r in rules]}
    swapped = json.loads(json.dumps(first))
    swapped.update(action=SWAP[first['action']], goal_label=None, feature=None, place_labels=[],
                   hold_minutes=None)
    if swapped['action'] == 'wait' and any(a['fact'] == 'is_walking' and a['value'] is True
                                           for c in swapped['when'] for a in c):
        # A wait that requires walking cancels itself; drop that guard for a valid wait.
        swapped['when'] = [[a for a in c if a['fact'] != 'is_walking'] or [{'fact': 'lost_awareness', 'op': 'eq', 'value': True}]
                           for c in swapped['when']]
    out['swap'] = {**policy, 'rules': [swapped if r is first else r for r in rules]}
    return {k: Policy.model_validate(p) for k, p in out.items()}


def walk_snapshots(env_net, site, personal, policy, scenario, walkers, seed):
    start = GeoPoint(**site['location'])
    p = person(start)
    p.attraction_points = [AttractionPoint(label=x['label'], location=GeoPoint(**g['location']),
                                           place_type=x['place_type'])
                           for x, g in zip(personal['places'], site['goals'])]
    base = prior()
    base.strategy_probs = dict(scenario['strategy'])
    base.attraction_weights = {a.label: 1.0 for a in p.attraction_points}
    modes = {}

    def hook(part, loc):
        # Mode plus whether a personal rule drives it (population fatigue rest is not personal).
        state = (part.mode, part.hold_rule_id is not None and not part.last_baseline)
        seq = modes.setdefault(part.seed, [])
        if not seq or seq[-1] != state:
            seq.append(state)

    pop = Population(env_net, p, base, policy, start, scenario['start'], count=walkers, seed=seed,
                     behavior_observations=v2.behavior_observations(scenario),
                     environment_observations=v2.environment_observations(scenario, env_net.facilities),
                     trace_hook=hook)
    snaps = {}
    for minute in HOURS:
        pop.advance_to(minute)
        parts = pop.particles
        rewalk = sum(any(seq[i][0] in ('wait', 'rest') and seq[i][1] and seq[j][0] in ('walk', 'seek', 'avoid')
                         for i in range(len(seq)) for j in range(i + 1, len(seq)))
                     for seq in modes.values())
        snaps[minute] = {'mean_wait': round(statistics.mean(x.waiting for x in parts), 3),
                         'mean_personal_rest': round(statistics.mean(x.rest - x.population_rest_minutes for x in parts), 3),
                         'mean_path_km': round(statistics.mean(x.distance for x in parts) / 1000, 4),
                         'avoid_walkers': sum(any(m == 'avoid' for m, _ in s) for s in modes.values()),
                         'released_then_walked': rewalk,
                         'arrived': sum(len(x.completed_goals) > 0 for x in parts)}
    return snaps


def _init(map_path, site):
    _STATE['net'] = verified_network(map_path)
    _STATE['site'] = site
    socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('offline'))


def _task(task):
    iid, personal, policy, scenario_name, walkers, seed, label = task
    env_net = v2.environment_network(_STATE['net'], _STATE['site'], personal)
    snaps = walk_snapshots(env_net, _STATE['site'], personal, Policy.model_validate(policy),
                           v2.SCENARIOS[scenario_name], walkers, seed)
    return iid, label, scenario_name, seed, snaps


def detected(a, b, tolerance):
    hits = []
    for h in HOURS:
        for k, va in a[h].items():
            tol = tolerance.get((h, k), 0.0)
            if abs(va - b[h][k]) > tol + 1e-9:
                hits.append(f'{h // 60}h:{k}:{round(va - b[h][k], 3)}')
    return hits


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=Path, default=Path(v2.__file__).parent / 'dataset' / 'dev128')
    parser.add_argument('--map', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--walkers', type=int, default=40)
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--seeds', default='17,18,19', help='first = comparison seed, rest = noise')
    parser.add_argument('--limit-inputs', type=int, default=None)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('refusing to overwrite ' + str(args.output))
    if hashlib.sha256(args.map.read_bytes()).hexdigest() != v2.MAP_SHA256:
        raise SystemExit('map hash differs from the verified KINTEX map')
    seeds = [int(s) for s in args.seeds.split(',')]
    site = next(s for s in json.loads((scoring.ROOT / 'sites.json').read_text())['sites'] if s['site_id'] == v2.SITE)
    inputs = [json.loads(x) for x in (args.dataset / 'dev128_inputs.jsonl').read_text().splitlines() if x.strip()]
    reference = json.loads((args.dataset / 'dev128_reference.NOT_MODEL_INPUT.json').read_text())
    plan, muts = [], {}
    for r in inputs:
        own = personal_rules(reference[r['id']], r['personal'])
        if not own:
            continue
        muts[r['id']] = mutants(reference[r['id']], r['personal'])
        ref = reference[r['id']]
        rev = {**ref, 'rules': ref['rules'][::-1]}
        for sc in v2.SCENARIOS:
            for seed in seeds:
                plan.append((r['id'], r['personal'], ref, sc, args.walkers, seed, 'reference'))
            plan.append((r['id'], r['personal'], rev, sc, args.walkers, seeds[1], 'reference_reversed'))
            for name, pol in muts[r['id']].items():
                plan.append((r['id'], r['personal'], pol.model_dump(), sc, args.walkers, seeds[0], name))
        if args.limit_inputs and len(muts) >= args.limit_inputs:
            break
    results = {}
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=get_context('spawn'),
                             initializer=_init, initargs=(args.map, site)) as pool:
        for iid, label, sc, seed, snaps in pool.map(_task, plan, chunksize=2):
            results.setdefault(iid, {}).setdefault(sc, {})[(label, seed)] = snaps
    rows, counts = [], {k: {'inputs': 0, 'detected': 0} for k in ('delete', 'flip', 'swap', 'false_alarm')}
    for iid, by_sc in results.items():
        row = {'input_id': iid, 'mutants': {}, 'false_alarm': False, 'release_rewalk_reference': {}}
        hits = {k: [] for k in ('delete', 'flip', 'swap')}
        false_alarm = []
        for sc, walks in by_sc.items():
            refs = [walks[('reference', s)] for s in seeds]
            noise = refs[1:] + [walks[('reference_reversed', seeds[1])]]
            tolerance = {}
            for h in HOURS:
                for k in refs[0][h]:
                    values = [w[h][k] for w in [refs[0]] + noise[:-1]]
                    tolerance[(h, k)] = max(values) - min(values)
            base = refs[0]
            # Seed noise sets the tolerance; the reversed-order walk is the held-out
            # control (same meaning, must not be flagged).
            false_alarm += detected(walks[('reference_reversed', seeds[1])], base, tolerance)
            for name in hits:
                if (name, seeds[0]) in walks:
                    hits[name] += [f'{sc}:{x}' for x in detected(walks[(name, seeds[0])], base, tolerance)]
            row['release_rewalk_reference'][sc] = {h // 60: base[h]['released_then_walked'] for h in HOURS}
        for name in hits:
            if (name, seeds[0]) in next(iter(by_sc.values())):
                counts[name]['inputs'] += 1
                counts[name]['detected'] += bool(hits[name])
                row['mutants'][name] = {'detected': bool(hits[name]), 'evidence': hits[name][:6]}
        counts['false_alarm']['inputs'] += 1
        counts['false_alarm']['detected'] += bool(false_alarm)
        row['false_alarm'] = bool(false_alarm)
        row['false_alarm_evidence'] = false_alarm[:6]
        rows.append(row)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        'scope': 'detector validation on authored references with typed mutants; synthetic facilities, '
                 'not real KINTEX environment; not K accuracy',
        'model_calls': 0, 'map_sha256': v2.MAP_SHA256, 'walkers': args.walkers, 'seeds': seeds,
        'snapshots_min': HOURS, 'scenarios': list(v2.SCENARIOS),
        'summary': counts, 'rows': rows}, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == '__main__':
    main()
