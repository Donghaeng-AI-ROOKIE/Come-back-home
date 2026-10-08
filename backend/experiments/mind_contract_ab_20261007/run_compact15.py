"""D15 on eight declared diagnostic inputs; includes failures and controls."""
import argparse
from pathlib import Path
from experiments.mind_contract_ab_20261007 import run_v2 as r, resume_concise8 as guarded

IDS=('DEV_P02_original','DEV_P16_preserve','DEV_P21_original','DEV_P23_original',
     'DEV_P25_original','DEV_P26_hard','DEV_P29_original','DEV_P31_original')


def selected_dataset():
    inputs,scenes,refs,files=r._split(r.DEV128,'dev128')
    by_id={x['id']:x for x in inputs}
    return [by_id[i] for i in IDS],[s for s in scenes if s['input_id'] in IDS],{i:refs[i] for i in IDS},files


def register():
    r.CANDIDATES['d15']=('contract_d15','compile_d15','PLAN_d15.md')
    for f in (__file__,guarded.__file__):
        path=Path(f).resolve()
        if path not in r.COMMON:r.COMMON.append(path)
    old_dataset=r.dataset
    r.dataset=lambda stage:selected_dataset() if stage=='d15_dev8' else old_dataset(stage)
    old_execute,old_score,old_summary=r.execute,r.score,r.summarize
    r.execute=lambda *args:guarded.execute_guarded(old_execute,*args)
    r.score=lambda *args:guarded.score_with_unavailable(old_score,*args)
    def summarize(module,rows):
        s=old_summary(module,rows)
        s['trait_accounting']={'available':False,'unmeasured_responses':len(rows),
            'note':'source-to-action distinctions are not sentence-level coverage measurement'}
        return s
    r.summarize=summarize


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-dir',required=True)
    p.add_argument('--ledger');p.add_argument('--execute',action='store_true');a=p.parse_args()
    register();argv=['--stage','d15_dev8','--run-dir',a.run_dir]
    if a.ledger:argv+=['--ledger',a.ledger]
    if a.execute:argv+=['--execute']
    r.main(argv)


if __name__=='__main__':main()
