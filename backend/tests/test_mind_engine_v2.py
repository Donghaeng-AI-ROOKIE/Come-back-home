"""engine_outputs_v2: synthetic environment layer, empty-policy baseline,
scenario fact switching, per-input tolerance, self comparison and pair logic.

Walks use the small verified KINTEX fixture and few walkers. Handwritten
policies here test the harness only; they are not model outputs.
"""
import json
import math

import pytest

from app.geo.h3grid import haversine_km
from app.geo.roadnet import OSMnxNetwork
from app.llm.mind_policy import Policy
from app.schemas.common import GeoPoint
from app.schemas.prediction import LognormalParams
from experiments.mind_contract_ab_20261007 import engine_outputs_v2 as v2
from experiments.mind_contract_ab_20261007 import scoring
from tests.test_mind_upgrade import FIXTURE
from tests.test_mind_upgrade import prior as base_prior

SITE = next(s for s in json.loads((scoring.ROOT / 'sites.json').read_text())['sites'] if s['site_id'] == 'C')
INPUTS = {json.loads(x)['id']: json.loads(x)
          for x in (v2.DEV128 / 'dev128_inputs.jsonl').read_text().splitlines() if x.strip()}
REFERENCE = json.loads((v2.DEV128 / 'dev128_reference.NOT_MODEL_INPUT.json').read_text())
PERSONAL = INPUTS['DEV_P04_original']['personal']
EXACT = {s: dict(v2.FLOOR) for s in v2.SCENARIOS}
S1, S2, S3 = v2.SCENARIOS


def rule(rid, action, when, feature=None, goal=None, places=(), hold=None):
    return {'id': rid, 'when': when, 'action': action, 'goal_label': goal, 'feature': feature,
            'place_labels': list(places), 'hold_minutes': hold, 'supersedes': [],
            'evidence': [{'note_id': 'N1'}]}


def policy(*rules):
    return Policy.model_validate({'rules': list(rules), 'unrepresented': []})


def atom(fact, value, op='eq'):
    return {'fact': fact, 'op': op, 'value': value}


def plain(horizon=90, **kw):
    """No observations: isolates the environment layer from scenario facts."""
    return {'start': v2.SCENARIOS[S1]['start'], 'horizon': horizon,
            'strategy': {'random_walk': 1.0}, 'behavior': [], 'environment': [], **kw}


@pytest.fixture(scope='module')
def net():
    return OSMnxNetwork.from_graphml(FIXTURE)


@pytest.fixture(scope='module')
def env(net):
    return v2.environment_network(net, SITE, PERSONAL)


def nearest_m(feature, env, loc):
    return min(haversine_km(loc, GeoPoint(lat=p['lat'], lng=p['lng'])) for p in env.facilities[feature]) * 1000


def walk(env, pol, scenario, walkers=6, seed=17, personal=PERSONAL):
    return v2.walk(env, SITE, personal, pol, v2.SCENARIOS[scenario], walkers=walkers, seed=seed)


# ── synthetic environment layer ───────────────────────────────────────────
def test_layer_reports_distances_to_labelled_synthetic_facilities_without_touching_the_map(net, env):
    assert {p['label'] for p in env.facilities['park']} == {'느티공원', '솔빛쉼터'}
    assert [p['label'] for p in env.facilities['market']] == ['해든상가']
    assert all(p['source'].startswith('synthetic') for f in ('forest', 'water') for p in env.facilities[f])
    node = env.nearest_node(GeoPoint(lat=env.facilities['market'][0]['lat'], lng=env.facilities['market'][0]['lng']))
    layer = env.env(node)
    assert set(layer) == {'market_m', 'park_m', 'forest_m', 'water_m'}
    assert layer['market_m'] < 60 < layer['forest_m']
    assert net.node_env == {} and net.env(node) == {}  # product map object untouched
    assert '합성' in v2.SYNTHETIC_LABEL


