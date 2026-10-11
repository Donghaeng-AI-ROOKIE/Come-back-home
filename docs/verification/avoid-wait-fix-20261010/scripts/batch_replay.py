"""Offline batch replay of saved EFFICIENCY people with the backend on PYTHONPATH.

Mirrors the frozen experiment harness (one Case reused 1->2->4->6 h,
run_pair(...), complete rule, alpha_pool .7/.3 linear) and adds the deployed
road-anchor connection exactly as pipeline._load_roadnet does (PR #274).
The map is loaded once per process. Network is disabled. No model calls.

D arm  : product path run_pair (stored or re-prepared K policy via ready()).
B/C arm: component comparison only - the same continuous executor with an
         explicitly empty personal policy (NOT the deployed unprepared path).

Usage:
  python batch_replay.py <exp_root> <out_dir> <arm> <seed> <pid,pid,...> [--policy-dir DIR]
"""
import argparse, json, os, socket, time
from copy import deepcopy
from pathlib import Path


def _blocked(*a, **k):
    raise RuntimeError('network disabled in offline replay')


socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.create_connection = _blocked

ap = argparse.ArgumentParser()
ap.add_argument('exp'); ap.add_argument('out'); ap.add_argument('arm'); ap.add_argument('seed', type=int)
ap.add_argument('people'); ap.add_argument('--policy-dir'); ap.add_argument('--hours', default='1,2,4,6')
args = ap.parse_args()
R = Path(args.exp); OUT = Path(args.out); hours = [int(h) for h in args.hours.split(',')]
GRAPH = os.environ['CBH_KINTEX_GRAPHML']
first = json.loads((R / 'output/people' / args.people.split(',')[0] / 'prepared.json').read_text())
os.environ.update(PERSIST_STORAGE='false', PUSH_ENABLED='false', PRIVACY_SCHEDULER_ENABLED='false',
                  POA_REFRESH_ENABLED='false', EXAONE_WARMUP_ENABLED='false',
                  MIND_POLICY_CONTRACT='guarded_core', MIND_POLICY_DEPLOYMENT='staging', USE_ROADNET='true',
                  PERSONAL_WALK_CACHE_PATH=GRAPH, MC_NUM_WALKERS='500',
                  RESEARCH_USAGE_LEDGER_PATH=str(OUT / 'no_calls.ledger.jsonl'))
model = os.environ.get('KEXAONE_MODEL')
import app
from app.schemas.persona import Persona
from app.schemas.report import MissingReport
from app.schemas.case import Case
from app.schemas.prediction import PriorParams
from app.geo.roadnet import verified_network
from app.geo.road_anchors import connect_anchors
from app.phase2 import combine, continuous_prediction as cp
from app.phase0 import mind_preparation
from app.llm.mind_policy import Policy

t0 = time.monotonic(); base_net = verified_network(Path(GRAPH)); load_s = time.monotonic() - t0
original_ready = mind_preparation.ready
EMPTY = Policy(rules=[], unrepresented=[])


def _behaviour(checkpoint):
    """Executed behaviour totals from the committed walker state (None if not committed)."""
    if not checkpoint:
        return None
    ps = checkpoint['particles']; n = len(ps)
    rules = {}
    for p in ps:
        for rid, minutes in (p.get('rule_minutes') or {}).items():
            rules[rid] = rules.get(rid, 0.) + minutes
    insufficient = {}
    for p in ps:
        for rid, minutes in (p.get('env_insufficient_minutes') or {}).items():
            insufficient[rid] = insufficient.get(rid, 0.) + minutes
    return dict(walkers=n, mean_rule_minutes={k: v / n for k, v in sorted(rules.items())},
                mean_wait_minutes=sum(p.get('waiting', 0.) for p in ps) / n,
                mean_rest_minutes=sum(p.get('rest', 0.) for p in ps) / n,
                mean_population_rest_minutes=sum(p.get('population_rest_minutes', 0.) for p in ps) / n,
                mean_walking_minutes=sum(p.get('walking', 0.) for p in ps) / n,
                mean_distance_m=sum(p.get('distance', 0.) for p in ps) / n,
                modes={m: sum(p.get('mode') == m for p in ps) for m in ('walk', 'seek', 'avoid', 'rest', 'wait')},
                mean_environment_insufficient_minutes={k: v / n for k, v in sorted(insufficient.items())},
                wait_completions=sum(len(p.get('completed_waits') or []) for p in ps),
                followup_active=sum(bool(p.get('followup_rule_id')) for p in ps))

for pid in args.people.split(','):
    prepared = json.loads((R / 'output/people' / pid / 'prepared.json').read_text())
    report = MissingReport.model_validate(prepared['report'])
    spec = prepared['arms'][args.arm]
    raw_persona = deepcopy(spec['persona'])
    policy_source = 'stored'
    if args.arm == 'D_full_prepared' and args.policy_dir:
        f = Path(args.policy_dir) / f'{pid}.json'
        if f.exists():
            row = json.loads(f.read_text())
            if row.get('policy') is not None and not row.get('error') and row['policy'] != row.get('stored_policy'):
                raw_persona['prepared_mind']['policy'] = row['policy']
                policy_source = 'reprepared_with_recorded_K_responses'
    person = Persona.model_validate(raw_persona); prior = PriorParams.model_validate(spec['prior'])
    # Works for both code versions: both read the policy through ready().
    if args.arm == 'D_full_prepared':
        mind_preparation.ready = original_ready
        status = original_ready(person)[1]
    else:
        mind_preparation.ready = lambda persona: (EMPTY, 'component_empty_policy')
        status = 'component_empty_policy'
    points = [report.lkp] + [a.location for a in person.attraction_points]
    net = connect_anchors(base_net, points)
    case = Case(id=f'{pid}-{args.arm}-{args.seed}', report=report, lkp=report.lkp, lkp_time=report.lkp_time)
    snaps = []; t = time.monotonic()
    for hour in hours:
        a, b, q = cp.run_pair(case, person, prior, net, hour, seed=args.seed)
        complete = (a is not None and b is not None and q.get('unresolved_mass', 1) <= 1e-9
                    and abs(sum(a.values()) - 1) < 1e-8 and abs(sum(b.values()) - 1) < 1e-8)
        cells = combine.alpha_pool([a, b], alphas=[.7, .3], mode='linear') if complete else {}
        snaps.append(dict(hour=hour, complete=complete, cells=cells, quality=q,
                          channels_identical=bool(a is not None and b is not None and a == b),
                          behaviour=dict(agent=_behaviour(case.continuous_state.get('checkpoint')),
                                         statistical=_behaviour((case.continuous_state.get('statistical') or {}).get('checkpoint')))))
    out = OUT / 'people' / pid; out.mkdir(parents=True, exist_ok=True)
    result = dict(person_id=pid, arm=args.arm, seed=args.seed, split=prepared.get('split'), family=prepared.get('family'),
                  seconds=round(time.monotonic() - t, 1), backend=app.__file__, policy_status=status,
                  policy_source=policy_source, anchor_connections=getattr(net, 'anchor_connections', []),
                  graph_load_seconds=round(load_s, 1), snapshots=snaps)
    (out / f'walk_{args.arm}_{args.seed}.json').write_text(json.dumps(result, ensure_ascii=False) + '\n')
    print(json.dumps(dict(pid=pid, arm=args.arm, seed=args.seed, status=status, policy_source=policy_source,
                          anchors=len(result['anchor_connections']), seconds=result['seconds'],
                          complete=[s['complete'] for s in snaps])), flush=True)
