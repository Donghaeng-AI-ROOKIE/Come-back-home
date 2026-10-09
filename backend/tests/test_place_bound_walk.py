"""Real cached KINTEX geometry, synthetic locations/observations, no calls."""
from datetime import timedelta
import json
import os
from pathlib import Path

import pytest
from app.geo.roadnet import verified_network
from app.geo.h3grid import haversine_km
from app.llm import mind_policy as m
from app.phase2.person_walk import Population
from app.phase2.place_bound_walk import PlaceBoundPopulation, PlaceRecognition, bound_possibilities
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint
from tests.kintex_fixtures import person, prior, START
from tests.test_person_policy import policy, rule, obs


@pytest.fixture(scope='module')
def cached():
    root = Path(__file__).resolve().parents[4]
    configured = os.environ.get('CBH_KINTEX_GRAPHML')
    path = Path(configured) if configured else root / '실험/MIND_completion_20261004/map_full_support/kintex_walk.graphml'
    if not path.exists() and not configured:
        pytest.skip('KINTEX spatial validation not performed: set CBH_KINTEX_GRAPHML to the verified cache')
    assert path.exists(), 'Configured KINTEX cache is missing; no other geography fallback'
    net = verified_network(path)
    node = net.nearest_node(GeoPoint(lat=37.6631, lng=126.7458))
    start = net.node_location(node)
    other = next(n for n in net.graph.nodes if .15 < haversine_km(start, net.node_location(n)) < .25)
    return net, node, other


def recognition(label='A', value=True, start=0, end=20):
    return PlaceRecognition(fact='target_recognized', value=value, place_label=label,
        valid_from=START+timedelta(minutes=start), valid_until=START+timedelta(minutes=end), source='synthetic_scenario')


def make(cached, *, cls=PlaceBoundPopulation, pol=None, **kwargs):
    net, a, b = cached; center = net.node_location(a)
    persona = person(center)
    persona.attraction_points = [AttractionPoint(label=label, location=net.node_location(node), place_type='park')
                                 for label, node in [('A', a), ('B', b)]]
    base = prior(); base.attraction_weights = {'A': 1., 'B': 1.}
    if pol is None:
        r = rule('wait', when=[[{'fact': 'physical_arrival', 'op': 'eq', 'value': True},
                               {'fact': 'target_recognized', 'op': 'eq', 'value': True}]])
        r['place_labels'] = ['A']; pol = policy(r)
    return cls(net, persona, base, pol, center, START, count=4, seed=17, **kwargs)


def choices(pop):
    p = pop.particles[0]; labels, features = pop.near(p)
    options, unknown = pop._policy_options(p, pop.facts(p), labels, features)
    return {x.action if x else 'baseline' for x in options}, unknown


def test_unselected_place_arrival_is_local_not_old_target_history(cached):
    pop = make(cached, place_recognitions=[recognition()])
    assert pop.particles[0].target is None and pop.particles[0].arrived is False
    assert choices(pop)[0] == {'wait'}


def test_other_place_recognition_or_old_arrival_cannot_trigger_named_wait(cached):
    pop = make(cached, place_recognitions=[recognition('A', False), recognition('B', True)])
    p = pop.particles[0]; p.target = 'B'; p.arrived = True
    assert choices(pop)[0] == {'baseline'}
    pop = make(cached, place_recognitions=[recognition('B', True)])
    p = pop.particles[0]; p.target = 'B'; p.arrived = True
    assert choices(pop)[0] == {'baseline', 'wait'}  # A recognition is unknown, never inferred true from B.


def test_departing_arrival_node_does_not_keep_arrival_true(cached):
    pop = make(cached, place_recognitions=[recognition()])
    p = pop.particles[0]; p.target = 'A'; p.arrived = True
    other = pop.neighbors[p.node][0]
    p.edge_to = other; p.edge_length = float(pop.attrs[p.node, other]['length']); p.edge_remaining = p.edge_length*.9
    assert choices(pop)[0] == {'baseline'}


def test_legacy_global_recognition_is_not_named_place_evidence(cached):
    pop = make(cached, behavior_observations=[obs('target_recognized', True)])
    options, unknown = choices(pop)
    assert options == {'wait', 'baseline'}
    assert any('target_recognized' in x and 'A' in x for x in unknown)


def test_conflict_and_expiry_are_unknown_not_confirmed(cached):
    pop = make(cached, place_recognitions=[recognition('A', True, end=.25), recognition('A', False, end=.25)])
    assert choices(pop)[0] == {'wait', 'baseline'}
    pop = make(cached, place_recognitions=[recognition('A', True, end=.25)])
    assert choices(pop)[0] == {'wait'}
    pop.particles[0].minute = .25
    assert choices(pop)[0] == {'wait', 'baseline'}


def test_fractional_release_and_checkpoint_keep_same_path(cached):
    observations = [recognition('A', True, end=.25), recognition('A', False, start=.25)]
    whole = make(cached, place_recognitions=observations)
    expected = whole.advance_to(2)
    assert all(x.waiting == pytest.approx(.25) and x.walking == pytest.approx(1.75) for x in whole.particles)
    split = make(cached, place_recognitions=observations); split.advance_to(.25)
    restored = make(cached, place_recognitions=observations, checkpoint=json.loads(json.dumps(split.checkpoint())))
    assert restored.advance_to(2) == expected
    assert restored.checkpoint() == whole.checkpoint()
    assert len(whole._policy_cache) <= 3
    with pytest.raises(ValueError, match='stale place recognition'):
        make(cached, place_recognitions=[], checkpoint=split.checkpoint())


def test_other_personal_behavior_is_unchanged(cached):
    pol = policy(rule('rest'))
    a = make(cached, cls=Population, pol=pol)
    b = make(cached, pol=pol)
    assert a.advance_to(12) == b.advance_to(12)
    cp = b.checkpoint(); cp.pop('place_binding_digest')
    assert a.checkpoint() == cp


def test_invalid_place_input_and_ambiguous_multi_place_rule_rejected(cached):
    with pytest.raises(ValueError, match='unregistered'):
        make(cached, place_recognitions=[recognition('unknown')])
    with pytest.raises(ValueError):
        recognition().model_validate(recognition().model_dump() | {'unexpected': 'not silently ignored'})
    r = rule('wait', when=[[dict(fact='physical_arrival', op='eq', value=True)]])
    r['place_labels'] = ['A', 'B']
    with pytest.raises(ValueError, match='one named place'):
        make(cached, pol=policy(r))


def test_unbound_logic_matches_existing_evaluator_and_correlations():
    a = rule('wait', when=[[dict(fact='lost_awareness', op='eq', value=True)]])
    b = rule('walk', when=[[dict(fact='lost_awareness', op='eq', value=False)]]); b['id'] = 'r2'
    for value in (None, False, True):
        facts = {'lost_awareness': value}; pol = policy(a, b)
        old = m.possibilities(pol, facts, near_places=[], near_features={})[0]
        new = bound_possibilities(pol, facts, {}, near_places=[], near_features={})[0]
        assert {x.id if x else None for x in old} == {x.id if x else None for x in new}
    b['supersedes'] = ['r1']; b['when'] = [[]]
    assert [x.id for x in bound_possibilities(policy(a,b), {}, {}, near_places=[], near_features={})[0]] == ['r2']
