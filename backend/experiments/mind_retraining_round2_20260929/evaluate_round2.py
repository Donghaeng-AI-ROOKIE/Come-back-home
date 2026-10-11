"""Offline scores only; explanation correctness requires an explicit review."""
import json,re
from pathlib import Path
from collections import defaultdict
from contract import validate
ROOT=Path(__file__).resolve().parent
FIELDS=('status','action','goal_operation','goal_label','avoid_feature')

def evaluate():
    rows=[json.loads(x) for x in (ROOT/'dataset_augmented/development.jsonl').read_text().splitlines()]
    byid={r['id']:r for r in rows};summary={};comparisons=[]
    for arm in ['original72','augmented120']:
      for epoch in [2,4,6]:
        p=ROOT/'results'/'runs'/arm/('epoch_'+str(epoch)+'_development.jsonl')
        if not p.exists():continue
        outputs=[json.loads(x) for x in p.read_text().splitlines()];counts=defaultdict(int);families=defaultdict(list)
        for o in outputs:
            r=byid[o['id']];raw=o['raw'];strict=False;v=None
            try:v=json.loads(raw);validate(v,r['context']);strict=True
            except (ValueError,TypeError):pass
            match=False
            try:
                m=re.match(r'^\s*```(?:json)?\s*\n(.*?)\n```',raw,re.S)
                readable=json.loads(m.group(1) if m else raw)
                match=all(readable.get(k)==r['expected'][k] for k in FIELDS)
            except (ValueError,TypeError,AttributeError):readable=None
            counts['responses']+=1;counts['raw_contract_pass']+=strict
            counts['readable_action_match']+=match
            counts['strict_action_match']+=strict and match
            families[r['case_family']].append(match and strict)
            comparisons.append({'arm':arm,'epoch':epoch,'id':o['id'],'raw':raw,'decoded':readable,
                'raw_contract_pass':strict,'action_match':match,'expected':r['expected'],'context':r['context'],
                'explanation_review':'pending','usage':o['usage']})
        counts['families_all_four_correct']=sum(len(v)==4 and all(v) for v in families.values())
        summary[arm+'_epoch'+str(epoch)]=dict(counts)
    result={'scores':summary,'not_clinical_accuracy':True,'independent_human_review':False,'explanation_review_required':True}
    (ROOT/'results/evaluation_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'results/comparison.jsonl').write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in comparisons)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':evaluate()
