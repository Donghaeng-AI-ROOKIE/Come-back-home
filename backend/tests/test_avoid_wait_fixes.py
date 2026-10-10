"""Regression tests for the avoidance-scope and wait-order fixes (2026-10-10).

Covers: same-note wait->movement ordering at execution time (with negative
controls), draft place-scope restoration after a correction, and place-type
signal facts evaluated only near known sites. Synthetic fixtures only.
"""
import pytest
from app.llm import mind_policy as m
from app.llm import mind_policy_guarded_core as guarded
from app.phase2.persistent_context_walk import PersistentContextPopulation
from app.geo.h3grid import haversine_km
from tests.kintex_fixtures import geography, person, prior, START
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


# ---- normalization (pure policy structure) ---------------------------------

def test_same_note_wait_then_move_becomes_completion_followup():
    rest = rule('rest')
    pol = policy(wait_rule(), seek_rule(), rest)
    out, report = m.normalize_sequences(pol)
    assert [r.id for r in out.rules] == ['w', 'r1']
    w = out.rules[0]
    assert w.after_wait.action == 'seek' and w.after_wait.goal_label == '등록 목적지'
    assert [[(a.fact, a.value) for a in c] for c in w.after_wait.when] == [[('family_present', False)]]
    assert report['converted'] == [{'wait_rule_id': 'w', 'movement_rule_id': 's', 'note_id': 'N0'}]
    # Unrelated traits are preserved byte for byte.
    assert out.rules[1].model_dump() == pol.rules[2].model_dump()


@pytest.mark.parametrize('case,expected', [
    # Exception-like movement not conditioned on the wait trigger: never sequenced.
    ('trigger_not_contained', 'movement_not_conditioned_on_wait_trigger'),
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
    assert report['converted'] == []
    if expected:
        assert {x['reason'] for x in report['not_converted']} == {expected}


def test_stored_followup_without_condition_still_parses():
    raw = wait_rule()
    raw['after_wait'] = dict(action='walk', goal_label=None, evidence=[dict(note_id='N0', quote=Q)])
    parsed = policy(raw)
    assert parsed.rules[0].after_wait.when == [[]]


# ---- execution: the wait is not skipped -------------------------------------

def _far_goal_person(net, center, metres=400):
    node, loc = next((n, l) for n, l in ((n, net.node_location(n)) for n in net.graph.nodes)
                     if abs(haversine_km(center, l) * 1000 - metres) < 60)
    base = person(center)
    return base.model_copy(update={'attraction_points': [a.model_copy(update={'location': loc, 'place_type': None})
                                                          for a in base.attraction_points]})


def _walk(geography, pol, observations, minutes):
    net, center = geography
    pop = PersistentContextPopulation(net, _far_goal_person(net, center), prior(), pol, center, START,
                                      count=40, seed=17, behavior_observations=observations)
    return pop, pop.advance_to(minutes)


def test_normalized_pair_waits_full_duration_then_departs(geography):
    raw = policy(wait_rule(), seek_rule())
    normalized, _ = m.normalize_sequences(raw)
    observations = [obs('lost_awareness', True), obs('family_present', False)]
    _, before = _walk(geography, raw, observations, 9.9)
    pop, after = _walk(geography, normalized, observations, 9.9)
    # The unordered pair lets some walkers leave before the wait ends.
    assert before['quality']['unresolved_mass'] == 0
    assert all(p.mode == 'wait' and p.distance == 0 for p in pop.particles)
    pop.advance_to(14)
    assert all(any(e['kind'] == 'sourced_wait_followup' for e in p.events) for p in pop.particles)
    assert sum(p.distance > 0 for p in pop.particles) == len(pop.particles)


def test_followup_withheld_when_condition_false_at_completion(geography):
    normalized, _ = m.normalize_sequences(policy(wait_rule(), seek_rule()))
    pop, _ = _walk(geography, normalized, [obs('lost_awareness', True), obs('family_present', True)], 14)
    assert all(any(e['kind'] == 'sourced_wait_followup_withheld' for e in p.events) for p in pop.particles)
    assert not any(p.mode == 'seek' for p in pop.particles)


def test_unordered_pair_baseline_skips_wait_for_some_walkers(geography):
    """Documents the defect the normalization fixes (deployed behaviour)."""
    raw = policy(wait_rule(), seek_rule())
    pop, _ = _walk(geography, raw, [obs('lost_awareness', True), obs('family_present', False)], 9.9)
    assert any(p.distance > 0 for p in pop.particles)


# ---- draft place scope restoration ------------------------------------------

def _draft(scope, condition='market.noisy'):
    return {'source_assessment': '합성', 'non_action_note_ids': [],
            'rules': [{'action': 'avoid_market', 'goal_place': '', 'applies_only_at': scope,
                       'condition': condition, 'hold_minutes': 0, 'note_ids': ['N0']}]}


def _compiled(scope, condition='market.noisy'):
    return guarded.compile(_draft(scope, condition), m.source(person()))


def test_correction_that_only_drops_place_scope_is_restored():
    src = m.source(person())
    review = _compiled([])
    restored, audit = guarded.restore_draft_scope(_draft(['등록 목적지']), review, src)
    assert restored.rules[0].place_labels == ['등록 목적지']
    assert audit == [{'rule_id': 'a_0', 'restored_place_labels': ['등록 목적지']}]


@pytest.mark.parametrize('draft_scope,review_scope,review_condition', [
    ([], ['등록 목적지'], 'market.noisy'),          # legitimately added scope kept
    (['등록 목적지'], [], 'market.crowded'),          # condition changed: not the same rule
])
def test_legitimate_corrections_are_not_reverted(draft_scope, review_scope, review_condition):
    src = m.source(person())
    review = _compiled(review_scope, review_condition)
    out, audit = guarded.restore_draft_scope(_draft(draft_scope), review, src)
    assert audit == [] and out.model_dump() == review.model_dump()


def test_undecodable_draft_restores_nothing():
    review = _compiled([])
    out, audit = guarded.restore_draft_scope('not json', review, m.source(person()))
    assert audit == [] and out is review


# ---- place-type signals only near known sites -------------------------------

def test_unscoped_signal_movement_fires_only_near_a_known_site(geography):
    """'시장이 시끄러우면 쉼터로' without place scope must not fire everywhere."""
    net, center = geography
    who = _far_goal_person(net, center)
    # Make the registered place a market at the start, the goal is elsewhere.
    market = who.attraction_points[0].model_copy(update={'label': '시장', 'location': center, 'place_type': 'market'})
    who = who.model_copy(update={'attraction_points': [market, who.attraction_points[0]]})
    s = seek_rule(when=[[dict(fact='market.noisy', op='eq', value=True)]])
    pop = PersistentContextPopulation(net, who, prior(), policy(s), center, START, count=40, seed=17)
    p = pop.particles[0]
    labels, features = pop.near(p)
    assert features['market'] is True and pop.known_sites(p, 'market') == ['registered:시장']
    far = next(n for n, l in pop.locations.items() if haversine_km(center, l) * 1000 > 800)
    p.node = far
    rule_, _, _ = pop._select_rule(p, __import__('random').Random(1), pop.facts(p), *pop.near(p))
    assert rule_ is None
    assert 's' in p.env_insufficient_rules
    # Near the registered market an unknown noise is a grounded, persistent hypothesis.
    q = pop.particles[1]
    pop._select_rule(q, __import__('random').Random(1), pop.facts(q), *pop.near(q))
    assert any(k.startswith('["environment", "market.noisy", ["sites"') for k in q.context_assumptions)
