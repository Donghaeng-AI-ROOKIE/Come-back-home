"""Post-hoc local diagnostic, never a replacement for the fixed comparison.

Separates incomplete generation from tiny framing text around one intact JSON
object. Refuses truncated generations and multiple possible root objects.
Does not change model outputs, compiled policies, primary scores or live code.
"""
import json
from run_comparison import D,candidate,evaluator,score,write

def intact_single_object(content,personal):
 decoder=json.JSONDecoder();matches=[]
 for i,ch in enumerate(content):
  if ch!='{':continue
  try:value,length=decoder.raw_decode(content[i:])
  except json.JSONDecodeError:continue
  if not isinstance(value,dict) or set(value)!={'source_assessment','rules','non_action_note_ids'}:continue
  remainder=(content[:i]+content[i+length:]).strip()
  if len(remainder)>64 or any(c in remainder for c in '{}[]'):continue
  try:policy=candidate.compile_note(value,personal,'ALL',whole_person=True)
  except Exception:continue
  matches.append((value,policy,remainder))
 if len(matches)!=1:raise ValueError('not_exactly_one_intact_root_object')
 return matches[0]

def main():
 profiles={r['person_id']:r['personal'] for r in json.loads((D/'profiles.json').read_text())}
 scenes=json.loads((D/'scenes.json').read_text());rows=[];counts={}
 for path in sorted((D/'comparison').glob('*/*/*/result.json')):
  r=json.loads(path.read_text())
  if r['valid']:continue
  public_path=path.parent/'response.public.json';public=json.loads(public_path.read_text()) if public_path.exists() else {}
  result={k:r[k] for k in ('job','person_id','arm','rep')};result.update(recoverable_framing_only=False,finish_reason=public.get('finish_reason'))
  if public.get('finish_reason')=='stop':
   try:
    value,policy,remainder=intact_single_object(public.get('final_content') or '',profiles[r['person_id']])
    checks=[{'id':s['id'],'pass':score(evaluator.decide(policy,profiles[r['person_id']],s['scene']),s)} for s in scenes if s['person_id']==r['person_id']]
    result.update(recoverable_framing_only=True,removed_framing=remainder,posthoc_scene_checks=checks)
   except Exception as e:result['diagnostic_error']=type(e).__name__
  rows.append(result)
 for arm in ('on','off'):
  rs=[r for r in rows if r['arm']==arm]
  counts[arm]={'failed_outputs_observed':len(rs),'incomplete_outputs':sum(r['finish_reason']=='length' for r in rs),
    'intact_json_with_short_framing':sum(r['recoverable_framing_only'] for r in rs),
    'posthoc_matching_scenes':sum(s['pass'] for r in rs for s in r.get('posthoc_scene_checks',[]))}
 write(D/'completion_diagnostic.json',{'posthoc_only':True,'primary_results_changed':False,'model_calls':0,'counts':counts,'outputs':rows})
 print(json.dumps(counts,ensure_ascii=False))
if __name__=='__main__':main()
