"""Two frozen channel definitions, same selector/truth; no engine mutations."""
from pathlib import Path
import os,sys,socket,json,hashlib,time
O=Path(__file__).resolve().parents[1];R=O.parents[2];B=R/'결선/실험';C=R/'결선/개발/cbh-independent-alert-core-20261011'
os.environ.update(PERSIST_STORAGE='false',PUSH_ENABLED='false',PUSH_TARGET_RES='9',PERSONAL_CHANNEL_WEIGHT='.3',ALERT_SELECTION_POLICY='area_budget',MAX_ALERT_AREA_KM2='5.8',MPLCONFIGDIR='/tmp/cbh-mpl')
def blocked(*a,**kw):raise RuntimeError('offline comparison forbids network')
socket.socket.connect=blocked;socket.create_connection=blocked
sys.path.insert(0,str(C/'backend'))
import numpy as np,h3
from app import storage
from app.config import settings
from app.phase2.combine import alpha_pool
from app.phase3 import alerts,devices,webpush_entry
from app.phase3.area_budget import cell_area_km2
from app.schemas.case import Case
from app.schemas.report import MissingReport
from app.schemas.device import Platform,Engagement
from fastapi.testclient import TestClient
from app.main import app
from app.llm.usage_ledger import append_event
P=json.loads((O/'protocol.json').read_text());sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
for f,digest in P['source_hashes'].items():assert sha(C/f)==digest
ledger=R/'결선/연구지원_사용기록/usage_events.jsonl'
append_event({'event_type':'offline_comparison_started','run_id':O.name,'model_calls':0,'remote_calls':0,'actual_push':0,'actual_cost':None},ledger)
armnames=list(P['arms']);sels=[];raw_cache={};provenance={};errors=[];fanout_checks=0;query_checks=0
client=TestClient(app)
def load_truth(path,expected_hash=None):
 if expected_hash:assert sha(path)==expected_hash
 truth=json.loads(path.read_text());assert len(truth)==351
 return truth
datasets={'retrospective':load_truth(B/'DIRECTIONAL_ALERT_SAFETY_20261012/truth_private.json',P['existing_truth']['sha256'])}
if (O/'truth_private.json').exists():
 m=json.loads((O/'truth_manifest.json').read_text());assert sha(O/'protocol.json')==m['protocol_sha256']
 datasets['fresh_confirmation']=load_truth(O/'truth_private.json',m['truth_sha256'])
assert 'fresh_confirmation' in datasets,'wait for fixed road-truth generation'
rows={k:[] for k in datasets};indexed={key:{pid:[r for r in truth if r['person_id']==pid] for pid in P['people']} for key,truth in datasets.items()}
for pid in P['people']:
 litpath=B/f'SAR_DISTANCE_ONLY_20261012/results/distance_maps/{pid}.json';assert sha(litpath)==P['literature_sha256'][pid]
 literature={s['hour']:s['cells'] for s in json.loads(litpath.read_text())['snapshots']}
 source=json.loads((B/f'EFFICIENCY_KINTEX_v1_20261009/output/people/{pid}/prepared.json').read_text())
 report=MissingReport.model_validate(source['report']);provenance[pid]={'sar_source':source['SAR_personal'].get('source'),'sar_fallback_reason':source['SAR_personal'].get('fallback_reason'),'axis_scores_present':bool(source['arms']['D_full_prepared']['persona'].get('axis_scores'))}
 for seed in P['prediction_seeds']:
  path=B/f'CHANNEL_ALERT_repair_20261011/results_independent_sar/{pid}_{seed}.json';assert sha(path)==P['cached_prediction_sha256'][pid][str(seed)]
  cache=json.loads(path.read_text());assert cache['statistical_prior_source']=='original_sar_numeric_snapshot' and cache['new_model_calls']==0
  for snap in cache['snapshots']:
   hour=snap['hour'];a=snap['personal'];sar=snap['statistical'];q=snap['statistical_quality']
   assert q['unresolved_mass']==0 and q['new_model_calls_during_walk']==0 and q['walkers']==500
   assert all(abs(sum(d.values())-1)<1e-8 for d in [a,sar,literature[hour]])
   for arm in armnames:
    stat=literature[hour] if arm=='current_literature70' else sar
    settings.statistical_channel_definition=P['arms'][arm]['statistical_definition']
    mixed=alpha_pool([a,stat],[.3,.7],mode='linear')
    chosen=alerts.select_alert_cells(mixed,max_cells=500);targets=alerts.target_parent_cells(chosen,res=9)
    area=sum(cell_area_km2(c) for c in sorted(targets));assert 0<area<=5.8+1e-9 and all(h3.get_resolution(c)==9 for c in targets)
    sels.append({'person_id':pid,'prediction_seed':seed,'hour':hour,'arm':arm,'cells':chosen,'target_cells':sorted(targets),'area_km2':area,'selected_mass':sum(mixed[c] for c in chosen),'personal_mass_contribution':sum(.3*a.get(c,0) for c in chosen),'statistical_mass_contribution':sum(.7*stat.get(c,0) for c in chosen),'positive_support_cells':len(mixed),'statistical_only_target_cells':len(targets-set(a))})
    case=Case(id='final-offline-channel-comparison',report=report,lkp=report.lkp,lkp_time=report.lkp_time,current_poa=mixed);storage.cases.save(case.id,case)
    assert set(alerts.describe_alert(case)['target_cells'])==targets
    assert webpush_entry.target_for_case(case)[1]==chosen
    devices.reset();receivers={}
    for name,truth in datasets.items():
     for t in indexed[name][pid]:
      pos=next(s['position'] for s in t['snapshots'] if s['hour']==hour);cell=h3.latlng_to_cell(pos['lat'],pos['lng'],9);hit=int(cell in targets)
      rows[name].append({'person_id':pid,'prediction_seed':seed,'truth_seed':t['truth_seed'],'future':t['future'],'distance_band':t['distance_band'],'hour':hour,'arm':arm,'hit':hit,'area_km2':area})
      got=client.get('/phase3/alerts',params={'target_cell':cell});assert got.status_code==200
      assert any(r['case_id']==case.id for r in got.json())==bool(hit);query_checks+=1
      for level in Engagement:
       token=f'{name}-{t["truth_seed"]}-{t["future"]}-{level.value}';d=devices.register(token,Platform.android,cell,level);receivers[token]=hit
       assert bool(webpush_entry.targets(cell,d))==bool(hit)
    captured=[]
    def stub(tokens,**kw):
     assert set(kw['data']['target_cells'])==targets and kw['data']['target_res']==9
     captured.extend(tokens);return {'sent':len(tokens),'failed':0,'sent_tokens':tokens,'failed_tokens':[],'stub':True}
    alerts.push.send=stub
    sent=alerts.send_alerts(case.id,chosen,'synthetic study',poa=mixed)
    assert set(captured)=={k for k,v in receivers.items() if v};fanout_checks+=len(receivers)
 print(pid,flush=True)
