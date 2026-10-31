"""Representative walker traces (continuous_state.walker_traces, contract v1).

Spatial tests walk the verified KINTEX road fixture; there is no synthetic
geography. Pure helpers are checked on explicit point lists.
"""
import copy
import json
import math
import random
import sqlite3
from datetime import timedelta
from itertools import pairwise

import pytest

from app import storage
from app.config import settings
from app.llm import mind_policy
from app.phase2 import continuous_prediction, pipeline, walker_traces
from app.phase2.simulation import STRATEGIES
from app.schemas.prediction import LognormalParams, PriorParams
from tests import kintex_fixtures
from tests.kintex_fixtures import START
from tests.test_continuous_prediction import case_for, prepared
from tests.test_person_policy import obs

WALKERS = 40
geography = kintex_fixtures.geography  # verified KINTEX road fixture


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    storage.reset_for_tests()
    monkeypatch.setattr(settings, 'mc_num_walkers', WALKERS)
    monkeypatch.setattr(settings, 'walker_trace_count', 8)
    # These test executor mechanics, not model release qualification.
    monkeypatch.setattr(mind_policy, 'RELEASE_QUALIFIED', True)
    yield
    storage.reset_for_tests()


def mixed_prior():
    return PriorParams(strategy_probs={'random_walk': .3, 'route_following': .3, 'direction_keeping': .2,
                                       'staying_put': .1, 'landmark_seeking': .1},
                       attraction_weights={'등록 목적지': 1}, radius_lognormal=LognormalParams(mu=0, sigma=1))


def walk(case, person, net, hours, **kw):
    return continuous_prediction.run(case, person, mixed_prior(), net, hours, seed=42, **kw)


# ── selection ────────────────────────────────────────────────────────────

def test_largest_remainder_selection_is_exact_and_deterministic():
    # Per 20 walkers: 10 route, 6 random, 3 direction, 1 staying (50/30/15/5%).
    pattern = ['route_following'] * 10 + ['random_walk'] * 6 + ['direction_keeping'] * 3 + ['staying_put']
    strategies = [pattern[i % 20] for i in range(500)]
    # Quotas 4, 2.4, 1.2, 0.4 -> floors 4,2,1,0; the last seat is a remainder
    # tie (random 0.4 vs staying 0.4) won by the larger group.
    picked = walker_traces.select(strategies, 8, STRATEGIES)
    assert picked == [0, 1, 2, 3, 10, 11, 12, 16]
    assert walker_traces.select(list(strategies), 8, STRATEGIES) == picked
    assert walker_traces.select(strategies, 0, STRATEGIES) == []
    assert walker_traces.select(strategies[:5], 8, STRATEGIES) == [0, 1, 2, 3, 4]


@pytest.mark.parametrize('seed', range(25))
def test_selection_seats_follow_assigned_strategy_shares(seed):
    rng = random.Random(seed)
    total = rng.randint(8, 600)
    count = rng.randint(1, 12)
    strategies = rng.choices(STRATEGIES, weights=[rng.random() for _ in STRATEGIES], k=total)
    picked = walker_traces.select(strategies, count, STRATEGIES)
    assert len(picked) == min(count, total) == len(set(picked))
    for strategy in set(strategies):
        members = [i for i, s in enumerate(strategies) if s == strategy]
        quota = min(count, total) * len(members) / total
        mine = [i for i in picked if strategies[i] == strategy]
        assert math.floor(quota) <= len(mine) <= math.ceil(quota)
        assert mine == members[:len(mine)]  # lowest indices within a strategy


def test_selection_is_the_same_for_fresh_and_restored_population(geography):
    net, center = geography
    p = prepared(center)
    first = case_for(p)
    walk(first, p, net, .5)
    second = case_for(p)
    walk(second, p, net, .5)
    a = first.continuous_state['walker_traces']['walkers']
    b = second.continuous_state['walker_traces']['walkers']
    assert [w['walker_idx'] for w in a] == [w['walker_idx'] for w in b]
    assert a == b
    strategies = [x['strategy'] for x in first.continuous_state['checkpoint']['particles']]
    assert [w['walker_idx'] for w in a] == walker_traces.select(strategies, 8, STRATEGIES)
    assert [w['strategy'] for w in a] == [strategies[w['walker_idx']] for w in a]


