import json,os,time,uuid,subprocess,importlib.util
from pathlib import Path
from datetime import datetime,timezone
from types import SimpleNamespace
D=Path(__file__).resolve().parent
model='depmkuykpfon9lg'
args=SimpleNamespace(provider='k',stage='development')
spec=importlib.util.spec_from_file_location('guarded_ledger',D.parents[1]/'개발/cbh-simulation-integration-20261004/backend/app/llm/usage_ledger.py')
base_ledger=importlib.util.module_from_spec(spec);spec.loader.exec_module(base_ledger)
ledger=SimpleNamespace(append_event=lambda event, **kw: base_ledger.append_event(event, ledger_path=D.parents[1]/'연구지원_사용기록/usage_events.jsonl', **kw))
now=lambda:datetime.now(timezone.utc).isoformat()
REMOTE=r'''
import os,json,time,uuid
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
pack=json.loads(PACK)
D=Path('/tmp/MIND_diverse_comparison_20261006');D.mkdir(exist_ok=True)
def event(x):
 with (D/'usage_events.jsonl').open('a') as f:f.write(json.dumps(x,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
start=pack['start'];event(start)
key=os.environ['KEXAONE_API_KEY'];base=os.environ['KEXAONE_BASE_URL'].rstrip('/');model=os.environ['KEXAONE_MODEL']
assert pack['body']['model']==model
url=base+'/chat/completions'
t=time.monotonic();response=None;end={**{k:v for k,v in start.items() if k not in ['event_id','event_type','started_at']},'event_id':str(uuid.uuid4()),'event_type':'api_attempt_finished','usage':None,'actual_cost':None,'estimated_cost':None,'support_round':None,'gpu_billed_hours':None}
try:
 req=Request(url,data=json.dumps(pack['body'],ensure_ascii=False).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
 with urlopen(req,timeout=420) as r:response=json.loads(r.read());end['http_status']=r.status
 end.update(outcome='response_received',usage=response.get('usage'),provider_response_id=response.get('id'),finish_reason=response.get('choices',[{}])[0].get('finish_reason'))
except Exception as e:
 end.update(outcome='error',error_type=type(e).__name__,http_status=e.code if isinstance(e,HTTPError) else None)
 if isinstance(e,HTTPError):
  try:
   detail=json.loads(e.read()).get('detail',[])
   if isinstance(detail,list):end['validation_errors']=[{'loc':d.get('loc'),'type':d.get('type'),'msg':d.get('msg')} for d in detail if isinstance(d,dict)]
   elif isinstance(detail,str):end['validation_errors']=[{'msg':detail[:500]}]
  except Exception:pass
end['duration_seconds']=time.monotonic()-t;event(end)
(D/(pack['id']+'.json')).write_text(json.dumps({'request':pack['body'],'response':response,'end':end},ensure_ascii=False))
print(json.dumps({'response':response,'end':end},ensure_ascii=False),flush=True)
'''

def invoke(body,job,*,resume_unsubmitted_start=None):
 start={'event_id':str(uuid.uuid4()),'event_type':'api_attempt_started','attempt_id':str(uuid.uuid4()),'logical_request_id':job,'attempt':1,'run_id':D.name,'role':'mind_state_alignment_'+args.stage,'provider':'K_EXAONE_API','model_requested':model,'started_at':now(),'actual_cost':None,'support_round':None,'billing_basis':'API_rate_unconfirmed'}
 if resume_unsubmitted_start is not None:
  start=dict(resume_unsubmitted_start)
  assert start['event_type']=='api_attempt_started' and start['logical_request_id']==job and start['run_id']==D.name
  ledger.append_event({'event_id':str(uuid.uuid4()),'event_type':'api_transport_resumed','attempt_id':start['attempt_id'],'logical_request_id':job,'run_id':D.name,'reason':'transport ended before model submission; remote no-launch/no-event evidence saved; first model submission of existing reserved attempt'})
 else:
  ledger.append_event(start, max_started=192)
 pack={'id':job,'body':body,'start':start}
 code=REMOTE.replace('PACK',repr(json.dumps(pack,ensure_ascii=False)))
 # Detach the single metered model request. Polling reads only its durable file;
 # neither an SSH interruption nor a status miss resends the model request.
 launch="""import os,sys,json,subprocess
from pathlib import Path
D=Path('/tmp/MIND_diverse_comparison_20261006');D.mkdir(exist_ok=True)
job=JOB
fd=os.open(str(D/(job+'.launch')),os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
script=D/(job+'.worker.py');script.write_text(WORKER)
with (D/(job+'.stdout')).open('w') as out,(D/(job+'.stderr')).open('w') as err:
 subprocess.Popen([sys.executable,str(script)],stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True,close_fds=True)
print(json.dumps({'submitted':job}),flush=True)
""".replace('JOB',repr(job)).replace('WORKER',repr(code))
 ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','damisoda@<REMOTE_HOST>','export PATH=/opt/homebrew/bin:$PATH; docker exec -i come-back-home-backend-1 python -']
 try:
  result=subprocess.run(ssh,input=launch,text=True,capture_output=True,timeout=20)
  if result.returncode:
   ledger.append_event({**start,'event_id':str(uuid.uuid4()),'event_type':'api_transport_incomplete','error_type':'SSHTransportError','remote_event_recovery_required':True})
   raise RuntimeError('K_bridge_transport_failure')
  assert json.loads(result.stdout)['submitted']==job
  read="from pathlib import Path\np=Path("+repr('/tmp/MIND_diverse_comparison_20261006/'+job+'.json')+")\nprint(p.read_text() if p.exists() else '{\"pending\":true}')"
  deadline=time.monotonic()+450;received=None
  while time.monotonic()<deadline:
   time.sleep(3)
   try:
    status=subprocess.run(ssh,input=read,text=True,capture_output=True,timeout=15)
    if status.returncode:continue
    candidate=json.loads(status.stdout)
    if 'end' in candidate:received=candidate;break
   except (subprocess.TimeoutExpired,json.JSONDecodeError):continue
  if received is None:raise subprocess.TimeoutExpired('remote completion polling',450)
  ledger.append_event(received['end'])
  if received['response'] is None:raise RuntimeError('K_API_'+received['end'].get('error_type','unknown'))
  return received['response']
 except (subprocess.TimeoutExpired,json.JSONDecodeError) as e:
  ledger.append_event({**start,'event_id':str(uuid.uuid4()),'event_type':'api_transport_incomplete','error_type':type(e).__name__,'remote_event_recovery_required':True});raise
