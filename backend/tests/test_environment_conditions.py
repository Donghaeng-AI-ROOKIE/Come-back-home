"""Scene conditions must change real graph choices only where/when observed."""
from datetime import datetime,timedelta
from pathlib import Path
import pytest
from app.schemas.environment import EnvironmentObservation
from app.schemas.persona import Persona,EnvResponse
from app.schemas.common import GeoPoint
from app.phase2.environment_conditions import SceneConditions,matches
from app.phase2.gauges import env_response_weight
from app.phase2 import simulation
from app.config import settings

T=datetime(2026,9,25,22)
P=GeoPoint(lat=37.6061,lng=127.0106)

def observation(**kw):
    return EnvironmentObservation(**({'feature':'market','location':P,'radius_m':100,
        'valid_from':T,'valid_until':T+timedelta(minutes=5),'crowded':True,'noisy':True,
        'source':'synthetic_scenario'}|kw))

def person(clauses):
    return Persona(id='conditional',type='dementia',name='synthetic',age=80,home=P,
        env_responses=[EnvResponse(feature='market',direction='회피',strength=.5,condition_clauses=clauses)])

AND=[[{'signal':'crowded','state':'present'},{'signal':'noisy','state':'present'}]]
OR=[[{'signal':'crowded','state':'present'}],[{'signal':'noisy','state':'present'}]]

@pytest.mark.parametrize('signals,active',[( {},False),({'crowded':True},False),({'crowded':True,'noisy':False},False),({'crowded':True,'noisy':None},False),({'crowded':True,'noisy':True},True),({'crowded':'true','noisy':True},False)])
def test_and_unknown_not_promoted(signals,active):
    p=person(AND);w=env_response_weight({'market_m':20},p,conditions={'market':signals})
    assert (w<1)==active
    assert env_response_weight({'market_m':1000},p,conditions={'market':signals})==1


def test_or_and_negative_do_not_treat_missing_as_false():
    assert matches(person(OR).env_responses[0].condition_clauses,{'noisy':True})
    negative=person([[{'signal':'noisy','state':'absent'}]]).env_responses[0].condition_clauses
    assert not matches(negative,{}) and not matches(negative,{'noisy':None})
    assert matches(negative,{'noisy':False})


class Net:
    def node_location(self,node):return P if node==0 else GeoPoint(lat=37.7,lng=127.1)


def test_space_time_conflict_and_feature_scope():
    net=Net();scene=SceneConditions(net,[observation()],T)
    assert scene.at(0,0)['market']=={'crowded':True,'noisy':True}
    assert scene.at(0,5)=={} and scene.at(0,-1)=={} and scene.at(1,0)=={}
    conflict=SceneConditions(net,[observation(),observation(noisy=False)],T)
    assert conflict.at(0,1)['market']['noisy'] is None
    assert env_response_weight({'market_m':5},person(AND),conditions=conflict.at(0,1))==1
    forest=SceneConditions(net,[observation(feature='forest')],T)
    assert env_response_weight({'market_m':5},person(AND),conditions=forest.at(0,1))==1
    assert SceneConditions(net,[observation()],None).at(0,0)=={}


@pytest.mark.parametrize('kwargs',[{'noisy':'true'},{'valid_until':T},{'radius_m':0},{'radius_m':float('nan')},{'crowded':None,'noisy':None}])
def test_invalid_observations_rejected(kwargs):
    with pytest.raises(ValueError):observation(**kwargs)


def test_unconditional_backward_compatibility():
    assert env_response_weight({'market_m':10},person([]))<1


