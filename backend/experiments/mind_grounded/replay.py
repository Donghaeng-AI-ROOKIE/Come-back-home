"""Consume saved valid decisions on KINTEX; no new interpretation or API call.

This isolates the executor. The synthetic environmental layer and saved answers
must not be described as model-in-the-loop trajectories or real observations.
"""
import argparse,json,math
from pathlib import Path
from datetime import datetime,timedelta
from copy import deepcopy
from app.geo.roadnet import OSMnxNetwork
from app.geo.h3grid import haversine_km
from app.schemas.common import GeoPoint
from app.schemas.persona import Persona
from app.schemas.prediction import PriorParams
from experiments.mind_upgrade.runtime import WalkingSession,RuntimePolicy
from .contract import validate


def run(out,source):
    cases={c['id']:c for c in json.loads((out/'development.json').read_text())}
    net=OSMnxNetwork.from_graphml(Path(__file__).parents[2]/'tests/fixtures/kintex_walk.graphml')
    rows=[]
    for row in json.loads(source.read_text()):
        if not row.get('contract_pass'):continue
        case=cases[row['case']];context=case['context'];decision=validate(row['parsed'],context)
        person=Persona.model_validate(case['persona']);prior=PriorParams.model_validate(case['prior'])
        center=net.node_location(net.nearest_node(person.home))
        # A synthetic feature 20 m east of the snapped start, explicitly not a POI.
        feature=decision.avoid_feature or 'market'
        anchor=GeoPoint(lat=center.lat,lng=center.lng+20/(111320*math.cos(math.radians(center.lat))))
        net.node_env={n:{feature+'_m':haversine_km(net.node_location(n),anchor)*1000} for n in net.graph}
        calls=[]
        def provider(c):
            calls.append(c)
            if len(calls)>1:raise RuntimeError('new_context_requires_new_validated_decision')
            return decision.model_dump(mode='json')
        state=context['state'];start=datetime.fromisoformat(context['clock_time'])-timedelta(minutes=state['elapsed_minutes'])
        s=WalkingSession(net,person,prior,center,start,provider,
                         policy=RuntimePolicy(rest_minutes=5,reassess_minutes=20))
        s.g.elapsed_min=state['elapsed_minutes'];s.g.F=state['fatigue'];s.g.C=state['confusion']
        s.distance=state['distance_m'];s.target=state['target_label'];s.target_reached=state['target_reached']
        s.last_rest_end=state['last_rest_end_minutes'];s.history=deepcopy(state['recent_events'])
        s.action=state['current_action'];s.travel_action=state['current_action']
        s.path=[{'minute':s.g.elapsed_min,'node':s.node}]
        before=s.snapshot();after=s.advance_to(state['elapsed_minutes']+.05)
        moved=after['state']['distance_m']-before['state']['distance_m']
        assert (moved==0) if decision.action in ('rest','stay') else (moved>0)
        if decision.goal_operation=='keep':assert s.target==state['target_label']
        rows.append({'case':case['id'],'saved_job':row['job'],'saved_action':decision.action,
                     'executor_action':s.action,'elapsed_seconds':3,'moved_m':moved,
                     'target_after':s.target,'next_node':s.edge_to,'snapshot':after,
                     'saved_decision_consumptions':len(calls),'new_model_calls':0})
    result={'scope':'saved decision → executor, not new model interpretation',
            'map':'cached KINTEX OSMnx','environment':'synthetic distances, no measured POI/noise',
            'replayed':len(rows),'rows':rows,'new_model_calls':0}
    (out/'KINTEX_저장응답_행동연결.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'replayed':len(rows),'new_model_calls':0,'all_motion_contracts_pass':True}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--source',type=Path,required=True)
    a=p.parse_args();run(a.out,a.source)
