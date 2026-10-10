"""Regression tests for the avoidance-scope and wait-order fixes (2026-10-10).

Covers: same-note wait->movement precedence (nothing deleted, with negative
controls), draft place-scope restoration after a correction, and place-type
signal facts evaluated only near known sites. Synthetic fixtures only.
"""
import random
import pytest
from app.llm import mind_policy as m
from app.llm import mind_policy_guarded_core as guarded
from app.phase2.persistent_context_walk import PersistentContextPopulation
from app.geo.h3grid import haversine_km
from tests.kintex_fixtures import geography, person, prior, START  # noqa: F401 (pytest fixture)
from tests.test_person_policy import policy, rule, obs

Q = '무릎이 아프면'


def wait_rule(rid='w', note='N0', when=None, hold=10.):
    return dict(id=rid, when=when or [[dict(fact='lost_awareness', op='eq', value=True)]], action='wait',
                goal_label=None, feature=None, place_labels=[], hold_minutes=hold, supersedes=[],
                evidence=[dict(note_id=note, quote=Q)])


def seek_rule(rid='s', note='N0', when=None, goal='등록 목적지'):
    return dict(id=rid, when=when or [[dict(fact='lost_awareness', op='eq', value=True),
                                       dict(fact='family_present', op='eq', value=False)]],
                action='seek', goal_label=goal, feature=None, place_labels=[], hold_minutes=None,
                supersedes=[], evidence=[dict(note_id=note, quote=Q)])


# ---- ordering (pure policy structure) ----------------------------------------

def test_same_note_wait_gets_precedence_and_nothing_is_deleted():
    pol = policy(wait_rule(), seek_rule(), rule('rest'))
    out, report = m.normalize_sequences(pol)
    assert [r.id for r in out.rules] == ['w', 's', 'r1']
    assert out.rules[0].supersedes == ['s']
    # The movement keeps its own condition; unrelated traits are byte-identical.
    assert out.rules[1].model_dump() == pol.rules[1].model_dump()
    assert out.rules[2].model_dump() == pol.rules[2].model_dump()
    assert report['ordered'] == [{'wait_rule_id': 'w', 'movement_rule_id': 's', 'note_id': 'N0'}]


@pytest.mark.parametrize('case,expected', [
    ('trigger_not_contained', 'movement_not_conditioned_on_wait_trigger'),  # possible exception: never ordered
    ('different_note', None),
    ('scoped', None),
    ('referenced', None),
    ('two_moves', 'not_one_to_one'),
])
def test_ambiguous_pairs_are_left_unchanged_and_reported(case, expected):
    w = wait_rule(); s = seek_rule(); extra = []
    if case == 'trigger_not_contained':
        s['when'] = [[dict(fact='family_present', op='eq', value=False)]]
    if case == 'different_note':
        s['evidence'] = [dict(note_id='N1', quote=Q)]
    if case == 'scoped':
        s['place_labels'] = ['등록 목적지']; s['action'] = 'walk'; s['goal_label'] = None
    if case == 'referenced':
        extra = [dict(rule('rest'), supersedes=['s'])]
    if case == 'two_moves':
        extra = [dict(seek_rule('s2'), action='walk', goal_label=None)]
    pol = policy(w, s, *extra)
    out, report = m.normalize_sequences(pol)
    assert out.model_dump() == pol.model_dump()
    assert report['ordered'] == []
    if expected:
        assert expected in {x['reason'] for x in report['not_ordered']}


def test_unrelated_same_note_movement_does_not_block_a_valid_pair():
    rain = dict(seek_rule('s2', when=[[dict(fact='rain_observed', op='eq', value=True)]]), action='walk', goal_label=None)
    out, report = m.normalize_sequences(policy(wait_rule(), seek_rule(), rain))
    assert out.rules[0].supersedes == ['s']
    assert {x['movement_rule_id']: x['reason'] for x in report['not_ordered']} == {'s2': 'movement_not_conditioned_on_wait_trigger'}


# ---- execution: the wait is not skipped, and the departure is not lost ------

def _far_goal_person(net, center, metres=400):
    loc = next(l for l in (net.node_location(n) for n in net.graph.nodes)
               if abs(haversine_km(center, l) * 1000 - metres) < 60)
    base = person(center)
    return base.model_copy(update={'attraction_points': [a.model_copy(update={'location': loc, 'place_type': None})
                                                          for a in base.attraction_points]})