def _population(geography):
    from tests.kintex_fixtures import person
    from tests.test_person_policy import policy
    net, center = geography
    return continuous_prediction.Population(net, person(center), mixed_prior(), policy(), center, START,
                                            count=WALKERS, seed=42)


def test_only_selected_walkers_reach_the_hook(geography):
    pop = _population(geography)
    seen = set()

    class Spy(walker_traces.Recorder):
        def __call__(self, p, loc):
            seen.add(id(p))
            super().__call__(p, loc)
    recorder = Spy(pop, 8, key='k', strategy_order=STRATEGIES)
    pop.trace_hook = recorder
    pop.advance_to(10)
    assert seen == {id(pop.particles[i]) for i in recorder.selected}


def test_trace_names_the_initial_target_even_if_a_rule_changes_it(geography):
    pop = _population(geography)
    recorder = walker_traces.Recorder(pop, 8, key='k', strategy_order=STRATEGIES)
    targeted = [i for i in recorder.selected if pop.particles[i].strategy in walker_traces.TARGET_STRATEGIES]
    assert targeted
    for i in targeted:
        pop.particles[i].target = 'a later sourced seek goal'
    walkers = {w['walker_idx']: w for w in recorder.result(pop, 0)['walkers']}
    assert all(walkers[i]['target'] == '등록 목적지' for i in targeted)


# ── recording never changes the forecast ─────────────────────────────────

def test_recording_on_or_off_gives_identical_maps_and_checkpoints(geography, monkeypatch):
    net, center = geography
    p = prepared(center)
    base = case_for(p)
    runs = {}
    for count in (8, 0):
        monkeypatch.setattr(settings, 'walker_trace_count', count)
        c = base.model_copy(deep=True)
        first = walk(c, p, net, .5)
        second = walk(c, p, net, 1)
        runs[count] = (first, second, copy.deepcopy(c.continuous_state))
    on, off = runs[8], runs[0]
    assert on[0] == off[0] and on[1] == off[1]  # cells and quality, both horizons
    assert on[1][1]['checkpoint_reused'] and on[1][1]['checkpoint_committed']
    assert on[2]['checkpoint'] == off[2]['checkpoint']
    assert on[2]['key'] == off[2]['key'] and on[2]['seed'] == off[2]['seed']
    assert 'walker_traces' in on[2] and 'walker_traces' not in off[2]


def test_recording_failure_drops_traces_but_not_the_forecast(geography, monkeypatch):
    net, center = geography
    p = prepared(center)
    base = case_for(p)
    monkeypatch.setattr(settings, 'walker_trace_count', 0)
    reference = base.model_copy(deep=True)
    expected = walk(reference, p, net, .5)
    monkeypatch.setattr(settings, 'walker_trace_count', 8)

    def broken(*a):
        raise RuntimeError('trace bug')
    monkeypatch.setattr(walker_traces, '_meters', broken)
    c = base.model_copy(deep=True)
    assert walk(c, p, net, .5) == expected
    assert c.continuous_state['checkpoint'] == reference.continuous_state['checkpoint']
    assert 'walker_traces' not in c.continuous_state


# ── continuation ─────────────────────────────────────────────────────────