def test_category_avoidance_walks_away_from_the_facility_instead_of_freezing(net, env):
    avoid_park = policy(rule('a', 'avoid', [[]], feature='park'))
    bare = v2.SyntheticEnvNetwork(net, {f: [] for f in v2.FEATURES})
    bare.places_key = env.places_key  # same map without any environment layer (the v1 condition)
    frozen = v2.walk(bare, SITE, PERSONAL, avoid_park, plain(), walkers=12, seed=17)
    assert frozen['unresolved'].get('unmapped_avoidance', 0) > 0

    steps, near = [], {'avoid': 0, 'null': 0}

    def observe(kind):
        last = {}

        def hook(part, loc):
            d = nearest_m('park', env, loc)
            if kind == 'avoid' and part.mode == 'avoid' and part.seed in last:
                steps.append(d - last[part.seed])
            last[part.seed] = d
            near[kind] += d <= v2.PERCEPTION_M['park']
        return hook

    walked = v2.walk(env, SITE, PERSONAL, avoid_park, plain(), walkers=24, seed=17, observer=observe('avoid'))
    v2.walk(env, SITE, PERSONAL, v2.empty_policy(PERSONAL), plain(), walkers=24, seed=17, observer=observe('null'))
    assert 'unmapped_avoidance' not in walked['unresolved']
    assert walked['avoid_by_target'].get('feature:park', 0) > 0
    assert len(steps) >= 3 and sum(steps) / len(steps) > 0  # distance to the park grows while avoiding
    assert near['avoid'] < near['null']  # less time inside the park's perception range


def test_snapshot_truncates_the_graph_and_still_walks_exactly_like_the_full_view(net, monkeypatch):
    def small_prior():  # p95 cap about 0.6 km instead of 5.2 km, so the snapshot really cuts the fixture
        p = base_prior()
        p.radius_lognormal = LognormalParams(mu=math.log(0.6), sigma=0.01)
        return p
    monkeypatch.setattr(v2, 'prior', small_prior)
    probe = policy(rule('w', 'wait', [[atom('family_present', False)]], hold=5.0),
                   rule('a', 'avoid', [[atom('lost_awareness', True)]], feature='park'))
    out, part = v2.support_equivalence(net, SITE, PERSONAL, [('probe', probe), ('empty', v2.empty_policy(PERSONAL))],
                                       S1, 8, 17)
    assert len(part.graph.nodes) < len(net.graph.nodes) / 2
    assert all(x['snapshot_nodes'] == len(part.graph.nodes) < x['full_nodes'] for x in out)
    assert max(x['max_reach_km'] for x in out) > 0.9 * part.support_km  # walkers reach the cut
    assert all(x['identical'] for x in out)


# ── scenarios ──────────────────────────────────────────────────────────────
def test_at_least_three_scenarios_and_no_fact_is_always_true():
    assert len(v2.SCENARIOS) >= 3
    for name, s in v2.SCENARIOS.items():
        for fact in {f for f, *_ in s['behavior']}:
            states = v2.fact_states(s, fact)
            assert states != {True} and len(states) >= 2, (name, fact, states)
            spans = sorted((a, b) for f, _, a, b in s['behavior'] if f == fact)
            assert all(b <= c for (_, b), (c, _) in zip(spans, spans[1:])), (name, fact)  # no conflicting overlap
        for feature in {f for f, *_ in s['environment']}:
            for k, signal in ((3, 'noisy'), (4, 'crowded')):
                values = {e[k] for e in s['environment'] if e[0] == feature}
                assert values != {True}, (name, feature, signal)


def test_lost_and_recognized_switch_at_different_times_so_substitution_shows():
    s = v2.SCENARIOS[S1]

    def at(fact, m):
        return next((v for f, v, a, b in s['behavior'] if f == fact and a <= m < b), None)
    differ = [m for m in range(s['horizon']) if at('lost_awareness', m) != at('target_recognized', m)]
    assert len(differ) > 60


