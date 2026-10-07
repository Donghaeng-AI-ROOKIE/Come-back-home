"""Frozen two-stage D9 development comparison, both original and interpreted source retained."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
from pathlib import Path
import threading
from experiments.mind_contract_ab_20261007 import (
    run_v2 as r, run_repair8, contract_d9 as d9, completion, condition_probe, audit_repair8)

STAGE='d9_dev8'
RUN='MIND_contract_ab_20261007_'+STAGE


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--ledger',type=Path,required=True)
    p.add_argument('--execute',action='store_true')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    r.CANDIDATES['d9']=('contract_d9','compile_d9','PLAN_d9.md')
    inputs,scenes,refs,files=run_repair8.repair_dataset()
    jobs=[{'job':f'{STAGE}_{x["id"]}_{rep}','input':x,'rep':rep,
           'body':d9.interpretation_request(x['personal'],r.transport.MODEL)} for x in inputs for rep in (1,2)]
    sources=r.sources('d9')+[Path(__file__).resolve(),Path(run_repair8.__file__).resolve()]
    manifest={'stage':STAGE,'version':d9.VERSION,'source_sha256':{str(x.relative_to(r.BACKEND)):r.digest(x) for x in sources},
        'data_sha256':{str(x):r.digest(x) for x in files},'jobs':jobs,'max_calls':48,
        'automatic_retries':False,'standing_authorization':'2026-10-08 user continue without budget reapproval',
        'actual_cost':None,'support_round':None}
    path=a.out/'manifest.json'
    if path.exists() and r.read(path)!=manifest:raise SystemExit('frozen manifest differs')
    r.write(path,manifest)
    if not a.execute:return
    if not r.os.environ.get('CBH_K_BRIDGE_SSH'):raise SystemExit('bridge not set; no calls')
    lock=(a.out/'runner.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    for src in sources:
        dest=a.out/'source_snapshot'/src.relative_to(r.BACKEND);dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists() and dest.read_bytes()!=src.read_bytes():raise SystemExit('source snapshot differs')
        dest.write_bytes(src.read_bytes())
    stopped=threading.Event()
    def call(body,job,folder):
        if (folder/'result.json').exists():return r.read(folder/'response.public.json')
        if (folder/'request.json').exists():raise RuntimeError('unresolved request; recover before resending')
        r.write(folder/'request.json',body)
        try:
            response=r.transport.invoke(body,job,run_id=RUN,role='mind_staged_source_interpretation',ledger_path=a.ledger,max_started=48)
            public=r.transport.public(response);r.write(folder/'response.public.json',public)
            r.write(folder/'result.json',{'submitted':True,'response_saved':True});return public
        except Exception as e:
            r.write(folder/'result.json',{'submitted':True,'response_saved':False,'error_type':type(e).__name__})
            stopped.set();raise
    def one(j):
        if stopped.is_set():return
        f=a.out/j['input']['id']/str(j['rep'])
        if (f/'pipeline_terminal.json').exists():return
        public=call(j['body'],j['job']+'_interpret',f/'interpret')
        if public is None:
            r.write(f/'pipeline_terminal.json',{'stage':'interpret','error':'no_response'});return
        status,value=completion.classify(public)
        try:
            if status!='complete_json':raise ValueError(status)
            d9.validate_cards(value,j['input']['personal'])
            body=d9.request_with_cards(j['input']['personal'],value,r.transport.MODEL)
        except ValueError as e:
            r.write(f/'pipeline_terminal.json',{'stage':'interpret','error':str(e)[:800]});return
        work=dict(j,body=body)
        try:
            if r.execute(STAGE,a.out,[work],d9,d9.compile_d9,a.ledger,48):stopped.set()
        except ValueError as e:
            if str(e)!='input byte cap; original evidence is not truncated':raise
            r.write(f/'pipeline_terminal.json',{'stage':'correction','error':str(e)})
        print(json.dumps({'input_id':j['input']['id'],'rep':j['rep'],'completed':True}),flush=True)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(one,jobs))
    finally:
        rows=[]
        for j in jobs:
            x=j['input'];f=a.out/x['id']/str(j['rep'])
            key=x['root_id'] if x.get('form')=='original' else x['id']
            row=r.score_response(d9,d9.compile_d9,f,x,[s for s in scenes if s['input_id']==x['id']],refs,key);row['rep']=j['rep']
            terminal=r.read(f/'pipeline_terminal.json')
            if terminal:
                if row['policy'] is not None:raise RuntimeError('terminal failure has policy')
                row.update(complete=True,pipeline_failure=terminal)
            rows.append(row)
        summary=r.summarize(d9,rows)
        r.write(a.out/'scored.json',{'rows':rows,'summary':summary,'manifest_sha256':r.digest(path),'gate':r.gate(STAGE,summary),'source_interpretation_is_not_human_review':True})
        r.write(a.out/'usage_summary.json',audit_repair8.usage(a.ledger,STAGE))
        if summary['complete']:r.write(a.out/'condition_probes.json',condition_probe.audit({'rows':rows},refs))
        print(json.dumps({'summary':{k:v for k,v in summary.items() if k!='by_input'}},ensure_ascii=False),flush=True)
    if stopped.is_set():raise SystemExit('transport failure; diagnose before continuation')


if __name__=='__main__':main()
