"""Controlled wait-order check on the stored D policies of the wait family.

Facts held fixed for the whole run (synthetic control, not a patient scenario):
lost_awareness=True, family_present=False, and optionally target_recognized=False.
For each finite wait rule, count walkers that moved before the wait duration
ended and walkers moving shortly after it. Both code versions read the policy
through the same entry they use in production (deployed: ready(); fixed:
_executable_policy -> ready() + execution-time ordering). No model calls.

Usage: python controlled_wait.py <exp_root> <out.json> <label>
"""
import json, os, socket, sys
from datetime import timedelta
from pathlib import Path


def _blocked(*a, **k):
    raise RuntimeError('network disabled')


socket.socket.connect = _blocked; socket.create_connection = _blocked
R = Path(sys.argv[1]); OUT = Path(sys.argv[2]); LABEL = sys.argv[3]
GRAPH = os.environ['CBH_KINTEX_GRAPHML']
os.environ.update(PERSIST_STORAGE='false', MIND_POLICY_CONTRACT='guarded_core', MIND_POLICY_DEPLOYMENT='staging',
                  USE_ROADNET='true', PERSONAL_WALK_CACHE_PATH=GRAPH, PUSH_ENABLED='false', EXAONE_WARMUP_ENABLED='false')
from app.schemas.persona import Persona
from app.schemas.report import MissingReport
from app.schemas.prediction import PriorParams
from app.schemas.environment import BehaviorObservation
from app.geo.roadnet import verified_network
from app.geo.road_anchors import connect_anchors
from app.phase0 import mind_preparation
from app.phase2 import continuous_prediction as cp
from app.phase2.persistent_context_walk import PersistentContextPopulation

WAIT_FAMILY = ['E03', 'E07', 'E11', 'E15', 'E19', 'E23', 'E27', 'E31', 'E35', 'E39']
base = verified_network(Path(GRAPH))
results = []
for pid in WAIT_FAMILY:
    prepared = json.loads((R / 'output/people' / pid / 'prepared.json').read_text())
    report = MissingReport.model_validate(prepared['report'])
    spec = prepared['arms']['D_full_prepared']
    person = Persona.model_validate(spec['persona']); prior = PriorParams.model_validate(spec['prior'])
    if hasattr(cp, '_executable_policy'):
        policy, status, seq = cp._executable_policy(person)
    else:
        (policy, status), seq = mind_preparation.ready(person), None
    waits = [r for r in policy.rules if r.action == 'wait' and r.hold_minutes is not None]
    net = connect_anchors(base, [report.lkp] + [a.location for a in person.attraction_points])
    for recognised in (False, None):
        start = report.lkp_time
        facts = [('lost_awareness', True), ('family_present', False)] + ([('target_recognized', False)] if recognised is False else [])
        obs = [BehaviorObservation(fact=f, value=v, valid_from=start, valid_until=start + timedelta(minutes=361),
                                   source='synthetic_scenario') for f, v in facts]
        for wait in waits:
            hold = float(wait.hold_minutes)
            pop = PersistentContextPopulation(net, person, prior, policy, report.lkp, report.lkp_time, count=500,
                                              seed=104729, behavior_observations=obs,
                                              environment_observations=report.environment_observations)
            pop.advance_to(max(hold - .1, .1))
            before = sum(p.distance > 0 for p in pop.particles)
            waiting = sum(p.mode == 'wait' and p.hold_rule_id == wait.id for p in pop.particles)
            pop.advance_to(hold + 5)
            after = sum(p.distance > 0 for p in pop.particles)
            followups = sum(any(e['kind'] == 'sourced_wait_followup' and e.get('rule_id') == wait.id for e in p.events)
                            for p in pop.particles)
            results.append(dict(label=LABEL, person_id=pid, wait_rule_id=wait.id, hold_minutes=hold,
                                recognition='false' if recognised is False else 'unobserved',
                                policy_status=status, sequence_normalization=seq,
                                after_wait=wait.after_wait.model_dump(mode='json') if wait.after_wait else None,
                                moved_before_wait_end=before, waiting_on_rule_before_end=waiting,
                                moved_by_end_plus_5=after, followup_departures=followups, walkers=500))
OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1) + '\n')
for r in results:
    print(r['person_id'], r['wait_rule_id'], r['recognition'], 'hold', r['hold_minutes'],
          'moved_before_end', r['moved_before_wait_end'], 'waiting', r['waiting_on_rule_before_end'],
          'moved_after', r['moved_by_end_plus_5'], 'followups', r['followup_departures'],
          'converted', bool(r['after_wait']))