def _walk(geography, pol, observations, minutes, count=40):
    net, center = geography
    pop = PersistentContextPopulation(net, _far_goal_person(net, center), prior(), pol, center, START,
                                      count=count, seed=17, behavior_observations=observations)
    return pop, pop.advance_to(minutes)


LOST = [obs('lost_awareness', True), obs('family_present', False)]


def test_unordered_pair_baseline_skips_wait_for_some_walkers(geography):
    """Documents the deployed defect the ordering fixes."""
    pop, _ = _walk(geography, policy(wait_rule(), seek_rule()), LOST, 9.9)
    assert any(p.distance > 0 for p in pop.particles)


def test_ordered_pair_waits_full_duration_then_departs(geography):
    ordered, _ = m.normalize_sequences(policy(wait_rule(), seek_rule()))
    pop, _ = _walk(geography, ordered, LOST, 9.9)
    assert all(p.mode == 'wait' and p.distance == 0 for p in pop.particles)
    pop.advance_to(14)
    assert all(p.distance > 0 and p.target == '등록 목적지' for p in pop.particles)


def test_walking_state_condition_still_departs_after_the_wait(geography):
    """Review #6/#14: a movement conditioned on walking state must not vanish."""
    s = seek_rule(when=[[dict(fact='lost_awareness', op='eq', value=True), dict(fact='is_walking', op='eq', value=True)]])
    ordered, report = m.normalize_sequences(policy(wait_rule(), s))
    assert report['ordered']
    pop, _ = _walk(geography, ordered, [obs('lost_awareness', True)], 9.9)
    assert all(p.distance == 0 for p in pop.particles)
    pop.advance_to(16)
    assert sum(p.target == '등록 목적지' and p.distance > 0 for p in pop.particles) == len(pop.particles)


def test_later_condition_after_the_wait_is_preserved(geography):
    """Review #7: a departure whose own condition becomes true later still happens."""
    s = seek_rule(when=[[dict(fact='lost_awareness', op='eq', value=True), dict(fact='dark_observed', op='eq', value=True)]])
    ordered, _ = m.normalize_sequences(policy(wait_rule(), s))
    observations = [obs('lost_awareness', True), obs('dark_observed', False, 0, 20), obs('dark_observed', True, 20, 360)]
    pop, _ = _walk(geography, ordered, observations, 19)
    assert not any(p.target == '등록 목적지' for p in pop.particles)
    pop.advance_to(26)
    assert sum(p.target == '등록 목적지' for p in pop.particles) == len(pop.particles)


def test_ordering_is_execution_only_and_reported_in_quality():
    from app.phase2 import continuous_prediction as cp
    from tests.kintex_fixtures import person as base_person
    stored = policy(wait_rule(), seek_rule())
    who = base_person().model_copy(update={'prepared_mind': {'policy': stored.model_dump(mode='json')}})
    original = cp.mind_preparation.ready
    try:
        cp.mind_preparation.ready = lambda persona: (m.Policy.model_validate(persona.prepared_mind['policy']), 'ready')
        executed, status, report = cp._executable_policy(who)
    finally:
        cp.mind_preparation.ready = original
    assert status == 'ready' and executed.rules[0].supersedes == ['s'] and report['ordered']
    # The stored policy is untouched.
    assert who.prepared_mind['policy']['rules'][0]['supersedes'] == []


# ---- draft place scope restoration ------------------------------------------

def _draft(*items):
    return {'source_assessment': '합성', 'non_action_note_ids': [], 'rules': list(items)}


def _avoid(scope, condition='market.noisy'):
    return {'action': 'avoid_market', 'goal_place': '', 'applies_only_at': scope,
            'condition': condition, 'hold_minutes': 0, 'note_ids': ['N0']}


def _compiled(*items):
    return guarded.compile(_draft(*items), m.source(person()))


