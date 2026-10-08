"""Rescore saved compact outputs with explicit operator aliases; no model calls."""
import argparse,json
from pathlib import Path
from experiments.mind_contract_ab_20261007 import run_v2 as r, run_repair8, compact_syntax as alias, audit_repair8, condition_probe


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--candidate',choices=('d12','d13','d14'),required=True)
    a=p.parse_args()
    if a.output.exists(): raise SystemExit('preserve prior analysis')
    before=r.read(a.source/'scored.json')
    if not before or not before['summary']['complete']:raise SystemExit('original batch incomplete')
    name=a.candidate;stage=name+'_dev8'
    r.CANDIDATES[name]=('contract_'+name,'compile_'+name,'PLAN_'+name+'.md')
    old_dataset=r.dataset;r.dataset=lambda s:run_repair8.repair_dataset() if s==stage else old_dataset(s)
    old_load=r.load_candidate
    def load(c):
        module,compiler,plan=old_load(c)
        return module,(alias.compile_aliases if c==name else compiler),plan
    r.load_candidate=load
    rows,summary,gate=r.score(stage,a.source)
    summary['trait_accounting']={'available':False,'unmeasured_responses':len(rows)}
    after={'rows':rows,'summary':summary,'gate':gate}
    changes=[]
    for row in rows:
        folder=a.source/row['input_id']/str(row['rep'])
        for attempt in ('first','fix'):
            public=r.read(folder/attempt/'response.public.json')
            if not public: continue
            status,value=r.completion.classify(public)
            if status!='complete_json':continue
            try: _,edited=alias.prepare(value)
            except Exception as error:
                changes.append({'input_id':row['input_id'],'rep':row['rep'],'attempt':attempt,'normalization_error':type(error).__name__});continue
            if edited:changes.append({'input_id':row['input_id'],'rep':row['rep'],'attempt':attempt,'lexical_changes':edited})
    paired=audit_repair8.paired(before,after)
    before_by={(x['input_id'],x['rep']):x for x in before['rows']}
    valid_unchanged=all(before_by[x['input_id'],x['rep']]['policy']==x['policy'] for x in rows
                      if before_by[x['input_id'],x['rep']]['policy'] is not None)
    if not valid_unchanged:raise ValueError('operator normalization changed an already accepted policy')
    _,_,refs,_=run_repair8.repair_dataset()
    r.write(a.output/'scored.json',after)
    r.write(a.output/'condition_probes.json',condition_probe.audit(after,refs))
    r.write(a.output/'audit.json',{'source_score_sha256':r.digest(a.source/'scored.json'),
        'compiler_sha256':r.digest(Path(alias.__file__)),'new_external_calls':0,
        'raw_responses_unchanged':True,'previously_valid_policies_unchanged':True,
        'lexical_changes':changes,'paired':paired,'release_qualified':False,
        'meaning':'output syntax compatibility only; not a change in K interpretation quality'})
    print(json.dumps({'before':before['summary']['passed'],'after':summary['passed'],
        'valid_before':before['summary']['final_valid'],'valid_after':summary['final_valid'],
        'fixed':paired['fixed_scenes'],'regressed':paired['regressed_scenes'],'previous_valid_unchanged':valid_unchanged}))


if __name__=='__main__':main()
