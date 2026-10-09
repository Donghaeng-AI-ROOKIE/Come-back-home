"""Dynamics consumers: separate movement history, observed conditions, and assumptions."""
import pytest
from tests.kintex_fixtures import geography
from tests.test_person_policy import population,rule,policy,obs

def test_named_environment_scope_does_not_expand_to_all_markets(geography):
    p=population(geography);r=rule('avoid',when=[[dict(fact='market.noisy',op='eq',value=True)]]);r.update(feature='market',place_labels=['등록 목적지'])
    from app.llm.mind_policy import possibilities
    pol=policy(r)
    assert possibilities(pol,{'market.noisy':True},near_places=[],near_features=['market'])[0]==[None]
    choices,_=possibilities(pol,{'market.noisy':True},near_places=['등록 목적지'],near_features=['market'])
    assert [r.action for r in choices]==['avoid']

def test_explicit_rest_override_beats_wait(geography):
    wait=rule('wait',when=[[dict(fact='lost_awareness',op='eq',value=True)]]);wait['id']='wait'
    rest=rule('rest',when=[[dict(fact='pain_observed',op='eq',value=True)]]);rest['supersedes']=['wait']
    p=population(geography,policy(wait,rest),behavior_observations=[obs('lost_awareness',True),obs('pain_observed',True)])
    p.advance_to(4)
    assert all(x.rest==pytest.approx(4) and x.waiting==0 for x in p.particles)

def test_clock_not_identical_after_four_hours(geography):
    p=population(geography,policy(rule()),count=12)
    a=p.advance_to(240);d=[x.distance for x in p.particles];b=p.advance_to(360)
    alive=[i for i,x in enumerate(p.particles) if not x.blocked]
    assert alive and all(p.particles[i].distance>d[i] for i in alive)
    assert a['cells']!=b['cells']

def test_wait_is_legitimately_identical_across_hours(geography):
    r=rule('wait',when=[[dict(fact='lost_awareness',op='eq',value=True)]])
    p=population(geography,policy(r),behavior_observations=[obs('lost_awareness',True,0,361)])
    a=p.advance_to(240);b=p.advance_to(360)
    assert a['cells']==b['cells'] and all(x.waiting==pytest.approx(360) for x in p.particles)

def test_same_fatigue_state_different_personal_responses(geography):
    # Model supplies the response; the engine supplies a labelled provisional
    # fatigue state. Never infer the personal response from guardian keywords.
    condition=[[dict(fact='fatigue_high',op='eq',value=True)]]
    rest=population(geography,policy(rule('rest',when=condition)))
    walk=population(geography,policy(rule('walk',when=condition)))
    for pop in (rest,walk):
        for p in pop.particles:p.fatigue=.8
    rest.advance_to(2);walk.advance_to(2)
    assert all(p.rest==pytest.approx(2) for p in rest.particles)
    assert all(p.walking==pytest.approx(2) for p in walk.particles)

def test_recognition_alone_does_not_invent_a_stopping_response(geography):
    p=population(geography,behavior_observations=[obs('target_recognized',True)])
    for x in p.particles:x.target='등록 목적지';x.strategy='route_following'
    p.advance_to(2)
    assert all(x.arrived and x.walking==pytest.approx(2) and x.waiting==0 for x in p.particles)

def test_sourced_arrival_response_can_stop_and_retains_goal(geography):
    r=rule('wait',when=[[dict(fact='physical_arrival',op='eq',value=True),dict(fact='target_recognized',op='eq',value=True)]])
    p=population(geography,policy(r),behavior_observations=[obs('target_recognized',True)])
    for x in p.particles:x.target='등록 목적지';x.strategy='route_following'
    p.advance_to(2)
    assert all(x.arrived and x.target=='등록 목적지' and x.waiting==pytest.approx(2) for x in p.particles)

def test_unmapped_avoidance_is_not_fake_success(geography):
    r=rule('avoid',when=[[]]);r.update(feature='market')
    p=population(geography,policy(r),count=30)
    original=p.net.node_env;p.net.node_env={}
    try:
        result=p.advance_to(1)
        assert result['quality']['unresolved_mass']>0
        assert any(e['kind']=='unmapped_avoidance' for x in p.particles for e in x.events)
        assert sum(result['cells'].values())+result['quality']['unresolved_mass']==pytest.approx(1)
    finally:p.net.node_env=original

def test_environment_observation_uses_partial_edge_position(geography):
    from datetime import timedelta
    from app.schemas.environment import EnvironmentObservation
    from app.phase2.environment_conditions import SceneConditions
    from tests.kintex_fixtures import START
    p=population(geography);x=p.particles[0]
    u,v=max(p.attrs,key=lambda edge:float(p.attrs[edge].get('length',0)))
    x.node=u;x.edge_to=v;x.edge_length=float(p.attrs[u,v]['length']);x.edge_remaining=x.edge_length/2
    location=p.position(x)
    observation=EnvironmentObservation(feature='market',location=location,radius_m=1,valid_from=START,valid_until=START+timedelta(minutes=5),noisy=True,source='synthetic_scenario')
    p.scene=SceneConditions(p.net,[observation],START)
    assert p.scene.at(u,0)=={}
    assert p.facts(x)['market.noisy'] is True
