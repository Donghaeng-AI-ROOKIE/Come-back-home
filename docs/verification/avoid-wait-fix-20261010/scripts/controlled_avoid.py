"""E20 place-avoidance check, separate from map publication.

Guardian N3: '가상 E20 시장이 시끄러울 때만 그곳을 피해서 가상 E20 쉼터 쪽으로 가요.
조용하면 가상 E20 시장에 들어가세요. 모든 공원이나 시장을 피하는 것은 아니에요.'

Scenarios (500 walkers, 15 min, synthetic observations):
 A noisy_at_market : start at the registered market, report noisy=True (120 m)
 B quiet_at_market : start at the registered market, report noisy=False
 C far_no_info     : start at the case's last-known point (~2 km away), no report near
Success is counted only where the market is a known site and the signal is
observed. Time that could not be checked (insufficient environment
information) is reported separately and never counted as success.

Usage: python controlled_avoid.py <exp_root> <out.json> <label> [--policy-dir DIR]
"""
import argparse, json, os, socket
from copy import deepcopy
from pathlib import Path


def _blocked(*a, **k):
    raise RuntimeError('network disabled')


socket.socket.connect = _blocked; socket.create_connection = _blocked
ap = argparse.ArgumentParser(); ap.add_argument('exp'); ap.add_argument('out'); ap.add_argument('label')
ap.add_argument('--policy-dir'); args = ap.parse_args()
R = Path(args.exp); GRAPH = os.environ['CBH_KINTEX_GRAPHML']
os.environ.update(PERSIST_STORAGE='false', MIND_POLICY_CONTRACT='guarded_core', MIND_POLICY_DEPLOYMENT='staging',
                  USE_ROADNET='true', PERSONAL_WALK_CACHE_PATH=GRAPH, PUSH_ENABLED='false', EXAONE_WARMUP_ENABLED='false')
from app.schemas.persona import Persona
from app.schemas.report import MissingReport
from app.schemas.prediction import PriorParams
from app.schemas.environment import EnvironmentObservation
from app.geo.roadnet import verified_network
from app.geo.road_anchors import connect_anchors
from app.geo.h3grid import haversine_km
from app.phase0 import mind_preparation
from app.phase2 import continuous_prediction as cp
from app.phase2.persistent_context_walk import PersistentContextPopulation

pid = 'E20'
prepared = json.loads((R / 'output/people' / pid / 'prepared.json').read_text())
report = MissingReport.model_validate(prepared['report'])
raw = deepcopy(prepared['arms']['D_full_prepared']['persona'])
source = 'stored'
if args.policy_dir and (Path(args.policy_dir) / f'{pid}.json').exists():
    row = json.loads((Path(args.policy_dir) / f'{pid}.json').read_text())
    if row.get('policy') and row['policy'] != row.get('stored_policy'):
        raw['prepared_mind']['policy'] = row['policy']; source = 'reprepared_with_recorded_K_responses'
person = Persona.model_validate(raw); prior = PriorParams.model_validate(prepared['arms']['D_full_prepared']['prior'])
policy, status = (cp._executable_policy(person)[:2] if hasattr(cp, '_executable_policy') else mind_preparation.ready(person))
market = next(a for a in person.attraction_points if a.label == '가상 E20 시장').location
shelter = next(a for a in person.attraction_points if a.label == '가상 E20 쉼터').location
base = verified_network(Path(GRAPH))
noisy = report.environment_observations[0]


def obs(value):
    return [EnvironmentObservation(**{**noisy.model_dump(), 'noisy': value})]


scenarios = {'A_noisy_at_market': (market, obs(True)), 'B_quiet_at_market': (market, obs(False)),
             'C_far_no_info': (report.lkp, [])}
out = dict(label=args.label, person_id=pid, policy_source=source, policy_status=status,
           rules=[dict(id=r.id, action=r.action, feature=r.feature, goal=r.goal_label, place_labels=r.place_labels,
                       when=[[(a.fact, a.value) for a in c] for c in r.when]) for r in policy.rules], scenarios={})
for name, (start, observations) in scenarios.items():
    net = connect_anchors(base, [start] + [a.location for a in person.attraction_points])
    pop = PersistentContextPopulation(net, person, prior, policy, start, report.lkp_time, count=500, seed=104729,
                                      environment_observations=observations)
    result = pop.advance_to(15)
    ps = pop.particles
    def first_action(p):
        return next((e for e in p.events if e['kind'] == 'action'), {})
    start_d = [haversine_km(pop.position(p), market) * 1000 for p in ps]
    avoided = [p for p in ps if any(e['kind'] == 'action' and e.get('action') == 'avoid' for e in p.events)]
    shelter_seek = [p for p in ps if any(e['kind'] == 'action' and e.get('action') == 'seek' and e.get('goal') == '가상 E20 쉼터' for e in p.events)]
    market_seek = [p for p in ps if any(e['kind'] == 'action' and e.get('action') == 'seek' and e.get('goal') == '가상 E20 시장' for e in p.events)]
    q = result['quality']
    out['scenarios'][name] = dict(
        map_published=q['unresolved_mass'] <= 1e-9, unresolved_mass=q['unresolved_mass'], unresolved_reasons=q['unresolved_reasons'],
        walkers=len(ps), executed_avoid=len(avoided), executed_seek_shelter=len(shelter_seek), executed_seek_market=len(market_seek),
        beyond_60m_from_market_at_15min=sum(d > 60 for d in start_d), beyond_120m_from_market_at_15min=sum(d > 120 for d in start_d),
        mean_distance_from_market_m=sum(start_d) / len(start_d),
        mean_distance_to_shelter_m=sum(haversine_km(pop.position(p), shelter) * 1000 for p in ps) / len(ps),
        environment_insufficient_minutes=q.get('environment_insufficient_minutes'),
        environment_insufficient_walkers=q.get('environment_insufficient_walkers'))
Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n')
print(json.dumps({k: v for k, v in out.items() if k != 'rules'}, ensure_ascii=False, indent=1))
