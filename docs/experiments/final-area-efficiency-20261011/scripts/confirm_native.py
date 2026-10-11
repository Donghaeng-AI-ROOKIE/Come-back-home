from pathlib import Path
import os,sys,json,hashlib,math,argparse
from functools import lru_cache
import numpy as np,h3
from shapely.geometry import Polygon
from pyproj import Geod
R=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path.cwd();X=R/'결선/실험/CHANNEL_ALERT_repair_20261011';E=R/'결선/실험/EFFICIENCY_KINTEX_v1_20261009';C=Path(__file__).resolve().parents[4]/'backend'
sys.path.insert(0,str(C));os.environ['PERSIST_STORAGE']='false'
from app.geo.h3cover import overlapping_cells
from app.phase3.alerts import select_alert_cells
from app.phase2.combine import alpha_pool
T={(r['person_id'],s['hour'],r['future']):s['position'] for r in json.loads((E/'truth_private.json').read_text()) for s in r['snapshots']}
old=[json.loads(s) for s in (R/'결선/실험/EFFICIENCY_avoid_wait_fix_20261010/service_final/rows.jsonl').read_text().splitlines()]
g=Geod(ellps='WGS84');weights=[0,.3,.5,.6,.7,.8,.9,1];resolutions=[8,9];coverages=[.8,.85,.9,.95];out=Path(sys.argv[2]).resolve() if len(sys.argv)>2 else X/'results_area_efficiency_final';out.mkdir(exist_ok=True)
@lru_cache(maxsize=40000)
def area(c):return abs(g.geometry_area_perimeter(Polygon([(lon,lat) for lat,lon in h3.cell_to_boundary(c)]))[0])/1e6
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def evaluate(ids,ratios):
 rows=[];native=[];hashes={}
 for pid in ids:
  for seed in (104729,130363):
   path=X/f'results_independent_sar/{pid}_{seed}.json';hashes[path.name]=digest(path)
   for s in json.loads(path.read_text())['snapshots']:
    for w in ratios:
     mixed=alpha_pool([s['personal'],s['statistical']],[w,1-w]);ranked=sorted(((c,p) for c,p in mixed.items() if p>0),key=lambda t:(-t[1],t[0]))
     for res in resolutions:
      union=set();first={};cumulative=0.
      for fine,prob in ranked:
       added=overlapping_cells(fine,res)-union;cumulative+=sum(area(c) for c in added)
       first.update({c:cumulative for c in added});union.update(added)
      base={'person_id':pid,'seed':seed,'hour':s['hour'],'weight':w,'res':res}
      for future in ('habitual','departure','contradictory'):
       p=T[pid,s['hour'],future];cell=h3.latlng_to_cell(p['lat'],p['lng'],res);f=first.get(cell)
       rows.append(base|{'future':future,'first_area_km2':f,'auc10':100*max(0.,1-f/10) if f is not None else 0.,'auc30':100*max(0.,1-f/30) if f is not None else 0.})
      for cov in coverages:
       selected=select_alert_cells(mixed,coverage=cov);targets=set().union(*(overlapping_cells(c,res) for c in selected)) if selected else set();a=sum(area(c) for c in targets)
       for future in ('habitual','departure','contradictory'):
        p=T[pid,s['hour'],future];native.append(base|{'future':future,'coverage':cov,'area_km2':a,'hit':int(h3.latlng_to_cell(p['lat'],p['lng'],res) in targets)})
  print(pid,flush=True)
 return rows,native,hashes
def mean(rows,field):return float(np.mean([r[field] for r in rows]))
def stats(rows):return {'people':len({r['person_id'] for r in rows}),'checks':len(rows),'area_km2':mean(rows,'area_km2'),'hit':mean(rows,'hit')}
def dump(name,v):
 p=out/name;assert not p.exists(),str(p);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');return p
locked=out/'selection.json';sha=digest(locked);sel=json.loads(locked.read_text());ids=['E%02d'%i for i in range(9,41) if i!=20];rows,native,hashes=evaluate(ids,sorted({sel['weight'],.7}));fixed=[r for r in native if r['weight']==sel['weight'] and r['res']==sel['res'] and r['coverage']==sel['coverage']];auc=[r for r in rows if r['weight']==sel['weight'] and r['res']==sel['res']];pre=[r for r in old if r['person_id'] in ids and r['arm']=='preliminary']
def ci(a,b,key):
 v=np.array([mean([r for r in a if r['person_id']==pid],key)-mean([r for r in b if r['person_id']==pid],key) for pid in ids]);ix=np.random.default_rng(2026101105).integers(0,len(ids),(10000,len(ids)));return {'delta':float(v.mean()),'ci95':np.quantile(v[ix].mean(axis=1),[.025,.975]).tolist()}
# The preserved preliminary service is res7 + its old threshold, so native9 AUC
# is reported alongside the frozen original geographic res7 AUC, never relabeled.
original=json.loads((X/'results_independent_analysis/seen31_summary.json').read_text())
result={'status':'previously_seen31_exploratory_confirmation','selection_sha256':sha,'settings':{k:sel[k] for k in ['weight','res','coverage']},'candidate_native':stats(fixed),'preliminary_native':stats(pre),'candidate_native_auc':{key:mean(auc,key) for key in ['auc10','auc30']},'native_grid':[{'weight':w,'res':res,'coverage':cov,**stats([r for r in native if r['weight']==w and r['res']==res and r['coverage']==cov])} for w in sorted({r['weight'] for r in native}) for res in resolutions for cov in coverages],'candidate_minus_preliminary':{k:ci(fixed,pre,k) for k in ['hit','area_km2']},'original_res7_auc_reference':original['auc'],'new_api_calls':0,'fresh_holdout_done':False,'input_hashes':hashes,'source_sha256':digest(Path(__file__))}
result['gates']={'native_hit_noninferior_ci':result['candidate_minus_preliminary']['hit']['ci95'][0]>=0,'native_area_reduction_ci':result['candidate_minus_preliminary']['area_km2']['ci95'][1]<0,'fresh_holdout_done':False,'external_push_receipt_done':False};assert digest(locked)==sha
dump('seen31_summary.json',result);dump('seen31_auc_rows.json',rows);dump('seen31_native_rows.json',native);print(json.dumps(result,ensure_ascii=False))
