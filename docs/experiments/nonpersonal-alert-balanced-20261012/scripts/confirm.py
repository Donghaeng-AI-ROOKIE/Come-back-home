from pathlib import Path
import os,sys,socket,json,hashlib
import numpy as np,h3
O=Path(__file__).resolve().parents[1];R=O.parents[2];E=R/'결선/실험/EFFICIENCY_KINTEX_v1_20261009';X=R/'결선/실험/CHANNEL_ALERT_repair_20261011';L=R/'결선/실험/SAR_DISTANCE_ONLY_20261012';C=R/'결선/개발/cbh-independent-alert-core-20261011'
os.environ.update(PERSIST_STORAGE='false',PUSH_ENABLED='false',PUSH_TARGET_RES='9',ALERT_COVERAGE='.95',PERSONAL_CHANNEL_WEIGHT='.9');sys.path.insert(0,str(C/'backend'))
def blocked(*a,**k):raise RuntimeError('network forbidden')
socket.socket.connect=blocked;socket.create_connection=blocked
from app.config import settings
from app import storage
from app.phase2.combine import alpha_pool
from app.phase3 import alerts,devices,webpush_entry
from app.phase3.area_budget import cell_area_km2
from app.schemas.device import Platform,Engagement
from app.schemas.case import Case
from app.schemas.report import MissingReport
p=json.loads((O/'protocol.json').read_text());truth=json.loads((O/'truth_private.json').read_text());manifest=json.loads((O/'truth_manifest.json').read_text());sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest();assert sha(O/'protocol.json')==manifest['protocol_sha256'];assert sha(O/'truth_private.json')==manifest['truth_sha256'];rows=[];selections=[];fanout_checks=0
for pid in p['people']:
 litpath=L/f'results/distance_maps/{pid}.json';assert sha(litpath)==p['literature_maps'][pid];lit={s['hour']:s['cells'] for s in json.loads(litpath.read_text())['snapshots']};local=[t for t in truth if t['person_id']==pid];report=MissingReport.model_validate(json.loads((E/'output/people'/pid/'prepared.json').read_text())['report'])
 for seed in p['prediction_seeds']:
  path=X/f'results_independent_sar/{pid}_{seed}.json';assert sha(path)==p['predictions'][pid][str(seed)];raw={s['hour']:s for s in json.loads(path.read_text())['snapshots']};preserved=json.loads((E/f'service_comparison/output/people/{pid}/walk_preliminary_{seed}.json').read_text())
  for pre in preserved['snapshots']:
   assert pre['complete'];hour=pre['hour'];s=raw[hour]
   for arm in ['preliminary','current','candidate']:
    settings.push_target_res=7 if arm=='preliminary' else 9
    if arm=='preliminary':mixed=pre['cells'];chosen=pre['alert_cells'];targets=set(chosen)
    else:
     settings.alert_selection_policy='coverage' if arm=='current' else 'area_budget';settings.max_alert_area_km2=p['candidate_selection']['max_area_km2'];weight=.9 if arm=='current' else p['personal_weight'];mixed=alpha_pool([s['personal'],s['statistical'] if arm=='current' else lit[hour]],[weight,1-weight]);chosen=alerts.select_alert_cells(mixed,coverage=.95,max_cells=500);targets=alerts.target_parent_cells(chosen)
    area=sum(cell_area_km2(c) for c in sorted(targets));assert arm!='candidate' or area<=p['candidate_selection']['max_area_km2']+1e-9
    selections.append(dict(person_id=pid,prediction_seed=seed,hour=hour,arm=arm,cells=chosen,area_km2=area,statistical_only_cells=len(set(chosen)-set(s['personal'])) if arm=='candidate' else None))
    if arm!='preliminary':
     case=Case(id='offline-case',report=report,lkp=report.lkp,lkp_time=report.lkp_time,current_poa=mixed);storage.cases.save(case.id,case);assert set(alerts.describe_alert(case)['target_cells'])==targets;assert webpush_entry.target_for_case(case)[1]==chosen;devices.reset();receivers={}
    for t in local:
     pos=next(z['position'] for z in t['snapshots'] if z['hour']==hour);cell=h3.latlng_to_cell(pos['lat'],pos['lng'],settings.push_target_res);hit=int(cell in targets);rows.append(dict(person_id=pid,prediction_seed=seed,truth_seed=t['truth_seed'],future=t['future'],distance_band=t['distance_band'],hour=hour,arm=arm,hit=hit,area_km2=area))
     if arm!='preliminary':
      for level in Engagement:
       token=f'offline-{t["truth_seed"]}-{t["future"]}-{level.value}';device=devices.register(token,Platform.android,cell,level);receivers[token]=hit;assert bool(webpush_entry.targets(cell,device))==bool(hit)
    if arm!='preliminary':
     captured=[]
     def stub(tokens,**kw):
      captured.extend(tokens);assert set(kw['data']['target_cells'])==targets;return dict(sent=len(tokens),failed=0,stub=True,sent_tokens=tokens,failed_tokens=[])
     alerts.push.send=stub;out=alerts.send_alerts(case.id,chosen,'synthetic replay',poa=mixed);assert set(captured)=={k for k,v in receivers.items() if v};fanout_checks+=len(receivers)
 print(pid,flush=True)
