"""Release-blocking dynamics on the real cached KINTEX graph, no model calls."""
import json
from datetime import timedelta

import pytest

from tests.kintex_fixtures import geography
from tests.test_person_policy import population, policy, rule, obs


def test_missing_personal_rest_does_not_disable_fatigue_response(geography):
    pop = population(geography)
    for walker in pop.particles:
        walker.fatigue = 5.0
    result = pop.advance_to(7)
    assert all(walker.rest > 0 for walker in pop.particles)
    assert all(walker.walking < 7 for walker in pop.particles)
    assert result['quality']['population_rest_is_provisional'] is True
    assert all(walker.walking + walker.rest + walker.waiting == pytest.approx(7)
               for walker in pop.particles)


def test_explicit_personal_walk_is_not_overwritten_by_population_rest(geography):
    r = rule('walk', when=[[dict(fact='fatigue_high', op='eq', value=True)]])
    pop = population(geography, policy(r))
    for walker in pop.particles:
        walker.fatigue = 5.0
    pop.advance_to(7)
    assert all(walker.walking == pytest.approx(7) and walker.rest == 0
               for walker in pop.particles)


def test_walking_when_lost_does_not_imply_endurance_when_fatigued(geography):
    r=rule('walk',when=[[dict(fact='lost_awareness',op='eq',value=True)]])
    pop=population(geography,policy(r),behavior_observations=[obs('lost_awareness',True)])
    for walker in pop.particles:walker.fatigue=5.
    pop.advance_to(7)
    assert all(w.rest>0 for w in pop.particles)


def test_inactive_physical_clause_does_not_disable_rest(geography):
    r=rule('walk',when=[[dict(fact='lost_awareness',op='eq',value=True)],
                       [dict(fact='continuous_walk_minutes',op='gte',value=1000)]])
    pop=population(geography,policy(r),behavior_observations=[obs('lost_awareness',True)])
    for walker in pop.particles:walker.fatigue=5.
    pop.advance_to(7)
    assert all(w.rest>0 for w in pop.particles)


def test_fractional_observation_change_interrupts_wait_at_its_time(geography):
    r = rule('wait', when=[[dict(fact='lost_awareness', op='eq', value=True),
                           dict(fact='family_present', op='eq', value=False)]])
    # The release is a fractional-time change of the wait condition itself.
    # (A family observed beside the person is a reunion and is not walked on.)
    pop = population(geography, policy(r), behavior_observations=[
        obs('lost_awareness', True, 0, .25), obs('lost_awareness', False, .25),
        obs('family_present', False),
    ])
    pop.advance_to(1)
    assert all(walker.waiting == pytest.approx(.25) for walker in pop.particles)
    assert all(walker.walking == pytest.approx(.75) for walker in pop.particles)


def test_fractional_environment_expiry_changes_response_at_its_time(geography):
    from app.schemas.environment import EnvironmentObservation
    from tests.kintex_fixtures import START
    _, center = geography
    r = rule('wait', when=[[dict(fact='market.noisy', op='eq', value=True)]])
    pop = population(geography, policy(r), environment_observations=[
        EnvironmentObservation(feature='market', location=center, radius_m=500,
            valid_from=START, valid_until=START+timedelta(minutes=.25),
            noisy=True, source='synthetic_scenario'),
        EnvironmentObservation(feature='market', location=center, radius_m=500,
            valid_from=START+timedelta(minutes=.25), valid_until=START+timedelta(minutes=2),
            noisy=False, source='synthetic_scenario'),
    ])
    pop.advance_to(1)
    assert all(walker.waiting == pytest.approx(.25) for walker in pop.particles)


def test_population_rest_restarts_with_the_same_clock_and_random_state(geography):
    whole = population(geography)
    split = population(geography)
    for pop in (whole, split):
        for walker in pop.particles:
            walker.fatigue = 5.0
    expected = whole.advance_to(23)
    split.advance_to(7)
    restored = population(geography, checkpoint=json.loads(json.dumps(split.checkpoint())))
    actual = restored.advance_to(23)
    assert actual == expected
    assert restored.checkpoint() == whole.checkpoint()


def test_cumulative_trigger_gauge_does_not_erase_directional_state(geography):
    pop = population(geography)
    walker = pop.particles[0]
    walker.strategy = 'directional';walker.heading = .5
    class Capture:
        def choices(self, nodes, weights):
            self.weights = list(weights)
            return [nodes[0]]
    a = Capture();pop._edge(walker, a)
    walker.edge_to = None;walker.heading = .5
    walker.confusion = 5.
    b = Capture();pop._edge(walker, b)
    assert a.weights == b.weights
    assert pop.distribution(0)['quality']['direction_state_source'] == 'unobserved_default_0.5'


def test_fatigue_can_interrupt_seek_without_deleting_destination(geography):
    r = rule('seek', when=[[]]);r.update(goal_label='등록 목적지', hold_minutes=None)
    pop = population(geography, policy(r))
    # A distant mapped destination; the guardian intent is not an endurance claim.
    target = max(pop.locations, key=lambda n:pop.locations[n].lat)
    pop.goals['등록 목적지'] = target
    for walker in pop.particles:walker.fatigue = 5.
    pop.advance_to(7)
    assert all(w.rest > 0 and w.target == '등록 목적지' for w in pop.particles)
    assert all(w.population_rest_minutes > 0 for w in pop.particles)
    for walker in pop.particles:walker.fatigue = 0.
    # Finish any current rest, then observe the personal destination being resumed.
    end = max(w.hold_until for w in pop.particles) + .5
    pop.advance_to(end)
    assert all(w.mode == 'seek' and w.target == '등록 목적지' for w in pop.particles)


def test_updated_direction_state_is_separate_from_trigger_gauge(geography):
    from app.schemas.prediction import MindState
    pop=population(geography,mind=MindState(changed=True,confusion=.85))
    pop.particles[0].confusion=10.
    quality=pop.distribution(0)['quality']
    assert quality['direction_state']==.85
    assert quality['direction_state_source']=='updated_mind_state'


def test_korean_clock_follows_stored_server_local_time(geography,monkeypatch):
    # Stored naive times are server-local (schemas.common._to_local_naive), the
    # same reading as the SAR prompt and the app (walkFormat.serverTimeMs). On a
    # UTC server, 08:00 Korean time is stored as 23:00 of the previous day.
    import time
    from zoneinfo import ZoneInfo
    from tests.kintex_fixtures import START
    monkeypatch.setenv('TZ','UTC');time.tzset()
    try:
        stored=START.replace(tzinfo=ZoneInfo('Asia/Seoul')).astimezone().replace(tzinfo=None)
        assert stored.hour==(START.hour-9)%24
        net,center=geography
        from tests.test_person_policy import person,prior,policy
        from app.phase2.person_walk import Population
        pop=Population(net,person(center),prior(),policy(),center,stored,count=4)
        assert pop.facts(pop.particles[0])['clock_hour']==START.hour
    finally:
        monkeypatch.undo();time.tzset()
