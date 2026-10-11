import json,hashlib
from pathlib import Path
from contract import messages,validate

def audit(root):
 root=Path(root);m=json.loads((root/'manifest.json').read_text());errors=[];families={}
 for name,entry in m['files'].items():
  blob=(root/name).read_bytes();rows=[json.loads(x) for x in blob.decode().splitlines()]
  if hashlib.sha256(blob).hexdigest()!=entry['sha256']:errors.append(name+':hash')
  if len(rows)!=entry['records']:errors.append(name+':count')
  families[name]={r['case_family'] for r in rows}
  for r in rows:
   try:
    validate(r['expected'],r['context'])
    assert r['messages'][:-1]==messages(r['context'])
    assert json.loads(r['messages'][-1]['content'])==r['expected']
    assert not any(k in r['context'] for k in ('expected','rubric','review'))
    assert r['context']['person']['prepared_person_interpretation']['provenance']=='synthetic_authored_not_K_generated'
   except Exception as e:errors.append(r['id']+':'+type(e).__name__)
 if families['train.jsonl'] & families['development.jsonl']:errors.append('family leakage')
 return {'errors':errors,'counts':{n:e['records'] for n,e in m['files'].items()}}

if __name__=='__main__':
 import sys
 result=audit(Path(__file__).parent/'dataset');print(json.dumps(result));sys.exit(bool(result['errors']))
