from pathlib import Path
import json,math,hashlib,datetime,socket,ast
from functools import lru_cache
import numpy as np,h3
from pyproj import Geod
from shapely.geometry import Polygon
O=Path(__file__).resolve().parents[1];R=O.parents[2];X=R/'결선/실험/CHANNEL_ALERT_repair_20261011';E=R/'결선/실험/EFFICIENCY_KINTEX_v1_20261009'
def block(*a,**k):raise RuntimeError('network forbidden')
socket.socket.connect=block;socket.create_connection=block
P=json.loads((O/'protocol/protocol.json').read_text());plan=json.loads((O/'protocol/reserved_safety.json').read_text());G=Geod(ellps='WGS84')
@lru_cache(maxsize=100000)
def area(c):return abs(G.geometry_area_perimeter(Polygon([(lon,lat) for lat,lon in h3.cell_to_boundary(c)]))[0])/1e6
def select_budget(distribution,budget,excluded=frozenset(),limit=500):
 selected=[];used=0.
 for c,p in sorted(((c,p) for c,p in distribution.items() if p>0 and c not in excluded),key=lambda item:(-item[1]/area(item[0]),item[0])):
  if len(selected)>=limit:break
  a=area(c)
  if used+a<=budget+1e-12:selected.append(c);used+=a
 return selected,used
# Exactly the same paired-person CI implementation as the fixed comparison.
tree=ast.parse((O/'scripts/score.py').read_text());methods=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['stats','comparison']],type_ignores=[]);exec(compile(methods,'fixed-scoring-functions','exec'))
old=json.loads((O/'results/rows.json').read_text());current=[r for r in old if r['person_id'] in P['seen_comparison_people'] and r['arm']=='current'];by={(r['person_id'],r['seed'],r['hour']):r for r in current};T={(r['person_id'],s['hour'],r['future']):s['position'] for r in json.loads((E/'truth_private.json').read_text()) for s in r['snapshots']};rows=[];diagnostics=[];example={}
for pid in P['seen_comparison_people']:
 ds={s['hour']:s for s in json.loads((O/f'results/distance_maps/{pid}.json').read_text())['snapshots']}
 for seed in P['seeds']:
  for s in json.loads((X/f'results_independent_sar/{pid}_{seed}.json').read_text())['snapshots']:
   hour=s['hour'];budget=by[pid,seed,hour]['area_km2'];personal=s['personal'];stat=ds[hour]['cells'];full,_=select_budget(personal,budget);base,pa=select_budget(personal,.9*budget);safety,sa=select_budget(stat,.1*budget,excluded=set(full),limit=500-len(base));target=set(base)|set(safety);used=pa+sa
   assert used<=budget+1e-9 and not(set(base)&set(safety)) and not(set(safety)&set(full));assert len(target)<=500
   diagnostics.append({'person_id':pid,'seed':seed,'hour':hour,'budget_km2':budget,'area_km2':used,'personal_area_km2':pa,'safety_area_km2':sa,'personal_cells':len(base),'safety_cells':len(safety),'newly_covered_outside_personal_only_budget':len(safety),'reserved_cells':safety})
   for future in P['futures']:
    p=T[pid,hour,future];cell=h3.latlng_to_cell(p['lat'],p['lng'],9);rows.append({'person_id':pid,'seed':seed,'hour':hour,'future':future,'arm':'distance_only','hit':int(cell in target),'area_km2':used,'auc10':0.})
   if pid=='E09' and seed==104729 and hour==4:example={'personal_cells':base,'safety_cells':safety,'personal_only_full_budget_cells':full,'budget_km2':budget,'area_km2':used,'personal_area_km2':pa,'safety_area_km2':sa}
 print(pid,flush=True)
result={'experiment_id':'SAR_RESERVED_NOVELTY_AREA10_20261012','status':'one_fixed_candidate_seen31_exploratory','policy':plan,'comparison':comparison(P['seen_comparison_people'],current+rows),'future_slices':{},'max_budget_overspend_km2':max(d['area_km2']-d['budget_km2'] for d in diagnostics),'maps':len(diagnostics),'mean_safety_area_km2':float(np.mean([d['safety_area_km2'] for d in diagnostics])),'min_safety_cells':min(d['safety_cells'] for d in diagnostics),'max_safety_cells':max(d['safety_cells'] for d in diagnostics),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'protocol_sha256':hashlib.sha256((O/'protocol/reserved_safety.json').read_bytes()).hexdigest(),'selection_labels':'distance_only is reserved-safety arm here; auc10 is deliberately uncomputed for a quota policy and omitted below'}
for f in P['futures']:result['future_slices'][f]=comparison(P['seen_comparison_people'],[r for r in current+rows if r['future']==f])
# A fixed quota selector is not a complete ranked curve: never invent AUC values.
for result_slice in [result['comparison'],*result['future_slices'].values()]:
 for arm in ['current','distance_only']:
  for key in ['auc10','budget5_hit','budget10_hit']:result_slice[arm].pop(key,None)
 result_slice['candidate_minus_current'].pop('auc10_pp',None)
d=result['comparison']['candidate_minus_current'];cd=result['future_slices']['contradictory']['candidate_minus_current'];result['gates']={'contradictory_inclusion_positive_ci':cd['hit_pp']['ci95'][0]>0,'overall_inclusion_noninferior_ci':d['hit_pp']['ci95'][0]>=0,'area_efficiency_noninferior_ci':d['efficiency_pp_per_km2']['ci95'][0]>=0,'no_budget_overspend':result['max_budget_overspend_km2']<=1e-9,'fresh_holdout':False,'product_default_changed':False}
for name,value in [('reserved_safety_summary.json',result),('reserved_safety_rows.json',rows),('reserved_safety_diagnostics.json',diagnostics),('reserved_safety_example.json',example)]:
 p=O/'results'/name;assert not p.exists();p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
print(json.dumps(result,ensure_ascii=False,allow_nan=False))