def test_same_key_appends_and_key_change_starts_new_traces(geography):
    net, center = geography
    p = prepared(center)
    c = case_for(p)
    walk(c, p, net, .5)
    first = copy.deepcopy(c.continuous_state['walker_traces'])
    _, q = walk(c, p, net, 1)
    assert q['checkpoint_reused']
    second = c.continuous_state['walker_traces']
    assert second['key'] == c.continuous_state['key'] == first['key']
    assert first['until_minute'] == 30. and second['until_minute'] == 60.
    for a, b in zip(first['walkers'], second['walkers'], strict=True):
        assert (a['walker_idx'], a['strategy'], a['target']) == (b['walker_idx'], b['strategy'], b['target'])
        assert b['starts_at_minute'] == 0.
        assert b['points'][:len(a['points'])] == a['points']
        assert b['points'][-1][2] == 60.

    # A changed report changes the key: the walk and its traces restart at 0.
    fresh = c.model_copy(deep=True)
    fresh.continuous_state = {}
    for x in (c, fresh):
        x.report.behavior_observations = [obs('lost_awareness', True)]
    _, q = walk(c, p, net, 1)
    assert not q['checkpoint_reused']
    third = c.continuous_state['walker_traces']
    assert third['key'] == c.continuous_state['key'] != second['key']
    walk(fresh, p, net, 1)
    assert third == fresh.continuous_state['walker_traces']
    assert all(w['starts_at_minute'] == 0. and w['points'][0][2] == 0. for w in third['walkers'])


def test_checkpoint_without_traces_records_from_its_minute(geography, monkeypatch):
    net, center = geography
    p = prepared(center)
    c = case_for(p)
    monkeypatch.setattr(settings, 'walker_trace_count', 0)
    walk(c, p, net, .5)  # e.g. a case predicted before this feature shipped
    assert 'walker_traces' not in c.continuous_state
    monkeypatch.setattr(settings, 'walker_trace_count', 8)
    _, q = walk(c, p, net, 1)
    assert q['checkpoint_reused']
    traces = c.continuous_state['walker_traces']
    assert traces['until_minute'] == 60.
    for w in traces['walkers']:
        assert w['starts_at_minute'] == 30. and w['points'][0][2] == 30. and w['points'][-1][2] == 60.


def test_earlier_horizon_without_reuse_restarts_traces(geography):
    net, center = geography
    p = prepared(center)
    c = case_for(p)
    walk(c, p, net, 1)
    _, q = walk(c, p, net, .5)  # checkpoint is past this horizon: walk again from 0
    assert not q['checkpoint_reused']
    traces = c.continuous_state['walker_traces']
    assert traces['until_minute'] == 30.
    assert all(w['starts_at_minute'] == 0. and w['points'][-1][2] == 30. for w in traces['walkers'])


# ── shape, precision, size ───────────────────────────────────────────────

def _road_distance_m(net):
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree
    south, west, north, east = net.coverage_bbox
    lat0, lng0 = (south + north) / 2, (west + east) / 2
    k = math.cos(math.radians(lat0))

    def local(lng, lat):
        return ((lng - lng0) * 111_320 * k, (lat - lat0) * 111_320)
    lines = []
    for u, v, data in net.graph.edges(data=True):
        coords = (list(data['geometry'].coords) if data.get('geometry') is not None else
                  [(net.graph.nodes[u]['x'], net.graph.nodes[u]['y']), (net.graph.nodes[v]['x'], net.graph.nodes[v]['y'])])
        lines.append(LineString([local(x, y) for x, y in coords]))
    tree = STRtree(lines)

    def distance(lat, lng):
        point = Point(local(lng, lat))
        return point.distance(lines[tree.nearest(point)])
    return distance


