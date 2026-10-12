from pathlib import Path
import os,sys,json,socket,re,hashlib,math
os.environ.update(PERSIST_STORAGE='false',PUSH_ENABLED='false',MPLCONFIGDIR='/tmp/cbh-mpl')
def blocked(*a,**k):raise RuntimeError('no network in directional exploration')
socket.socket.connect=blocked;socket.create_connection=blocked
import osmnx as ox,numpy as np,h3
from shapely.geometry import shape,Point
from shapely.ops import unary_union
O=Path(__file__).resolve().parents[1];R=O.parents[2];E=R/'결선/실험/EFFICIENCY_KINTEX_v1_20261009'
X=R/'결선/실험/CHANNEL_ALERT_repair_20261011';L=R/'결선/실험/SAR_DISTANCE_ONLY_20261012';B=Path("/Users/damisoda/Desktop/서강대학교/INSIGHT/인공지능 루키대회/결선/실험/PERSONAL_FIRST_ALERT_COST_20261012")
sys.path.insert(0,str(R/'결선/개발/cbh-independent-alert-core-20261011/backend'))
from app.phase3.directional_safety import reachable_features,opposite_scores,add_safety_to_core,select_core_with_places,reachable_place_guards
from app.phase3.area_budget import select,cell_area_km2
from app.phase2.combine import alpha_pool
from app.geo.h3cover import cover
from app.schemas.common import GeoPoint
p=json.loads((O/'exploration_protocol.json').read_text());truth=json.loads((B/'truth_private.json').read_text())
graphpath=R/'결선/실험/MIND_completion_20261004/map_full_support/kintex_walk.graphml'
assert hashlib.sha256(graphpath.read_bytes()).hexdigest()==p['map_sha256'];g=ox.load_graphml(graphpath)
inputs={z['person_id']:z for z in json.loads((E/'inputs.json').read_text())}
anchors={z['person_id']:z for z in json.loads((E/'dataset_manifest.json').read_text())}
precache=json.loads((B/'results/confirmation_selections.json').read_text())
pre={(z['person_id'],z['prediction_seed'],z['hour']):z for z in precache if z['arm']=='preliminary'}
admin=json.loads((E/'service_comparison/baseline_selections.json').read_text())
admrows={z['person_id']:z for z in admin['rows']}
geoms={k:shape(json.loads((E/f'service_comparison/boundaries/{k}_osm.geojson').read_text())['features'][0]['geometry']) for k in ('ilsanseo','ilsandong','goyang')}
(O/'results/directional_maps').mkdir(exist_ok=True)
rows=[];sels=[];configs={}
for weight in p['personal_weights']:
 for res in p['target_res_candidates']:
  configs[f'base_w{weight}_r{res}']={'weight':weight,'target_res':res,'mode':'base','fraction':0,'progress':None}
  for mode in p['directional_modes']:
   for frac in p['directional_fractions']:
    if mode=='reserved' and frac==.05:continue
    for progress in p['radial_progress_centers']:
     configs[f'dir_w{weight}_r{res}_{mode}_{frac}_p{progress}']={'weight':weight,'target_res':res,'mode':mode,'fraction':frac,'progress':progress}