def test_population_clock_and_observed_facts_follow_each_scenario(env):
    def facts_at(name, minute):
        s = v2.SCENARIOS[name]
        pop = v2.Population(env, v2.person(v2.GeoPoint(**SITE['location'])), v2.prior(), v2.empty_policy(PERSONAL),
                            v2.GeoPoint(**SITE['location']), s['start'], count=1, seed=1,
                            behavior_observations=v2.behavior_observations(s),
                            environment_observations=v2.environment_observations(s, env.facilities))
        p = pop.particles[0]
        p.minute = minute
        return pop.facts(p)

    assert facts_at(S1, 0)['clock_hour'] == 8.0
    evening = [facts_at(S2, m) for m in (10, 30, 90, 215, 330)]
    assert [f['dark_observed'] for f in evening] == [False, True, True, True, True]
    assert [f['family_present'] for f in evening] == [True, True, False, True, False]
    assert evening[0]['clock_hour'] == pytest.approx(18 + 40 / 60) and evening[-1]['clock_hour'] == 0.0
    sparse = facts_at(S3, 120)
    assert sparse['lost_awareness'] is None and sparse['family_present'] is None and sparse['clock_hour'] == 16.5
    market = facts_at(S1, 10)  # at the start, within 300 m of the market observation
    assert market['market.noisy'] is True and market['market.crowded'] is True


def test_walk_runs_each_scenario_on_its_own_clock(env):
    # 23:45-00:15 is reached only by the evening scenario that crosses midnight.
    midnight = policy(rule('w', 'wait', [[atom('clock_hour', 23.75, 'gte')], [atom('clock_hour', 0.25, 'lt')]],
                           hold=5.0))
    minutes = {s: walk(env, midnight, s, walkers=4)['rule_minutes'].get('w', 0) for s in v2.SCENARIOS}
    assert minutes[S2] > 0 and minutes[S1] == 0 and minutes[S3] == 0
    morning = policy(rule('w', 'wait', [[atom('clock_hour', 8.5, 'gte'), atom('clock_hour', 9, 'lt')]], hold=5.0))
    minutes = {s: walk(env, morning, s, walkers=4)['rule_minutes'].get('w', 0) for s in v2.SCENARIOS}
    assert minutes[S1] > 0 and minutes[S2] == 0 and minutes[S3] == 0


def test_morning_scenario_gives_walkers_goals_so_arrival_conditions_can_fire(env):
    s1 = walk(env, v2.empty_policy(PERSONAL), S1, walkers=12)
    assert sum(s1['arrived'].values()) > 0
    assert sum(walk(env, v2.empty_policy(PERSONAL), S2, walkers=12)['arrived'].values()) == 0  # random walk only
    on_arrival = policy(rule('w', 'wait', [[atom('physical_arrival', True)]], hold=20.0))
    assert walk(env, on_arrival, S1, walkers=12)['rule_minutes'].get('w', 0) > 0


def test_continuous_walk_metric_follows_a_rest_limit(env):
    rest = policy(rule('r', 'rest', [[atom('is_walking', True), atom('continuous_walk_minutes', 10, 'gte')]],
                       hold=3.0))
    for s in v2.SCENARIOS:
        limited = walk(env, rest, s)['mean_max_continuous_walk_min']
        free = walk(env, v2.empty_policy(PERSONAL), s)['mean_max_continuous_walk_min']
        assert 9.0 <= limited <= 10.0 + 1e-6 < free, (s, limited, free)


# ── empty-policy baseline and self comparison ─────────────────────────────
def walks(env, pol, walkers=6):
    return {s: walk(env, pol, s, walkers=walkers) for s in v2.SCENARIOS}


