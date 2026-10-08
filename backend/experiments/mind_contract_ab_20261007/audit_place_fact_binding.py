"""Offline constructed-state diagnosis of arrival/recognition place binding.

Uses real KINTEX nodes and synthetic registered places. Constructed states are
not a claimed observed route. No policy or original benchmark is repaired.
"""
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import socket

from app.llm.mind_policy import Policy, possibilities
from app.phase2.person_walk import Population
from app.schemas.common import GeoPoint
from app.schemas.environment import BehaviorObservation
from app.schemas.persona import AttractionPoint
from experiments.mind_contract_ab_20261007 import run_v2 as r, run_compact15, engine_outputs_v2 as e


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--map', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists(): raise SystemExit('preserve completed diagnostic')
    if r.digest(a.map) != e.MAP_SHA256: raise ValueError('wrong KINTEX cache')
    inputs, _, refs, _ = run_compact15.selected_dataset()
    key = 'DEV_P16_preserve'
    personal = next(x['personal'] for x in inputs if x['id'] == key)
    policy = Policy.model_validate(refs[key])
    socket.socket.connect = e._offline
    site = next(x for x in r.read(e.scoring.ROOT / 'sites.json')['sites'] if x['site_id'] == e.SITE)
    net = e.verified_network(a.map)
    env = e.environment_network(net, site, personal)
    start = GeoPoint(**site['location'])
    persona = e.person(start)
    persona.attraction_points = [AttractionPoint(label=x['label'], location=GeoPoint(**g['location']), place_type=x['place_type'])
                                 for x, g in zip(personal['places'], site['goals'])]
    now = datetime(2026, 10, 9, 8)
    obs = BehaviorObservation(fact='target_recognized', value=True, valid_from=now,
                              valid_until=now+timedelta(minutes=30), source='synthetic_scenario')
    base = e.prior(); base.strategy_probs = {'random_walk': 1.0}
    pop = Population(env, persona, base, policy, start, now, count=1, seed=17,
                     behavior_observations=[obs])
    particle = pop.particles[0]
    particle.node = pop.goals['솔빛쉼터']; particle.edge_to = None
    near, features = pop.near(particle)
    assert '솔빛쉼터' in near
    def snapshot(label):
        facts = pop.facts(particle)
        options, unknown = possibilities(policy, facts, near_places=near, near_features=features)
        return {'state': label, 'target': particle.target, 'near_places': near,
                'facts': {k: facts[k] for k in ('physical_arrival', 'target_recognized')},
                'possible_actions': [x.action if x else 'baseline' for x in options], 'unknown': unknown}
    particle.target = None; particle.arrived = False
    unselected = snapshot('exact snapped shelter node, not a selected target')
    particle.target = '느티공원'; particle.arrived = True
    historical = snapshot('constructed past park arrival flag while now at shelter')
    output = {'scope': 'constructed engine states, not clinical observations or complete route replay',
              'new_external_calls': 0, 'map_sha256': r.digest(a.map), 'source_sha256': r.digest(Path(__file__)),
              'engine_sha256': r.digest(r.BACKEND / 'app/phase2/person_walk.py'),
              'observation_fields': list(BehaviorObservation.model_fields), 'cases': [unselected, historical],
              'findings': ['physical_arrival is selected-target history, not arrival at every named place',
                           'target_recognized observations currently have no target/place binding'],
              'original_scores_unchanged': True, 'release_qualified': False}
    r.write(a.output, output)
    print(output['cases'])


if __name__ == '__main__': main()
