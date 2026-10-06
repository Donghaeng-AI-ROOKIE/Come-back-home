"""Approval-gated, fixed-candidate comparison. Default is dry run."""
import argparse,fcntl,hashlib,importlib.util,json,random,sys,threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from math import ceil
from pathlib import Path
D=Path(__file__).resolve().parent;B=D.parents[1]/'개발/cbh-simulation-integration-20261004/backend';sys.path.insert(0,str(B))
from app.llm import mind_policy,initial_behavior
from experiments.mind_policy_candidates import condition_program as candidate,note_policy_eval as evaluator
import transport

def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def sources():return {str(Path(m.__file__).resolve()):digest(Path(m.__file__)) for m in (candidate,evaluator,mind_policy,initial_behavior)}
def events():
 p=D.parents[1]/'연구지원_사용기록/usage_events.jsonl'
 return [r for line in p.read_text().splitlines() if line.strip() for r in [json.loads(line)] if r.get('run_id')==D.name] if p.exists() else []

def score(decision,row):
 return decision['status']==row['expected_status'] and set(decision['commands'])==set(row['expected_commands']) and (row['expected_possible_commands'] is None or set(decision['possible_commands'])==set(row['expected_possible_commands']))

def jobs_for(profiles):
 jobs=[]
 for person in profiles:
  for arm in ('on','off'):
   for rep in (1,2):
    jobs.append({'job':f"v4_{person['person_id']}_{arm}_{rep}",'person_id':person['person_id'],'arm':arm,'rep':rep,'personal':person['personal'],'body':candidate.request(person['personal'],'ALL',transport.model,thinking=arm=='on',whole_person=True)})
 random.Random(20261006).shuffle(jobs)
 return jobs

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
 manifest=json.loads((D/'manifest.json').read_text());profiles=json.loads((D/'profiles.json').read_text());scenes=json.loads((D/'scenes.json').read_text())
 for name,h in manifest['data_sha256'].items():assert digest(D/name)==h
 for name,h in manifest['runtime_sha256'].items():assert digest(D/name)==h
 assert sources()==manifest['source_sha256'],'frozen candidate changed'
 jobs=jobs_for(profiles);assert len(jobs)==128
 assert all(len(json.dumps(j['body'],ensure_ascii=False).encode())<=40000 for j in jobs)
 print(json.dumps({'planned_calls':128,'profiles':32,'scenes':128,'arms':['on','off'],'repetitions':2,'decisions_per_arm':256,'max_request_utf8_bytes':max(len(json.dumps(j['body'],ensure_ascii=False).encode()) for j in jobs),'dry_run':not args.execute},ensure_ascii=False),flush=True)
 if not args.execute:return
 approval=json.loads((D/'authorization.json').read_text())
 if approval.get('status')!='approved' or not approval.get('human_approval'):raise SystemExit('Approval pending: no SSH or model submission')
 assert approval['comparison_max']==128 and approval['total_max']==192
 if any(e['event_type']=='api_attempt_started' for e in events()):raise SystemExit('Existing attempts: recover durable jobs explicitly, never resubmit')
 with (D/'runner.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  out=D/'comparison';out.mkdir(exist_ok=False)
  write(out/'execution_manifest.json',{'source_sha256':sources(),'input_sha256':manifest['data_sha256'],'order':[j['job'] for j in jobs],'automatic_retries':False})
  transport.args.stage='comparison';stop=threading.Event()
  def one(j):
   folder=out/j['arm']/j['person_id']/str(j['rep']);r={k:j[k] for k in ('job','arm','person_id','rep')};r.update(valid=False,output=None,error_type=None,submitted=False)
   if stop.is_set():r['error_type']='not_submitted_after_transport_error';write(folder/'result.json',r);return r
   write(folder/'request.json',j['body'])
   try:
    r['submitted']=True;response=transport.invoke(j['body'],j['job']);choice=response['choices'][0];content=choice['message'].get('content') or ''
    if '</think>' in content:content=content.rsplit('</think>',1)[-1].strip()
    if '<think>' in content:content='[no separable final output]'
    write(folder/'response.public.json',{'final_content':content,'finish_reason':choice.get('finish_reason'),'usage':response.get('usage')})
    if choice.get('finish_reason')!='stop':raise ValueError('incomplete_output')
    value=initial_behavior.decode_json_content(content);policy=candidate.compile_note(value,j['personal'],'ALL',whole_person=True)
    write(folder/'compiled_policy.json',policy.model_dump());r.update(valid=True,output=value)
   except Exception as e:
    r['error_type']=type(e).__name__
    if type(e).__name__=='TimeoutExpired' or str(e)=='K_bridge_transport_failure' or str(e).startswith('K_API_'):stop.set()
   write(folder/'result.json',r);print({k:r[k] for k in ('job','valid','error_type')},flush=True);return r
  with ThreadPoolExecutor(max_workers=2) as pool:outputs=list(pool.map(one,jobs))
  result=[];people={p['person_id']:p['personal'] for p in profiles}
  for outrow in outputs:
   pol=None
   if outrow['valid']:pol=candidate.compile_note(outrow['output'],people[outrow['person_id']],'ALL',whole_person=True)
   for row in [r for r in scenes if r['person_id']==outrow['person_id']]:
    r={**row,'arm':outrow['arm'],'rep':outrow['rep'],'decision':None,'pass':False,'error_type':outrow['error_type']}
    if pol is not None:
     try:r['decision']=evaluator.decide(pol,people[row['person_id']],row['scene']);r['pass']=score(r['decision'],row)
     except Exception as e:r['error_type']=type(e).__name__
    result.append(r)
  gates={}
  for arm in ('on','off'):
   rs=[r for r in result if r['arm']==arm];outs=[r for r in outputs if r['arm']==arm]
   assert len(rs)==256 and len({(r['id'],r['rep']) for r in rs})==256
   groups={f:{'passed':sum(r['pass'] for r in rs if r['family']==f),'total':sum(r['family']==f for r in rs),'required':26} for f in sorted({r['family'] for r in rs})}
   passed=sum(r['pass'] for r in rs);valid=sum(r['valid'] for r in outs)
   positive=[r for r in rs if r['expected_status']=='supported'];positive_passed=sum(r['pass'] for r in positive)
   gates[arm]={'positive_passed':positive_passed,'positive_total':len(positive),'positive_required':ceil(.9*len(positive)),'passed':passed,'total':256,'required':231,'valid_outputs':valid,'output_total':64,'required_valid_outputs':61,'families':groups,'by_repetition':{str(rep):{'passed':sum(r['pass'] for r in rs if r['rep']==rep),'total':128} for rep in (1,2)},'pass_gate':passed>=231 and positive_passed>=ceil(.9*len(positive)) and valid>=61 and all(g['passed']>=26 for g in groups.values())}
  write(out/'summary.json',{'gates':gates,'model_outputs':outputs,'results':result,'synthetic_profiles':32,'clinical_patients':0,'independent_human_raters':0,'scoring':'strict expected status, selected command, and specified possible command sets; not location accuracy'})
  print(json.dumps(gates,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