def test_contract_shape_precision_and_real_road_positions(geography):
    net, center = geography
    p = prepared(center)
    c = case_for(p)
    walk(c, p, net, 1)
    traces = c.continuous_state['walker_traces']
    assert set(traces) == {'version', 'key', 'channel', 'total_walkers', 'until_minute', 'walkers'}
    assert (traces['version'], traces['channel'], traces['total_walkers']) == (1, 'personal', WALKERS)
    assert traces['key'] == c.continuous_state['key']
    assert len(traces['walkers']) == 8
    assert [w['walker_idx'] for w in traces['walkers']] == sorted(w['walker_idx'] for w in traces['walkers'])
    on_road = _road_distance_m(net)
    particles = c.continuous_state['checkpoint']['particles']
    for w in traces['walkers']:
        assert list(w) == ['walker_idx', 'strategy', 'target', 'starts_at_minute', 'points']
        assert 0 <= w['walker_idx'] < WALKERS and w['strategy'] in STRATEGIES
        if w['strategy'] in walker_traces.TARGET_STRATEGIES:
            assert w['target'] == '등록 목적지'
        else:
            assert w['target'] is None
        points = w['points']
        assert 2 <= len(points) <= walker_traces.MAX_POINTS
        minutes = [x[2] for x in points]
        assert minutes == sorted(set(minutes)) and minutes[0] == 0. and minutes[-1] == 60.
        for lat, lng, minute in points:
            assert (round(lat, 5), round(lng, 5), round(minute, 1)) == (lat, lng, minute)
            assert on_road(lat, lng) < 2.  # 5-decimal rounding is about 1 m
        # The last point is where the walker counts in the probability map.
        last = particles[w['walker_idx']]
        assert abs(last['minute'] - 60.) < 1e-6
    size = len(json.dumps(traces, ensure_ascii=False, separators=(',', ':')).encode())
    assert size < 8 * walker_traces.MAX_POINTS * 30


def test_point_cap_thins_evenly_and_keeps_endpoints(geography, monkeypatch):
    net, center = geography
    p = prepared(center)
    c = case_for(p)
    walk(c, p, net, .5)
    monkeypatch.setattr(walker_traces, 'MAX_POINTS', 6)
    walk(c, p, net, 1)
    for w in c.continuous_state['walker_traces']['walkers']:
        assert len(w['points']) <= 6
        assert w['points'][0][2] == 0. and w['points'][-1][2] == 60.


def test_thin_simplify_and_round_helpers():
    line = [(37.0, 126.0 + i * 1e-5, i * .1) for i in range(1000)]  # straight, constant speed
    assert walker_traces.simplify(line) == [line[0], line[-1]]
    thinned = walker_traces.thin(line, 400)
    assert len(thinned) == 400 and thinned[0] == line[0] and thinned[-1] == line[-1]
    gaps = {b[2] - a[2] for a, b in pairwise(thinned)}
    assert max(gaps) - min(gaps) < .11  # evenly spaced by index
    assert walker_traces.thin(line[:10], 400) == line[:10]
    merged = walker_traces.rounded([(37.000001, 126.000001, 0.), (37.00001, 126.00001, 1.04),
                                    (37.00002, 126.00002, 1.01), (37.00003, 126.00003, 1.96)])
    assert merged == [[37.0, 126.0, 0.0], [37.00002, 126.00002, 1.0], [37.00003, 126.00003, 2.0]]


def test_simplify_keeps_the_time_spent_standing_still():
    def east(m):
        return 126.0 + m / (111_320 * math.cos(math.radians(37.)))
    walk_in = [(37.0, east(i * 60), float(i)) for i in range(11)]          # 0-10 min, 600 m
    stop = [(37.0, east(600), float(t)) for t in range(15, 41, 5)]         # 10-40 min, standing
    walk_out = [(37.0 + i * 60 / 111_320, east(600), 40. + i) for i in range(1, 11)]
    simplified = walker_traces.simplify(walk_in + stop + walk_out)
    minutes = [x[2] for x in simplified]
    assert minutes == [0., 10., 40., 50.]


# ── channels, persistence, public API ────────────────────────────────────

