"""Walk the REAL K outputs (v2): synthetic environment layer, discrimination
baseline, three observation scenarios, per-input seed-noise tolerance and pair
comparison.

Fixes the engine/leakage findings of code_review_d3.json on engine_outputs.py:

1. The verified KINTEX map has no market/park/forest/water layer, so a category
   avoidance froze walkers at the start ('unmapped_avoidance'). Here a read-only
   network snapshot answers env(node) with distances to SYNTHETIC facilities
   (registered park/market goals of the site and one synthetic forest and water
   point near the site). These are experiment-only facilities, not map data.
   Product code (app/) is unchanged and the loaded map object is never modified.
2. Every input is also walked with the empty policy (fixed rules only, what an
   output that drops every behavior compiles to). An input whose reference walk
   equals the empty walk within tolerance in every scenario is 'not
   discriminable' and is excluded from the preservation rate, reported apart.
3. Three scenarios (morning lost / evening past midnight in the dark / sparse
   afternoon) run the same policy. Observed facts switch on and off over time;
   no fact is observed true for the whole horizon. The departure clock is
   Population.started_at: observation windows and clock_hour (Asia/Seoul,
   naive local time) both derive from it.
4. K and reference walk with the same seed and scenario. The tolerance is set
   PER INPUT and per metric component: the range (max - min) of that input's
   own reference walked with three seeds and, for a multi-rule reference, with
   its rules in reverse order (the engine picks among simultaneously active
   rules by list position, so order alone moves the walk). References only,
   fixed before any K walk is compared. A noisy input never widens another
   input's tolerance. The previous pooled maximum over all inputs and the exact
   (same-seed determinism) view are reported as sensitivity analyses; the
   pooled view names the input that set each family's value.
5. Pairs inside a root (original/preserve/counterfactual/hard): changed-meaning
   pairs whose references walk differently are checked for a K change in the
   same direction; same-meaning pairs are checked for equal K walks. A pair is
   judged with the component-wise larger of its two inputs' tolerances.
6. A failed output is 'not walkable' and stays in every denominator. Responses
   whose rules equal the reference up to ids, order and evidence are counted
   apart inside the same denominator (never re-judged or repaired).

No model or network call. This measures propagation on roads under synthetic
observations, not location accuracy or clinical validity. Guardian text is
never read here; only compiled typed policies are walked, never repaired.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import socket
import statistics
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta
from multiprocessing import get_context
from pathlib import Path

from app.geo.h3grid import haversine_km
from app.geo.roadnet import verified_network
from app.llm.mind_policy import Policy, fixed_rules
from app.phase2 import radius
from app.phase2.person_walk import Population
from app.schemas.common import GeoPoint
from app.schemas.environment import BehaviorObservation, EnvironmentObservation
from app.schemas.persona import AttractionPoint
from experiments.mind_contract_ab_20261007 import scoring
from tests.test_mind_upgrade import person, prior

HERE = Path(__file__).resolve().parent
DEV128 = HERE / 'dataset' / 'dev128'
MAP_SHA256 = '953d2bca91fe7388011e9ca161dc576c3c79366c578ed314d7cc8deea677db92'
SITE, SEED = 'C', 17
# Reference-only seeds besides SEED: three seeds per reference measure its own noise.
NOISE_SEEDS = (18, 19)
# Timed sample (2026-10-07, 4 workers, another experiment running on the same
# machine): 321 unique walks at 150 walkers = 9.3 CPU-s and 2.33 s wall each.
# Full 128 inputs x 2 repetitions x 3 scenarios: 537 unique reference-phase
# walks (seeds 17/18/19, reverse order, empty policy) + 384..768 K walks
# (identical repetitions are walked once) + ~90 s map and checks
# = about 37 min to about 52 min.
DEFAULT_WALKERS, DEFAULT_WORKERS = 150, 4
SYNTHETIC_LABEL = '합성 시설(실험 전용 가정 좌표, 실제 지도 환경 레이어 아님)'
FEATURES = ('market', 'park', 'forest', 'water')
# Same perception limits as Population.near(); the snapshot only supplies distances.
PERCEPTION_M = {'market': 60, 'park': 60, 'forest': 60, 'water': 100}
# Deterministic compass offsets from the site, snapped to the nearest road node,
# close enough that early walkers pass within the perception limit.
SYNTHETIC_OFFSETS = {'forest': (160.0, 120.0), 'water': (20.0, 150.0)}
MIN_FACILITY_SEPARATION_M = 100.0
OBSERVATION_RADIUS_M = 300.0


# ── 1. synthetic environment layer ─────────────────────────────────────────
def _offset(point, bearing_deg, meters):
    b = math.radians(bearing_deg)
    return GeoPoint(lat=point.lat + meters * math.cos(b) / 111000.0,
                    lng=point.lng + meters * math.sin(b) / (111000.0 * math.cos(math.radians(point.lat))))


def places_key(site, personal):
    return json.dumps([[x['label'], x['place_type'], g['location']] for x, g in zip(personal['places'], site['goals'])],
                      ensure_ascii=False, sort_keys=True)


def facility_points(net, site, personal):
    """park/market from the registered goals' place_type; one synthetic forest and water point."""
    out = {f: [] for f in FEATURES}
    for x, g in zip(personal['places'], site['goals']):
        if x['place_type'] in ('park', 'market'):
            out[x['place_type']].append({'label': x['label'], 'lat': g['location']['lat'], 'lng': g['location']['lng'],
                                         'source': 'registered goal coordinate (synthetic placement in sites.json)'})
    start = GeoPoint(**site['location'])
    for feature, (bearing, meters) in SYNTHETIC_OFFSETS.items():
        node = net.nearest_node(_offset(start, bearing, meters))
        loc = net.node_location(node)
        out[feature].append({'label': 'synthetic_' + feature, 'lat': loc.lat, 'lng': loc.lng, 'node': node,
                             'source': f'synthetic: bearing {bearing} deg, {meters} m from site, snapped to road node'})
    points = [(f, p) for f in FEATURES for p in out[f]]
    for i, (fa, a) in enumerate(points):
        for fb, b in points[i + 1:]:
            if fa != fb and haversine_km(GeoPoint(lat=a['lat'], lng=a['lng']),
                                         GeoPoint(lat=b['lat'], lng=b['lng'])) * 1000 < MIN_FACILITY_SEPARATION_M:
                raise ValueError(f'synthetic facilities overlap: {a["label"]} / {b["label"]}')
    return out


