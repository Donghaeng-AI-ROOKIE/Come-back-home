"""Clock/action integration on cached KINTEX, not clinical/model accuracy."""
import pytest
from experiments.mind_upgrade.runtime import WalkingSession, RuntimePolicy
from app.llm.mind_handoff import context_for, validate_decision
from tests.test_mind_upgrade import geography, person, prior, START, decision
from experiments.mind_closed_loop.bridge import MeteredDecisionBridge, probability_snapshot


def test_walking_rest_wait_are_not_elapsed_time(geography):
    net, center = geography
    choices = iter([decision('rest'), decision('stay'), decision('roam')])
    s = WalkingSession(net, person(center), prior(), center, START,
        lambda c: next(choices), policy=RuntimePolicy(5,20),
        context_builder=context_for, decision_validator=validate_decision)
    s.advance_to(30)
    times = s.context('inspection')['locomotion']
    assert times['resting_minutes'] == 5
    assert times['waiting_minutes'] == 20
    assert times['walking_minutes'] == pytest.approx(5)
    assert times['continuous_walking_minutes'] == pytest.approx(5)
    assert sum(times[k] for k in ('walking_minutes','resting_minutes','waiting_minutes')) == pytest.approx(30)


def test_defer_does_not_fabricate_six_hours_standing(geography):
    net, center = geography
    s=WalkingSession(net, person(center), prior(), center, START,
        lambda c: None, policy=RuntimePolicy(5,20), allow_abstention=True)
    snap=s.advance_to(360)
    assert snap['termination_reason']=='model_abstained'
    assert snap['state']['elapsed_minutes']==0
    assert snap['locomotion']['waiting_minutes']==0


def test_split_hours_preserve_time_accounting(geography):
    net,center=geography
    def make():
        return WalkingSession(net,person(center),prior(),center,START,
            lambda c: decision('roam'),policy=RuntimePolicy(5,20),seed=45)
    whole,split=make(),make()
    a=whole.advance_to(360)
    for t in (60,120,240,360): b=split.advance_to(t)
    for key in ('walking_minutes','continuous_walking_minutes','resting_minutes','waiting_minutes'):
        assert a['locomotion'][key]==pytest.approx(b['locomotion'][key])
    assert a['locomotion']['walking_minutes']==pytest.approx(360)


def test_compiled_k_features_reach_walker_without_mutating_stored_person(geography):
    net,center=geography;p=person(center);params=prior()
    params.persona_adjustments={'persona_id':p.id,'persona_version':p.version,
        'axis_scores':{'도보 지속성':.9},'route_familiarity':[{'route':'등록 목적지','score':.8}],
        'env_responses':[{'feature':'market','direction':'회피','strength':.8}]}
    s=WalkingSession(net,p,params,center,START,lambda c: decision('roam'),policy=RuntimePolicy(5,20))
    assert s.persona.env_responses[0].direction=='회피'
    assert s.persona.route_familiarity[0].score==.8
    assert s.persona.axis_scores==params.persona_adjustments['axis_scores']
    assert p.env_responses==[] and p.route_familiarity==[]


def test_cache_cannot_reuse_other_condition_or_elapsed_time():
    calls=[]
    provider=MeteredDecisionBridge(lambda c:c,lambda r,c:r,
        lambda b: calls.append(b) or decision('roam'),max_calls=1)
    assert provider({'noise':True,'minute':0}) is not None
    assert provider({'noise':True,'minute':0}) is not None
    assert len(calls)==1
    assert provider({'noise':False,'minute':0}) is None
    assert provider.stop_reason=='call_budget_exhausted_without_equivalent_context'
    assert provider.last_response is None
    assert provider({'noise':True,'minute':1}) is None


