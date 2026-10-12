"""Structural/data-leakage audit, not a substitute for human semantic review."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from contract import validate, messages


def audit(root):
    manifest=json.loads((root/'manifest.json').read_text())
    families={};ids=set();inputs=set();counts=Counter();errors=[];chars=[]
    for name,entry in manifest['files'].items():
        blob=(root/name).read_bytes()
        if hashlib.sha256(blob).hexdigest()!=entry['sha256']:errors.append('hash '+name)
        rows=[json.loads(x) for x in blob.decode().splitlines() if x]
        if len(rows)!=entry['records']:errors.append('count '+name)
        for r in rows:
            try:
                validate(r['expected'],r['context'])
                if r['messages'][:-1]!=messages(r['context']):raise ValueError('input_builder_mismatch')
                if json.loads(r['messages'][-1]['content'])!=r['expected']:raise ValueError('target_mismatch')
                if r['id'] in ids:raise ValueError('duplicate_id')
                ids.add(r['id'])
                key=hashlib.sha256(r['messages'][1]['content'].encode()).hexdigest()
                if key in inputs:raise ValueError('duplicate_input')
                inputs.add(key)
                for kind in ('person_family','case_family','template_family'):
                    k=(kind,r[kind]);old=families.setdefault(k,r['split'])
                    if old!=r['split']:raise ValueError('family_leakage')
                if r['review']['real_guardian_data'] or r['review']['independent_human_review']:
                    raise ValueError('unexpected_real_data_or_human_review_claim')
                if r['context']['person']['type']!='dementia':raise ValueError('wrong_population')
                counts[r['split']]+=1
                chars.append(sum(len(x['content']) for x in r['messages']))
            except (ValueError,KeyError,TypeError) as e:errors.append(r.get('id','?')+':'+str(e))
    return {'records':sum(counts.values()),'split_counts':dict(counts),'errors':errors,
      'status':'PASS' if not errors else 'FAIL','checked':'hash, output fields, builder equality, IDs, declared family splits',
      'semantic_accuracy_measured':False,'token_lengths_measured':False,
      'characters_min_max':[min(chars),max(chars)],'clinical_review':False,
      'remaining':['manual semantic review','cross-family near-duplicate review','actual tokenizer truncation check',
                   'source-held-out evaluation','real saved onboarding pipeline inputs','KINTEX closed-loop model evaluation']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');a=p.parse_args();r=audit(Path(a.root));print(json.dumps(r,ensure_ascii=False,indent=2))
    raise SystemExit(bool(r['errors']))
