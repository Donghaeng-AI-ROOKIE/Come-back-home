"""Does the walking engine consume contract-compiled policies? Offline, no model.

Handwritten A/B fixtures and the saved 2026-10-06 failing policies are replayed
on the verified KINTEX road map (two sites x two seeds x 100 walkers, 6 h).
This checks rule -> movement propagation only. It is not model accuracy, not
more independent people, and not a real missing person's route.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import statistics
from pathlib import Path

from app.geo.h3grid import haversine_km
from app.geo.roadnet import verified_network
from app.llm.mind_policy import Policy
from app.phase2.person_walk import Population
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint
from experiments.mind_contract_ab_20261007 import contracts, scoring
from experiments.mind_contract_ab_20261007.fixtures import A_CORRECT, B_CORRECT
from tests.test_mind_upgrade import START, person, prior
from tests.test_person_policy import obs

MAP_SHA256 = '953d2bca91fe7388011e9ca161dc576c3c79366c578ed314d7cc8deea677db92'
SITES = ('C', 'NW')
SEEDS = (17, 73)
MINUTES = (60, 120, 240, 360)
SAVED = scoring.ROOT / 'comparison'


def no_network(*args, **kwargs):
    raise RuntimeError('offline replay forbids network')


def saved_policy(arm, pid, rep):
    path = SAVED / arm / pid / str(rep) / 'compiled_policy.json'
    return Policy.model_validate(json.loads(path.read_text())), str(path.relative_to(scoring.ROOT))


def cases():
    people, _, _ = scoring.load()
    personal = {pid: people[pid]['personal'] for pid in ('P05', 'P14', 'P25', 'P29')}
    empty = Policy(rules=[], unrepresented=[])
    always = lambda fact, value: [obs(fact, value)]  # noqa: E731
    return {
        'P14': {'observations': always('target_recognized', True), 'arms': {
            'A_fixture': contracts.compile_a(A_CORRECT['P14'], personal['P14']),
            'B_fixture': contracts.compile_b(B_CORRECT['P14'], personal['P14']),
            'saved_v4_on_2_walk_scoped': saved_policy('on', 'P14', 2)[0],
            'no_policy': empty}},
        'P05': {'observations': [], 'arms': {
            'A_fixture': contracts.compile_a(A_CORRECT['P05'], personal['P05']),
            'B_fixture': contracts.compile_b(B_CORRECT['P05'], personal['P05']),
            'saved_v4_off_1_rules_empty': saved_policy('off', 'P05', 1)[0],
            'no_policy': empty}},
        'P25': {'observations': always('family_present', False), 'arms': {
            'A_fixture': contracts.compile_a(A_CORRECT['P25'], personal['P25']),
            'B_fixture': contracts.compile_b(B_CORRECT['P25'], personal['P25']),
            'no_policy': empty}},
        'P29': {'observations': [obs('lost_awareness', True), obs('family_present', False, 0, 90),
                                 obs('family_present', True, 90)], 'arms': {
            'A_fixture': contracts.compile_a(A_CORRECT['P29'], personal['P29']),
            'B_fixture': contracts.compile_b(B_CORRECT['P29'], personal['P29']),
            'no_policy': empty}},
    }, personal


def run(net, site, seed, policy, personal, observations):
    start = GeoPoint(**site['location'])
    p = person(start)
    p.attraction_points = [AttractionPoint(label=o['label'], location=GeoPoint(**g['location']), place_type=t)
                           for o, g, t in zip(personal['places'], site['goals'], ('park', 'market', 'park'))]
    base = prior()
    base.attraction_weights = {a.label: 1.0 for a in p.attraction_points}
    peak = {}

    def hook(part, loc):
        if part.mode in ('walk', 'avoid', 'seek'):
            cw, ds = peak.get(part.seed, (0., 0.))
            peak[part.seed] = (max(cw, part.continuous_walk), max(ds, part.distance_since_rest))

    pop = Population(net, p, base, policy, start, START, count=100, seed=seed,
                     behavior_observations=observations, trace_hook=hook)
    goal = GeoPoint(**site['goals'][0]['location'])
    snaps = []
    for minute in MINUTES:
        out = pop.advance_to(minute)
        parts = pop.particles
        snaps.append({'minute': minute, 'mass': round(sum(out['cells'].values()) + out['quality']['unresolved_mass'], 9),
                      'mean_wait': round(statistics.mean(x.waiting for x in parts), 2),
                      'mean_rest': round(statistics.mean(x.rest for x in parts), 2),
                      'mean_personal_rest': round(statistics.mean(x.rest - x.population_rest_minutes for x in parts), 2),
                      'mean_walk': round(statistics.mean(x.walking for x in parts), 2),
                      'mean_path_km': round(statistics.mean(x.distance for x in parts) / 1000, 3),
                      'mean_km_to_first_place': round(statistics.mean(haversine_km(goal, pop.position(x)) for x in parts), 3),
                      'arrived_first_place': sum(p.attraction_points[0].label in x.completed_goals for x in parts)})
    walked = [v for v in peak.values()]
    return {'snapshots': snaps,
            'max_continuous_walk_min': round(max((v[0] for v in walked), default=0), 3),
            'max_distance_since_rest_m': round(max((v[1] for v in walked), default=0), 1)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--map', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('refusing to overwrite ' + str(args.output))
    if hashlib.sha256(args.map.read_bytes()).hexdigest() != MAP_SHA256:
        raise SystemExit('map hash differs from the verified KINTEX map')
    socket.socket.connect = no_network
    sites = {s['site_id']: s for s in json.loads((scoring.ROOT / 'sites.json').read_text())['sites']}
    net = verified_network(args.map)
    plan, personal = cases()
    results = []
    for pid, spec in plan.items():
        for arm, policy in spec['arms'].items():
            for site_id in SITES:
                for seed in SEEDS:
                    row = {'person_id': pid, 'arm': arm, 'site_id': site_id, 'seed': seed,
                           **run(net, sites[site_id], seed, policy, personal[pid], spec['observations'])}
                    results.append(row)
                    last = row['snapshots'][-1]
                    print(json.dumps({k: row[k] for k in ('person_id', 'arm', 'site_id', 'seed')}
                                     | {'6h': last, 'max_cw': row['max_continuous_walk_min'],
                                        'max_ds': row['max_distance_since_rest_m']}, ensure_ascii=False), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        'scope': 'handwritten fixtures and saved failing policies replayed on roads; not model accuracy',
        'model_calls': 0, 'map_sha256': MAP_SHA256, 'sites': SITES, 'seeds': SEEDS, 'walkers': 100,
        'start_clock': START.isoformat(), 'observations': 'synthetic; target recognized always (P14), '
        'family absent always (P25), lost and family absent until 90 min then present (P29)',
        'results': results}, ensure_ascii=False, indent=1) + '\n')


if __name__ == '__main__':
    main()