assert len(configs)<=p['local_candidate_profiles_max']
for pid in p['people']:
 prepared=json.loads((E/f'output/people/{pid}/prepared.json').read_text());origin=GeoPoint.model_validate(prepared['report']['lkp'])
 persona=prepared['arms']['D_full_prepared']['persona'];attractions=[(GeoPoint.model_validate(a['location']),a['weight']) for a in persona['attraction_points']]
 quote=inputs[pid]['persona']['onboarding_quotes']['mobility_transport_capacity'][0];bout,rest=map(int,re.findall(r'(\d+)분',quote)[:2])
 max_distance=6*60*p['planning_speed_m_min']*bout/(bout+rest)
 feats,roadmeta,distances=reachable_features(g,origin,max_distance,source_node=anchors[pid]['start_node'],return_distances=True)
 lit={z['hour']:z['cells'] for z in json.loads((L/f'results/distance_maps/{pid}.json').read_text())['snapshots']}
 local=[t for t in truth if t['person_id']==pid];district=unary_union([geoms[k] for k in admrows[pid]['districts']]);scorecache=[]
 for seed in p['prediction_seeds']:
  snapshots=json.loads((X/f'results_independent_sar/{pid}_{seed}.json').read_text())['snapshots']
  for s in snapshots:
   hr=s['hour'];q=lit[hr];scores={}
   for progress in p['radial_progress_centers']:
    scores[progress],meta=opposite_scores(s['personal'],origin,feats,hr,bout,rest,attractions=attractions,progress=progress,planning_speed_m_min=p['planning_speed_m_min'],angular_sigma_deg=p['heading_sigma_degrees'],literature=q)
    scorecache.append(dict(prediction_seed=seed,hour=hr,progress=progress,scores=scores[progress],metadata=meta))
   mixed={weight:alpha_pool([s['personal'],q],[weight,1-weight]) for weight in p['personal_weights']}
   cores={}
   reachable={z[0] for z in feats if z[2]<=hr*60*p['planning_speed_m_min']*bout/(bout+rest)}
   points=[origin,GeoPoint.model_validate(persona['home'])]+[GeoPoint.model_validate(a['location']) for a in persona['attraction_points'] if a.get('evidence')=='caregiver_report']
   guards={res:reachable_place_guards(g,points,distances,hr*60*p['planning_speed_m_min']*bout/(bout+rest),res)[0] for res in p['target_res_candidates']}
   results={}
   for arm,cfg in configs.items():
    weight,res,mode,fraction=cfg['weight'],cfg['target_res'],cfg['mode'],cfg['fraction']
    budget=5.8*(1-fraction) if mode=='reserved' else 5.8;key=(weight,res,budget)
    if key not in cores:
     try:cores[key]=select_core_with_places(mixed[weight],budget,500,res,guards[res])
     except ValueError:cores[key]=None
    if cores[key] is None:continue
    core=cores[key]
    if mode=='base':selected=core;meta={'core_cells':core,'safety_cells':[]}
    else:selected,meta=add_safety_to_core(core,scores[cfg['progress']],5.8*fraction,500,res)
    targets=cover(selected,res);area=sum(cell_area_km2(c) for c in sorted(targets))
    assert area<=5.8*(1+fraction if mode=='additional' else 1)+1e-9
    results[arm]=(targets,res,area)
    sels.append(dict(person_id=pid,prediction_seed=seed,hour=hr,arm=arm,cells=selected,target_cells=sorted(targets),area_km2=area,core_cells=meta['core_cells'],safety_cells=meta['safety_cells']))
   raw_current=select(mixed[.3],5.8,500,9);current_targets=cover(raw_current,9);results['current']=(current_targets,9,sum(cell_area_km2(c) for c in current_targets))
   ps=pre[(pid,seed,hr)];results['preliminary']=(set(ps['cells']),7,ps['area_km2'])
   for t in local:
    pos=next(v['position'] for v in t['snapshots'] if v['hour']==hr);pt=Point(pos['lng'],pos['lat'])
    common=dict(person_id=pid,prediction_seed=seed,truth_seed=t['truth_seed'],hour=hr,future=t['future'])
    for arm,(targets,res,area) in results.items():rows.append(dict(common,arm=arm,hit=int(h3.latlng_to_cell(pos['lat'],pos['lng'],res) in targets),area_km2=area))
    for arm,geom,area in [('alert_district_proxy',district,admrows[pid]['district_area_km2']),('alert_city_proxy',geoms['goyang'],admrows[pid]['city_area_km2'])]:rows.append(dict(common,arm=arm,hit=int(geom.covers(pt)),area_km2=area))
 (O/f'results/directional_maps/{pid}.json').write_text(json.dumps({'person_id':pid,'road_metadata':roadmeta,'snapshots':scorecache})+'\n')
 print(pid,flush=True)
summary={}
for arm in sorted({z['arm'] for z in rows}):
 r=[z for z in rows if z['arm']==arm];summary[arm]={'overall':100*np.mean([z['hit'] for z in r]),'area':np.mean([z['area_km2'] for z in r]),'efficiency':100*sum(z['hit'] for z in r)/sum(z['area_km2'] for z in r),**{f:100*np.mean([z['hit'] for z in r if z['future']==f]) for f in p['futures']}}
current=summary['current'];pre=summary['preliminary']
eligible=[a for a,c in configs.items() if c['weight']>=.5 and c['mode']!='base' and len([z for z in rows if z['arm']==a])==2808 and summary[a]['habitual']>=current['habitual'] and summary[a]['contradictory']>max(current['contradictory'],pre['contradictory']) and summary[a]['efficiency']>max(current['efficiency'],pre['efficiency'])]
winner=max(eligible,key=lambda a:(summary[a]['efficiency'],summary[a]['contradictory'])) if eligible else None
decision={'candidate':winner,'config':configs.get(winner),'eligible':eligible,'selection_rule':p['selection_rule'],'new_truth_not_generated_yet':True}
for name,obj in [('exploration_summary',summary),('exploration_rows',rows),('exploration_selections',sels),('candidate_configs',configs),('frozen_selection',decision)]:(O/f'results/{name}.json').write_text(json.dumps(obj,indent=2,default=lambda v:v.item())+'\n')
print('references',{a:summary[a] for a in ['alert_district_proxy','alert_city_proxy','preliminary','current','base_w0.3_r9','base_w0.5_r8','base_w0.7_r8','base_w0.9_r8']})
print('best candidates',sorted(((a,v) for a,v in summary.items() if a.startswith('dir')),key=lambda av:av[1]['efficiency'],reverse=True)[:10])
print('selection',decision)
