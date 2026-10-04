"""Corrected compiled-person handoff. Shared 96-call / 12-per-person ceiling."""
import concurrent.futures,json,os,hashlib
from bootstrap import D,BACK,sha
from run_v3 import load,session,HOURS
import transport


def old_count(case):
 return sum(len(list((D/folder/case).glob('*.request.json'))) for folder in ('live','projected'))

def main():
 # Capture exact source before launch. The interrupted unprojected probe is preserved.
 net,meta,people,places=load()
 sources=[BACK/'experiments/mind_upgrade/runtime.py',BACK/'experiments/mind_closed_loop/bridge.py',D/'run_v3.py',D/'run_final.py']
 manifest={'candidate':'compiled_K_valid_initial_motion_production_reversal_penalty','overall_call_cap_including_original_probe':96,
   'case_caps':{i[0]['id']:12-old_count(i[0]['id']) for i in people},
   'code_sha256':{str(p):sha(p) for p in sources},'max_tokens':12000,'concurrency':2,
   'actual_cost':None,'support_round':None,'new_map_calls':0,'new_embedding_calls':0,
   'original_probe_role':'Original: missing projection. Projected: three seek-without-target inputs excluded. Final: source initialization preserved.'}
 for item in people:
  check,_=session(net,item,places,lambda body:None)
  check.context('initial')
 fd=os.open(D/'FINAL_LOOP_STARTED',os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
 (D/'final_loop_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 def one(item):
  row=item[0];case=row['id'];case_dir=D/'final_loop'/case;case_dir.mkdir(parents=True)
  count=[0]
  def request(body):
   assert count[0]<manifest['case_caps'][case]
   count[0]+=1;job=f'final_{case}_{count[0]:02d}'
   (case_dir/(job+'.request.json')).write_text(json.dumps({'id':job,'body':body},ensure_ascii=False)+'\n')
   answer=transport.invoke(body,job);choice=(answer.get('choices') or [{}])[0]
   public={'content':choice.get('message',{}).get('content',''),'finish_reason':choice.get('finish_reason'),
           'usage':answer.get('usage'),'model':answer.get('model')}
   (case_dir/(job+'.public.json')).write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n')
   print(json.dumps({'case':case,'call':count[0],'response_saved':True},ensure_ascii=False),flush=True)
   return public
  s,bridge=session(net,item,places,request);bridge.max_calls=manifest['case_caps'][case]
  snaps={};error=None
  try:
   for t in HOURS:
    snap=s.advance_to(t);snaps[str(t)]=snap
    if s.terminated:break
  except Exception as exc:
   error=type(exc).__name__;s.terminated=True;s.termination_reason='provider_or_runtime_error'
  result={'id':case,'calls':count[0],'compiled_environment_responses':[r.model_dump(mode='json') for r in s.persona.env_responses],
     'snapshots':snaps,'last_snapshot':s.snapshot(),'decisions':s.decisions,'bridge_audit':bridge.audit,
     'error_type':error,'complete_to_360':not s.terminated and abs(s.g.elapsed_min-360)<1e-7}
  (case_dir/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
  print(json.dumps({'finished':case,'simulated_minutes':s.g.elapsed_min,'stop_reason':s.termination_reason,'error':error},ensure_ascii=False),flush=True)
  return result
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(one,people))
 report={'people':len(results),'calls':sum(r['calls'] for r in results),'completed_6h':sum(r['complete_to_360'] for r in results),
    'cases':[{'id':r['id'],'calls':r['calls'],'last_minute':r['last_snapshot']['state']['elapsed_minutes'],
              'last_distance_m':r['last_snapshot']['state']['distance_m'],'stop_reason':r['last_snapshot']['termination_reason'],
              'complete_to_360':r['complete_to_360']} for r in results],
    'clinical_accuracy_measured':False,'elapsed_accounting_fixed':True,'simulation_persona_applied':True}
 (D/'final_loop_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(report,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
