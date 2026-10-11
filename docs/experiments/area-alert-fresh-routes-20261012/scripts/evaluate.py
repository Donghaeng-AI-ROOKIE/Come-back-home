from pathlib import Path
import argparse,json,hashlib,socket,sys,os
import numpy as np,h3
O=Path(__file__).resolve().parents[1];R=O.parents[2];E=R/'결선/실험/EFFICIENCY_KINTEX_v1_20261009';X=R/'결선/실험/CHANNEL_ALERT_repair_20261011';L=R/'결선/실험/SAR_DISTANCE_ONLY_20261012';C=R/'결선/개발/cbh-independent-alert-core-20261011'
os.environ.update(PERSIST_STORAGE='false',PUSH_ENABLED='false',PUSH_TARGET_RES='9',PERSONAL_CHANNEL_WEIGHT='.9');sys.path.insert(0,str(C/'backend'))
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
ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['development','validation']);args=ap.parse_args();p=json.loads((O/'protocol.json').read_text());manifest=json.loads((O/'truth_manifest.json').read_text());sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest();assert sha(O/'truth_private.json')==manifest['truth_sha256'];assert sha(O/'protocol.json')==manifest['protocol_sha256'];truth=[t for t in json.loads((O/'truth_private.json').read_text()) if t['split']==args.stage];rows=[];diagnostics=[];fanout_checks=0
profiles=p['profiles'] if args.stage=='development' else {a:p['profiles'][a] for a in dict.fromkeys(['current',json.loads((O/'results/development_selection.json').read_text())['selected_candidate']])}
for pid in p['people']:
 lpath=L/f'results/distance_maps/{pid}.json';assert sha(lpath)==p['literature_maps'][pid];lit={s['hour']:s['cells'] for s in json.loads(lpath.read_text())['snapshots']};localtruth=[t for t in truth if t['person_id']==pid];report=MissingReport.model_validate(json.loads((E/'output/people'/pid/'prepared.json').read_text())['report'])
 for seed in p['prediction_seeds']:
  path=X/f'results_independent_sar/{pid}_{seed}.json';assert sha(path)==p['predictions'][pid][str(seed)]
  for s in json.loads(path.read_text())['snapshots']:
   hour=s['hour']
   for arm,profile in profiles.items():
    mixed=alpha_pool([s['personal'],s['statistical'] if arm=='current' else lit[hour]],[.9,1-.9]);settings.alert_selection_policy=profile['selection'];settings.max_alert_area_km2=profile.get('max_area_km2',6.368199998062131);settings.alert_coverage=.95;settings.max_alert_cells=500
    selected=alerts.select_alert_cells(mixed);targets=alerts.target_parent_cells(selected);size=sum(cell_area_km2(c) for c in sorted(targets));budget=profile.get('max_area_km2');assert budget is None or size<=budget+1e-8
    case=Case(id='offline-alert-case',report=report,lkp=report.lkp,lkp_time=report.lkp_time,current_poa=mixed);storage.cases.save(case.id,case)
    assert set(alerts.describe_alert(case)['target_cells'])==targets
    assert webpush_entry.target_for_case(case)[1]==selected
    diagnostics.append({'person_id':pid,'prediction_seed':seed,'hour':hour,'arm':arm,'selected_cells':len(selected),'selected_mass':sum(mixed[c] for c in selected),'area_km2':size,'budget_km2':budget})
    receivers={};devices.reset()
    for t in localtruth:
     pos=next(z['position'] for z in t['snapshots'] if z['hour']==hour);cell=h3.latlng_to_cell(pos['lat'],pos['lng'],9);hit=int(cell in targets);row={'person_id':pid,'prediction_seed':seed,'truth_seed':t['truth_seed'],'hour':hour,'future':t['future'],'distance_band':t['distance_band'],'arm':arm,'hit':hit,'area_km2':size};rows.append(row)
     if args.stage=='validation':
      for level in Engagement:
       token=f'offline-{t["truth_seed"]}-{t["future"]}-{level.value}';device=devices.register(token,Platform.android,cell,level);receivers[token]=hit;assert bool(webpush_entry.targets(cell,device))==bool(hit)
    if args.stage=='validation':
     captured=[]
     def stub(tokens,**kw):
      captured.extend(tokens);assert set(kw['data']['target_cells'])==targets;assert kw['data']['targeting_policy']==alerts.targeting_policy_name();return {'sent':len(tokens),'failed':0,'stub':True,'sent_tokens':tokens,'failed_tokens':[]}
     alerts.push.send=stub
     out=alerts.send_alerts(case.id,selected,'synthetic offline replay',poa=mixed)
     assert set(captured)=={k for k,v in receivers.items() if v};fanout_checks+=len(receivers)
 print(args.stage,pid,flush=True)
