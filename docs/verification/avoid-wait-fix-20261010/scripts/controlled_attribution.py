"""Attribute every walker that moved before a finite wait ended to the rule it ran.

Same synthetic control as controlled_wait.py (lost_awareness=True,
family_present=False for the whole run). For each walker that moved before the
wait duration ended, record the first movement action (rule id, action, goal,
source) and the evidence note of that rule, so each case can be judged
against the guardian's original answer. Optional --policy-override replaces a
person's stored policy (used for the documented E27 interpretation fix).

Usage: python controlled_attribution.py <exp_root> <out.json> <label> [--policy-override FILE]
"""
import argparse, json, os, socket
from datetime import timedelta
from pathlib import Path


def _blocked(*a, **k):
    raise RuntimeError('network disabled')


socket.socket.connect = _blocked; socket.create_connection = _blocked
ap = argparse.ArgumentParser(); ap.add_argument('exp'); ap.add_argument('out'); ap.add_argument('label')
ap.add_argument('--policy-override'); ap.add_argument('--people', default='E03,E07,E11,E15,E19,E23,E27,E31,E35,E39')
args = ap.parse_args()
R = Path(args.exp); GRAPH = os.environ['CBH_KINTEX_GRAPHML']
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

overrides = json.loads(Path(args.policy_override).read_text()) if args.policy_override else {}
base = verified_network(Path(GRAPH)); out = []
for pid in args.people.split(','):
    prepared = json.loads((R / 'output/people' / pid / 'prepared.json').read_text())
    report = MissingReport.model_validate(prepared['report'])
    raw = prepared['arms']['D_full_prepared']['persona']
    if pid in overrides:
        raw['prepared_mind']['policy'] = overrides[pid]['policy']
    person = Persona.model_validate(raw); prior = PriorParams.model_validate(prepared['arms']['D_full_prepared']['prior'])
    if hasattr(cp, '_executable_policy'):
        policy, status, seq = cp._executable_policy(person)
    else:
        (policy, status), seq = mind_preparation.ready(person), None
    notes = {e.note_id for r in policy.rules for e in r.evidence}
    by_id = {r.id: r for r in policy.rules}
    net = connect_anchors(base, [report.lkp] + [a.location for a in person.attraction_points])
    start = report.lkp_time
    obs = [BehaviorObservation(fact=f, value=v, valid_from=start, valid_until=start + timedelta(minutes=361),
                               source='synthetic_scenario') for f, v in (('lost_awareness', True), ('family_present', False))]
    for wait in [r for r in policy.rules if r.action == 'wait' and r.hold_minutes is not None]:
        pop = PersistentContextPopulation(net, person, prior, policy, report.lkp, report.lkp_time, count=500, seed=104729,
                                          behavior_observations=obs, environment_observations=report.environment_observations)
        pop.advance_to(max(float(wait.hold_minutes) - .1, .1))
        causes = {}
        for p in pop.particles:
            if p.distance <= 0:
                continue
            first = next((e for e in p.events if e['kind'] == 'action' and e.get('action') in ('walk', 'seek', 'avoid')), None)
            key = json.dumps([first.get('rule_id') if first else None, first.get('action') if first else None,
                              first.get('goal') if first else None, first.get('source') if first else None,
                              sorted(first.get('unknown_facts') or []) if first else None], ensure_ascii=False)
            causes[key] = causes.get(key, 0) + 1
        detail = []
        for key, n in sorted(causes.items(), key=lambda x: -x[1]):
            rid, action, goal, source, unknown = json.loads(key)
            r = by_id.get(rid)
            detail.append(dict(walkers=n, rule_id=rid, action=action, goal=goal, source=source, unknown_facts=unknown,
                               rule_when=[[dict(fact=a.fact, value=a.value, op=a.op) for a in c] for c in r.when] if r else None,
                               rule_note_ids=[e.note_id for e in r.evidence] if r else None,
                               rule_quote=[e.quote for e in r.evidence] if r else None))
        out.append(dict(label=args.label, person_id=pid, override=pid in overrides, wait_rule_id=wait.id,
                        wait_note_ids=[e.note_id for e in wait.evidence], wait_quote=[e.quote for e in wait.evidence],
                        hold_minutes=wait.hold_minutes, supersedes=wait.supersedes, sequence_normalization=seq,
                        moved_before_wait_end=sum(d['walkers'] for d in detail), causes=detail,
                        onboarding_turns=[dict(question=t['question'], answer=t['answer']) for t in raw.get('onboarding_turns') or []]))
Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n')
for o in out:
    print(o['person_id'], o['wait_rule_id'], 'override' if o['override'] else '', 'moved', o['moved_before_wait_end'],
          [(d['walkers'], d['rule_id'], d['action'], d['goal'], d['source'], d['unknown_facts']) for d in o['causes']])
