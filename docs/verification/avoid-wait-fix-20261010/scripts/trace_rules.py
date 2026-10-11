"""Full (untruncated) per-walker rule trace for selected people, 6 h, one seed.

Checks the movement-rule mechanics behind containment changes:
- repeated firing of the same seek rule after its goal was reached,
- what walkers do after physically arriving at a goal (stay vs leave),
- wait timer resets (a finite wait starting more than once per walker, or a
  completed wait lasting longer/shorter than its sourced duration).
Records every event via a wrapped Population._event (the stored list keeps
only the last 24). Same harness inputs as batch_replay (anchors, policy entry).

Usage: python trace_rules.py <exp_root> <out.json> <label> <pid,pid> [--seed S] [--policy-dir DIR]
"""
import argparse, json, os, socket
from copy import deepcopy
from pathlib import Path


def _blocked(*a, **k):
    raise RuntimeError('network disabled')


socket.socket.connect = _blocked; socket.create_connection = _blocked
ap = argparse.ArgumentParser(); ap.add_argument('exp'); ap.add_argument('out'); ap.add_argument('label'); ap.add_argument('people')
ap.add_argument('--seed', type=int, default=104729); ap.add_argument('--policy-dir'); ap.add_argument('--minutes', type=float, default=360)
args = ap.parse_args()
R = Path(args.exp); GRAPH = os.environ['CBH_KINTEX_GRAPHML']
os.environ.update(PERSIST_STORAGE='false', MIND_POLICY_CONTRACT='guarded_core', MIND_POLICY_DEPLOYMENT='staging',
                  USE_ROADNET='true', PERSONAL_WALK_CACHE_PATH=GRAPH, PUSH_ENABLED='false', EXAONE_WARMUP_ENABLED='false')
from app.schemas.persona import Persona
from app.schemas.report import MissingReport
from app.schemas.prediction import PriorParams
from app.geo.roadnet import verified_network
from app.geo.road_anchors import connect_anchors
from app.geo.h3grid import haversine_km
from app.phase0 import mind_preparation
from app.phase2 import continuous_prediction as cp
from app.phase2 import person_walk
from app.phase2.persistent_context_walk import PersistentContextPopulation

LOG = {}
original_event = person_walk.Population._event


def logged(self, p, kind, **extra):
    LOG.setdefault(p.seed, []).append({'minute': round(p.minute, 3), 'kind': kind, **extra})
    return original_event(self, p, kind, **extra)


