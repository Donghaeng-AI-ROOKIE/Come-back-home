from pathlib import Path
import os,sys,json,hashlib,socket,math
from functools import lru_cache
import numpy as np,h3
from pyproj import Geod
from shapely.geometry import Polygon
O=Path(__file__).resolve().parents[1];R=O.parents[2];X=R/'결선/실험/CHANNEL_ALERT_repair_20261011';E=R/'결선/실험/EFFICIENCY_KINTEX_v1_20261009';C=R/'결선/개발/cbh-independent-alert-core-20261011'
os.environ['PERSIST_STORAGE']='false';sys.path.insert(0,str(C/'backend'))
def blocked(*a,**k):raise RuntimeError('external call forbidden during scoring')
socket.socket.connect=blocked;socket.create_connection=blocked
from app.phase2.combine import alpha_pool
from app.phase3.alerts import select_alert_cells,target_parent_cells
G=Geod(ellps='WGS84')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
@lru_cache(maxsize=100000)
def area(c):return abs(G.geometry_area_perimeter(Polygon([(lon,lat) for lat,lon in h3.cell_to_boundary(c)]))[0])/1e6
P=json.loads((O/'protocol/protocol.json').read_text());frozen=sha(O/'protocol/protocol.json');assert sha(O/'scripts/distance_prior.py')==P['distance_source_sha256']
assert sha(E/'truth_private.json')==P['truth_sha256']
T={(r['person_id'],s['hour'],r['future']):s['position'] for r in json.loads((E/'truth_private.json').read_text()) for s in r['snapshots']}
rows=[];maps=[]
for pid in P['people']:
 generated=json.loads((O/f'results/distance_maps/{pid}.json').read_text());ds={s['hour']:s for s in generated['snapshots']}
 for seed in P['seeds']:
  path=X/f'results_independent_sar/{pid}_{seed}.json';assert sha(path)==P['inputs'][pid]['walk_map_sha256'][str(seed)]
  data=json.loads(path.read_text())
  for s in data['snapshots']:
   hour=s['hour'];new=ds[hour]['cells'];old=s['statistical'];personal=s['personal']
   assert abs(sum(personal.values())-1)<1e-8 and all(h3.get_resolution(c)==9 for c in new)
   for arm,stat in [('current',old),('distance_only',new)]:
    mixed=alpha_pool([personal,stat],[P["personal_weight"],1-P["personal_weight"]]);selected=select_alert_cells(mixed,coverage=.95,max_cells=500);targets=target_parent_cells(selected,res=9);assert targets==set(selected)
    size=sum(area(c) for c in targets);first={};a=0.
    for c,p in sorted(((c,p) for c,p in mixed.items() if p>0),key=lambda t:(-t[1],t[0])):a+=area(c);first[c]=a
    base={'person_id':pid,'seed':seed,'hour':hour,'arm':arm}
    maps.append(base|{'area_km2':size,'selected_mass':sum(mixed[c] for c in selected),'selected_cells':len(selected),'cell_cap_saturated':len(selected)>=500,'coverage_attained':sum(mixed[c] for c in selected)>=.95-1e-12,'statistical_tv_from_current':.5*sum(abs(old.get(c,0)-new.get(c,0)) for c in set(old)|set(new)),'distance_quality':ds[hour]['quality'] if arm=='distance_only' else None})
    for future in P['futures']:
     pos=T[pid,hour,future];cell=h3.latlng_to_cell(pos['lat'],pos['lng'],9);fa=first.get(cell)
     rows.append(base|{'future':future,'area_km2':size,'hit':int(cell in targets),'first_area_km2':fa,'auc10':100*max(0,1-fa/10) if fa is not None else 0.,'budget5_hit':int(fa is not None and fa<=5),'budget10_hit':int(fa is not None and fa<=10)})
 print(pid,flush=True)
# Reproduce the stored current score before any new comparison claim.
reference=json.loads((X/'results_area_efficiency_final/seen31_native_rows.json').read_text());reference={(r['person_id'],r['seed'],r['hour'],r['future']):r for r in reference if r['weight']==.9 and r['res']==9 and r['coverage']==.95}
for r in rows:
 if r['person_id'] in P['seen_comparison_people'] and r['arm']=='current':
  before=reference[r['person_id'],r['seed'],r['hour'],r['future']];assert r['hit']==before['hit'];assert abs(r['area_km2']-before['area_km2'])<1e-8
oldrows=[json.loads(s) for s in (R/'결선/실험/EFFICIENCY_avoid_wait_fix_20261010/service_final/rows.jsonl').read_text().splitlines()]
def stats(rs):
 hits=sum(r['hit'] for r in rs);total_area=sum(r['area_km2'] for r in rs)
 v={'people':len({r['person_id'] for r in rs}),'checks':len(rs),'hits':hits,'hit_pct':100*hits/len(rs),'mean_area_km2':total_area/len(rs),'efficiency_pp_per_km2':100*hits/total_area}
 for k in ['auc10','budget5_hit','budget10_hit']:
  if k in rs[0]:v[k]=float(np.mean([r[k] for r in rs]))*(100 if k.endswith('_hit') else 1)
 return v