class _SupportGraph:
    """Node iteration limited to the walk support. No full graph is carried."""

    def __init__(self, nodes):
        self.nodes = tuple(nodes)

    def reverse(self, copy=False):
        # Only used for familiar-route guidance, which this persona never has
        # (walk() checks). Fail loudly rather than search a truncated graph.
        raise NotImplementedError('route guidance needs the full graph')


class SyntheticEnvNetwork:
    """Read-only road network view adding synthetic facility distances.

    env(node) -> {'<feature>_m': distance to the nearest synthetic facility}.
    The wrapped network object and its node_env are never modified.

    support_km=None wraps the live network (full graph, used for the
    equivalence check). Otherwise it is a picklable snapshot: Population gives
    zero weight to any node farther than its p95 cap from the start, so the
    nodes within the cap plus one road hop are exactly what a walk can read.
    walk() refuses a population whose cap or start differs from the snapshot.
    """

    def __init__(self, net, facilities, *, support_center=None, support_km=None, anchors=()):
        self.facilities = facilities
        self.coverage_bbox = getattr(net, 'coverage_bbox', None)
        self.support_center, self.support_km = support_center, support_km
        self._points = {f: [GeoPoint(lat=p['lat'], lng=p['lng']) for p in facilities.get(f, [])] for f in FEATURES}
        self._env = {}
        if support_km is None:
            self._net, self.graph = net, net.graph
            self._loc, self._nbr, self._attrs, self._nearest = {}, {}, {}, {}
            return
        inner = [n for n in net.graph.nodes if haversine_km(support_center, net.node_location(n)) <= support_km]
        nodes = set(inner)
        for n in inner:
            nodes.update(net.neighbors(n))
        nodes = sorted(nodes)
        self._net, self.graph = None, _SupportGraph(nodes)
        self._loc = {n: net.node_location(n) for n in nodes}
        self._nbr = {n: net.neighbors(n) for n in nodes}
        self._attrs = {(n, v): net.edge_attrs(n, v) for n in nodes for v in self._nbr[n]}
        self._nearest = {(p.lat, p.lng): net.nearest_node(p) for p in anchors}

    def _get(self, cache, key, load):
        if key not in cache:
            if self._net is None:
                raise KeyError(f'{key} is outside the walk support snapshot')
            cache[key] = load()
        return cache[key]

    def env(self, node):
        if node not in self._env:
            here = self.node_location(node)
            self._env[node] = {f + '_m': round(min(haversine_km(here, p) for p in pts) * 1000, 3)
                               for f, pts in self._points.items() if pts}
        return self._env[node]

    def node_location(self, node):
        return self._get(self._loc, node, lambda: self._net.node_location(node))

    def neighbors(self, node):
        return self._get(self._nbr, node, lambda: self._net.neighbors(node))

    def edge_attrs(self, u, v):
        return self._get(self._attrs, (u, v), lambda: self._net.edge_attrs(u, v))

    def nearest_node(self, point):
        return self._get(self._nearest, (point.lat, point.lng), lambda: self._net.nearest_node(point))

    def __getattr__(self, name):
        net = self.__dict__.get('_net')
        if net is None:
            raise AttributeError(name)
        return getattr(net, name)


def environment_network(net, site, personal, *, snapshot=True):
    start = GeoPoint(**site['location'])
    cap = radius.statistical_p95_km(prior().radius_lognormal)
    anchors = [start] + [GeoPoint(**g['location']) for g in site['goals']]
    env = SyntheticEnvNetwork(net, facility_points(net, site, personal),
                              support_center=start if snapshot else None,
                              support_km=cap if snapshot else None, anchors=anchors)
    env.places_key = places_key(site, personal)
    return env


# ── 3. observation scenarios ───────────────────────────────────────────────
# Behavior: (fact, value, from_minute, until_minute). Gaps are unobserved
# (None), never filled in. Environment: (feature, from, until, noisy, crowded),
# applied at every facility of that feature within OBSERVATION_RADIUS_M.
SCENARIOS = {
    'S1_morning_lost': {
        'description': '오전 08:00 출발. 절반은 등록 장소를 향해 출발해 도착 조건이 생김. 길 잃음 인지 꺼짐→켜짐→꺼짐→켜짐, '
                       '장소 알아봄은 인지와 다른 시각에 바뀜, 가족 부재→도착→다시 부재, 비 50분, 통증 두 번, '
                       '짧은 어두운 구간(지하보도 가정). 장소 혼잡·소음은 보행자가 시설 근처에 많은 초반에 조합이 바뀜',
        'start': datetime(2026, 9, 28, 8, 0), 'horizon': 360,
        'strategy': {'random_walk': 0.5, 'landmark_seeking': 0.5},
        'behavior': [
            ('lost_awareness', False, 0, 40), ('lost_awareness', True, 40, 200),
            ('lost_awareness', False, 200, 260), ('lost_awareness', True, 260, 360),
            ('target_recognized', True, 5, 30), ('target_recognized', False, 30, 90),
            ('target_recognized', True, 90, 170), ('target_recognized', False, 170, 300),
            ('target_recognized', True, 300, 360),
            ('family_present', False, 0, 150), ('family_present', True, 150, 210), ('family_present', False, 210, 360),
            ('rain_observed', False, 0, 20), ('rain_observed', True, 20, 70), ('rain_observed', False, 70, 360),
            ('pain_observed', False, 0, 30), ('pain_observed', True, 30, 50), ('pain_observed', False, 50, 180),
            ('pain_observed', True, 180, 205), ('pain_observed', False, 205, 360),
            ('dark_observed', False, 0, 220), ('dark_observed', True, 220, 250), ('dark_observed', False, 250, 360)],
        'environment': [
            ('market', 0, 25, True, True), ('market', 25, 60, True, False),
            ('market', 60, 100, False, True), ('market', 100, 360, False, False),
            ('park', 0, 40, False, True), ('park', 40, 200, False, False), ('park', 200, 360, False, True),
            ('forest', 0, 10, False, False), ('forest', 10, 45, True, False), ('forest', 45, 80, False, False),
            ('forest', 80, 130, True, False), ('forest', 130, 360, False, False),
            ('water', 0, 20, True, False), ('water', 20, 80, False, True), ('water', 80, 360, False, False)]},
    'S2_evening_midnight_dark': {
        'description': '저녁 18:30 출발, 자정을 넘겨 00:30까지. 18:50부터 어두움, 가족이 있다가 없어지고 잠깐 '
                       '돌아왔다 다시 없음, 길 잃음 인지 변화, 비 80분, 통증 한 번',
        'start': datetime(2026, 9, 28, 18, 30), 'horizon': 360,
        'strategy': {'random_walk': 1.0},
        'behavior': [
            ('dark_observed', False, 0, 20), ('dark_observed', True, 20, 360),
            ('family_present', True, 0, 60), ('family_present', False, 60, 200),
            ('family_present', True, 200, 230), ('family_present', False, 230, 360),
            ('lost_awareness', False, 0, 45), ('lost_awareness', True, 45, 180),
            ('lost_awareness', False, 180, 240), ('lost_awareness', True, 240, 360),
            ('target_recognized', True, 0, 70), ('target_recognized', False, 70, 160),
            ('target_recognized', True, 220, 300), ('target_recognized', False, 300, 360),
            ('rain_observed', False, 0, 120), ('rain_observed', True, 120, 200), ('rain_observed', False, 200, 360),
            ('pain_observed', False, 0, 100), ('pain_observed', True, 100, 125), ('pain_observed', False, 125, 360)],
        'environment': [
            ('market', 0, 40, True, True), ('market', 40, 100, True, False), ('market', 100, 360, False, False),
            ('park', 0, 25, False, False), ('park', 25, 90, False, True), ('park', 90, 360, False, False),
            ('forest', 0, 30, False, False), ('forest', 30, 90, True, False), ('forest', 90, 360, False, False),
            ('water', 0, 50, False, True), ('water', 50, 110, True, False), ('water', 110, 360, False, False)]},
    'S3_sparse_afternoon': {
        'description': '오후 14:30 출발. 관측이 거의 없음: 가족 동행 60분과 가족 부재 90분, 비 40분만 관측. '
                       '나머지 사실과 장소 혼잡·소음은 미관찰로 남겨 엔진의 가능 분기로 처리',
        'start': datetime(2026, 9, 28, 14, 30), 'horizon': 360,
        'strategy': {'random_walk': 1.0},
        'behavior': [('family_present', True, 0, 60), ('family_present', False, 150, 240),
                     ('rain_observed', True, 60, 100)],
        'environment': []},
}


