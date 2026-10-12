from pathlib import Path
import json,ast,hashlib,os,sys,socket
from functools import lru_cache
import numpy as np,h3
from pyproj import Geod
from shapely.geometry import Polygon
O=Path(__file__).resolve().parents[1];R=O.parents[2];X=R/'결선/실험/CHANNEL_ALERT_repair_20261011';E=R/'결선/실험/EFFICIENCY_KINTEX_v1_20261009';C=R/'결선/개발/cbh-independent-alert-core-20261011';sys.path.insert(0,str(C/'backend'));os.environ['PERSIST_STORAGE']='false'
def blocked(*a,**k):raise RuntimeError('network forbidden')
socket.socket.connect=blocked;socket.create_connection=blocked
from app.phase2.combine import alpha_pool
P=json.loads((O/'protocol/protocol.json').read_text());plan=json.loads((O/'protocol/area_budget_selection.json').read_text());G=Geod(ellps='WGS84')
@lru_cache(maxsize=100000)
def area(c):return abs(G.geometry_area_perimeter(Polygon([(lon,lat) for lat,lon in h3.cell_to_boundary(c)]))[0])/1e6
old=json.loads((O/'results/rows.json').read_text());current=[r for r in old if r['person_id'] in P['seen_comparison_people'] and r['arm']=='current'];by={(r['person_id'],r['seed'],r['hour']):r for r in current};T={(r['person_id'],s['hour'],r['future']):s['position'] for r in json.loads((E/'truth_private.json').read_text()) for s in r['snapshots']};rows=[];diagnostics=[];examples={}
tree=ast.parse((O/'scripts/score.py').read_text());exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['stats','comparison']],type_ignores=[]),'fixed-scoring-functions','exec'))
for pid in P['seen_comparison_people']:
 ds={s['hour']:s['cells'] for s in json.loads((O/f'results/distance_maps/{pid}.json').read_text())['snapshots']}
 for seed in P['seeds']:
  for s in json.loads((X/f'results_independent_sar/{pid}_{seed}.json').read_text())['snapshots']:
   hour=s['hour'];mixed=alpha_pool([s['personal'],ds[hour]],[.9,1-.9]);ranked=sorted(((c,p) for c,p in mixed.items() if p>0),key=lambda item:(-item[1]/area(item[0]),item[0]))
   for arm,budget in [('matched_current_area_budget',by[pid,seed,hour]['area_km2']),('uniform_dev_current_mean_area_budget',plan['uniform_budget_km2'])]:
    selected=[];used=0.
    for c,p in ranked:
     if len(selected)>=500:break
     a=area(c)
     if used+a<=budget+1e-12:selected.append(c);used+=a
    target=set(selected);mass=sum(mixed[c] for c in selected);assert used<=budget+1e-8
    diagnostics.append({'person_id':pid,'seed':seed,'hour':hour,'arm':arm,'budget_km2':budget,'area_km2':used,'selected_mass':mass,'selected_cells':len(selected)})
    for f in P['futures']:
     p=T[pid,hour,f];cell=h3.latlng_to_cell(p['lat'],p['lng'],9);rows.append({'person_id':pid,'seed':seed,'hour':hour,'future':f,'arm':arm,'hit':int(cell in target),'area_km2':used,'auc10':0.})
    if pid=='E09' and seed==104729 and hour==4:examples[arm]={'cells':selected,'area_km2':used,'budget_km2':budget,'selected_mass':mass}
 print(pid,flush=True)
result={'experiment_id':'SAR_AREA_BUDGET_SELECTION_20261012','status':'two_fixed_cost_policies_seen31_exploratory','policy':plan,'arms':{},'new_model_calls':0,'actual_push':0,'fresh_holdout':False,'default_changed':False,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
for arm in plan['policies']:
 rs=[r|{'arm':'distance_only'} for r in rows if r['arm']==arm];ds=[d for d in diagnostics if d['arm']==arm];c=comparison(P['seen_comparison_people'],current+rs);slices={f:comparison(P['seen_comparison_people'],[r for r in current+rs if r['future']==f]) for f in P['futures']}
 for cs in [c,*slices.values()]:
  for key in ['current','distance_only']:
   for k in ['auc10','budget5_hit','budget10_hit']:cs[key].pop(k,None)
  cs['candidate_minus_current'].pop('auc10_pp',None)
 result['arms'][arm]={'comparison':c,'future_slices':slices,'selected_mass':{'min':min(d['selected_mass'] for d in ds),'mean':float(np.mean([d['selected_mass'] for d in ds])),'max':max(d['selected_mass'] for d in ds)},'budget_violations':sum(d['area_km2']>d['budget_km2']+1e-8 for d in ds)}
for n,v in [('area_budget_summary.json',result),('area_budget_rows.json',rows),('area_budget_diagnostics.json',diagnostics),('area_budget_example.json',examples)]:
 p=O/'results'/n;assert not p.exists();p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
print(json.dumps(result,ensure_ascii=False,allow_nan=False))
