from pathlib import Path
import os,sys,json,socket
os.environ.update(PERSIST_STORAGE='false',PUSH_ENABLED='false')
socket.socket.connect=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('no network'))
import numpy as np,h3
O=Path(__file__).resolve().parents[1];R=O.parents[2];B=Path("/Users/damisoda/Desktop/서강대학교/INSIGHT/인공지능 루키대회/결선/실험/PERSONAL_FIRST_ALERT_COST_20261012")
sys.path.insert(0,str(R/'결선/개발/cbh-independent-alert-core-20261011/backend'))
from app.phase3.directional_safety import add_safety_to_core
from app.phase3.area_budget import cell_area_km2
from app.geo.h3cover import cover
p=json.loads((O/'protocol.json').read_text());truth=json.loads((B/'truth_private.json').read_text())
old=json.loads((B/'results/confirmation_selections.json').read_text());base={(z['person_id'],z['prediction_seed'],z['hour']):z for z in old if z['arm']=='candidate'}
rows=[];sels=[];configs={}
for fraction in [.05,.1,.2]:
 for progress in [.35,.65]:
  for gate in [0.,.1,.25,.5]:
   configs[f'keep30_r9_f{fraction}_p{progress}_g{gate}']={'weight':.3,'target_res':9,'mode':'additional','fraction':fraction,'progress':progress,'outside_gate':gate,'keep_reference_core100pct':True}
for pid in p['people']:
 cache=json.loads((O/f'results/directional_maps/{pid}.json').read_text())['snapshots']
 for snap in cache:
  seed,hr,progress=snap['prediction_seed'],snap['hour'],snap['progress'];core=base[(pid,seed,hr)]['cells']
  for arm,cfg in configs.items():
   if cfg['progress']!=progress:continue
   chosen,meta=add_safety_to_core(core,snap['scores'],5.8*cfg['fraction'],500,9,min_outside_score_mass=cfg['outside_gate'])
   targets=cover(chosen,9);area=sum(cell_area_km2(c) for c in targets)
   assert set(core)<=set(chosen) and area<=5.8*(1+cfg['fraction'])+1e-9
   sels.append(dict(person_id=pid,prediction_seed=seed,hour=hr,arm=arm,cells=chosen,target_cells=sorted(targets),area_km2=area,core_cells=core,safety_cells=meta['safety_cells'],outside_score_fraction=meta['outside_score_fraction'],gate_skipped=meta['gate_skipped']))
   for t in truth:
    if t['person_id']!=pid:continue
    pos=next(z['position'] for z in t['snapshots'] if z['hour']==hr)
    rows.append(dict(person_id=pid,prediction_seed=seed,truth_seed=t['truth_seed'],future=t['future'],hour=hr,arm=arm,hit=int(h3.latlng_to_cell(pos['lat'],pos['lng'],9) in targets),area_km2=area))
 print(pid,flush=True)
summary={}
for a in configs:
 r=[z for z in rows if z['arm']==a];summary[a]={'overall':100*np.mean([z['hit'] for z in r]),'area':np.mean([z['area_km2'] for z in r]),'efficiency':100*sum(z['hit'] for z in r)/sum(z['area_km2'] for z in r),**{f:100*np.mean([z['hit'] for z in r if z['future']==f]) for f in p['futures']}}
current=json.loads((O/'results/exploration_summary.json').read_text())['current']
eligible=[a for a,v in summary.items() if v['habitual']>=current['habitual'] and v['contradictory']>current['contradictory'] and v['efficiency']>current['efficiency']]
winner=max(eligible,key=lambda a:(summary[a]['efficiency'],summary[a]['contradictory'])) if eligible else None
decision={'candidate':winner,'config':configs.get(winner),'eligible':eligible,'reason':'User global floor30% retained. Requested >=50%/res8 are separately measured comparisons, not assumed successful. Raw existing30/res9 core is kept100%. Skip extra area when most reverse scores already lie inside core; no truth input. Freeze before1251 fresh truth.','new_truth_not_generated_yet':True}
for name,obj in [('adaptive_summary',summary),('adaptive_rows',rows),('adaptive_selections',sels),('adaptive_configs',configs),('adaptive_frozen_selection',decision)]:(O/f'results/{name}.json').write_text(json.dumps(obj,indent=2,default=lambda v:v.item())+'\n')
print('best',sorted(summary.items(),key=lambda z:z[1]['efficiency'],reverse=True)[:10]);print(decision)
