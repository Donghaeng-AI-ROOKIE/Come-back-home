import json,os,secrets,sys,time,uuid
from pathlib import Path
import httpx
from app.config import settings
from app.llm.usage_ledger import append_event
folder=Path('/app/data/final-deploy-20261012');folder.mkdir(mode=0o700,exist_ok=True)
identity=folder/'synthetic-auth.json';counter=folder/'request-count.json'
base=os.environ['SUPABASE_URL'].rstrip('/');key=os.environ['SUPABASE_SERVICE_ROLE_KEY']
mode=sys.argv[1];count=json.loads(counter.read_text()) if counter.exists() else 0
run='SERVICE_final_deploy_20261012'
client=httpx.Client(timeout=30)
def req(method,path,body=None,token=None,admin=False):
 global count
 count+=1;assert count<=120,'transport cap120'
 counter.write_text(json.dumps(count));counter.chmod(0o600)
 common={'run_id':run,'attempt_id':str(uuid.uuid4()),'provider':'Supabase','role':mode+'_'+path.split('?')[0].split('/')[-1],'actual_cost':None}
 append_event({**common,'event_type':'transport_attempt_started'},settings.research_usage_ledger_path)
 headers={'apikey':key};status=None;error=None;start=time.monotonic()
 if admin or token:headers['Authorization']='Bearer '+(key if admin else token)
 try:
  r=client.request(method,base+path,json=body,headers=headers);status=r.status_code;r.raise_for_status();return r.json() if r.content else None
 except Exception as e:error=type(e).__name__;raise RuntimeError('transport failure '+str(status)+' '+str(error)) from None
 finally:append_event({**common,'event_type':'transport_attempt_finished','http_status':status,'error_type':error,'duration_ms':round((time.monotonic()-start)*1000,2)},settings.research_usage_ledger_path)
def job(method,path,body=None):
 rid=str(uuid.uuid4());req('POST','/rest/v1/rpc/cbh_submit',{'p_id':rid,'p_method':method,'p_path':path,'p_body':body},who['token'])
 for _ in range(36):
  result=req('POST','/rest/v1/rpc/cbh_result',{'p_id':rid},who['token'])
  if result and result.get('state') in ('done','interrupted','expired'):
   assert result['state']=='done' and result.get('status_code')==200,{'stage':path,'state':result.get('state'),'status':result.get('status_code')}
   return result['result']
  time.sleep(3)
 raise RuntimeError('job timed out; do not resubmit')
if mode=='init':
 if identity.exists():who=json.loads(identity.read_text())
 else:
  who={'email':'cbh-final-'+uuid.uuid4().hex+'@example.com','password':secrets.token_urlsafe(36)}
  user=req('POST','/auth/v1/admin/users',{**who,'email_confirm':True,'user_metadata':{'role':'guardian','synthetic_deployment_test':run}},admin=True)
  who['owner_id']=user['id'];identity.write_text(json.dumps(who));identity.chmod(0o600)
 auth=req('POST','/auth/v1/token?grant_type=password',{'email':who['email'],'password':who['password']});who['token']=auth['access_token'];assert auth['user']['id']==who['owner_id']
 identity.write_text(json.dumps(who));identity.chmod(0o600)
 slots=job('GET','/phase0/slots')
 print(json.dumps({'synthetic_auth_ready':True,'old_worker_roundtrip':bool(slots),'requests':count,'model_calls':0}),flush=True)
elif mode=='verify':
 who=json.loads(identity.read_text());cid='deploy-final-e09-c';pid='deploy-final-e09'
 policy=job('GET','/phase3/webpush/public-key')
 assert policy['target_res']==9 and policy['max_area_km2']==5.8 and policy['selection_policy']=='area_budget',policy
 out={'policy':policy,'checks':{'authenticated_read_lane_policy':True},'model_calls':0,'cached_synthetic_SAR_K_replay':True,'real_notifications':0}
 result=job('POST',f'/phase2/cases/{cid}/predict?seed=104729')
 q=result['quality'];assert q['personal_channel_weight']==.3 and q['statistical_definition']=='literature_distance_prior' and not q['channels_identical'] and q['unresolved_mass']==0
 a=result['poa_bottomup']['cells'];b=result['poa_statistical']['cells'];mix=result['poa_combined']['cells']
 delta=max(abs(mix.get(c,0)-(.3*a.get(c,0)+.7*b.get(c,0))) for c in set(a)|set(b));assert delta<1e-12
 from app.phase3 import alerts
 from app.phase3.area_budget import cell_area_km2
 targets=alerts.target_parent_cells(alerts.select_alert_cells(mix));area=sum(cell_area_km2(c) for c in targets);assert area<=5.8+1e-9
 out.update(engine=q['engine'],quality={k:q.get(k) for k in ['channels_identical','channel_total_variation','personal_channel_weight','statistical_definition','statistical_uses_onboarding_prior','statistical_uses_conditional_mind_program','checkpoint_committed']},target_cells=len(targets),area_km2=area,mixture_max_delta=delta)
 poa=job('GET',f'/phase3/cases/{cid}/poa?top=128');assert poa['roadnet_used'] and poa['prior_source']=='prepared_person' and poa['personal_interpretation_status']=='applied'
 repeat=job('POST',f'/phase2/cases/{cid}/predict?seed=104729');assert repeat['quality']['checkpoint_reused']
 out['checks'].update(actual_worker_prediction=True,prepared_person_map_query=True,checkpoint_reused=True,independent_channels=True,linear_30_70_exact=True,area_cap_and_res9=True)
 # Citizen list must exclude this server-marked synthetic incident.
 listed=job('GET','/phase3/alerts?target_cell='+next(iter(targets)));assert all(x['case_id']!=cid for x in listed)
 out['checks']['synthetic_excluded_from_citizen_list']=True
 sent=job('POST',f'/phase3/cases/{cid}/alerts');assert sent.get('status')=='synthetic_isolated' and sent.get('sent')==0
 out['checks']['synthetic_actual_delivery_blocked']=True
 out['requests']=count;out['passed']=all(out['checks'].values())
 (folder/'verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));(folder/'verification.json').chmod(0o600)
 print(json.dumps(out,ensure_ascii=False),flush=True)
elif mode=='cleanup':
 who=json.loads(identity.read_text());cid='deploy-final-e09-c';pid='deploy-final-e09'
 job('POST',f'/phase1/cases/{cid}/close',{'reason':'withdrawn'})
 job('DELETE',f'/phase1/cases/{cid}')
 job('DELETE',f'/phase0/personas/{pid}')
 req('DELETE','/auth/v1/admin/users/'+who['owner_id'],admin=True)
 identity.unlink()
 print(json.dumps({'synthetic_data_removed':True,'requests':count,'model_calls':0}),flush=True)
