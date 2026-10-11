"""Score only saved pilot outputs. No model/API calls; semantic review is separate."""
import json,sys,collections
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from contract import validate
FIELDS=('status','action','goal_operation','goal_label','avoid_feature')

def evaluate(dataset,results):
    cases={r['id']:r for r in map(json.loads,Path(dataset).read_text().splitlines())}
    summary={'evaluation_scope':'development only; four synthetic families, sixteen states',
             'independent_human_review':False,'clinical_accuracy_measured':False,'candidates':{}}
    output=[]
    for tag in ('base','lora_final'):
        p=Path(results)/(tag+'_development.jsonl')
        rows=[json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []
        if len({r['id'] for r in rows})!=len(rows):raise ValueError('duplicate case outputs')
        seen=set();scores=[]
        for r in rows:
            c=cases[r['id']];seen.add(r['id']);parsed=None;error=None
            try:
                parsed=json.loads(r['raw']);validate(parsed,c['context'])
            except (ValueError,TypeError) as exc:error=str(exc)
            match=error is None and all(parsed[k]==c['expected'][k] for k in FIELDS)
            item={'candidate':tag,'id':r['id'],'family':r['id'].split('-')[0],
                  'contract_pass':error is None,'action_tuple_match':match,'contract_error':error,
                  'expected':c['expected'],'actual':parsed,'raw':r['raw'],'usage':r.get('usage')}
            output.append(item);scores.append(item)
        families=collections.defaultdict(list)
        for r in scores:families[r['family']].append(r['action_tuple_match'])
        summary['candidates'][tag]={'expected_records':len(cases),'responses':len(rows),'missing_ids':sorted(set(cases)-seen),
              'contract_pass':sum(r['contract_pass'] for r in scores),'action_tuple_match':sum(r['action_tuple_match'] for r in scores),
              'all_states_correct_families':sum(len(v)==4 and all(v) for v in families.values()),
              'family_scores':{k:{'correct':sum(v),'states':len(v)} for k,v in families.items()},
              'failure_ids':[r['id'] for r in scores if not r['action_tuple_match']]}
    return summary,output

if __name__=='__main__':
    s,r=evaluate(sys.argv[1],sys.argv[2]);out=Path(sys.argv[2])
    (out/'evaluation_summary.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n')
    (out/'comparison.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in r))
    print(json.dumps(s,ensure_ascii=False,indent=2))