def stats(rs):return dict(checks=len(rs),hits=sum(r['hit'] for r in rs),hit_pct=100*np.mean([r['hit'] for r in rs]),mean_area_km2=np.mean([r['area_km2'] for r in rs]),efficiency_pp_per_km2=100*sum(r['hit'] for r in rs)/sum(r['area_km2'] for r in rs))
def comparison(base,future=None):
 rs=[r for r in rows if future is None or r['future']==future];a=[r for r in rs if r['arm']=='candidate'];b=[r for r in rs if r['arm']==base];v=np.array([[sum(r['hit'] for r in a if r['person_id']==pid),sum(r['area_km2'] for r in a if r['person_id']==pid),sum(r['hit'] for r in b if r['person_id']==pid),sum(r['area_km2'] for r in b if r['person_id']==pid),sum(r['person_id']==pid for r in a)] for pid in p['people']]);bt=v[np.random.default_rng(p['bootstrap']['seed']).integers(0,len(v),(p['bootstrap']['draws'],len(v)))].sum(axis=1);pt=v.sum(axis=0)
 def measures(t):return {'hit_pp':100*(t[...,0]-t[...,2])/t[...,4],'efficiency_pp_per_km2':100*t[...,0]/t[...,1]-100*t[...,2]/t[...,3],'area_km2':(t[...,1]-t[...,3])/t[...,4]}
 return {k:dict(point=float(value),ci95=np.quantile(measures(bt)[k],[.025,.975]).tolist()) for k,value in measures(pt).items()}
summary={'profiles':{},'comparisons':{},'fanout_recipient_checks':fanout_checks,'query_web_fanout_mismatches':0,'budget_violations':0,'model_calls':0,'external_calls':0,'actual_push':0,'source_sha256':sha(Path(__file__))}
for arm in p['profiles']:
 rs=[r for r in rows if r['arm']==arm];summary['profiles'][arm]=dict(overall=stats(rs),futures={f:stats([r for r in rs if r['future']==f]) for f in p['futures']},hours={h:stats([r for r in rs if r['hour']==h]) for h in p['hours']},bands={f:stats([r for r in rs if r['distance_band']==f]) for f in ['near','mid','far']})
for base in ['preliminary','current']:summary['comparisons'][base]={key:comparison(base,None if key=='overall' else key) for key in ['overall',*p['futures']]}
key=lambda r:(r['person_id'],r['prediction_seed'],r['truth_seed'],r['future'],r['hour']);candidate={key(r):r for r in rows if r['arm']=='candidate'};summary['paired_losses']={base:{f:sum(r['hit'] and not candidate[key(r)]['hit'] for r in rows if r['arm']==base and r['future']==f) for f in p['futures']} for base in ['preliminary','current']}
gates={f'{base}_{f}_point_noninferior':summary['profiles']['candidate']['futures'][f]['hit_pct']>=summary['profiles'][base]['futures'][f]['hit_pct'] for base in ['preliminary','current'] for f in p['futures']};gates['efficiency_vs_preliminary']=summary['profiles']['candidate']['overall']['efficiency_pp_per_km2']>summary['profiles']['preliminary']['overall']['efficiency_pp_per_km2'];gates['budget_and_parity']=True
cs=summary['comparisons']['current'];gates.update(efficiency_positive_ci_vs_current=cs['overall']['efficiency_pp_per_km2']['ci95'][0]>0,overall_noninferior_ci_vs_current=cs['overall']['hit_pp']['ci95'][0]>=0,habitual_noninferior_ci_vs_current=cs['habitual']['hit_pp']['ci95'][0]>=0,departure_noninferior_ci_vs_current=cs['departure']['hit_pp']['ci95'][0]>=0,contradictory_improvement_ci_vs_current=cs['contradictory']['hit_pp']['ci95'][0]>0,efficiency_positive_ci_vs_preliminary=summary['comparisons']['preliminary']['overall']['efficiency_pp_per_km2']['ci95'][0]>0)
summary['additional_confidence_checks']={'contradictory_noninferiority_ci_vs_preliminary':summary['comparisons']['preliminary']['contradictory']['hit_pp']['ci95'][0]>=0}
summary['decision']={'frozen_candidate':p['candidate_selection']['candidate'],'gates':gates,'confirm':all(gates.values()),'ci_not_used_as_point_pass':True,'zero_misses_guaranteed':False}
for name,obj in [('confirmation_rows',rows),('confirmation_selections',selections),('confirmation_summary',summary)]: (O/f'results/{name}.json').write_text(json.dumps(obj,indent=2,default=lambda v:v.item())+'\n')
print(json.dumps(summary,indent=2,default=lambda v:v.item()))
