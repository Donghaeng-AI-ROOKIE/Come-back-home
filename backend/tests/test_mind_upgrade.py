from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
import json
import pytest
from app.geo.roadnet import OSMnxNetwork
from app.schemas.common import GeoPoint
from app.schemas.persona import Persona,AttractionPoint
from app.schemas.prediction import PriorParams,LognormalParams
from app.schemas.environment import EnvironmentObservation
from experiments.mind_upgrade.contract import State,context_for,validate_decision,messages
from experiments.mind_upgrade.runtime import WalkingSession,RuntimePolicy

START=datetime(2026,9,28,8)
FIXTURE=Path(__file__).parent/'fixtures/kintex_walk.graphml'
MANIFEST=FIXTURE.with_suffix('.json')
# Contract tests do not simulate geography. Spatial tests require the verified
# KINTEX fixture; there is deliberately no fallback to the old test region.
P=GeoPoint(lat=0,lng=0)

def person(location=P):
    return Persona(id='synthetic',name='합성',age=78,type='dementia',home=location,
        onboarding_turns=[{'slot':'mobility','question':'피곤할 때는 어떻게 하나요?',
                           'answer':'무릎이 아프면 앉아서 쉬고 다시 걸어요.'}],
        behavior_notes=['피곤해도 계속 걷는다'],
        attraction_points=[AttractionPoint(label='등록 목적지',location=location,place_type='market')])

def prior():
    return PriorParams(strategy_probs={'random_walk':1},attraction_weights={'등록 목적지':1},
        radius_lognormal=LognormalParams(mu=0,sigma=1),
        initial_interpretation={'semantic_contract':{'other_traits':[{'type':'rest','condition':'pain'}]},
                                'unrepresented':[{'feature':'trait.rest'}]})

def state(**kw):return State(elapsed_minutes=60,distance_m=500,fatigue=.8,confusion=.2,**kw)

def ctx(**kw):
    return context_for(person(),prior(),state(),case_id='case',started_at=START,
        trigger='fatigue_changed',env={'market_m':20},observations=kw)

def decision(action='rest',**kw):
    return {'action':action,'goal_operation':'clear' if action=='roam' else 'keep',
            'goal_label':None,'avoid_feature':None,'evidence_ids':['N0'],
            'reason':'보호자 진술과 현재 상태를 고려한 합성 결정','confusion_level':'unknown',**kw}


def test_original_quote_and_unrepresented_k_traits_survive():
    c=ctx();p=c['person']
    assert '다시 걸어요' in p['evidence_notes'][0]['text']
    assert all(n['provenance']=='guardian_original' for n in p['evidence_notes'])
    assert '피곤해도 계속 걷는다' not in str(p['evidence_notes'])
    assert p['initial_interpretation']==prior().initial_interpretation


def test_current_time_and_elapsed_are_distinct():
    c=ctx();assert c['clock_time']=='2026-09-28T09:00:00'
    assert c['state']['elapsed_minutes']==60


def test_map_proximity_does_not_invent_noise_or_visibility():
    c=ctx();assert c['environment']['map_proximity_m']['market']==20
    assert c['environment']['observed_signals']['market']['noisy'] is None
    assert c['environment']['observed_place_labels']==[]


def test_explicit_false_is_preserved_not_unknown():
    assert ctx(market={'noisy':False})['environment']['observed_signals']['market']['noisy'] is False
    assert ctx(market={'noisy':True})['environment']['observed_signals']['market']['noisy'] is True


@pytest.mark.parametrize('patch',[{'action':'seek'}, {'goal_operation':'set','goal_label':'없는 장소'},
    {'avoid_feature':'water'}, {'evidence_ids':['fabricated']}, {'extra':'ignored'},
    {'action':'roam','goal_operation':'keep'}])
def test_invalid_decisions_rejected_not_silently_repaired(patch):
    with pytest.raises(ValueError):validate_decision(decision(**patch),ctx())


def test_unknown_environment_cannot_become_avoidance_target():
    with pytest.raises(ValueError):validate_decision(decision('avoid',avoid_feature='water'),ctx())


def test_person_revision_changes_with_guardian_correction():
    p=person();a=ctx()['person_revision'];p.onboarding_turns[0]['answer']='수정된 보호자 응답'
    b=context_for(p,prior(),state(),case_id='case',started_at=START,trigger='test',env={},observations={})
    assert a!=b['person_revision']


