"""Offline paired downstream audit. No model, network, mind or production mutation.

Frozen final K preparation vs the SAME preparation with each saved SAR baseline.
Real OSM topology; synthetic relocated places, not real missing-person trajectories.
Protocol is written before simulation. No distribution is treated as ground truth.
"""
import copy, hashlib, json, os, socket, sys, time
from pathlib import Path
from collections import Counter
from statistics import mean

D = Path(__file__).resolve().parent
P = D.parent / 'FRONT_SAR_ablation_20260927'
CODE = Path('/private/tmp/cbh-front-fixes-20260926')
os.environ.update(PERSIST_STORAGE='false', USE_ROADNET='false', TZ='Asia/Seoul')
time.tzset()
def blocked(*args, **kwargs):
    raise RuntimeError('external calls prohibited in offline audit')
socket.socket.connect = blocked
socket.create_connection = blocked
sys.path.insert(0, str(CODE / 'backend'))
from app.config import settings
settings.kexaone_model = "depmkuykpfon9lg"
from app.phase0 import person_preparation as prep
from app.llm.initial_behavior import simulation_persona
from app.llm import exaone, usage_ledger
from app.schemas.persona import Persona
from app.schemas.prediction import PriorParams
from app.schemas.report import MissingReport
from app.schemas.common import GeoPoint
from app.schemas.debug import SimTrace
from app.geo.roadnet import OSMnxNetwork
from app.geo.h3grid import haversine_km
from app.phase2.simulation import run_monte_carlo
exaone.generate_prior = exaone.reinterpret_mind = blocked

def read(p): return json.loads(p.read_text())
def write(p, v): p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def tv(a, b): return sum(abs(a.get(k, 0)-b.get(k, 0)) for k in set(a)|set(b))/2

