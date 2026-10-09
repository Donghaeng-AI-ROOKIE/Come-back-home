"""KINTEX road geometry + explicitly bounded synthetic observations, no map edits."""
import json
from datetime import timedelta
import pytest
from app.phase2.persistent_context_walk import PersistentContextPopulation
from app.phase2.environment_conditions import SceneConditions
from app.schemas.environment import EnvironmentObservation
from app.geo.h3grid import haversine_km
from tests.test_place_bound_walk import cached
from tests.kintex_fixtures import person, prior, START
from tests.test_person_policy import policy, rule

def observation(location,**kw):
    return EnvironmentObservation(**({'feature':'market','location':location,'radius_m':100,
        'valid_from':START,'valid_until':START+timedelta(minutes=10),
        'noisy':True,'source':'synthetic_scenario'}|kw))

def population(cached,observations=(),**kw):
    net,node,_=cached;start=net.node_location(node)
    r=rule('avoid',when=[[dict(fact='market.noisy',op='eq',value=True)]])
    r.update(feature='market',place_labels=[])
    return PersistentContextPopulation(net,person(start),prior(),policy(r),start,START,
        count=4,seed=17,environment_observations=observations,**kw)

def test_reported_area_supplies_missing_geometry_without_mutating_map(cached):
    net,node,_=cached;start=net.node_location(node);before=json.dumps(net.node_env,sort_keys=True)
    assert not net.node_env
    pop=population(cached,[observation(start)])
    p=pop.particles[0]
    assert pop.near(p)[1]['market'] is True
    assert pop.facts(p)['market.noisy'] is True
    p.avoid_feature='market'
    assert pop._feature_distance(p,node)==pytest.approx(0)
    nb=pop.neighbors[node][0]
    assert pop._feature_distance(p,nb)==pytest.approx(haversine_km(start,net.node_location(nb))*1000)
    result=pop.advance_to(.25)
    assert all(not x.blocked and x.mode=='avoid' and x.distance>0 for x in pop.particles)
    assert result['quality']['environment_observation_count']==1
    assert json.dumps(net.node_env,sort_keys=True)==before

def test_expiry_future_and_outside_are_unknown_not_quiet_or_absent(cached):
    net,node,other=cached;start=net.node_location(node)
    o=observation(start)
    pop=population(cached,[o]);p=pop.particles[0]
    assert pop.near(p)[1]['market'] is True
    p.minute=10
    assert pop.facts(p)['market.noisy'] is None and pop.near(p)[1]['market'] is None
    p.minute=-1
    assert pop.near(p)[1]['market'] is None
    p.minute=0;p.node=other
    assert pop.near(p)[1]['market'] is None and pop.facts(p)['market.noisy'] is None

def test_conflicting_noise_never_becomes_a_confirmed_avoidance(cached):
    net,node,_=cached;start=net.node_location(node)
    pop=population(cached,[observation(start),observation(start,noisy=False)])
    p=pop.particles[0]
    assert pop.near(p)[1]['market'] is True
    assert pop.facts(p)['market.noisy'] is None
    # Geometric evidence must not resolve the contradictory signal.
    assert pop.scene.at(node,0)['market']['noisy'] is None

def test_split_restart_preserves_reported_environment_walk(cached):
    net,node,_=cached;observations=[observation(net.node_location(node))]
    whole=population(cached,observations);expected=whole.advance_to(.5)
    split=population(cached,observations);split.advance_to(.25)
    restored=population(cached,observations,checkpoint=json.loads(json.dumps(split.checkpoint())))
    assert restored.advance_to(.5)==expected
    assert restored.checkpoint()==whole.checkpoint()