def test_reference_equal_to_empty_policy_is_not_discriminable(env):
    null = walks(env, v2.empty_policy(PERSONAL))
    firing = walks(env, policy(rule('w', 'wait', [[atom('family_present', False)]], hold=10.0)))
    never = walks(env, policy(rule('w', 'wait', [[atom('clock_hour', 3, 'gte'), atom('clock_hour', 4, 'lt')]])))
    yes = v2.discriminable(firing, null, EXACT)
    no = v2.discriminable(never, null, EXACT)
    assert any(v['discriminable'] for v in yes.values()) and yes[S1]['beyond']['mean_wait'] > 0
    assert not any(v['discriminable'] for v in no.values()) and all(v['bit_identical'] for v in no.values())
    rows = [{'input_id': i, 'form': 'original', 'family': 'f', 'walkable': True, 'engine_error': False,
             'preserved': True} for i in ('fires', 'never')]
    summary = v2.preservation(rows, {'fires': yes, 'never': no})
    assert summary['discriminable']['responses'] == 1 and summary['non_discriminable_input_ids'] == ['never']
    # The input's own tolerance decides: a tolerance wider than the effect makes it non-discriminable.
    wide = {s: {'mean_wait': 1e6, 'mean_personal_rest': 1e6, 'mean_path_km': 1e6, 'mean_max_continuous_walk_min': 1e6,
                'arrived': 1e6, 'avoid': 1e6} for s in v2.SCENARIOS}
    assert not any(v['discriminable'] for v in v2.discriminable(firing, null, wide).values())


def test_self_comparison_is_exact_and_renamed_ids_walk_identically(env):
    ref = Policy.model_validate(REFERENCE['DEV_P09_original'])
    personal = INPUTS['DEV_P09_original']['personal']
    k_like = Policy.model_validate({**REFERENCE['DEV_P09_original'], 'rules': [
        {**r, 'id': f'd3_{i}'} for i, r in enumerate(REFERENCE['DEV_P09_original']['rules'])]})
    a = walk(env, ref, S1, personal=personal)
    b = walk(env, ref, S1, personal=personal)
    c = walk(env, k_like, S1, personal=personal)
    assert a == b
    ok, diffs, over = v2.compare(a, a, EXACT[S1])
    assert ok and over == {} and set(diffs.values()) == {0}
    assert v2.compare(c, a, EXACT[S1])[0]
    by_s = {S1: a}
    assert v2.judge(by_s, by_s, EXACT)['preserved']


def test_reverse_order_reference_enters_its_own_tolerance(env):
    # Both rules are active together for long stretches, so list order changes which one a walker takes.
    rules = (rule('w', 'wait', [[atom('family_present', False)]], hold=10.0),
             rule('k', 'walk', [[atom('lost_awareness', True)]]))
    ref = policy(*rules)
    samples = [walk(env, ref, S1, seed=x) for x in (17, 18, 19)]
    reversed_walk = walk(env, v2.reversed_policy(ref), S1)
    assert [r.id for r in v2.reversed_policy(ref).rules] == ['k', 'w']
    tol = v2.input_tolerance(samples + [reversed_walk])
    k_reordered = walk(env, policy(*[dict(r, id=f'd3_{i}') for i, r in enumerate(reversed(rules))]), S1)
    assert not v2.compare(k_reordered, samples[0], EXACT[S1])[0]  # order alone moves the walk
    assert v2.compare(k_reordered, samples[0], tol)[0]
    wrong = walk(env, policy(rule('w', 'wait', [[atom('family_present', True)]], hold=10.0), rules[1]), S1)
    assert not v2.compare(wrong, samples[0], tol)[0]


def test_failed_output_stays_in_the_denominator():
    judged = v2.judge(None, {S1: {}}, EXACT)
    assert judged == {'walkable': False, 'engine_error': False, 'preserved': False, 'scenarios': {}}
    disc = {'x': {S1: {'discriminable': True}}}
    rows = [{'input_id': 'x', 'form': 'original', 'family': 'f', **judged},
            {'input_id': 'x', 'form': 'original', 'family': 'f', 'walkable': True, 'engine_error': False,
             'preserved': True}]
    out = v2.preservation(rows, disc)['discriminable']
    assert out['responses'] == 2 and out['preserved'] == 1 and out['not_walkable_in_denominator'] == 1