person_walk.Population._event = logged
base = verified_network(Path(GRAPH)); out = []
for pid in args.people.split(','):
    LOG.clear()
    prepared = json.loads((R / 'output/people' / pid / 'prepared.json').read_text())
    report = MissingReport.model_validate(prepared['report'])
    raw = deepcopy(prepared['arms']['D_full_prepared']['persona'])
    if args.policy_dir and (Path(args.policy_dir) / f'{pid}.json').exists():
        row = json.loads((Path(args.policy_dir) / f'{pid}.json').read_text())
        if row.get('policy') and row['policy'] != row.get('stored_policy'):
            raw['prepared_mind']['policy'] = row['policy']
    person = Persona.model_validate(raw); prior = PriorParams.model_validate(prepared['arms']['D_full_prepared']['prior'])
    policy, status = (cp._executable_policy(person)[:2] if hasattr(cp, '_executable_policy') else mind_preparation.ready(person))
    net = connect_anchors(base, [report.lkp] + [a.location for a in person.attraction_points])
    pop = PersistentContextPopulation(net, person, prior, policy, report.lkp, report.lkp_time, count=500, seed=args.seed,
                                      environment_observations=report.environment_observations)
    goals = {a.label: a.location for a in person.attraction_points}
    snapshots = {}
    for minute in (60, 120, 240, args.minutes):
        pop.advance_to(minute)
        snapshots[int(minute)] = [dict(seed=p.seed, mode=p.mode, target=p.target, arrived=p.arrived,
                                       completed_goals=list(p.completed_goals),
                                       dist_to_goals={g: round(haversine_km(pop.position(p), loc) * 1000) for g, loc in goals.items()})
                                  for p in pop.particles]
    rules = {r.id: r for r in policy.rules}
    waits = {r.id: r.hold_minutes for r in policy.rules if r.action == 'wait' and r.hold_minutes is not None}
    per = []
    for p in pop.particles:
        ev = LOG.get(p.seed, [])
        acts = [e for e in ev if e['kind'] == 'action']
        seek_starts = {}
        for e in acts:
            if e.get('action') == 'seek' and e.get('rule_id'):
                seek_starts[e['rule_id']] = seek_starts.get(e['rule_id'], 0) + 1
        arrivals = [e for e in ev if e['kind'] == 'physical_arrival']
        # seek starts for a goal after that goal was already reached
        reached = {}; reseek = 0
        for e in ev:
            if e['kind'] == 'physical_arrival':
                reached[e.get('goal')] = e['minute']
            if e['kind'] == 'action' and e.get('action') == 'seek' and e.get('goal') in reached:
                reseek += 1
        wait_starts = {}; wait_spans = {}
        current = None
        for e in acts:
            rid = e.get('rule_id')
            if e.get('action') == 'wait' and rid in waits:
                wait_starts[rid] = wait_starts.get(rid, 0) + 1
                current = (rid, e['minute'])
            elif current and e.get('action') != 'wait':
                wait_spans.setdefault(current[0], []).append(round(e['minute'] - current[1], 3)); current = None
        completes = [e for e in ev if e['kind'] == 'sourced_wait_complete']
        # after a physical arrival: how long until the next movement, and who chose it
        post = []
        for i, e in enumerate(ev):
            if e['kind'] != 'physical_arrival':
                continue
            nxt = next((x for x in ev[i + 1:] if x['kind'] == 'action' and x.get('action') in ('walk', 'seek', 'avoid')), None)
            post.append(dict(goal=e.get('goal'), minute=e['minute'], censored=nxt is None,
                             dwell=round((nxt['minute'] if nxt else args.minutes) - e['minute'], 3),
                             next_source=nxt.get('source') if nxt else None, next_rule=nxt.get('rule_id') if nxt else None))
        # what happened right before each repeated start of the same seek rule
        repeat_before = {}; seen_rules = set()
        for i, e in enumerate(ev):
            if e['kind'] == 'action' and e.get('action') == 'seek' and e.get('rule_id'):
                if e['rule_id'] in seen_rules:
                    k = i - 1
                    while k >= 0 and ev[k]['kind'] == 'context_assumption':
                        k -= 1
                    key = ev[k]['kind'] + (':' + str(ev[k].get('action')) if ev[k]['kind'] == 'action' else '') if k >= 0 else 'none'
                    repeat_before[key] = repeat_before.get(key, 0) + 1
                seen_rules.add(e['rule_id'])
        per.append(dict(seed=p.seed, seek_starts=seek_starts, reseek_after_arrival=reseek, arrivals=[(a['minute'], a.get('goal')) for a in arrivals],
                        post_arrival=post, repeat_before=repeat_before,
                        wait_starts=wait_starts, wait_spans=wait_spans, wait_completions=[(c['minute'], c.get('rule_id')) for c in completes],
                        final_mode=p.mode, final_target=p.target, completed_goals=p.completed_goals,
                        context_hypotheses={k: v.get('value') for k, v in p.context_assumptions.items()}))
    summary = dict(
        walkers=len(per),
        seek_starts_per_rule={rid: sum(x['seek_starts'].get(rid, 0) for x in per) for rid in rules if rules[rid].action == 'seek'},
        walkers_with_repeated_seek_same_rule=sum(any(v > 1 for v in x['seek_starts'].values()) for x in per),
        reseek_after_arrival_events=sum(x['reseek_after_arrival'] for x in per),
        walkers_arrived=sum(bool(x['arrivals']) for x in per),
        wait_starts_per_rule={rid: sum(x['wait_starts'].get(rid, 0) for x in per) for rid in waits},
        walkers_with_wait_restarted={rid: sum(x['wait_starts'].get(rid, 0) > 1 for x in per) for rid in waits},
        completed_wait_spans_out_of_bounds={rid: sum(1 for x in per for s in x['wait_spans'].get(rid, []) if abs(s - waits[rid]) > 1e-6 and any(c[1] == rid for c in x['wait_completions'])) for rid in waits},
        wait_spans_examples={rid: sorted({s for x in per for s in x['wait_spans'].get(rid, [])})[:12] for rid in waits},
        repeated_seek_preceded_by={k: sum(x['repeat_before'].get(k, 0) for x in per) for k in sorted({k for x in per for k in x['repeat_before']})},
        post_arrival=dict(
            arrivals=sum(len(x['post_arrival']) for x in per),
            dwell_minutes_median=float(sorted(a['dwell'] for x in per for a in x['post_arrival'])[len([a for x in per for a in x['post_arrival']]) // 2]) if any(x['post_arrival'] for x in per) else None,
            left_within_1min=sum(a['dwell'] <= 1 and not a['censored'] for x in per for a in x['post_arrival']),
            stayed_to_end=sum(a['censored'] for x in per for a in x['post_arrival']),
            next_move_by={k: sum(1 for x in per for a in x['post_arrival'] if not a['censored'] and f"{a['next_source']}:{a['next_rule']}" == k)
                          for k in sorted({f"{a['next_source']}:{a['next_rule']}" for x in per for a in x['post_arrival'] if not a['censored']})}),
        family_hypothesis_true=sum(1 for x in per if any('family_present' in k and v for k, v in x['context_hypotheses'].items())),
        family_hypothesis_false=sum(1 for x in per if any('family_present' in k and v is False for k, v in x['context_hypotheses'].items())),
        lost_hypothesis_true=sum(1 for x in per if any('lost_awareness' in k and v for k, v in x['context_hypotheses'].items())),
        modes_at={m: {k: sum(1 for s in snapshots[m] if s['mode'] == k) for k in ('walk', 'seek', 'rest', 'wait', 'avoid')} for m in snapshots},
        near_goal_within_100m_at={m: {g: sum(1 for s in snapshots[m] if s['dist_to_goals'][g] <= 100) for g in goals} for m in snapshots})
    out.append(dict(label=args.label, person_id=pid, seed=args.seed, policy_status=status,
                    rules={rid: dict(action=r.action, goal=r.goal_label, hold=r.hold_minutes, supersedes=r.supersedes,
                                     when=[[(a.fact, a.value) for a in c] for c in r.when]) for rid, r in rules.items()},
                    summary=summary, walkers=per[:40]))
    print(pid, json.dumps(summary, ensure_ascii=False))
Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n')
