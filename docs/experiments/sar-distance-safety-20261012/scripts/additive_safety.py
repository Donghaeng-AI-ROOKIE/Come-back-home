from pathlib import Path
import sys,os,json,math,hashlib,socket,ast,datetime
from functools import lru_cache
import numpy as np,h3
from pyproj import Geod
from shapely.geometry import Polygon
O=Path(__file__).resolve().parents[1];R=O.parents[2];X=R/'결선/실험/CHANNEL_ALERT_repair_20261011';E=R/'결선/실험/EFFICIENCY_KINTEX_v1_20261009';C=R/'결선/개발/cbh-independent-alert-core-20261011'
sys.path.insert(0,str(C/'backend'));os.environ['PERSIST_STORAGE']='false'
def block(*a,**k):raise RuntimeError('network forbidden')
socket.socket.connect=block;socket.create_connection=block
from app.phase2.combine import alpha_pool
from app.phase3.alerts import select_alert_cells
P=json.loads((O/'protocol/protocol.json').read_text());G=Geod(ellps='WGS84')
@lru_cache(maxsize=100000)
def area(c):return abs(G.geometry_area_perimeter(Polygon([(lon,lat) for lat,lon in h3.cell_to_boundary(c)]))[0])/1e6
T={(r['person_id'],s['hour'],r['future']):s['position'] for r in json.loads((E/'truth_private.json').read_text()) for s in r['snapshots']};rows=[];diagnostics=[];example={}
for pid in P['seen_comparison_people']:
 ds={s['hour']:s['cells'] for s in json.loads((O/f'results/distance_maps/{pid}.json').read_text())['snapshots']}
 for seed in P['seeds']:
  for s in json.loads((X/f'results_independent_sar/{pid}_{seed}.json').read_text())['snapshots']:
   hour=s['hour'];mixed=alpha_pool([s['personal'],s['statistical']],[.9,1-.9]);base=set(select_alert_cells(mixed,coverage=.95,max_cells=500));base_area=sum(area(c) for c in base);stat=ds[hour];outside=sorted(c for c,p in stat.items() if p>0 and c not in base);m=max(area(c) for c in outside);extra=max(.1*base_area,m);k=int(math.floor(extra/m+1e-12));q=np.array([stat[c] for c in outside]);q=q/q.sum();weights=dict(zip(outside,q));assert k>=1
   top=[];used=0.
   for c in sorted(outside,key=lambda c:(-stat[c]/area(c),c)):
    if used+area(c)<=extra+1e-12:top.append(c);used+=area(c)
   rng=np.random.default_rng(np.random.SeedSequence([seed,hour,20261012]));drawn=set(rng.choice(outside,size=k,replace=True,p=q));assert len(drawn)<=k
   expected_area=base_area+sum(area(c)*(-math.expm1(k*math.log1p(-weights[c]))) for c in outside)
   for arm,add in [('additive_top_density',set(top)),('additive_weighted_rotation',drawn)]:
    target=base|add;actual_area=sum(area(c) for c in target);assert add.isdisjoint(base) and base.issubset(target) and actual_area<=base_area+extra+1e-8
    diagnostics.append({'person_id':pid,'seed':seed,'hour':hour,'arm':arm,'base_area_km2':base_area,'extra_budget_km2':extra,'area_km2':actual_area,'added_cells':len(add),'sampling_draws':k,'outside_positive_support_cells':len(outside),'outside_probability_min':float(q.min()),'positive_probability_for_every_outside_support_cell':k>=1,'expected_area_km2':expected_area if arm=='additive_weighted_rotation' else actual_area})
    for f in P['futures']:
     p=T[pid,hour,f];cell=h3.latlng_to_cell(p['lat'],p['lng'],9);pi=weights.get(cell,0.);expected=1. if cell in base else (-math.expm1(k*math.log1p(-pi)) if 0<pi<1 else pi);rows.append({'person_id':pid,'seed':seed,'hour':hour,'future':f,'arm':arm,'hit':int(cell in target),'area_km2':actual_area,'baseline_hit':int(cell in base),'expected_hit':expected if arm=='additive_weighted_rotation' else int(cell in target),'expected_area_km2':expected_area if arm=='additive_weighted_rotation' else actual_area,'truth_in_literature_support':cell in stat,'single_cycle_safety_inclusion_probability':expected if cell not in base else None})
    if pid=='E09' and seed==104729 and hour==4:example[arm]={'base_cells':sorted(base),'safety_cells':sorted(add),'area_km2':actual_area,'extra_budget_km2':extra,'draws':k}
 print(pid,flush=True)
def stats(rs,expected=False):
 hit='expected_hit' if expected else 'hit';ar='expected_area_km2' if expected else 'area_km2';h=sum(r[hit] for r in rs);a=sum(r[ar] for r in rs);return {'checks':len(rs),'hit_pct':100*h/len(rs),'mean_area_km2':a/len(rs),'efficiency_pp_per_km2':100*h/a,'metric_kind':'analytic sampling expectation, not measured accuracy' if expected else 'realized synthetic inclusion, two existing seeds only'}
result={'experiment_id':'SAR_ADDITIVE_SAFETY_20261012','status':'fixed_two_policy_seen31_exploratory','policy':json.loads((O/'protocol/additive_safety.json').read_text()),'baseline':json.loads((O/'results/summary.json').read_text())['seen31']['current'],'arms':{},'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'new_model_calls':0,'default_changed':False,'fresh_holdout':False,'actual_push':False}
for arm in ['additive_top_density','additive_weighted_rotation']:
 rs=[r for r in rows if r['arm']==arm];ds=[d for d in diagnostics if d['arm']==arm];result['arms'][arm]={'realized':stats(rs),'analytic_expectation':stats(rs,True) if arm.endswith('rotation') else None,'future_slices':{f:{'realized':stats([r for r in rs if r['future']==f]),'analytic_expectation':stats([r for r in rs if r['future']==f],True) if arm.endswith('rotation') else None} for f in P['futures']},'lost_baseline_hits':sum(r['baseline_hit'] and not r['hit'] for r in rs),'max_extra_area_fraction':max((d['area_km2']/d['base_area_km2']-1) for d in ds),'max_extra_area_km2':max(d['area_km2']-d['base_area_km2'] for d in ds),'min_added_cells':min(d['added_cells'] for d in ds),'max_added_cells':max(d['added_cells'] for d in ds),'positive_probability_every_outside_support_cell':arm.endswith('rotation') and all(d['positive_probability_for_every_outside_support_cell'] for d in ds),'uncovered_contradictory_outside_literature_support':sum(not r['truth_in_literature_support'] for r in rs if r['future']=='contradictory'),'missing_baseline_contradictory_with_positive_expected_probability':sum(r['expected_hit']>0 and not r['baseline_hit'] for r in rs if r['future']=='contradictory') if arm.endswith('rotation') else None}
for n,v in [('additive_safety_summary.json',result),('additive_safety_rows.json',rows),('additive_safety_diagnostics.json',diagnostics),('additive_safety_example.json',example)]:
 p=O/'results'/n;assert not p.exists();p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
print(json.dumps(result,ensure_ascii=False,allow_nan=False))