def comparison(ids,rs):
 current=[r for r in rs if r['arm']=='current'];candidate=[r for r in rs if r['arm']=='distance_only'];vectors=[]
 for pid in ids:
  a=[r for r in candidate if r['person_id']==pid];b=[r for r in current if r['person_id']==pid]
  vectors.append([sum(r['hit'] for r in a),sum(r['area_km2'] for r in a),sum(r['hit'] for r in b),sum(r['area_km2'] for r in b),len(a),sum(r['auc10'] for r in a),sum(r['auc10'] for r in b)])
 v=np.array(vectors);ix=np.random.default_rng(20261012).integers(0,len(ids),(10000,len(ids)));bt=v[ix].sum(axis=1);pt=v.sum(axis=0)
 def measures(t):return {'efficiency_pp_per_km2':100*t[...,0]/t[...,1]-100*t[...,2]/t[...,3],'hit_pp':100*(t[...,0]-t[...,2])/t[...,4],'mean_area_km2':(t[...,1]-t[...,3])/t[...,4],'auc10_pp':(t[...,5]-t[...,6])/t[...,4],'relative_efficiency_gain_pct':100*((t[...,0]/t[...,1])/(t[...,2]/t[...,3])-1)}
 with np.errstate(divide='ignore',invalid='ignore'):
  sampled=measures(bt);point=measures(pt)
 deltas={}
 for k,value in point.items():
  valid=np.isfinite(sampled[k]);deltas[k]={'point':float(value),'ci95':np.quantile(sampled[k],[.025,.975]).tolist() if valid.all() else None,'undefined_bootstrap_draws':int((~valid).sum())}
  if not valid.all():deltas[k]['ci95_status']='undefined: resampled baseline has zero hits; draws not silently discarded'
 return {'current':stats(current),'distance_only':stats(candidate),'candidate_minus_current':deltas}
result={'experiment_id':P['experiment_id'],'protocol_sha256':frozen,'source_sha256':sha(Path(__file__)),'settings':{k:P[k] for k in ['personal_weight','statistical_weight','resolution','coverage','max_alert_cells']},'development':comparison(P['development_people'],[r for r in rows if r['person_id'] in P['development_people']]),'seen31':comparison(P['seen_comparison_people'],[r for r in rows if r['person_id'] in P['seen_comparison_people']]),'future_slices':{},'hour_slices':{},'bootstrap':P['bootstrap'],'current_score_parity':True,'private_inputs_excluded_from_new_prior':True,'new_model_calls':0,'actual_push':0,'fresh_holdout':False,'release_qualification':False,'product_default_changed':False}
seen=[r for r in rows if r['person_id'] in P['seen_comparison_people']]
for f in P['futures']:
 s=comparison(P['seen_comparison_people'],[r for r in seen if r['future']==f]);s['preliminary_native']=stats([r for r in oldrows if r['person_id'] in P['seen_comparison_people'] and r['arm']=='preliminary' and r['future']==f]);result['future_slices'][f]=s
for hour in P['hours']:result['hour_slices'][str(hour)]=comparison(P['seen_comparison_people'],[r for r in seen if r['hour']==hour])
result['preliminary_native']=stats([r for r in oldrows if r['person_id'] in P['seen_comparison_people'] and r['arm']=='preliminary'])
result['selection_diagnostics']={}
for arm in ['current','distance_only']:
 ms=[m for m in maps if m['person_id'] in P['seen_comparison_people'] and m['arm']==arm]
 result['selection_diagnostics'][arm]={'maps':len(ms),'min_selected_mass':min(m['selected_mass'] for m in ms),'mean_selected_mass':float(np.mean([m['selected_mass'] for m in ms])),'max_selected_cells':max(m['selected_cells'] for m in ms),'cell_cap_saturated_maps':sum(m['cell_cap_saturated'] for m in ms),'coverage_not_attained_maps':sum(not m['coverage_attained'] for m in ms)}
result['distance_tail_by_hour']={str(s['hour']):s['quality']['excluded_distance_tail_mass'] for s in generated['snapshots']}
d=result['seen31']['candidate_minus_current'];result['gates']={'efficiency_positive_ci':d['efficiency_pp_per_km2']['ci95'][0]>0,'inclusion_noninferior_ci':d['hit_pp']['ci95'][0]>=0,'area_reduction_ci':d['mean_area_km2']['ci95'][1]<0,'all_future_point_inclusion_at_least_current':all(v['distance_only']['hit_pct']>=v['current']['hit_pct'] for v in result['future_slices'].values()),'requested_coverage_attained_all_maps':result['selection_diagnostics']['distance_only']['coverage_not_attained_maps']==0,'fresh_holdout':False,'actual_push':False}
for name,value in [('summary.json',result),('rows.json',rows),('map_diagnostics.json',maps)]:
 p=O/'results'/name;assert not p.exists();p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
assert sha(O/'protocol/protocol.json')==frozen
print(json.dumps(result,ensure_ascii=False,allow_nan=False))