@pytest.mark.parametrize('mode',['agent','statistical'])
def test_observations_reach_actual_osm_graph_neighbor_weights(monkeypatch,mode):
    from app.geo.roadnet import OSMnxNetwork
    from app.schemas.prediction import PriorParams,LognormalParams
    net=OSMnxNetwork.from_graphml(Path(__file__).parent/'fixtures/jeongneung_walk_800m.graphml')
    # Actual cached graph, controlled environment annotation; no live crowd claim.
    net.node_env={n:{'market_m':10 if net.node_location(n).lng > P.lng else 1000} for n in net.graph.nodes}
    original={n:dict(e) for n,e in net.node_env.items()}
    monkeypatch.setattr(settings,'mind_call_budget',0)
    monkeypatch.setattr(settings,'mind_transitions_per_walker',0)
    values=[];original_weight=simulation.gauge_mod.env_response_weight
    def capture(env,p,**kw):
        v=original_weight(env,p,**kw);values.append(v);return v
    monkeypatch.setattr(simulation.gauge_mod,'env_response_weight',capture)
    prior=PriorParams(strategy_probs={'random_walk':1.},attraction_weights={},radius_lognormal=LognormalParams(mu=0,sigma=.1),reasoning='test',source='stub')
    active=observation(radius_m=500,valid_until=T+timedelta(hours=2))
    active_poa=simulation.run_monte_carlo(P,prior,person(AND),.1,mode=mode,net=net,n_walkers=48,seed=42,environment_observations=[active],started_at=T)
    assert values and any(v<1 for v in values)
    values.clear()
    calm_poa=simulation.run_monte_carlo(P,prior,person(AND),.1,mode=mode,net=net,n_walkers=48,seed=42,environment_observations=[observation(noisy=False)],started_at=T)
    assert values and all(v==1 for v in values)
    assert active_poa != calm_poa
    assert net.node_env==original


def test_report_api_persists_typed_observation():
    from fastapi.testclient import TestClient
    from app.main import app
    response=TestClient(app).post('/phase1/reports',json={
        'missing_type':'dementia','lkp':P.model_dump(),'lkp_time':T.isoformat(),
        'environment_observations':[observation().model_dump(mode='json')]})
    assert response.status_code==200
    body=response.json()
    restored=TestClient(app).get('/phase1/cases/'+body['id']).json()
    assert restored['report']['environment_observations'][0]['noisy'] is True


def test_pipeline_passes_same_person_and_observations_to_both_modes_and_preview(monkeypatch):
    from app import storage
    from app.phase2 import pipeline
    from app.schemas.report import MissingReport
    from app.schemas.case import Case
    from app.llm.exaone import ExaoneClient
    from app.geo import h3grid
    p=person(AND);storage.personas.save(p.id,p)
    report=MissingReport(id='condition-report',persona_id=p.id,missing_type='dementia',lkp=P,lkp_time=T,environment_observations=[observation()])
    case=Case(id='condition-case',report=report,lkp=P,lkp_time=T)
    prior=ExaoneClient()._default_prior(p,report);called=[];seen=[]
    monkeypatch.setattr(pipeline.exaone,'generate_prior',lambda *a:prior)
    monkeypatch.setattr(pipeline,'apply_prepared',lambda *a:called.append(a) or prior)
    monkeypatch.setattr(pipeline,'_load_roadnet',lambda *a:(None,'test'))
    monkeypatch.setattr(simulation,'run_monte_carlo',lambda *a,**kw:seen.append((a,kw)) or {h3grid.cell_of(P):1.})
    pipeline.run_prediction(case,now=T+timedelta(hours=1),seed=1)
    pipeline.poa_at_elapsed(case,2,seed=1)
    assert len(called)==1 and len(seen)==4
    for args,kw in seen:
        assert args[2].env_responses[0].condition_clauses
        assert kw['environment_observations']==report.environment_observations
        assert kw['started_at']==T
    assert [kw['mode'] for _,kw in seen]==['agent','statistical','agent','statistical']


def test_citizen_story_does_not_erase_conditions():
    from app.phase3.storytelling import to_tone_params
    from app.schemas.case import Case
    from app.schemas.report import MissingReport
    report=MissingReport(id='r',missing_type='dementia',lkp=P,lkp_time=T)
    case=Case(id='c',report=report,lkp=P,lkp_time=T)
    assert to_tone_params(case,person(AND),now=T).env==[]
    assert to_tone_params(case,person([]),now=T).env==[('market','회피')]
