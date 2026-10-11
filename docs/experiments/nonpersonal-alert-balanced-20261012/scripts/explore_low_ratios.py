from pathlib import Path
import os,sys,json,socket
import numpy as np,h3
O=Path(__file__).resolve().parents[1];R=O.parents[2];OLD=R/'결선/실험/AREA_ALERT_FRESH_ROUTES_20261012';X=R/'결선/실험/CHANNEL_ALERT_repair_20261011';L=R/'결선/실험/SAR_DISTANCE_ONLY_20261012';C=R/'결선/개발/cbh-independent-alert-core-20261011'
os.environ.update(PERSIST_STORAGE='false',PUSH_ENABLED='false',PUSH_TARGET_RES='9',ALERT_SELECTION_POLICY='coverage');sys.path.insert(0,str(C/'backend'))
socket.socket.connect=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('network forbidden'))
from app.phase2.combine import alpha_pool
from app.phase3.alerts import select_alert_cells
from app.phase3.area_budget import cell_area_km2,select
p=json.loads((O/'exploration_protocol.json').read_text());truth=json.loads((OLD/'truth_private.json').read_text());rows=[];selections=[]
for pid in p['people']:
 lit={s['hour']:s['cells'] for s in json.loads((L/f'results/distance_maps/{pid}.json').read_text())['snapshots']};local=[t for t in truth if t['person_id']==pid]
 for seed in p['prediction_seeds']:
  for s in json.loads((X/f'results_independent_sar/{pid}_{seed}.json').read_text())['snapshots']:
   hour=s['hour'];q=lit[hour];current=alpha_pool([s['personal'],s['statistical']],[.9,.1]);mixed=alpha_pool([s['personal'],q],[.9,.1]);base=select_alert_cells(current,coverage=.95,max_cells=500,policy='coverage');personal=select_alert_cells(s['personal'],coverage=.95,max_cells=500,policy='coverage')
   arms={'current':base}
   for weight in [.1,.2,.3,.4]:
    mixed=alpha_pool([s['personal'],q],[weight,1-weight])
    for budget in [5.281216032677167,6.368199998062131,7.]:arms[f'w{weight}_area{budget:.2f}']=select(mixed,budget,500,9)
   for arm,cells in arms.items():
    targets=set(cells);area=sum(cell_area_km2(c) for c in sorted(targets));selections.append(dict(person_id=pid,prediction_seed=seed,hour=hour,arm=arm,cells=cells,area_km2=area))
    for t in local:
     pos=next(z['position'] for z in t['snapshots'] if z['hour']==hour);rows.append(dict(person_id=pid,prediction_seed=seed,truth_seed=t['truth_seed'],hour=hour,future=t['future'],arm=arm,hit=int(h3.latlng_to_cell(pos['lat'],pos['lng'],9) in targets),area_km2=area))
 print(pid,flush=True)
summary={}
for arm in sorted({r['arm'] for r in rows}):
 rs=[r for r in rows if r['arm']==arm];summary[arm]=dict(overall=100*np.mean([r['hit'] for r in rs]),area=np.mean([r['area_km2'] for r in rs]),efficiency=100*sum(r['hit'] for r in rs)/sum(r['area_km2'] for r in rs),**{f:100*np.mean([r['hit'] for r in rs if r['future']==f]) for f in p['futures']})
for name,obj in [('low_personal_exploration_rows',rows),('low_personal_exploration_selections',selections),('low_personal_exploration_summary',summary)]: (O/f'results/{name}.json').write_text(json.dumps(obj,indent=2)+'\n')
print(json.dumps(summary,indent=2))