def test_correction_that_only_drops_place_scope_is_restored():
    src = m.source(person())
    review = _compiled(_avoid([]))
    bad_rest = {'action': 'rest', 'goal_place': '', 'applies_only_at': [], 'condition': 'is_0walking',
                'hold_minutes': 5, 'note_ids': ['N0']}
    restored, audit, unresolved = guarded.restore_draft_scope(_draft(bad_rest, _avoid(['등록 목적지'])), review, src)
    assert restored.rules[0].place_labels == ['등록 목적지']
    assert audit == [{'rule_id': 'a_0', 'restored_place_labels': ['등록 목적지']}] and unresolved == []


@pytest.mark.parametrize('draft_scope,review_scope,review_condition', [
    ([], ['등록 목적지'], 'market.noisy'),         # legitimately added scope kept
    (['등록 목적지'], [], 'market.crowded'),         # condition changed: not the same rule
])
def test_legitimate_corrections_are_not_reverted(draft_scope, review_scope, review_condition):
    src = m.source(person())
    review = _compiled(_avoid(review_scope, review_condition))
    out, audit, _ = guarded.restore_draft_scope(_draft(_avoid(draft_scope)), review, src)
    assert audit == [] and out.model_dump() == review.model_dump()


def test_numeric_literal_form_does_not_hide_a_dropped_scope():
    src = m.source(person())
    review = _compiled(_avoid([], 'market.noisy and clock_hour >= 18.0'))
    out, audit, _ = guarded.restore_draft_scope(_draft(_avoid(['등록 목적지'], 'market.noisy and clock_hour >= 18')), review, src)
    assert out.rules[0].place_labels == ['등록 목적지'] and audit


def test_draft_with_scoped_and_unscoped_versions_is_reported_not_narrowed():
    src = m.source(person())
    review = _compiled(_avoid([]))
    out, audit, unresolved = guarded.restore_draft_scope(_draft(_avoid([]), _avoid(['등록 목적지'])), review, src)
    assert audit == [] and out.rules[0].place_labels == []
    assert unresolved and unresolved[0]['reason'] == 'ambiguous_draft_scopes'


def test_fixed_initial_rules_are_never_narrowed():
    from app.llm import mind_policy_compact as compact
    base = person()
    initial = {'version': 'x', 'core': {}, 'scope': {'environment': {'market': {
        'response': 'avoid', 'scope': 'conditional_category', 'note_ids': ['N0'],
        'condition_clauses': [[{'signal': 'noisy', 'state': 'present'}]]}}}}
    src = m.source(base.model_copy(update={'prepared_initial': initial}))
    fixed = compact.fixed(src)
    assert [r.id for r in fixed] == ['initial_env_market']
    review = m.Policy(rules=fixed, unrepresented=[])
    out, audit, _ = guarded.restore_draft_scope(_draft(_avoid(['등록 목적지'])), review, src)
    assert audit == [] and out.rules[0].place_labels == []


def test_undecodable_draft_is_reported():
    review = _compiled(_avoid([]))
    out, audit, unresolved = guarded.restore_draft_scope('not json', review, m.source(person()))
    assert audit == [] and out is review and unresolved == [{'reason': 'draft_unparsed_scope_check_skipped'}]


# ---- place-type signals only near known sites -------------------------------

def _market_and_goal(net, center):
    who = _far_goal_person(net, center)
    market = who.attraction_points[0].model_copy(update={'label': '시장', 'location': center, 'place_type': 'market'})
    return who.model_copy(update={'attraction_points': [market, who.attraction_points[0]]})


def test_unscoped_signal_movement_fires_only_near_a_known_site(geography):
    """'시장이 시끄러우면 쉼터로' without place scope must not fire everywhere."""
    net, center = geography
    s = seek_rule(when=[[dict(fact='market.noisy', op='eq', value=True)]])
    pop = PersistentContextPopulation(net, _market_and_goal(net, center), prior(), policy(s), center, START, count=40, seed=17)
    p = pop.particles[0]
    assert pop.near(p)[1]['market'] is True and pop.nearest_site(p, 'market') == ['places', ['시장']]
    p.node = next(n for n, l in pop.locations.items() if haversine_km(center, l) * 1000 > 800)
    chosen, _, _ = pop._select_rule(p, random.Random(1), pop.facts(p), *pop.near(p))
    assert chosen is None and 's' in p.env_insufficient_rules
    # Near the registered market an unknown noise is one persistent hypothesis
    # per physical site, shared with a named rule for the same place.
    q = pop.particles[1]
    pop._select_rule(q, random.Random(1), pop.facts(q), *pop.near(q))
    assert any('["places", ["시장"]]' in k for k in q.context_assumptions)