def test_only_the_personal_channel_records(geography, monkeypatch):
    net, center = geography
    p = prepared(center)
    monkeypatch.setattr(settings, 'statistical_channel_definition', 'onboarded_population_prior')
    c = case_for(p)
    _, _, q = continuous_prediction.run_pair(c, p, mixed_prior(), net, .5, seed=42)
    assert q['checkpoint_committed']
    assert c.continuous_state['walker_traces']['channel'] == 'personal'
    assert 'walker_traces' not in c.continuous_state['statistical']
    # Production channel definition. The literature support fits this small
    # verified map only up to 15 minutes; it never clips and renormalizes.
    monkeypatch.setattr(settings, 'statistical_channel_definition', 'literature_distance_prior')
    c = case_for(p)
    _, _, q = continuous_prediction.run_pair(c, p, mixed_prior(), net, .25, seed=42)
    assert q['checkpoint_committed'] and q['statistical_definition'] == 'literature_distance_prior'
    assert c.continuous_state['walker_traces']['until_minute'] == 15.
    assert 'statistical' not in c.continuous_state


def test_preview_and_uncommitted_runs_store_no_traces(geography):
    net, center = geography
    p = prepared(center)
    c = case_for(p)
    walk(c, p, net, .5)
    before = c.model_dump(mode='json')
    continuous_prediction.run_pair(c, p, mixed_prior(), net, 1, seed=42, persist=False)
    walk(c, p, net, 1, persist=False)
    assert c.model_dump(mode='json') == before


def test_legacy_engine_has_no_traces_field(geography):
    net, center = geography
    p = prepared(center)
    c = case_for(p)

    class Uncovered:
        graph = net.graph
        coverage_bbox = None
    cells, q = walk(c, p, Uncovered(), 1)
    assert cells is None and q['engine'] == 'legacy'
    assert 'walker_traces' not in c.continuous_state
    p.onboarding_turns[0]['answer'] = '바뀐 관찰'  # stale policy -> legacy engine
    cells, q = walk(c, p, net, 1)
    assert cells is None and 'walker_traces' not in c.continuous_state


def test_pipeline_persists_traces_at_the_dashboard_path(geography, monkeypatch, tmp_path):
    net, center = geography
    p = prepared(center)
    monkeypatch.setattr(settings, 'persist_storage', True)
    monkeypatch.setattr(settings, 'storage_db_path', str(tmp_path / 'storage.db'))
    storage.reset_for_tests()
    storage.personas.save(p.id, p)
    c = case_for(p)
    storage.cases.save(c.id, c)
    monkeypatch.setattr(pipeline, '_load_roadnet', lambda *a, **k: (net, ''))
    monkeypatch.setattr(pipeline.situation_link, 'cached', lambda *a: [])
    monkeypatch.setattr(pipeline, '_initial_prior', lambda *a: mixed_prior())
    pipeline.run_prediction(c, now=START + timedelta(minutes=30), seed=42)
    pipeline.run_prediction(c, now=START + timedelta(hours=1), seed=42)
    with sqlite3.connect(tmp_path / 'storage.db') as db:
        row = db.execute("SELECT json_extract(data,'$.continuous_state.key'),"
                         "json_extract(data,'$.continuous_state.walker_traces') FROM cases WHERE id=?",
                         (c.id,)).fetchone()
    key, raw = row
    traces = json.loads(raw)
    assert traces['key'] == key and traces['until_minute'] == 60. and traces['version'] == 1
    assert all(w['starts_at_minute'] == 0. and w['points'][-1][2] == 60. for w in traces['walkers'])


def test_public_case_api_never_returns_checkpoint_or_traces(geography):
    from fastapi.testclient import TestClient

    from app.main import app
    net, center = geography
    p = prepared(center)
    storage.personas.save(p.id, p)
    c = case_for(p)
    c.guardian_id = 'guardian'
    walk(c, p, net, .5)
    assert c.continuous_state['walker_traces']['walkers']
    storage.cases.save(c.id, c)
    client = TestClient(app)
    one = client.get('/phase1/cases/' + c.id)
    many = client.get('/phase1/cases', params={'guardian_id': 'guardian'})
    assert one.status_code == 200 and many.status_code == 200 and len(many.json()) == 1
    for body in (one.text, many.text):
        assert 'continuous_state' not in body and 'walker_traces' not in body and 'walker_idx' not in body
    assert storage.cases.get(c.id).continuous_state['walker_traces']['walkers']