def behavior_observations(scenario):
    t0 = scenario['start']
    return [BehaviorObservation(fact=f, value=v, valid_from=t0 + timedelta(minutes=a),
                                valid_until=t0 + timedelta(minutes=b), source='synthetic_scenario')
            for f, v, a, b in scenario['behavior']]


def environment_observations(scenario, facilities):
    t0, out = scenario['start'], []
    for feature, a, b, noisy, crowded in scenario['environment']:
        for p in facilities.get(feature, []):
            out.append(EnvironmentObservation(feature=feature, location=GeoPoint(lat=p['lat'], lng=p['lng']),
                                              radius_m=OBSERVATION_RADIUS_M, valid_from=t0 + timedelta(minutes=a),
                                              valid_until=t0 + timedelta(minutes=b), noisy=noisy, crowded=crowded,
                                              source='synthetic_scenario'))
    return out


def fact_states(scenario, fact, step=1.0):
    """Observed states of one behavior fact over the horizon (None = unobserved)."""
    states, minute = set(), 0.0
    while minute < scenario['horizon']:
        values = {v for f, v, a, b in scenario['behavior'] if f == fact and a <= minute < b}
        states.add(next(iter(values)) if len(values) == 1 else None)
        minute += step
    return states


# ── walking and metrics ────────────────────────────────────────────────────
def _avoid_target(part):
    return ('place:' + '+'.join(sorted(part.avoid_labels)) if part.avoid_labels
            else 'feature:' + str(part.avoid_feature))


def empty_policy(personal):
    """What an output dropping every behavior compiles to: fixed rules only."""
    return Policy(rules=fixed_rules(personal), unrepresented=[])


def walk(env_net, site, personal, policy, scenario, *, walkers, seed, observer=None):
    if getattr(env_net, 'places_key', None) != places_key(site, personal):
        raise ValueError('environment network was built for other registered places')
    start = GeoPoint(**site['location'])
    p = person(start)
    p.attraction_points = [AttractionPoint(label=x['label'], location=GeoPoint(**g['location']),
                                           place_type=x['place_type'])
                           for x, g in zip(personal['places'], site['goals'])]
    if p.route_familiarity or any(a.origin_slot == 'routine_destinations' for a in p.attraction_points):
        raise RuntimeError('route guidance is outside this snapshot design')
    base = prior()
    base.strategy_probs = dict(scenario['strategy'])
    base.attraction_weights = {a.label: 1.0 for a in p.attraction_points}
    track = {}

    def hook(part, loc):
        t = track.setdefault(part.seed, [set(), 0.0])
        if part.mode == 'avoid':
            t[0].add(_avoid_target(part))
        if part.continuous_walk > t[1]:
            t[1] = part.continuous_walk
        if observer is not None:
            observer(part, loc)

    pop = Population(env_net, p, base, policy, start, scenario['start'], count=walkers, seed=seed,
                     behavior_observations=behavior_observations(scenario),
                     environment_observations=environment_observations(scenario, env_net.facilities),
                     trace_hook=hook)
    if env_net.support_km is not None and (pop.cap > env_net.support_km + 1e-9
                                           or haversine_km(start, env_net.support_center) > 1e-9):
        raise RuntimeError('walk support snapshot smaller than the population radius cap')
    out = pop.advance_to(scenario['horizon'])
    parts = pop.particles
    avoid_by_target, rule_minutes = {}, {}
    for t, _ in track.values():
        for target in t:
            avoid_by_target[target] = avoid_by_target.get(target, 0) + 1
    for x in parts:
        for rid, minutes in x.rule_minutes.items():
            rule_minutes[rid] = rule_minutes.get(rid, 0.0) + minutes
    return {'mass': round(sum(out['cells'].values()) + out['quality']['unresolved_mass'], 9),
            'mean_wait': round(statistics.mean(x.waiting for x in parts), 4),
            'mean_personal_rest': round(statistics.mean(x.rest - x.population_rest_minutes for x in parts), 4),
            'mean_path_km': round(statistics.mean(x.distance for x in parts) / 1000, 4),
            'mean_max_continuous_walk_min': round(statistics.mean(
                max(track.get(x.seed, [None, 0.0])[1], x.continuous_walk) for x in parts), 4),
            'avoid_walkers': sum(bool(t) for t, _ in track.values()),
            'avoid_by_target': dict(sorted(avoid_by_target.items())),
            'arrived': {a.label: sum(a.label in x.completed_goals for x in parts) for a in p.attraction_points},
            'unresolved': dict(sorted(out['quality']['unresolved_reasons'].items())),
            'rule_minutes': {k: round(v, 3) for k, v in sorted(rule_minutes.items())}}