def test_or_branch_that_is_true_still_runs_without_environment_information(geography):
    """Review #9: one unknown environment branch must not switch off a true branch."""
    w = wait_rule(when=[[dict(fact='market.noisy', op='eq', value=True)], [dict(fact='lost_awareness', op='eq', value=True)]])
    pop, _ = _walk(geography, policy(w), [obs('lost_awareness', True)], 5)
    assert all(p.mode == 'wait' for p in pop.particles)


def test_layer_absence_is_false_not_insufficient(geography):
    """Review #12: a layer that shows no market nearby is absence, not missing information."""
    net, center = geography
    s = seek_rule(when=[[dict(fact='market.noisy', op='eq', value=True)]])
    original = net.node_env
    try:
        net.node_env = {n: {'market_m': 5000.0} for n in net.graph.nodes}
        pop = PersistentContextPopulation(net, _far_goal_person(net, center), prior(), policy(s), center, START, count=10, seed=17)
        p = pop.particles[0]
        assert pop.feature_absent(p, 'market') is True
        chosen, _, _ = pop._select_rule(p, random.Random(1), pop.facts(p), *pop.near(p))
        assert chosen is None and p.env_insufficient_rules == []
        assert pop.distribution(0)['quality']['environment_knowledge']['market'] == 'map_layer'
    finally:
        net.node_env = original


def test_layer_nearness_uses_interpolated_edge_position(geography):
    """Review #10/#15: leaving a mapped feature, 'near' follows the road position."""
    net, center = geography
    original = net.node_env
    try:
        pop = PersistentContextPopulation(net, _far_goal_person(net, center), prior(), policy(), center, START, count=1, seed=17)
        p = pop.particles[0]; u = p.node; v = pop.neighbors[u][0]
        net.node_env = {n: {'market_m': 2000.0} for n in net.graph.nodes}
        net.node_env[u] = {'market_m': 10.0}; net.node_env[v] = {'market_m': 400.0}
        p.edge_to = v; p.edge_length = 100.; p.edge_remaining = 20.  # 80% along the edge
        assert pop.near(p)[1]['market'] is False and pop.known_sites(p, 'market') == []
    finally:
        net.node_env = original


# ---- open case: family is not beside the person -----------------------------

def test_unobserved_family_is_uncertain_not_a_confirmed_absence(geography):
    """No observation never becomes a confirmed fact in a personal condition."""
    s = seek_rule(when=[[dict(fact='family_present', op='eq', value=False)]])
    pop, result = _walk(geography, policy(s), [], 2)
    q = result['quality']
    assert q['family_presence_observed'] is False and 'unknown' in q['family_presence_source']
    assert any('family_present' in k for p in pop.particles for k in p.context_assumptions)
    hypotheses = [v['value'] for p in pop.particles for k, v in p.context_assumptions.items() if 'family_present' in k]
    assert True in hypotheses and False in hypotheses
    assert 0 < sum(p.target == '등록 목적지' for p in pop.particles) < len(pop.particles)


def test_observed_absence_is_used_as_a_fact(geography):
    s = seek_rule(when=[[dict(fact='family_present', op='eq', value=False)]])
    pop, _ = _walk(geography, policy(s), [obs('family_present', False)], 2)
    assert all(p.target == '등록 목적지' for p in pop.particles)


def test_observed_reunion_stops_walking(geography):
    """A family observed beside the person ends walking; it is not re-walked."""
    s = seek_rule(when=[[dict(fact='lost_awareness', op='eq', value=True)]])
    observations = [obs('lost_awareness', True), obs('family_present', False, 0, 5), obs('family_present', True, 5, 360)]
    pop, _ = _walk(geography, policy(s), observations, 5)
    moved = [p.distance for p in pop.particles]
    assert any(d > 0 for d in moved)
    result = pop.advance_to(30)
    assert [p.distance for p in pop.particles] == pytest.approx(moved)
    assert result['quality']['reunion_observed_walkers'] == len(pop.particles)