def stats(rs):
 return {'checks':len(rs),'hits':sum(r['hit'] for r in rs),'hit_pct':100*np.mean([r['hit'] for r in rs]),'mean_delivery_area_km2':np.mean([r['area_km2'] for r in rs]),'efficiency_pp_per_km2':100*sum(r['hit'] for r in rs)/sum(r['area_km2'] for r in rs)}
def comparison(arm,future=None):
 rs=[r for r in rows if future is None or r['future']==future];a=[r for r in rs if r['arm']==arm];b=[r for r in rs if r['arm']=='current'];v=np.array([[sum(r['hit'] for r in a if r['person_id']==pid),sum(r['area_km2'] for r in a if r['person_id']==pid),sum(r['hit'] for r in b if r['person_id']==pid),sum(r['area_km2'] for r in b if r['person_id']==pid),sum(r['person_id']==pid for r in a)] for pid in p['people']]);ix=np.random.default_rng(p['bootstrap']['seed']).integers(0,len(v),(p['bootstrap']['draws'],len(v)));bt=v[ix].sum(axis=1);pt=v.sum(axis=0)
 def measures(t):return {'hit_pp':100*(t[...,0]-t[...,2])/t[...,4],'efficiency_pp_per_km2':100*t[...,0]/t[...,1]-100*t[...,2]/t[...,3],'area_km2':(t[...,1]-t[...,3])/t[...,4]}
 delta={k:{'point':float(value),'ci95':np.quantile(measures(bt)[k],[.025,.975]).tolist()} for k,value in measures(pt).items()};return {'current':stats(b),'candidate':stats(a),'delta':delta}
summary={'stage':args.stage,'truth_manifest':manifest,'profiles':{},'actual_push':0,'external_calls':0,'fanout_recipient_checks':fanout_checks,'query_web_fanout_parity':True,'budget_violations':0,'source_sha256':sha(Path(__file__))}
for arm in profiles:
 rs=[r for r in rows if r['arm']==arm];ds=[d for d in diagnostics if d['arm']==arm];summary['profiles'][arm]={'overall':stats(rs),'futures':{f:stats([r for r in rs if r['future']==f]) for f in p['futures']},'distance_bands':{f:stats([r for r in rs if r['distance_band']==f]) for f in ['near','mid','far']},'selected_mass':{'min':min(d['selected_mass'] for d in ds),'mean':float(np.mean([d['selected_mass'] for d in ds]))}}
 if arm!='current':summary['profiles'][arm]['comparisons']={'overall':comparison(arm),**{f:comparison(arm,f) for f in p['futures']}}
for n,v in [(f'{args.stage}_rows.json',rows),(f'{args.stage}_diagnostics.json',diagnostics),(f'{args.stage}_summary.json',summary)]:
 dest=O/'results'/n;assert not dest.exists();dest.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
if args.stage=='development':
 eligible=[arm for arm in profiles if arm!='current' and all(summary['profiles'][arm]['futures'][f]['hit_pct']>=summary['profiles']['current']['futures'][f]['hit_pct'] for f in p['futures'])];winner=max(eligible,key=lambda arm:summary['profiles'][arm]['overall']['efficiency_pp_per_km2']) if eligible else 'current';selection={'selected_candidate':winner,'eligible':eligible,'protocol_sha256':sha(O/'protocol.json'),'development_rows_sha256':sha(O/'results/development_rows.json'),'validation_scored':False};assert winner==json.loads((O/'results/development_selection.json').read_text())['selected_candidate'];(O/'results/development_repair_selection_check.json').write_text(json.dumps(selection,indent=2)+'\n');print(selection)
else:
 arm=json.loads((O/'results/development_selection.json').read_text())['selected_candidate'];gate={'development_candidate_qualified':arm!='current','budget_violations':False}
 if arm!='current':
  cs=summary['profiles'][arm]['comparisons'];gate={'efficiency_positive_ci':cs['overall']['delta']['efficiency_pp_per_km2']['ci95'][0]>0,'overall_noninferior_ci':cs['overall']['delta']['hit_pp']['ci95'][0]>=0,'habitual_noninferior_ci':cs['habitual']['delta']['hit_pp']['ci95'][0]>=0,'departure_noninferior_ci':cs['departure']['delta']['hit_pp']['ci95'][0]>=0,'contradictory_improvement_ci':cs['contradictory']['delta']['hit_pp']['ci95'][0]>0,'budget_no_violations':True}
 decision={'candidate':arm,'gates':gate,'final_default':arm if all(gate.values()) else 'current','selection_sha256':sha(O/'results/development_selection.json'),'validation_rows_sha256':sha(O/'results/validation_rows.json'),'retuning_on_validation':False};(O/'results/final_decision.json').write_text(json.dumps(decision,indent=2)+'\n');print(decision)
print(json.dumps(summary,ensure_ascii=False,allow_nan=False))