def test_same_rule_set_responses_stay_in_the_denominator_and_are_counted_apart():
    disc = {'x': {S1: {'discriminable': True}}}
    base = {'input_id': 'x', 'form': 'original', 'family': 'f', 'walkable': True, 'engine_error': False}
    rows = [base | {'preserved': False, 'same_rule_set': True}, base | {'preserved': True, 'same_rule_set': True},
            base | {'preserved': False, 'same_rule_set': False}]
    out = v2.preservation(rows, disc)['discriminable']
    assert out['responses'] == 3 and out['preserved'] == 1
    assert out['same_rule_set_in_denominator'] == 2 and out['same_rule_set_walk_mismatch'] == 1


def test_engine_refusal_is_recorded_not_repaired(env):
    runner = v2.Runner(env, SITE, walkers=2)
    huge = policy(*[rule(f'r{i}', 'wait', [[atom(f, True)]]) for i, f in enumerate(
        ('lost_awareness', 'pain_observed', 'target_recognized', 'dark_observed', 'rain_observed',
         'market.noisy', 'park.noisy', 'forest.noisy', 'water.noisy'))])
    out = runner.run([(PERSONAL, huge, S3, 17)] * 2)
    assert 'engine_error' in out[0] and runner.walked == 1  # cached, not retried


# ── tolerance and pairs ────────────────────────────────────────────────────
def metrics(wait=0.0, path=1.0, avoid=None, arrived=None, cont=10.0):
    return {'mean_wait': wait, 'mean_personal_rest': 0.0, 'mean_path_km': path,
            'mean_max_continuous_walk_min': cont, 'avoid_walkers': sum((avoid or {}).values()),
            'avoid_by_target': avoid or {}, 'arrived': arrived or {'느티공원': 0}}


def test_tolerance_is_each_inputs_own_range_and_a_noisy_input_does_not_widen_another():
    noisy = v2.input_tolerance([metrics(wait=20), metrics(wait=8), metrics(wait=14),
                                metrics(avoid={'feature:park': 3}, wait=20)])
    quiet = v2.input_tolerance([metrics(wait=5, path=2.0), metrics(wait=7, path=2.05), metrics(wait=6, path=2.0)])
    assert noisy['mean_wait'] == 12 and noisy['avoid:feature:park'] == 3 and noisy['avoid_walkers'] == 3
    assert quiet['mean_wait'] == 2 and quiet['mean_path_km'] == pytest.approx(0.05)
    assert quiet['avoid_walkers'] == 0 and 'avoid:feature:park' not in quiet
    wrong = metrics(wait=15, path=2.0)  # 10 minutes more waiting than the quiet reference
    assert not v2.compare(wrong, metrics(wait=5, path=2.0), quiet)[0]
    pooled, source = v2.pooled_tolerance({'noisy': noisy, 'quiet': quiet})
    assert v2.compare(wrong, metrics(wait=5, path=2.0), pooled)[0]  # the old pooled rule lets it pass
    assert source['wait'] == {'input_id': 'noisy', 'component': 'mean_wait', 'value': 12}
    # A behavior the reference never shows has only the floor: one avoiding walker is beyond.
    assert not v2.compare(metrics(wait=5, path=2.0, avoid={'feature:market': 1}), metrics(wait=5, path=2.0),
                          quiet)[0]
    assert v2.input_tolerance([metrics(wait=5), {'engine_error': 'x'}])['mean_wait'] == v2.FLOOR['wait']


