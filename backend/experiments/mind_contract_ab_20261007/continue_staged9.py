"""After D8 completes, run registered D9 then offline KINTEX verification."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
from datetime import datetime,timezone
from experiments.mind_contract_ab_20261007 import run_v2 as r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--ledger',type=Path,required=True)
    p.add_argument('--reference-walks',type=Path,required=True);p.add_argument('--frozen-backend',type=Path,required=True)
    p.add_argument('--map',type=Path,required=True)
    a=p.parse_args();out=a.root/'d9_staged';out.mkdir(exist_ok=True)
    def mark(state,**extra):
        r.write(out/'continuation_status.json',{'state':state,'updated_at':datetime.now(timezone.utc).isoformat(),
           'runner_sha256':r.digest(Path(__file__)),'automatic_paid_retries':False,**extra})
    if not os.environ.get('CBH_K_BRIDGE_SSH'):raise SystemExit('bridge missing')
    mark('waiting_for_registered_d8_comparison')
    deadline=time.monotonic()+5400
    while True:
        status=r.read(a.root/'d8_concise/continuation_status.json') or {}
        if status.get('state')=='comparison_complete_not_release_verdict':break
        if status.get('state')=='needs_diagnosis' or time.monotonic()>deadline:
            mark('needs_diagnosis',predecessor=status);raise SystemExit(2)
        time.sleep(5)
    def run(mod,args):
        mark('running',module=mod)
        with (out/(mod+'.log')).open('a') as f:
            result=subprocess.run([sys.executable,'-m','experiments.mind_contract_ab_20261007.'+mod,*map(str,args)],cwd=r.BACKEND,stdout=f,stderr=subprocess.STDOUT)
        if result.returncode:
            mark('needs_diagnosis',module=mod,exit_code=result.returncode);raise SystemExit(result.returncode)
    run('run_staged9',['--out',out/'d9_dev8','--ledger',a.ledger,'--execute'])
    scored=r.read(out/'d9_dev8/scored.json')
    if not scored['summary']['complete']:
        mark('needs_diagnosis',reason='D9 incomplete');raise SystemExit(2)
    run('walk_repair8',['--scored',out/'d9_dev8/scored.json','--reference-walks',a.reference_walks,
        '--frozen-backend',a.frozen_backend,'--map',a.map,'--output',out/'d9_dev8/engine_outputs_reused_v2.json'])
    mark('comparison_complete_not_release_verdict')


if __name__=='__main__':main()
