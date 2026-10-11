"""Execution/interface tests; no model performance claim."""
import json
import pytest
from app.llm import mind_action_decision as contract
from tests.test_mind_person_handoff import context, prepared_person
from tests.test_mind_upgrade import geography, prior, START
from experiments.mind_person_handoff.session import create_v5_session
from experiments.mind_upgrade.runtime import RuntimePolicy


def output(**changes):
    return {'status':'insufficient_information','action':None,'goal_operation':None,
            'goal_label':None,'avoid_feature':None,'evidence_ids':['N0','state'],
            'reason':'현재 개인 조건을 확인할 정보가 부족함.','confusion_level':'unknown',**changes}


def test_abstention_is_not_an_executable_action():
    assert contract.executable(output(), context()) is None
    with pytest.raises(ValueError): contract.validate(output(action='stay'),context())


def test_previous_rest_requires_explicit_resume():
    c=context(execution={'previous_travel_action':'seek'});c['state']['current_action']='rest'
    with pytest.raises(ValueError,match='stationary'):
        contract.validate(output(status='decision',action='continue',goal_operation='keep'),c)
    assert contract.executable(output(status='decision',action='seek',goal_operation='set',goal_label='등록 목적지'),c)['action']=='seek'


def test_original_k_scope_and_evidence_survive_message_builder():
    c=context();sent=json.loads(contract.messages(c)[1]['content'])
    assert sent['person']==c['person']
    assert sent['engine_current_facts']['fatigue_band']=='high'
    assert sent['engine_current_facts']['current_environment_observations']['market']['crowded'] is None
    assert 'expected' not in sent


def test_deferred_probe_does_not_move_or_claim_a_personal_action(geography):
    net,center=geography
    s=create_v5_session(net,prepared_person(center),prior(),center,START,
        request=lambda body:output(),model='offline',provider='kexaone',policy=RuntimePolicy(5,20))
    result=s.advance_to(60)
    assert result['state']['distance_m']==0
    assert result['termination_reason']=='model_abstained'
    assert s.decisions[0]['decision'] is None
    assert s.decisions[0]['model_response']['status']=='insufficient_information'
    assert len(s.decisions)==1


def test_rest_then_explicit_resume_on_kintex(geography):
    net,center=geography;calls=[]
    def request(body):
        c=json.loads(body['messages'][1]['content']);calls.append(c)
        return output(status='decision', action='rest' if len(calls)==1 else 'roam',
                      goal_operation='keep' if len(calls)==1 else 'clear')
    s=create_v5_session(net,prepared_person(center),prior(),center,START,
        request=request,model='offline',provider='kexaone',policy=RuntimePolicy(5,20))
    assert s.advance_to(3)['state']['distance_m']==0
    assert s.advance_to(6)['state']['distance_m']>0
    assert calls[1]['state']['current_action']=='rest'
    assert calls[1]['state']['last_rest_end_minutes']==5


def test_v5_hourly_continuity_through_six_hours_on_kintex(geography):
    """Scripted actions verify the executor, not live model quality."""
    net, center = geography

    def make():
        return create_v5_session(
            net, prepared_person(center), prior(), center, START,
            request=lambda body: output(status='decision', action='roam',
                                        goal_operation='clear'),
            model='offline', provider='kexaone', policy=RuntimePolicy(5, 20), seed=42)

    split, whole = make(), make()
    snapshots = [split.advance_to(minute) for minute in (60, 120, 240, 360)]
    expected = whole.advance_to(360)
    distances = [s['state']['distance_m'] for s in snapshots]
    assert all(a < b for a, b in zip(distances, distances[1:]))
    assert distances[-1] == pytest.approx(expected['state']['distance_m'])
    assert [p['node'] for p in snapshots[-1]['path']] == [p['node'] for p in expected['path']]
    assert [p['minute'] for p in snapshots[-1]['path']] == pytest.approx(
        [p['minute'] for p in expected['path']])
    assert snapshots[-1]['state']['elapsed_minutes'] == 360


def test_v5_expired_observation_is_unknown_and_can_defer(geography):
    from datetime import timedelta
    from app.schemas.environment import EnvironmentObservation

    net, center = geography
    observation = EnvironmentObservation(
        feature='market', location=center, radius_m=500,
        valid_from=START, valid_until=START + timedelta(minutes=10),
        noisy=True, source='synthetic_scenario')
    seen = []

    def request(body):
        c = json.loads(body['messages'][1]['content'])
        seen.append(c)
        if c['environment']['observed_signals']['market']['noisy'] is None:
            return output()
        return output(status='decision', action='stay', goal_operation='keep')

    session = create_v5_session(
        net, prepared_person(center), prior(), center, START, request=request,
        model='offline', provider='kexaone', policy=RuntimePolicy(5, 20),
        observations=[observation])
    result = session.advance_to(60)
    assert seen[0]['environment']['observed_signals']['market']['noisy'] is True
    assert seen[-1]['environment']['observed_signals']['market']['noisy'] is None
    assert result['termination_reason'] == 'model_abstained'
    assert result['state']['distance_m'] == 0
    assert session.decisions[-1]['decision'] is None