def rule_set(policy):
    """Rules as an unordered set without ids or evidence (diagnostic only; never walked)."""
    rules = [r.model_dump(exclude={'evidence'}) for r in policy.rules]
    body = {r['id']: json.dumps({k: v for k, v in r.items() if k not in ('id', 'supersedes')},
                                ensure_ascii=False, sort_keys=True) for r in rules}
    return sorted(body[r['id']] + '|' + json.dumps(sorted(body.get(x, x) for x in r['supersedes']),
                                                   ensure_ascii=False) for r in rules)


def walk_key(scenario_name, seed, walkers, site, personal, policy):
    """Everything the walk depends on. Evidence quotes do not reach Population."""
    rules = [r.model_dump(exclude={'evidence'}) for r in policy.rules]
    return hashlib.sha256(json.dumps([scenario_name, seed, walkers, places_key(site, personal), rules],
                                     ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _walk_or_refusal(env_net, site, walkers, personal, policy, scenario_name, seed):
    """An engine refusal of a valid policy is recorded, never repaired."""
    try:
        return walk(env_net, site, personal, policy, SCENARIOS[scenario_name], walkers=walkers, seed=seed)
    except ValueError as error:
        return {'engine_error': str(error).splitlines()[0][:200]}


_WORKER = {}


def _offline(*a, **k):
    raise RuntimeError('offline replay forbids network')


def _init_worker(env_net, site, walkers):
    socket.socket.connect = _offline
    _WORKER.update(env_net=env_net, site=site, walkers=walkers)


def _walk_task(task):
    key, personal, policy, scenario_name, seed = task
    t = time.monotonic()
    m = _walk_or_refusal(_WORKER['env_net'], _WORKER['site'], _WORKER['walkers'], personal,
                         Policy.model_validate(policy), scenario_name, seed)
    return key, m, time.monotonic() - t


class Runner:
    """Deterministic walk cache over unique (scenario, seed, policy) keys."""

    def __init__(self, env_net, site, walkers, workers=1):
        self.env_net, self.site, self.walkers, self.workers = env_net, site, walkers, workers
        self.cache, self.walked, self.seconds = {}, 0, 0.0
        self.pool = (ProcessPoolExecutor(workers, mp_context=get_context('spawn'), initializer=_init_worker,
                                         initargs=(env_net, site, walkers)) if workers > 1 else None)

    def close(self):
        if self.pool is not None:
            self.pool.shutdown()

    def run(self, requests, label=''):
        """requests: [(personal, policy, scenario_name, seed)] -> metrics in the same order."""
        keys, todo = [], {}
        for personal, policy, s, seed in requests:
            key = walk_key(s, seed, self.walkers, self.site, personal, policy)
            keys.append(key)
            if key not in self.cache and key not in todo:
                todo[key] = (key, personal, policy.model_dump(), s, seed)
        started = time.monotonic()
        if self.pool is None:
            done = (_walk_in_process(self, t) for t in todo.values())
        else:
            done = (f.result() for f in as_completed([self.pool.submit(_walk_task, t) for t in todo.values()]))
        for i, (key, m, seconds) in enumerate(done, 1):
            self.cache[key], self.walked, self.seconds = m, self.walked + 1, self.seconds + seconds
            if i % 25 == 0 or i == len(todo):
                print(json.dumps({'phase': label, 'walked': i, 'of': len(todo),
                                  'elapsed_s': round(time.monotonic() - started, 1)}), flush=True)
        return [self.cache[k] for k in keys]


def _walk_in_process(runner, task):
    key, personal, policy, scenario_name, seed = task
    t = time.monotonic()
    m = _walk_or_refusal(runner.env_net, runner.site, runner.walkers, personal, Policy.model_validate(policy),
                         scenario_name, seed)
    return key, m, time.monotonic() - t


# ── 4. comparison with a per-input seed-noise tolerance ────────────────────
SCALAR_FAMILIES = {'mean_wait': 'wait', 'mean_personal_rest': 'personal_rest', 'mean_path_km': 'path_km',
                   'mean_max_continuous_walk_min': 'max_continuous_walk', 'avoid_walkers': 'avoid'}
# Resolution floor only (rounding of the reported means; counts are exact).
FLOOR = {'wait': 0.001, 'personal_rest': 0.001, 'path_km': 0.0001, 'max_continuous_walk': 0.001,
         'avoid': 0, 'arrived': 0}
# A tolerance is a dict keyed by component ('mean_wait', 'arrived:느티공원', ...)
# and/or by family ('wait', 'arrived', ...); see tolerance_of().


def components(m):
    c = {k: m[k] for k in SCALAR_FAMILIES}
    c.update({'avoid:' + t: n for t, n in m['avoid_by_target'].items()})
    c.update({'arrived:' + g: n for g, n in m['arrived'].items()})
    return c


def family(component):
    return SCALAR_FAMILIES.get(component) or component.split(':', 1)[0]


def differences(a, b):
    """Signed a - b per component; a component absent on one side counts as 0."""
    ca, cb = components(a), components(b)
    return {k: round(ca.get(k, 0) - cb.get(k, 0), 6) for k in sorted(set(ca) | set(cb))}


def tolerance_of(tolerance, component):
    """The component's own entry, else its family's entry, never below the rounding floor."""
    f = family(component)
    return max(tolerance.get(component, 0), tolerance.get(f, 0), FLOOR[f])


def beyond(diffs, tolerance):
    return {k: d for k, d in diffs.items() if abs(d) > tolerance_of(tolerance, k) + 1e-9}


def reversed_policy(policy):
    """Same rules in reverse list order (references only, for calibration; never a K output)."""
    return Policy.model_validate({**policy.model_dump(), 'rules': policy.model_dump()['rules'][::-1]})


def input_tolerance(samples):
    """Per-component range (max - min) over walks of ONE reference policy in one scenario.

    samples: the reference at the comparison seed, at the noise seeds and, for a
    multi-rule reference, with its rules reversed (same meaning; the engine picks
    among simultaneously active rules by list position). A same-seed K walk of
    an equivalent output can differ from the reference only by such
    re-randomization, so a difference inside this input's own range is not
    evidence of a different behavior. A component absent from a walk counts as
    0; engine errors are left out; with fewer than two usable samples only the
    rounding floor remains (exact comparison).
    """
    ok = [components(m) for m in samples if 'engine_error' not in m]
    keys = sorted(set().union(*ok)) if ok else []
    return {k: round(max(FLOOR[family(k)], max(c.get(k, 0) for c in ok) - min(c.get(k, 0) for c in ok)), 6)
            for k in keys}


def pooled_tolerance(per_input):
    """Sensitivity view only: the largest per-input value per family, and the input that set it.

    per_input: {input_id: tolerance of one scenario}. One noisy input sets the
    value for every input here, which lets wrong outputs of quiet inputs pass;
    the primary judgment never uses it.
    """
    out, source = dict(FLOOR), {f: None for f in FLOOR}
    for iid in sorted(per_input):
        for k, v in sorted(per_input[iid].items()):
            f = family(k)
            if v > out[f]:
                out[f], source[f] = v, {'input_id': iid, 'component': k, 'value': v}
    return out, source


def pair_tolerance(ta, tb):
    """Component-wise larger of two tolerances (a pair carries both inputs' noise)."""
    return {k: max(ta.get(k, 0), tb.get(k, 0)) for k in sorted(set(ta) | set(tb))}


def tolerance_spread(per_input):
    """Distribution of per-input component tolerances per family (one scenario)."""
    values = {f: [] for f in FLOOR}
    for tol in per_input.values():
        for k, v in tol.items():
            values[family(k)].append(v)
    out = {}
    for f, vals in values.items():
        v = sorted(vals)

        def q(p):
            return v[min(len(v) - 1, int(math.ceil(p * len(v))) - 1)]
        out[f] = ({'n': len(v), 'above_floor': sum(x > FLOOR[f] for x in v), 'median': q(0.5), 'q90': q(0.9),
                   'max': v[-1]} if v else {'n': 0})
    return out


def compare(k, ref, tolerance):
    """(within tolerance, signed differences k - ref, components beyond)."""
    if 'engine_error' in k:
        return False, None, None
    diffs = differences(k, ref)
    out = beyond(diffs, tolerance)
    return not out, diffs, out


def discriminable(ref_by_scenario, null_by_scenario, tolerances):
    """Per scenario: does the reference walk differ from the empty-policy walk?

    tolerances: {scenario: tolerance} of THIS input (per-input view).
    """
    out = {}
    for s, ref in ref_by_scenario.items():
        null = null_by_scenario[s]
        if 'engine_error' in ref or 'engine_error' in null:
            out[s] = {'discriminable': False, 'reason': 'engine_error'}
            continue
        diffs = differences(ref, null)
        over = beyond(diffs, tolerances[s])
        out[s] = {'discriminable': bool(over), 'beyond': over,
                  'bit_identical': all(d == 0 for d in diffs.values())}
    return out


def judge(k_by_scenario, ref_by_scenario, tolerances):
    """Preservation of one K response in every scenario; failures stay counted.

    tolerances: {scenario: tolerance} of the response's own input.
    """
    out = {'walkable': k_by_scenario is not None, 'engine_error': False, 'preserved': False, 'scenarios': {}}
    if k_by_scenario is None:
        return out
    ok_all = True
    for s, ref in ref_by_scenario.items():
        if 'engine_error' in ref:
            out['scenarios'][s] = {'reference_engine_error': ref['engine_error']}
            continue
        ok, _, over = compare(k_by_scenario[s], ref, tolerances[s])
        out['engine_error'] = out['engine_error'] or 'engine_error' in k_by_scenario[s]
        out['scenarios'][s] = {'within_tolerance': ok, 'beyond': over}
        ok_all = ok_all and ok
    out['preserved'] = ok_all
    return out


# ── 5. pairs inside a root ─────────────────────────────────────────────────
def pair_relation(rel_a, rel_b):
    changed = (rel_a == 'change') + (rel_b == 'change')
    return 'same' if changed == 0 else 'changed' if changed == 1 else None


def k_pair(ka, kb, ref_beyond_by_scenario, tolerances, relation):
    """One K response pair. ka/kb: {scenario: metrics} or None (output not walkable).

    tolerances: {scenario: tolerance} of the pair (pair_tolerance of both inputs).
    """
    if ka is None or kb is None:
        return {'status': 'not_walkable'}
    if any('engine_error' in ka[s] or 'engine_error' in kb[s] for s in ka):
        return {'status': 'engine_error'}
    if relation == 'same':
        moved = {s: beyond(differences(ka[s], kb[s]), tolerances[s]) for s in ka}
        return {'status': 'compared', 'equal': not any(moved.values()),
                'k_beyond': {s: m for s, m in moved.items() if m}}
    checks, all_ok, any_ok = {}, True, False
    for s, ref_over in ref_beyond_by_scenario.items():
        k_diff = differences(ka[s], kb[s])
        for c, d in ref_over.items():
            kd = k_diff.get(c, 0)
            ok = abs(kd) > tolerance_of(tolerances[s], c) + 1e-9 and (kd > 0) == (d > 0)
            checks.setdefault(s, {})[c] = {'reference': d, 'k': kd, 'same_direction': ok}
            all_ok, any_ok = all_ok and ok, any_ok or ok
    return {'status': 'compared', 'same_direction_all': all_ok, 'same_direction_any': any_ok, 'checks': checks}


def pair_report(inputs, relations, ref_walks, k_walks, tolerances, discrimination, ref_rule_sets=None):
    """inputs: {input_id: root_id}; k_walks: {(input_id, rep): {scenario: metrics} | None};
    tolerances: {input_id: {scenario: tolerance}}."""
    roots, details, skipped = {}, [], 0
    for iid, root in inputs.items():
        roots.setdefault(root, []).append(iid)
    for root, ids in sorted(roots.items()):
        ids = sorted(ids)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                relation = pair_relation(relations[a], relations[b])
                if relation is None:
                    skipped += 1
                    continue
                tol = {s: pair_tolerance(tolerances[a][s], tolerances[b][s]) for s in ref_walks[a]}
                ref_over = {s: beyond(differences(ref_walks[a][s], ref_walks[b][s]), tol[s])
                            for s in ref_walks[a]
                            if 'engine_error' not in ref_walks[a][s] and 'engine_error' not in ref_walks[b][s]}
                ref_over = {s: o for s, o in ref_over.items() if o}
                nontrivial = any(v['discriminable'] for x in (a, b) for v in discrimination[x].values())
                row = {'root_id': root, 'a': a, 'b': b, 'relation': relation, 'reference_beyond': ref_over,
                       'reference_differs': bool(ref_over), 'nontrivial': nontrivial, 'k': {}}
                for r in sorted({r for (x, r) in k_walks if x in (a, b)}):
                    if (a, r) in k_walks and (b, r) in k_walks:
                        row['k'][r] = k_pair(k_walks[a, r], k_walks[b, r], ref_over, tol, relation)
                details.append(row)

    def count(rows, pred):
        return sum(pred(x) for r in rows for x in r['k'].values())

    changed = [r for r in details if r['relation'] == 'changed']
    measurable = [r for r in changed if r['reference_differs']]
    same = [r for r in details if r['relation'] == 'same']
    same_eq = [r for r in same if not r['reference_differs']]
    nontrivial_eq = [r for r in same_eq if r['nontrivial']]
    summary = {
        'changed_meaning': {
            'pairs': len(changed), 'reference_walks_differ': len(measurable),
            'not_measurable_with_these_scenarios': len(changed) - len(measurable),
            'k_comparisons': count(measurable, lambda x: True),
            'k_same_direction_all_components': count(measurable, lambda x: x.get('same_direction_all') is True),
            'k_same_direction_any_component': count(measurable, lambda x: x.get('same_direction_any') is True),
            'k_not_walkable': count(measurable, lambda x: x['status'] == 'not_walkable'),
            'k_engine_error': count(measurable, lambda x: x['status'] == 'engine_error')},
        'same_meaning': {
            'pairs': len(same), 'reference_walks_equal': len(same_eq),
            'reference_walks_differ': [{'pair': f"{r['a']}~{r['b']}", 'same_reference_rule_set':
                                        None if ref_rule_sets is None
                                        else ref_rule_sets[r['a']] == ref_rule_sets[r['b']]}
                                       for r in same if r['reference_differs']],
            'k_comparisons': count(same_eq, lambda x: True),
            'k_equal': count(same_eq, lambda x: x.get('equal') is True),
            'k_not_walkable': count(same_eq, lambda x: x['status'] == 'not_walkable'),
            'k_engine_error': count(same_eq, lambda x: x['status'] == 'engine_error'),
            'nontrivial_k_comparisons': count(nontrivial_eq, lambda x: True),
            'nontrivial_k_equal': count(nontrivial_eq, lambda x: x.get('equal') is True)},
        'both_changed_pairs_skipped': skipped,
        'rule': ('changed: a K pair passes when every component where the references differ beyond tolerance '
                 'also differs beyond tolerance with the same sign, in every scenario. same: a K pair passes when '
                 'no component differs beyond tolerance in any scenario (pairs whose references are equal). '
                 'nontrivial = either side has a reference distinguishable from the empty policy. K responses are '
                 'paired by repetition index. A not-walkable side fails the comparison. A pair uses the '
                 'component-wise larger tolerance of its two inputs; each input tolerance already contains the '
                 'reverse-order walk of a multi-rule reference, because the engine picks among simultaneously '
                 'active rules by list position.')}
    return summary, details


# ── 2/6. preservation summary ──────────────────────────────────────────────
def preservation(rows, discrimination):
    """rows: dicts with input_id, form, family, walkable, engine_error, preserved and
    optionally same_rule_set (rules equal to the reference up to ids, order and
    evidence). Those responses stay in the denominator; they are only counted
    apart so an order-only walk mismatch is visible, never re-judged."""
    disc_ids = {i for i, d in discrimination.items() if any(v['discriminable'] for v in d.values())}

    def block(sel):
        out = {'responses': len(sel), 'preserved': sum(r['preserved'] for r in sel),
               'not_walkable_in_denominator': sum(not r['walkable'] for r in sel),
               'engine_error_in_denominator': sum(r['engine_error'] for r in sel),
               'same_rule_set_in_denominator': sum(r.get('same_rule_set') is True for r in sel),
               'same_rule_set_walk_mismatch': sum(r.get('same_rule_set') is True and not r['preserved']
                                                  for r in sel)}
        out['rate'] = round(out['preserved'] / out['responses'], 4) if sel else None
        return out

    def by(sel, key):
        return {k: block([r for r in sel if str(r[key]) == k]) for k in sorted({str(r[key]) for r in sel})}

    disc = [r for r in rows if r['input_id'] in disc_ids]
    other = [r for r in rows if r['input_id'] not in disc_ids]
    return {'discriminable_inputs': len(disc_ids & {r['input_id'] for r in rows}),
            'non_discriminable_inputs': len({r['input_id'] for r in other}),
            'non_discriminable_input_ids': sorted({r['input_id'] for r in other}),
            'discriminable_by_scenario': {s: sum(d[s]['discriminable'] for d in discrimination.values())
                                          for s in next(iter(discrimination.values()), {})},
            'discriminable': block(disc) | {'by_form': by(disc, 'form'), 'by_family': by(disc, 'family')},
            'non_discriminable_reported_apart': block(other) | {
                'note': 'reference walk equals the empty-policy walk in every scenario; not a preservation rate'},
            'all_responses': {'responses': len(rows), 'walkable': sum(r['walkable'] for r in rows),
                              'not_walkable': sum(not r['walkable'] for r in rows),
                              'engine_error': sum(r['engine_error'] for r in rows)}}


def support_equivalence(net, site, personal, policies, scenario_name, walkers, seed):
    """Snapshot vs full-graph view of the same synthetic layer must walk bit-identically.

    Also reports how much of the graph the snapshot cut away and how far the
    walkers reached, so an equality on an untruncated graph is visible as such.
    """
    full = environment_network(net, site, personal, snapshot=False)
    part = environment_network(net, site, personal, snapshot=True)
    start = GeoPoint(**site['location'])
    out = []
    for name, policy in policies:
        reach = [0.0]

        def observe(_, loc):
            reach[0] = max(reach[0], haversine_km(start, loc))
        a = walk(full, site, personal, policy, SCENARIOS[scenario_name], walkers=walkers, seed=seed)
        b = walk(part, site, personal, policy, SCENARIOS[scenario_name], walkers=walkers, seed=seed, observer=observe)
        out.append({'policy': name, 'scenario': scenario_name, 'walkers': walkers, 'identical': a == b,
                    'full_nodes': len(net.graph.nodes), 'snapshot_nodes': len(part.graph.nodes),
                    'support_km': round(part.support_km, 4), 'max_reach_km': round(reach[0], 4)})
    return out, part


def reference_plan(ids, names, reference, noise_seeds):
    """Phase A walks: reference at SEED and at every noise seed, the reverse-order
    reference at SEED when it has several rules, and the empty policy at SEED."""
    plan = []
    for iid in ids:
        pol = Policy.model_validate(reference[iid])
        kinds = [('ref', SEED, pol)] + [(f'seed{x}', x, pol) for x in noise_seeds]
        if len(pol.rules) > 1:
            kinds.append(('rev', SEED, reversed_policy(pol)))
        kinds.append(('null', SEED, None))
        plan.extend((iid, s, seed, kind, p) for s in names for kind, seed, p in kinds)
    return plan


def per_input_tolerances(ids, names, walks, noise_seeds):
    """{input_id: {scenario: tolerance}} from each input's own reference samples."""
    out = {}
    for i in ids:
        for s in names:
            samples = ([walks['ref'][i][s]] + [walks[f'seed{x}'][i][s] for x in noise_seeds]
                       + ([walks['rev'][i][s]] if i in walks.get('rev', {}) else []))
            out.setdefault(i, {})[s] = input_tolerance(samples)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scored', type=Path, required=True, help='scored.json of a run_candidate dev128 stage')
    parser.add_argument('--dataset', type=Path, default=DEV128, help='dev128 folder')
    parser.add_argument('--map', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--walkers', type=int, default=DEFAULT_WALKERS)
    parser.add_argument('--workers', type=int, default=DEFAULT_WORKERS, help='local processes; 1 = in-process')
    parser.add_argument('--scenarios', default=','.join(SCENARIOS),
                        help='comma list of scenario names, or a count N for the first N')
    parser.add_argument('--noise-seeds', default=','.join(map(str, NOISE_SEEDS)),
                        help='reference-only seeds besides the comparison seed (at least one)')
    parser.add_argument('--limit-inputs', type=int, default=None, help='timing samples only: first N inputs')
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('refusing to overwrite ' + str(args.output))
    if hashlib.sha256(args.map.read_bytes()).hexdigest() != MAP_SHA256:
        raise SystemExit('map hash differs from the verified KINTEX map')
    names = (list(SCENARIOS)[:int(args.scenarios)] if args.scenarios.isdigit()
             else [s for s in args.scenarios.split(',') if s])
    if not names or any(s not in SCENARIOS for s in names):
        raise SystemExit('unknown scenario in ' + args.scenarios)
    noise_seeds = tuple(int(x) for x in args.noise_seeds.split(',') if x.strip())
    if not noise_seeds or SEED in noise_seeds or len(set(noise_seeds)) != len(noise_seeds):
        raise SystemExit('noise seeds must be distinct and differ from the comparison seed')
    socket.socket.connect = _offline
    t_start = time.monotonic()
    site = next(s for s in json.loads((scoring.ROOT / 'sites.json').read_text())['sites'] if s['site_id'] == SITE)
    net = verified_network(args.map)
    inputs = {json.loads(x)['id']: json.loads(x)
              for x in (args.dataset / 'dev128_inputs.jsonl').read_text().splitlines() if x.strip()}
    reference = json.loads((args.dataset / 'dev128_reference.NOT_MODEL_INPUT.json').read_text())
    relations = {json.loads(x)['id']: json.loads(x)['expected_relation']
                 for x in (args.dataset / 'dev128_review.NOT_MODEL_INPUT.jsonl').read_text().splitlines()
                 if x.strip()}
    rows = json.loads(args.scored.read_text())['rows']
    ids = sorted({r['input_id'] for r in rows})
    if args.limit_inputs:
        ids = ids[:args.limit_inputs]
        rows = [r for r in rows if r['input_id'] in set(ids)]
    if len({places_key(site, inputs[i]['personal']) for i in ids}) != 1:
        raise SystemExit('this run expects one registered place set per site')
    first = inputs[ids[0]]['personal']
    probe = [('reference:' + ids[0], Policy.model_validate(reference[ids[0]])), ('empty', empty_policy(first))]
    equivalence, env_net = support_equivalence(net, site, first, probe, names[0], min(args.walkers, 10), SEED)
    determinism = []
    for s in names:
        a = walk(env_net, site, first, probe[0][1], SCENARIOS[s], walkers=args.walkers, seed=SEED)
        b = walk(env_net, site, first, probe[0][1], SCENARIOS[s], walkers=args.walkers, seed=SEED)
        determinism.append({'scenario': s, 'identical': a == b, 'in_process': a})
    if not all(x['identical'] for x in equivalence + determinism):
        raise SystemExit('walk support or determinism check failed')
    t_checks = time.monotonic() - t_start
    runner = Runner(env_net, site, args.walkers, args.workers)
    try:
        # Phase A: references (all seeds, reverse order) and the empty policy. No K walk yet.
        t_a = time.monotonic()
        plan = reference_plan(ids, names, reference, noise_seeds)
        got = runner.run([(inputs[iid]['personal'], empty_policy(inputs[iid]['personal']) if p is None else p, s, seed)
                          for iid, s, seed, _, p in plan], 'reference')
        walks = {}
        for (iid, s, _, kind, _), m in zip(plan, got):
            walks.setdefault(kind, {}).setdefault(iid, {})[s] = m
        ref_walks, null_walks = walks['ref'], walks['null']
        for x in determinism:  # spawned workers reproduce the in-process walk
            x['worker_identical'] = ref_walks[ids[0]][x['scenario']] == x.pop('in_process')
        if not all(x['worker_identical'] for x in determinism):
            raise SystemExit('worker walks differ from the in-process walk')
        per_input = per_input_tolerances(ids, names, walks, noise_seeds)
        pooled, pooled_source = {}, {}
        for s in names:
            pooled[s], pooled_source[s] = pooled_tolerance({i: per_input[i][s] for i in ids})
        modes = {'per_input': per_input, 'pooled_max': {i: pooled for i in ids},
                 'exact': {i: {s: dict(FLOOR) for s in names} for i in ids}}
        discrimination = {m: {i: discriminable(ref_walks[i], null_walks[i], t[i]) for i in ids}
                          for m, t in modes.items()}
        # Phase B: every K response (failed outputs stay as not walkable).
        t_b = time.monotonic()
        walkable = [r for r in rows if r['policy'] is not None]
        plan = [(r['input_id'], r['rep'], s) for r in walkable for s in names]
        got = runner.run([(inputs[r['input_id']]['personal'], Policy.model_validate(r['policy']), s, SEED)
                          for r in walkable for s in names], 'k')
        k_walks = {(r['input_id'], r['rep']): None for r in rows}
        for (iid, rep, s), m in zip(plan, got):
            k_walks[iid, rep] = (k_walks[iid, rep] or {}) | {s: m}
    finally:
        runner.close()
    results, summaries, pairs = [], {}, {}
    ref_sets = {i: rule_set(Policy.model_validate(reference[i])) for i in ids}
    for r in rows:
        row = {'input_id': r['input_id'], 'root_id': r['root_id'], 'form': r['form'], 'family': r.get('family'),
               'rep': r['rep'], 'final_problem': r.get('final_problem'),
               'same_rule_set_as_reference': (None if r['policy'] is None else
                                              rule_set(Policy.model_validate(r['policy'])) == ref_sets[r['input_id']]),
               'k_walks': k_walks[r['input_id'], r['rep']]}
        for m, t in modes.items():
            row[m] = judge(k_walks[r['input_id'], r['rep']], ref_walks[r['input_id']], t[r['input_id']])
            row[m]['discriminable'] = any(v['discriminable'] for v in discrimination[m][r['input_id']].values())
        results.append(row)
    pair_details = {}
    for m, t in modes.items():
        flat = [{'input_id': x['input_id'], 'form': x['form'], 'family': x['family'],
                 'same_rule_set': x['same_rule_set_as_reference']} | x[m] for x in results]
        summaries[m] = preservation(flat, discrimination[m])
        pairs[m], pair_details[m] = pair_report({i: inputs[i]['root_id'] for i in ids}, relations, ref_walks,
                                                k_walks, t, discrimination[m], ref_sets)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        'scope': ('real K outputs vs authored references on one KINTEX start under three synthetic observation '
                  'scenarios; propagation on roads, not location accuracy or clinical validity'),
        'version': 'engine_outputs_v2', 'model_calls': 0, 'network_calls': 0, 'scored': str(args.scored),
        'map_sha256': MAP_SHA256, 'site': SITE, 'seed': SEED, 'noise_seeds': list(noise_seeds),
        'walkers': args.walkers, 'workers': args.workers,
        'synthetic_environment': {
            'label': SYNTHETIC_LABEL, 'facilities': env_net.facilities, 'observation_radius_m': OBSERVATION_RADIUS_M,
            'perception_limits_m': PERCEPTION_M,
            'engine_side_effects': ('the product engine also reads forest_m for its existing hostile-exposure gauge '
                                    '(<=30 m), which feeds anxiety_high; env_responses are empty for this persona, '
                                    'so no other movement weighting changes')},
        'scenarios': {s: {k: (v.isoformat() if isinstance(v, datetime) else v)
                          for k, v in SCENARIOS[s].items()} for s in names},
        'clock_handling': ('Population(started_at=scenario start, naive Asia/Seoul local time): observation windows '
                           'use started_at + minute and clock_hour uses the same origin; S2 crosses midnight'),
        'tolerance': {
            'primary': 'per_input',
            'rule': ('per input, scenario and metric component: the range (max - min) of that input\'s own '
                     f'reference walked with seeds {[SEED, *noise_seeds]} and, when it has several rules, with its '
                     'rules in reverse order at seed 17 (the engine picks among simultaneously active rules by list '
                     'position). Floored at the rounding resolution; a component the reference never shows has '
                     'only the floor. Fixed from references before any K walk is compared. K and reference share '
                     'seed 17, so an identical policy walks bit-identically; the range only forgives '
                     're-randomization by a differently structured equivalent output. A pair of inputs uses the '
                     'component-wise larger tolerance of the two.'),
            'per_input_by_scenario': per_input,
            'per_input_spread': {s: tolerance_spread({i: per_input[i][s] for i in ids}) for s in names},
            'sensitivity_pooled_max': {
                'by_scenario': pooled, 'set_by': pooled_source,
                'note': ('previous rule: one value per scenario and family = the largest per-input value; the '
                         'input in set_by decides it for every input, so wrong outputs of quiet inputs can pass')},
            'sensitivity_exact': ('same-seed determinism verified (checks.same_seed_determinism); exact view uses '
                                  'only the rounding floor'), 'floor': FLOOR},
        'checks': {'support_equivalence_full_graph': equivalence, 'same_seed_determinism': determinism},
        'summary': summaries, 'pairs': pairs, 'discrimination': discrimination, 'pair_details': pair_details,
        'reference_walks': ref_walks, 'empty_policy_walks': null_walks,
        'reference_noise_walks': {str(x): walks[f'seed{x}'] for x in noise_seeds},
        'reference_reversed_walks': walks.get('rev', {}),
        'results': results,
        'runtime': {'seconds_total': round(time.monotonic() - t_start, 1), 'seconds_map_and_checks': round(t_checks, 1),
                    'seconds_references': round(t_b - t_a, 1), 'seconds_k': round(time.monotonic() - t_b, 1),
                    'unique_walks': runner.walked, 'walk_cpu_seconds': round(runner.seconds, 1),
                    'inputs': len(ids), 'responses': len(rows), 'scenarios': len(names)}},
        ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({m: {'preservation': summaries[m]['discriminable'], 'pairs': pairs[m]} for m in modes},
                     ensure_ascii=False))


if __name__ == '__main__':
    # Run through the package module so pickled objects resolve in spawned workers.
    from experiments.mind_contract_ab_20261007.engine_outputs_v2 import main as _main
    _main()
