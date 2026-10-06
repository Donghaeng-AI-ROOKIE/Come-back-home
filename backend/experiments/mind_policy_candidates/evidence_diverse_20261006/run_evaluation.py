"""Select a prospectively passing arm, freeze it, then use the carried 64 calls.

Default dry run. Refuses evaluation if neither comparison arm passes or if any
previous owner has used the carried allowance. No prompt tuning in evaluation.
"""
import argparse, fcntl, json, random, threading, unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from run_comparison import D, candidate, evaluator, initial_behavior, sources, digest, write, events
import transport

INPUT=D.parent/'MIND_condition_contract_20261006/evaluation_inputs.json'
INPUT_SHA='7b941f695f0513e1ee4578121d8fe5f87ca8ca4106fe6e77f37edf58523f8d39'

def select(summary):
 eligible=[a for a,g in summary['gates'].items() if g['pass_gate']]
 if not eligible:return None
 ends=[r for r in events() if r['event_type']=='api_attempt_finished' and r['role']=='mind_state_alignment_comparison']
 def rank(arm):
  g=summary['gates'][arm]
  used=[r for r in ends if '_'+arm+'_' in r['logical_request_id']]
  tokens=[(r.get('usage') or {}).get('completion_tokens') for r in used]
  durations=[r.get('duration_seconds') for r in used]
  cost=-sum(tokens) if all(v is not None for v in tokens) else float('-inf')
  latency=-sum(durations) if all(v is not None for v in durations) else float('-inf')
  return (min(v['passed'] for v in g['families'].values()),g['passed'],g['valid_outputs'],cost,latency)
 return max(eligible,key=rank)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
 path=D/'comparison/summary.json'
 if not path.exists():raise SystemExit('Comparison incomplete; no evaluation call')
 summary=json.loads(path.read_text());arm=select(summary)
 if arm is None:
  write(D/'selection.json',{'selected_arm':None,'reason':'Neither arm passed all prospective comparison criteria','comparison_gates':summary['gates'],'evaluation_calls':0})
  print('No passing arm. Separate evaluation not started.');return
 manifest=json.loads((D/'manifest.json').read_text())
 normalize=lambda d:{unicodedata.normalize('NFC',str(Path(k).resolve())):v for k,v in d.items()}
 assert normalize(sources())==normalize(manifest['source_sha256'])
 assert digest(INPUT)==INPUT_SHA
 rows=json.loads(INPUT.read_text());people={}
 for r in rows:
  if r['person_id'] in people:assert people[r['person_id']]==r['personal']
  people[r['person_id']]=r['personal']
 assert len(people)==32 and len(rows)==64
 jobs=[]
 for pid,p in people.items():
  for rep in (1,2):
   jobs.append({'job':f'eval_{arm}_{pid}_{rep}','person_id':pid,'rep':rep,'personal':p,'body':candidate.request(p,'ALL',transport.model,thinking=arm=='on',whole_person=True)})
 random.Random(20261007).shuffle(jobs)
 assert len(jobs)==64 and all(len(json.dumps(j['body'],ensure_ascii=False).encode())<=40000 for j in jobs)
 selected={'selected_arm':arm,'selection_order':'minimum family score, overall behavior score, completion rate, recorded generation tokens, duration',
  'comparison_gates':summary['gates'],'comparison_summary_sha256':digest(path),'source_sha256':sources(),
  'evaluation_input_sha256':INPUT_SHA,'runner_sha256':digest(Path(__file__)),'transport_sha256':digest(D/'transport.py'),
  'calls':64,'scene_decisions':128,'required':116,
  'evaluation_scoring':'Preserved prior action agreement criterion; strict status agreement separately reported. Neither is clinical accuracy.'}
 print(json.dumps({'selected_arm':arm,'calls':64,'decisions':128,'dry_run':not args.execute}),flush=True)
 if not args.execute:return
 approval=json.loads((D/'authorization.json').read_text())
 assert approval['status']=='approved' and approval['human_approval'] and approval['total_max']==192
 with (D/'runner.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  all_events=[json.loads(s) for s in (D.parents[1]/'연구지원_사용기록/usage_events.jsonl').read_text().splitlines() if s.strip()]
  owners={'MIND_practical_gate_20261006','MIND_condition_contract_20261006',D.name}
  old_eval=[e for e in all_events if e.get('run_id') in owners and e.get('role')=='mind_state_alignment_evaluation' and e.get('event_type')=='api_attempt_started']
  if old_eval:raise SystemExit('Evaluation already started: recover existing results, never rerun automatically')
  if sum(e['event_type']=='api_attempt_started' for e in events())!=128:raise SystemExit('Complete exactly128 comparison submissions first')
  out=D/'evaluation';out.mkdir(exist_ok=False);write(D/'selection.json',selected)
  write(out/'manifest.json',{**selected,'job_order':[j['job'] for j in jobs]})
  transport.args.stage='evaluation';stop=threading.Event()
  def one(j):
   folder=out/j['person_id']/str(j['rep']);r={k:j[k] for k in ('job','person_id','rep')};r.update(valid=False,output=None,error_type=None,submitted=False)
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
    r.update(error_type=type(e).__name__,error_message=str(e)[:300])
    if type(e).__name__=='TimeoutExpired' or str(e)=='K_bridge_transport_failure' or str(e).startswith('K_API_'):stop.set()
   write(folder/'result.json',r);print({k:r[k] for k in ('job','valid','error_type')},flush=True);return r
  with ThreadPoolExecutor(max_workers=2) as pool:outputs=list(pool.map(one,jobs))
  results=[]
  for r in outputs:
   p=people[r['person_id']];policy=candidate.compile_note(r['output'],p,'ALL',whole_person=True) if r['valid'] else None
   for row in [x for x in rows if x['person_id']==r['person_id']]:
    scored={'id':row['id'],'person_id':r['person_id'],'rep':r['rep'],'family':row['family'],'label':','.join(row['expected_commands']) or 'unknown','pass':False,'strict_pass':False,'decision':None,'error_type':r['error_type']}
    if policy is not None:
     try:
      d=evaluator.decide(policy,p,row['scene']);scored['decision']=d
      scored['pass']=evaluator.score(d,row['expected_commands'])
      scored['strict_pass']=d['status'] in row['expected_statuses'] and set(d['commands'])==set(row['expected_commands'])
     except Exception as e:scored['error_type']=type(e).__name__
    results.append(scored)
  write(out/'summary.json',{'model_outputs':outputs,'results':results,'gate':evaluator.gate(results,[r['id'] for r in rows],[1,2]),'strict_passed':sum(r['strict_pass'] for r in results),'total':128,'clinical_patients':0,'independent_human_raters':0})
  print('Evaluation complete; report action agreement and strict status agreement separately.',flush=True)
if __name__=='__main__':main()