def test_history_cannot_come_from_future():
    with pytest.raises(ValueError):state(last_rest_end_minutes=61)


@pytest.fixture(scope='module')
def geography():
    if not FIXTURE.exists() or not MANIFEST.exists():pytest.skip('KINTEX cache required; no alternate geography')
    meta=json.loads(MANIFEST.read_text());assert meta['region']=='KINTEX, Goyang'
    return OSMnxNetwork.from_graphml(FIXTURE),GeoPoint(**meta['center'])


def session(geography,provider,**kw):
    net,center=geography
    return WalkingSession(net,person(center),prior(),center,START,provider,
        policy=RuntimePolicy(rest_minutes=5,reassess_minutes=20),**kw)


def test_rest_consumes_time_preserves_destination_and_resumes(geography):
    def provider(c):return decision('rest' if c['trigger']=='initial' else 'roam')
    s=session(geography,provider);s.target='등록 목적지'
    a=s.advance_to(3)
    assert a['state']['distance_m']==0 and a['state']['elapsed_minutes']==3
    assert a['state']['target_label']=='등록 목적지' and len(s.decisions)==1
    b=s.advance_to(6)
    assert b['state']['distance_m']>0 and b['state']['last_rest_end_minutes']==5
    assert any(e['kind']=='rest_complete' for e in b['history'])


def test_wait_remains_at_location_without_ending_clock(geography):
    s=session(geography,lambda c:decision('stay'));a=s.advance_to(60)
    assert a['state']['distance_m']==0 and a['state']['elapsed_minutes']==60
    assert not s.terminated


def test_hourly_snapshots_preserve_continuous_path(geography):
    a=session(geography,lambda c:decision('roam'),seed=42)
    b=session(geography,lambda c:decision('roam'),seed=42)
    a.advance_to(60);a.advance_to(120);x=a.advance_to(180);y=b.advance_to(180)
    assert [p['node'] for p in x['path']]==[p['node'] for p in y['path']]
    assert [p['minute'] for p in x['path']]==pytest.approx([p['minute'] for p in y['path']])
    assert x['state']['distance_m']==pytest.approx(y['state']['distance_m'])
    assert x['edge_to']==y['edge_to']


def test_noise_reaches_mind_and_expires(geography):
    observation=EnvironmentObservation(feature='market',location=geography[1],radius_m=500,
        valid_from=START,valid_until=START+timedelta(minutes=10),noisy=True,source='synthetic_scenario')
    s=session(geography,lambda c:decision('stay'),observations=[observation]);s.advance_to(21)
    assert s.decisions[0]['context']['environment']['observed_signals']['market']['noisy'] is True
    assert s.decisions[-1]['context']['environment']['observed_signals']['market']['noisy'] is None


def test_provider_failure_is_not_hidden(geography):
    def fail(c):raise RuntimeError('synthetic model failure')
    with pytest.raises(RuntimeError):session(geography,fail).advance_to(2)


def test_explicit_avoidance_beats_destination_bearing_without_forgetting_it(geography):
    from app.geo.h3grid import haversine_km
    net,center=geography
    node=min((n for n in net.graph if len(net.neighbors(n))>=3),
             key=lambda n:haversine_km(center,net.node_location(n)))
    neighbors=net.neighbors(node);toward=neighbors[0]
    old=deepcopy(net.node_env)
    try:
        # Synthetic distances on actual KINTEX branches, not measured local noise.
        # All exceed 180 m: the old absolute clamp gave them equal avoid weights.
        net.node_env={node:{'market_m':500},toward:{'market_m':300},
                      **{n:{'market_m':700} for n in neighbors[1:]}}
        s=session(geography,lambda c:decision('avoid',avoid_feature='market'))
        s.node=node;s.target='등록 목적지';s.labels[s.target]=toward;s._decide('test')
        class Capture:
            def choices(self,population,weights):
                self.weights=dict(zip(population,weights));return [population[0]]
        capture=Capture();s.rng=capture;s._choose_edge()
        assert all(capture.weights[n]>capture.weights[toward] for n in neighbors[1:])
        assert s.target=='등록 목적지' and s.action=='avoid'
    finally:
        net.node_env=old