def main():
    assert not (D/'results.json').exists(), 'do not overwrite evidence'
    graph = CODE/'backend/tests/fixtures/jeongneung_walk_800m.graphml'
    cases = read(P/'cases.json')
    protocol = {
        'new_model_calls': 0, 'mind_enabled': False, 'network_enabled': False,
        'code_commit': '24650adc938a17ddad1da9a2131cb6075b6d486b',
        'graph_sha256': sha(graph), 'cases': [c['id'] for c in cases],
        'K_preparation': 'grounding_v3/personas/*_r1.json, fixed across arms',
        'SAR_baselines': 'outputs/*_r1.json and *_r2.json B.baseline',
        'seeds': [41, 73, 109, 137, 173], 'hours': [1, 4], 'layouts': [0, 1],
        'walkers': 500, 'expected_runs': 360,
        'arms': ['K_profile_baseline', 'K_SAR_r1', 'K_SAR_r2'],
        'prespecified_expectations': [
            'W1 waiting yields more endpoints within 100m than W2 continuing, same setting',
            'W2 continuing yields greater mean path distance than W1 waiting, same setting',
            'G2 current market routine yields more market endpoints than G1 historical-only, same setting',
            'identical seed 1h/4h outputs are diagnostic, not automatically a failure',
            'between-SAR-repeat variation is sensitivity, not an accuracy score',
        ],
        'decision_rule': 'An explicit personal contrast reversal rejects adequacy on that contrast. Passing contrasts alone does not prove calibrated probabilities or clinical non-inferiority. No winner from concentration or path length alone.',
        'limits': ['small cached 800m OSM graph', 'synthetic places relocated to nodes; layout 1 rotates their locations', 'no real crowd/noise layers, E1/E2 environmental superiority not judged', 'same K outputs and development cases, no independent clinical sample'],
        'sources': {},
    }
    for c in cases:
        cid=c['id']
        for f in [P/'grounding_v3/personas'/f'{cid}_r1.json']+[P/'outputs'/f'{cid}_r{r}.json' for r in (1,2)]:
            protocol['sources'][str(f.relative_to(P))]=sha(f)
    write(D/'protocol.json', protocol)
    ledger = D.parents[1]/'연구지원_사용기록/usage_events.jsonl'
    started=time.monotonic()
    usage_ledger.append_event({'event_type':'resource_session_started','run_id':D.name,'resource':'local CPU offline replay','actual_cost':None,'support_round':None,'new_model_requests':0},ledger)
    rows=[];priors={};failed=True
    try:
        net=OSMnxNetwork.from_graphml(graph)
        loc={n:net.node_location(n) for n in net.graph.nodes}
        adj={n:net.neighbors(n) for n in loc}
        attrs={(n,m):net.edge_attrs(n,m) for n in loc for m in adj[n]}
        net.node_location=lambda n:loc[n]
        net.neighbors=lambda n:adj[n]
        net.edge_attrs=lambda n,m:attrs[(n,m)]
        net.degree=lambda n:len(adj[n])
        start=net.nearest_node(GeoPoint(lat=37.6061,lng=127.0106))
        targets=[net.nearest_node(GeoPoint(lat=a,lng=b)) for a,b in [(37.6075,127.0118),(37.6038,127.0100),(37.6065,127.0075)]]
        assert len(set(targets+[start]))==4
        coordinates={tuple((p.lat,p.lng)):n for n,p in loc.items()}
        write(D/'geometry.json', {'start_node':start,'target_nodes':targets,'nodes':len(loc),'edges':net.graph.number_of_edges(),'locations':{str(n):loc[n].model_dump() for n in [start]+targets},'real_POI_locations':False})
        for c in cases:
            cid=c['id']; p=Persona.model_validate(read(P/'grounding_v3/personas'/f'{cid}_r1.json'))
            report=MissingReport.model_validate(c['reports']['day'])
            assert prep.fingerprint(p)==p.prepared_initial['fingerprint']
            default=exaone._default_prior(p,report)
            default=default.model_copy(update={'source':'profile_baseline','strategy_before_behavior':dict(default.strategy_probs)})
            bases={'K_profile_baseline':default}
            for r in (1,2):bases[f'K_SAR_r{r}']=PriorParams.model_validate(read(P/'outputs'/f'{cid}_r{r}.json')['B']['baseline'])
            variants={a:prep.apply_prepared(p,report,b,default,[]) for a,b in bases.items()}
            assert all(z.initial_interpretation['status']=='applied' for z in variants.values())
            assert all(z.initial_interpretation['semantic_contract']==variants['K_profile_baseline'].initial_interpretation['semantic_contract'] for z in variants.values())
            priors[cid]={a:z.model_dump(mode='json') for a,z in variants.items()}
            for layout in (0,1):
                pts=targets[layout:]+targets[:layout]
                for arm,prior in variants.items():
                    person=simulation_persona(p,prior).model_copy(deep=True)
                    person.home=loc[start]
                    for ap,n in zip(person.attraction_points,pts):ap.location=loc[n]
                    for hours in (1,4):
                        for seed in protocol['seeds']:
                            trace=SimTrace(max_paths=500)
                            poa=run_monte_carlo(loc[start],prior,person,hours,mode='statistical',net=net,n_walkers=500,seed=seed,trace=trace)
                            assert len(trace.walkers)==500 and not trace.mind_events
                            lengths=[];dist=[];endnodes=[];at_limit=0
                            h=hashlib.sha256()
                            for w in trace.walkers:
                                ids=[coordinates[tuple(q)] for q in w.path]
                                pairs=list(zip(ids,ids[1:]));assert all(pair in attrs for pair in pairs)
                                lengths.append(sum(float(attrs[pair].get('length',0)) for pair in pairs)/1000)
                                dist.append(haversine_km(loc[start],loc[ids[-1]]));endnodes.append(ids[-1])
                                at_limit+=len(pairs)==300
                                h.update(json.dumps([w.strategy,ids],separators=(',',':')).encode())
                            row={'case':cid,'arm':arm,'layout':layout,'hours':hours,'seed':seed,'mean_path_km':mean(lengths),'mean_displacement_km':mean(dist),'within_100m':sum(d<=.1 for d in dist)/500,'market_endpoint':sum(n==pts[1] for n in endnodes)/500,'target_endpoint_shares':{ap.label:sum(n==node for n in endnodes)/500 for ap,node in zip(person.attraction_points,pts)},'max_steps_share':at_limit/500,'all_paths_hash':h.hexdigest(),'strategy_counts':dict(Counter(w.strategy for w in trace.walkers)),'poa':poa}
                            rows.append(row)
            print(cid, 'completed',len(rows),flush=True)
            write(D/'progress.json',{'runs':len(rows),'case_completed':cid})
        write(D/'priors.json',priors)
        write(D/'results.json',rows)
        assert len(rows)==protocol['expected_runs']
        ix={(x['case'],x['arm'],x['layout'],x['hours'],x['seed']):x for x in rows}
        comparisons=[]
        for arm in bases:
            for layout in (0,1):
                for hours in (1,4):
                    for seed in protocol['seeds']:
                        pick=lambda cid:ix[cid,arm,layout,hours,seed]
                        w1,w2,g1,g2=map(pick,['W1','W2','G1','G2'])
                        comparisons.append({'arm':arm,'layout':layout,'hours':hours,'seed':seed,'waiting_nearby_delta':w1['within_100m']-w2['within_100m'],'continuing_distance_delta':w2['mean_path_km']-w1['mean_path_km'],'current_market_delta':g2['market_endpoint']-g1['market_endpoint']})
        aggregates={}
        for arm in bases:
            z=[v for v in comparisons if v['arm']==arm]
            aggregates[arm]={k:{'positive':sum(v[k]>0 for v in z),'zero':sum(v[k]==0 for v in z),'negative':sum(v[k]<0 for v in z),'mean':mean(v[k] for v in z)} for k in ['waiting_nearby_delta','continuing_distance_delta','current_market_delta']}
        summary={'runs':len(rows),'walkers':len(rows)*500,'new_model_calls':0,'all_edges_valid':True,'mind_events':0,'personal_contrast_results':aggregates,'identical_1h_4h_paths':sum(ix[c,a,l,1,s]['all_paths_hash']==ix[c,a,l,4,s]['all_paths_hash'] for c in priors for a in bases for l in (0,1) for s in protocol['seeds']),'time_pairs':180,'mean_max_steps_share':mean(v['max_steps_share'] for v in rows),'mean_SAR_repeat_POA_TV':mean(tv(ix[c,'K_SAR_r1',l,h,s]['poa'],ix[c,'K_SAR_r2',l,h,s]['poa']) for c in priors for l in (0,1) for h in (1,4) for s in protocol['seeds']),'does_not_establish':'clinical accuracy, calibrated strategy probabilities, or equivalence in the enabled mind pipeline'}
        write(D/'comparisons.json',comparisons);write(D/'summary.json',summary)
        print(json.dumps(summary,ensure_ascii=False,indent=2));failed=False
    finally:
        usage_ledger.append_event({'event_type':'resource_session_finished','run_id':D.name,'resource':'local CPU offline replay','status':'failed' if failed else 'complete','wall_seconds':time.monotonic()-started,'actual_cost':None,'support_round':None,'completed_simulations':len(rows),'new_model_requests':0},ledger)

if __name__=='__main__':main()