def stats(data):
 return {'checks':len(data),'hits':sum(r['hit'] for r in data),'hit_pct':100*np.mean([r['hit'] for r in data]),'mean_area_km2':float(np.mean([r['area_km2'] for r in data])),'efficiency_pp_per_km2':100*sum(r['hit'] for r in data)/sum(r['area_km2'] for r in data)}
def paired(data,future=None):
 a=[r for r in data if r['arm']=='personalized_sar70' and (future is None or r['future']==future)];b=[r for r in data if r['arm']=='current_literature70' and (future is None or r['future']==future)]
 v=np.array([[sum(r['hit'] for r in a if r['person_id']==pid),sum(r['area_km2'] for r in a if r['person_id']==pid),sum(r['hit'] for r in b if r['person_id']==pid),sum(r['area_km2'] for r in b if r['person_id']==pid),sum(r['person_id']==pid for r in a)] for pid in P['people']])
 bt=v[np.random.default_rng(P['bootstrap']['seed']).integers(0,len(v),(P['bootstrap']['draws'],len(v)))].sum(axis=1);pt=v.sum(axis=0)
 def measures(t):return {'hit_pp':100*(t[...,0]-t[...,2])/t[...,4],'efficiency_pp_per_km2':100*t[...,0]/t[...,1]-100*t[...,2]/t[...,3],'area_km2':(t[...,1]-t[...,3])/t[...,4]}
 return {k:{'point':float(value),'ci95':np.quantile(measures(bt)[k],[.025,.975]).tolist()} for k,value in measures(pt).items()}
summary={'conditions':P['conditions'],'datasets':{},'validation':{'fanout_recipient_checks':fanout_checks,'app_query_checks':query_checks,'app_web_fanout_mismatches':0,'budget_violations':0,'model_calls':0,'external_calls':0,'actual_push':0},'provenance':provenance}
for name,data in rows.items():
 result={'truth_seeds':sorted({r['truth_seed'] for r in data}),'profiles':{},'sar_minus_current':{f:paired(data,None if f=='overall' else f) for f in ['overall',*P['futures']]}}
 for arm in armnames:
  r=[v for v in data if v['arm']==arm];result['profiles'][arm]={'overall':stats(r),'futures':{f:stats([v for v in r if v['future']==f]) for f in P['futures']},'hours':{str(h):stats([v for v in r if v['hour']==h]) for h in P['hours']}}
 key=lambda r:(r['person_id'],r['prediction_seed'],r['truth_seed'],r['future'],r['hour'])
 current={key(r):r for r in data if r['arm']=='current_literature70'}
 result['current_to_sar_paired_changes']={f:{'lost':sum(current[key(r)]['hit'] and not r['hit'] for r in data if r['arm']=='personalized_sar70' and r['future']==f),'gained':sum(r['hit'] and not current[key(r)]['hit'] for r in data if r['arm']=='personalized_sar70' and r['future']==f)} for f in P['futures']}
 summary['datasets'][name]=result
 (O/f'results/{name}_rows.json').write_text(json.dumps(data)+'\n')
fresh=summary['datasets']['fresh_confirmation']['sar_minus_current'];gates={f: fresh[f]['hit_pp']['point']>=0 for f in P['futures']};gates['efficiency_positive_ci']=fresh['overall']['efficiency_pp_per_km2']['ci95'][0]>0
summary['decision']={'selection':'personalized_sar70' if all(gates.values()) else 'current_literature70','gates':gates,'source':'frozen two-arm same-area-cap new-path comparison','engine_changes':0,'service_changes':0,'all_behavior_superiority_claimed':False,'actual_cost':None}
for filename,value in [('summary',summary),('selections',sels)]: (O/f'results/{filename}.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
append_event({'event_type':'offline_comparison_finished','run_id':O.name,'model_calls':0,'remote_calls':0,'actual_push':0,'actual_cost':None,'rows':sum(len(r) for r in rows.values()),'selected':summary['decision']['selection'],'parity_mismatches':0,'protocol_sha256':sha(O/'protocol.json')},ledger)
print(json.dumps({'datasets':summary['datasets'],'validation':summary['validation'],'decision':summary['decision']},ensure_ascii=False,indent=2),flush=True)
