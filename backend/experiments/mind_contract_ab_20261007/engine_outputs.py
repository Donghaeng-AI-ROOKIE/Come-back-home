"""Walk the REAL K outputs of a run and compare them with the authored references.

For every input and repetition, the compiled policy of the saved K output and
the handwritten reference policy walk the same KINTEX start, seed and synthetic
observation timeline. A trait is preserved in movement when the K walk matches
the reference walk on wait, personal rest, avoidance, goal arrival and path
length within fixed tolerances. A failed K output is counted as not walkable,
never dropped. No model call; this is propagation on roads, not location
accuracy or clinical validity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import statistics
from datetime import timedelta
from pathlib import Path

from app.geo.roadnet import verified_network
from app.llm.mind_policy import Policy
from app.phase2.person_walk import Population
from app.schemas.common import GeoPoint
from app.schemas.environment import BehaviorObservation, EnvironmentObservation
from app.schemas.persona import AttractionPoint
from experiments.mind_contract_ab_20261007 import scoring
from tests.test_mind_upgrade import START, person, prior

MAP_SHA256 = '953d2bca91fe7388011e9ca161dc576c3c79366c578ed314d7cc8deea677db92'
WALKERS, SEED, SITE, HORIZON = 100, 17, 'C', 360
TOLERANCE = {'mean_wait': 5.0, 'mean_personal_rest': 5.0, 'mean_path_km': 0.3,
             'avoid_walkers': 5, 'arrived': 5}


def behavior_timeline():
    def o(fact, value, a, b):
        return BehaviorObservation(fact=fact, value=value, valid_from=START + timedelta(minutes=a),
                                   valid_until=START + timedelta(minutes=b), source='synthetic_scenario')
    return [o('lost_awareness', True, 0, HORIZON),
            o('family_present', False, 0, 120), o('family_present', True, 120, HORIZON),
            o('rain_observed', False, 0, 60), o('rain_observed', True, 60, 120), o('rain_observed', False, 120, HORIZON),
            o('dark_observed', False, 0, 240), o('dark_observed', True, 240, HORIZON),
            o('pain_observed', False, 0, 30), o('pain_observed', True, 30, 45), o('pain_observed', False, 45, HORIZON),
            o('target_recognized', True, 0, HORIZON)]


def environment_timeline(site):
    park, market = GeoPoint(**site['goals'][0]['location']), GeoPoint(**site['goals'][1]['location'])

    def e(feature, where, a, b, **signals):
        return EnvironmentObservation(feature=feature, location=where, radius_m=500,
                                      valid_from=START + timedelta(minutes=a), valid_until=START + timedelta(minutes=b),
                                      source='synthetic_scenario', **signals)
    return [e('market', market, 0, 90, noisy=True, crowded=True), e('market', market, 90, 180, noisy=True, crowded=False),
            e('market', market, 180, HORIZON, noisy=False, crowded=False),
            e('park', park, 0, 180, noisy=False, crowded=True), e('park', park, 180, HORIZON, noisy=False, crowded=False)]


def walk(net, site, personal, policy):
    start = GeoPoint(**site['location'])
    p = person(start)
    p.attraction_points = [AttractionPoint(label=x['label'], location=GeoPoint(**g['location']), place_type=x['place_type'])
                           for x, g in zip(personal['places'], site['goals'])]
    base = prior()
    base.attraction_weights = {a.label: 1.0 for a in p.attraction_points}
    modes = {}

    def hook(part, loc):
        modes.setdefault(part.seed, set()).add(part.mode)

    pop = Population(net, p, base, policy, start, START, count=WALKERS, seed=SEED,
                     behavior_observations=behavior_timeline(),
                     environment_observations=environment_timeline(site), trace_hook=hook)
    out = pop.advance_to(HORIZON)
    parts = pop.particles
    return {'mass': round(sum(out['cells'].values()) + out['quality']['unresolved_mass'], 9),
            'mean_wait': round(statistics.mean(x.waiting for x in parts), 2),
            'mean_personal_rest': round(statistics.mean(x.rest - x.population_rest_minutes for x in parts), 2),
            'mean_path_km': round(statistics.mean(x.distance for x in parts) / 1000, 3),
            'avoid_walkers': sum('avoid' in m for m in modes.values()),
            'arrived': {a.label: sum(a.label in x.completed_goals for x in parts) for a in p.attraction_points}}


def compare(k, ref):
    diff = {key: abs(k[key] - ref[key]) for key in ('mean_wait', 'mean_personal_rest', 'mean_path_km', 'avoid_walkers')}
    diff['arrived'] = max(abs(k['arrived'][g] - ref['arrived'][g]) for g in ref['arrived'])
    return diff, all(diff[key] <= TOLERANCE[key] for key in TOLERANCE)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scored', type=Path, required=True, help='scored.json of a run_candidate stage')
    parser.add_argument('--dataset', type=Path, required=True, help='dev128 folder')
    parser.add_argument('--map', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('refusing to overwrite ' + str(args.output))
    if hashlib.sha256(args.map.read_bytes()).hexdigest() != MAP_SHA256:
        raise SystemExit('map hash differs from the verified KINTEX map')
    socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('offline replay forbids network'))
    site = next(s for s in json.loads((scoring.ROOT / 'sites.json').read_text())['sites'] if s['site_id'] == SITE)
    net = verified_network(args.map)
    inputs = {json.loads(x)['id']: json.loads(x) for x in (args.dataset / 'dev128_inputs.jsonl').read_text().splitlines() if x.strip()}
    reference = json.loads((args.dataset / 'dev128_reference.NOT_MODEL_INPUT.json').read_text())
    rows = json.loads(args.scored.read_text())['rows']
    ref_walks, results = {}, []
    for r in rows:
        iid = r['input_id']
        personal = inputs[iid]['personal']
        if iid not in ref_walks:
            ref_walks[iid] = walk(net, site, personal, Policy.model_validate(reference[iid]))
        row = {'input_id': iid, 'root_id': r['root_id'], 'form': r['form'], 'rep': r['rep'],
               'reference_walk': ref_walks[iid], 'k_walk': None, 'walkable': r['policy'] is not None}
        if r['policy'] is not None:
            row['k_walk'] = walk(net, site, personal, Policy.model_validate(r['policy']))
            row['diff'], row['movement_preserved'] = compare(row['k_walk'], ref_walks[iid])
        else:
            row['movement_preserved'] = False
        results.append(row)
        print(json.dumps({k: row[k] for k in ('input_id', 'rep', 'walkable', 'movement_preserved')}), flush=True)
    by_form = {}
    for x in results:
        b = by_form.setdefault(x['form'], {'total': 0, 'walkable': 0, 'movement_preserved': 0})
        b['total'] += 1
        b['walkable'] += x['walkable']
        b['movement_preserved'] += x['movement_preserved']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        'scope': 'real K outputs vs authored references on one KINTEX start; propagation, not location accuracy',
        'model_calls': 0, 'map_sha256': MAP_SHA256, 'site': SITE, 'seed': SEED, 'walkers': WALKERS,
        'horizon_min': HORIZON, 'tolerance': TOLERANCE, 'start_clock': START.isoformat(),
        'summary': {'responses': len(results), 'walkable': sum(x['walkable'] for x in results),
                    'movement_preserved': sum(x['movement_preserved'] for x in results), 'by_form': by_form},
        'results': results}, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(by_form, ensure_ascii=False))


if __name__ == '__main__':
    main()