def test_reference_plan_walks_three_seeds_the_reverse_order_and_the_empty_policy():
    ref = {'one': REFERENCE['DEV_P09_original'], 'two': REFERENCE['DEV_P30_original']}
    assert (len(ref['one']['rules']), len(ref['two']['rules'])) == (1, 2)
    plan = v2.reference_plan(['one', 'two'], [S1, S2], ref, v2.NOISE_SEEDS)
    assert v2.NOISE_SEEDS == (18, 19) and v2.SEED == 17
    assert {(kind, seed) for _, _, seed, kind, _ in plan} == {('ref', 17), ('seed18', 18), ('seed19', 19),
                                                               ('rev', 17), ('null', 17)}
    assert len(plan) == 2 * (4 + 5)  # rev only for the multi-rule reference, every kind in every scenario
    rev = [p for iid, _, _, kind, p in plan if kind == 'rev']
    assert {iid for iid, _, _, kind, _ in plan if kind == 'rev'} == {'two'}
    assert [r.id for r in rev[0].rules] == [r['id'] for r in ref['two']['rules']][::-1]
    assert all(p is None for _, _, _, kind, p in plan if kind == 'null')


def test_per_input_tolerances_use_only_that_inputs_samples():
    walks = {'ref': {'a': {S1: metrics(wait=10)}, 'b': {S1: metrics(wait=10)}},
             'seed18': {'a': {S1: metrics(wait=22)}, 'b': {S1: metrics(wait=11)}},
             'seed19': {'a': {S1: metrics(wait=10)}, 'b': {S1: metrics(wait=10)}},
             'rev': {'b': {S1: metrics(wait=13)}}}
    tol = v2.per_input_tolerances(['a', 'b'], [S1], walks, (18, 19))
    assert tol['a'][S1]['mean_wait'] == 12 and tol['b'][S1]['mean_wait'] == 3  # b's range includes its reverse walk


def test_tolerance_argument_decides_compare_and_discriminable():
    ref, k = metrics(wait=10), metrics(wait=13)
    assert not v2.compare(k, ref, {'mean_wait': 2.9})[0]
    assert v2.compare(k, ref, {'mean_wait': 3.0})[0] and v2.compare(k, ref, {'wait': 3.0})[0]
    assert not v2.compare(k, ref, EXACT[S1])[0]
    assert v2.discriminable({S1: k}, {S1: ref}, {S1: {'mean_wait': 2.9}})[S1]['discriminable']
    assert not v2.discriminable({S1: k}, {S1: ref}, {S1: {'mean_wait': 3.0}})[S1]['discriminable']
    assert v2.pair_tolerance({'mean_wait': 1, 'arrived:a': 4}, {'mean_wait': 3}) == {'arrived:a': 4, 'mean_wait': 3}


def test_judge_needs_every_scenario_within_tolerance():
    ref = {S1: metrics(wait=10), S2: metrics(wait=10), S3: metrics(wait=10)}
    k = {S1: metrics(wait=10), S2: metrics(wait=10), S3: metrics(wait=11)}
    tol = {s: {'mean_wait': 0.5} for s in ref}
    out = v2.judge(k, ref, tol)
    assert not out['preserved'] and out['scenarios'][S3]['beyond'] == {'mean_wait': 1.0}
    assert out['scenarios'][S1]['within_tolerance'] and out['scenarios'][S2]['within_tolerance']
    assert v2.judge(k, ref, {s: {'mean_wait': 1.0} for s in ref})['preserved']