def test_unknown_walker_retains_missing_probability_mass(geography):
    net,center=geography
    good=WalkingSession(net,person(center),prior(),center,START,
        lambda c: decision('stay'),policy=RuntimePolicy(5,20))
    missing=WalkingSession(net,person(center),prior(),center,START,
        lambda c: None,policy=RuntimePolicy(5,20),allow_abstention=True)
    result=probability_snapshot(net,[good.advance_to(60),missing.advance_to(60)],60)
    assert result['resolved_mass']==pytest.approx(.5)
    assert result['unresolved_mass']==pytest.approx(.5)
    assert sum(result['cells'].values())==pytest.approx(.5)


def test_missing_seek_target_fails_before_model_call(geography):
    net,center=geography;calls=[]
    s=WalkingSession(net,person(center),prior(),center,START,
        lambda c:calls.append(c) or decision('roam'),policy=RuntimePolicy(5,20))
    s.action='seek'
    with pytest.raises(ValueError,match='registered current target'): s.advance_to(1)
    assert not calls


def test_immediate_reversal_matches_existing_production_penalty(geography):
    net,center=geography
    s=WalkingSession(net,person(center),prior(),center,START,
        lambda c:decision('roam'),policy=RuntimePolicy(5,20))
    s.node=next(n for n in net.graph.nodes if len(net.neighbors(n))>=3)
    class Capture:
        def choices(self,nodes,weights):
            self.weights=dict(zip(nodes,weights));return [nodes[0]]
    capture=Capture();s.rng=capture;s.action='avoid';s.avoid_feature='market'
    s._choose_edge();original=dict(capture.weights)
    back=next(iter(original));s.previous_node=back;s._choose_edge()
    assert capture.weights[back]==pytest.approx(original[back]*.2)
    assert all(capture.weights[n]==pytest.approx(w) for n,w in original.items() if n!=back)


def test_compiled_route_familiarity_changes_accumulated_confusion(geography):
    net, center = geography
    destination = max(net.graph.nodes, key=lambda n:
        abs(net.node_location(n).lat-center.lat)+abs(net.node_location(n).lng-center.lng))
    def make(score):
        p = person(center); p.attraction_points[0].location = net.node_location(destination)
        params = prior()
        params.persona_adjustments = {'persona_id':p.id, 'persona_version':p.version,
            'axis_scores':{}, 'env_responses':[],
            'route_familiarity':[{'route':'등록 목적지','score':score}]}
        s = WalkingSession(net,p,params,center,START,
            lambda c: decision('seek',goal_operation='set',goal_label='등록 목적지'),
            policy=RuntimePolicy(5,30),seed=104)
        s.mind_confusion = .5  # Same road-choice kernel; only the gauge consumer varies.
        return s
    unfamiliar, familiar = make(0.), make(1.)
    unfamiliar.advance_to(2); familiar.advance_to(2)
    assert unfamiliar.node == familiar.node
    assert unfamiliar.g.C-familiar.g.C == pytest.approx(2*unfamiliar.g.cfg.k_c1)


def test_latest_observation_survives_action_history_truncation(geography):
    net, center = geography
    s = WalkingSession(net,person(center),prior(),center,START,
        lambda c:decision('stay'),policy=RuntimePolicy(5,30),
        context_builder=context_for,decision_validator=validate_decision)
    s.history = [{'kind':'self_lost_awareness_observation', 'value':True,
                  'elapsed_minutes':0.,'provenance':'authored test observation'}]
    s.advance_to(270)
    events = s.context('inspection')['state']['recent_events']
    observations = [e for e in events if e['kind']=='self_lost_awareness_observation']
    assert len(observations)==1
    assert observations[0]['value'] is True and observations[0]['elapsed_minutes']==0.
    # A later unknown supersedes the earlier value; retaining history is not
    # permission to keep treating an old observation as a current fact.
    s.history.append({'kind':'self_lost_awareness_observation','value':None,
                      'elapsed_minutes':270.,'provenance':'authored test observation'})
    s.advance_to(540)
    events = s.context('inspection')['state']['recent_events']
    observations = [e for e in events if e['kind']=='self_lost_awareness_observation']
    assert len(observations)==1 and observations[0]['value'] is None
    assert observations[0]['elapsed_minutes']==270.
