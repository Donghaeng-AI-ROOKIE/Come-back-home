from pathlib import Path
import sys,os,json,concurrent.futures,time,socket,hashlib,datetime
from functools import lru_cache
import h3,numpy as np
from pyproj import Geod
from shapely.geometry import Polygon
from distance_prior import distance_map
O=Path(__file__).resolve().parents[1];R=O.parents[2];C=R/'결선/개발/cbh-independent-alert-core-20261011';X=R/'결선/실험/CHANNEL_ALERT_repair_20261011';E=R/'결선/실험/EFFICIENCY_KINTEX_v1_20261009'
sys.path.insert(0,str(C/'backend'));os.environ['PERSIST_STORAGE']='false'
from app.phase2.combine import alpha_pool
from app.phase3.alerts import select_alert_cells
G=Geod(ellps='WGS84')
def block(*a,**k):raise RuntimeError('network forbidden')
@lru_cache(maxsize=100000)
def area(c):return abs(G.geometry_area_perimeter(Polygon([(lon,lat) for lat,lon in h3.cell_to_boundary(c)]))[0])/1e6
P=json.loads((O/'protocol/protocol.json').read_text())
def one(pid):
 socket.socket.connect=block;socket.create_connection=block
 pos=P['inputs'][pid]['lkp'];low={s['hour']:s for s in json.loads((O/f'results/distance_maps/{pid}.json').read_text())['snapshots']};higher={};tv=[];rows=[]
 for hour in P['hours']:
  d,q=distance_map(pos['lat'],pos['lng'],hour,bands=128,coverage_bbox=P['map_manifest']['bbox_south_west_north_east']);higher[hour]=d;a=low[hour]['cells'];tv.append(.5*sum(abs(a.get(c,0)-d.get(c,0)) for c in set(a)|set(d)))
 T={(r['person_id'],s['hour'],r['future']):s['position'] for r in json.loads((E/'truth_private.json').read_text()) for s in r['snapshots']}
 for seed in P['seeds']:
  for s in json.loads((X/f'results_independent_sar/{pid}_{seed}.json').read_text())['snapshots']:
   mixed=alpha_pool([s['personal'],higher[s['hour']]],[.9,1-.9]);sel=select_alert_cells(mixed,coverage=.95,max_cells=500);a=sum(area(c) for c in sel)
   for f in P['futures']:
    p=T[pid,s['hour'],f];rows.append({'person_id':pid,'seed':seed,'hour':s['hour'],'future':f,'hit':int(h3.latlng_to_cell(p['lat'],p['lng'],9) in sel),'area_km2':a})
 return {'person_id':pid,'max_tv':max(tv),'rows':rows}
if __name__=='__main__':
 t=time.monotonic();results=[];ledger=O/'results/local_usage.jsonl';event_id='sar-distance-numerical-128'
 def log(phase,**kw):
  with ledger.open('a') as f:f.write(json.dumps({'event_id':event_id,'phase':phase,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'new_model_calls':0,'remote_runs':0,'actual_push':0,'cost_amount':None,**kw})+'\n')
 log('start',scope={'maps_max':124,'bands':128,'local_cpu_only':True})
 try:
  with concurrent.futures.ProcessPoolExecutor(max_workers=2) as pool:
   for x in pool.map(one,P['seen_comparison_people']):results.append(x);print(x['person_id'],x['max_tv'],flush=True)
 finally:log('end',wall_seconds=time.monotonic()-t,completed_people=len(results),error=None if len(results)==31 else 'incomplete')
 assert len(results)==31
 rows=[r for x in results for r in x['rows']];hits=sum(r['hit'] for r in rows);a=sum(r['area_km2'] for r in rows);low=[r for r in json.loads((O/'results/rows.json').read_text()) if r['person_id'] in P['seen_comparison_people'] and r['arm']=='distance_only'];index={(r['person_id'],r['seed'],r['hour'],r['future']):r for r in low};changed=sum(r['hit']!=index[r['person_id'],r['seed'],r['hour'],r['future']]['hit'] for r in rows)
 out={'purpose':'numerical quadrature validation, not new candidate','bands':128,'max_statistical_map_tv_64_to_128':max(x['max_tv'] for x in results),'hits_changed':changed,'checks':len(rows),'hit_pct':100*hits/len(rows),'mean_area_km2':a/len(rows),'efficiency_pp_per_km2':100*hits/a,'relative_efficiency_gain_vs_current_pct':100*((100*hits/a)/json.loads((O/'results/summary.json').read_text())['seen31']['current']['efficiency_pp_per_km2']-1),'future_hit_pct':{f:100*np.mean([r['hit'] for r in rows if r['future']==f]) for f in P['futures']},'primary_result_remains_64_bands':True,'product_default_changed':False,'new_model_calls':0,'wall_seconds':time.monotonic()-t,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
 (O/'results/numerical_validation.json').write_text(json.dumps(out,indent=2,allow_nan=False)+'\n');print(json.dumps(out))