def test_pair_direction_and_same_meaning_equality():
    tol = {'S1': dict(v2.FLOOR, wait=1.0)}
    ref_over = {'S1': {'mean_wait': 30.0}}
    same_dir = v2.k_pair({'S1': metrics(wait=40)}, {'S1': metrics(wait=5)}, ref_over, tol, 'changed')
    wrong = v2.k_pair({'S1': metrics(wait=5)}, {'S1': metrics(wait=40)}, ref_over, tol, 'changed')
    flat = v2.k_pair({'S1': metrics(wait=5)}, {'S1': metrics(wait=5.5)}, ref_over, tol, 'changed')
    assert same_dir['same_direction_all'] and not wrong['same_direction_any'] and not flat['same_direction_any']
    assert v2.k_pair({'S1': metrics(wait=5)}, {'S1': metrics(wait=5.5)}, {}, tol, 'same')['equal']
    assert v2.k_pair(None, {'S1': metrics()}, {}, tol, 'same') == {'status': 'not_walkable'}
    assert [v2.pair_relation(*p) for p in (('original', 'preserve'), ('original', 'change'), ('change', 'change'))] \
        == ['same', 'changed', None]


def test_pair_report_counts_only_reference_distinguishable_counterfactuals():
    tol = {i: {'S1': {}} for i in ('o', 'p', 'c', 'h')}
    refs = {'o': {'S1': metrics(wait=30)}, 'p': {'S1': metrics(wait=30)}, 'c': {'S1': metrics(wait=0)},
            'h': {'S1': metrics(wait=30)}}
    k = {('o', 1): {'S1': metrics(wait=30)}, ('p', 1): {'S1': metrics(wait=30)}, ('c', 1): {'S1': metrics(wait=30)},
         ('h', 1): None}
    disc = {i: {'S1': {'discriminable': i != 'c'}} for i in refs}
    summary, _ = v2.pair_report({i: 'R' for i in refs}, {'o': 'original', 'p': 'preserve', 'c': 'change',
                                                         'h': 'preserve'}, refs, k, tol, disc)
    changed, same = summary['changed_meaning'], summary['same_meaning']
    assert changed['pairs'] == 3 and changed['reference_walks_differ'] == 3
    assert changed['k_same_direction_all_components'] == 0 and changed['k_not_walkable'] == 1
    assert same['pairs'] == 3 and same['k_equal'] == 1 and same['k_not_walkable'] == 2


def test_pairs_whose_references_walk_alike_are_left_out_of_both_pair_checks():
    ids = ('o', 'p', 'c')
    rel = {'o': 'original', 'p': 'preserve', 'c': 'change'}
    # The counterfactual walks like the original, and the preserve form differs from the original:
    # neither pair can say anything about K, however K walks.
    refs = {'o': {'S1': metrics(wait=30)}, 'p': {'S1': metrics(wait=10)}, 'c': {'S1': metrics(wait=30)}}
    k = {('o', 1): {'S1': metrics(wait=30)}, ('p', 1): {'S1': metrics(wait=0)}, ('c', 1): {'S1': metrics(wait=0)}}
    disc = {i: {'S1': {'discriminable': True}} for i in ids}
    tight = {i: {'S1': {}} for i in ids}
    summary, details = v2.pair_report({i: 'R' for i in ids}, rel, refs, k, tight, disc)
    changed, same = summary['changed_meaning'], summary['same_meaning']
    assert changed['pairs'] == 2 and changed['reference_walks_differ'] == 1  # c~p differs, c~o does not
    assert changed['not_measurable_with_these_scenarios'] == 1 and changed['k_comparisons'] == 1
    assert same['pairs'] == 1 and same['reference_walks_equal'] == 0 and same['k_comparisons'] == 0
    assert [x['pair'] for x in same['reference_walks_differ']] == ['o~p']
    # The pair tolerance is the larger of the two inputs': the preserve form's noise of 25 min covers
    # o~p (20 min apart) and c~p (20 min apart), whichever side of the pair carries it.
    wide = dict(tight, p={'S1': {'mean_wait': 25.0}})
    summary, _ = v2.pair_report({i: 'R' for i in ids}, rel, refs, k, wide, disc)
    assert summary['same_meaning']['reference_walks_equal'] == 1 and summary['same_meaning']['k_comparisons'] == 1
    assert summary['same_meaning']['k_equal'] == 0  # K o and p differ by 30 > 25
    assert summary['changed_meaning']['reference_walks_differ'] == 0
