"""Finish offline audits after the frozen expansion; never starts model calls."""
import argparse
from datetime import datetime, timezone
import subprocess
import sys
import time
from pathlib import Path
from experiments.mind_contract_ab_20261007 import run_v2 as r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',type=Path,required=True)
    p.add_argument('--ledger',type=Path,required=True)
    p.add_argument('--before',type=Path,required=True)
    p.add_argument('--reference-walks',type=Path,required=True)
    p.add_argument('--frozen-backend',type=Path,required=True)
    p.add_argument('--map',type=Path,required=True)
    p.add_argument('--wait-seconds',type=int,default=7200)
    a=p.parse_args();out=a.run_dir/'d12_dev24';started=time.monotonic()
    def status(state,**extra):
        r.write(a.run_dir/'followup_status.json',{'state':state,'updated_at':datetime.now(timezone.utc).isoformat(),
            'new_external_calls':0,'release_qualified':False,**extra})
        print(state,flush=True)
    status('waiting_for_complete_model_batch')
    while not (out/'scored.json').exists():
        if time.monotonic()-started>a.wait_seconds:
            status('model_wait_timeout');return
        time.sleep(10)
    if not r.read(out/'scored.json')['summary']['complete']:
        status('model_batch_incomplete_no_walk');return
    commands=[('offline_scoring',[sys.executable,'-m','experiments.mind_contract_ab_20261007.audit_compact24',
        '--out',str(out),'--before',str(a.before),'--ledger',str(a.ledger)]),
        ('offline_kintex_walk',[sys.executable,'-m','experiments.mind_contract_ab_20261007.walk_compact24',
        '--scored',str(out/'scored.json'),'--reference-walks',str(a.reference_walks),
        '--frozen-backend',str(a.frozen_backend),'--map',str(a.map),
        '--output',str(out/'engine_outputs_reused_v2.json')])]
    for phase,cmd in commands:
        status(phase)
        result=subprocess.run(cmd)
        if result.returncode:
            status('offline_stage_failed',phase=phase,returncode=result.returncode);return
    status('model_scoring_and_kintex_walk_complete')


if __name__=='__main__':main()
