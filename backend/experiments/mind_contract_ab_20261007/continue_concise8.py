"""Execute the already frozen two-arm D8 comparison after D7 finishes.

No adaptive paid retry, source editing, prompt expansion or model selection.
Each arm has 16 first calls and at most 16 received-response corrections.
Audit and KINTEX walks then run without external calls. Durable status and
separate logs remain available if this controlling chat is interrupted.
"""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import time

from experiments.mind_contract_ab_20261007 import run_v2


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--ledger',type=Path,required=True)
    p.add_argument('--reference-walks',type=Path,required=True)
    p.add_argument('--frozen-backend',type=Path,required=True)
    p.add_argument('--map',type=Path,required=True)
    a=p.parse_args()
    out=a.root/'d8_concise';status=out/'continuation_status.json'
    def mark(state,**values):
        run_v2.write(status,{'state':state,'updated_at':datetime.now(timezone.utc).isoformat(),
            'automatic_paid_retries':False,'runner_sha256':run_v2.digest(Path(__file__)),**values})
    def run(module,args,name):
        with (out/(name+'.log')).open('a') as log:
            done=subprocess.run([sys.executable,'-m','experiments.mind_contract_ab_20261007.'+module,*map(str,args)],
                cwd=run_v2.BACKEND,stdout=log,stderr=subprocess.STDOUT)
        if done.returncode:
            mark('needs_diagnosis',step=name,exit_code=done.returncode)
            raise SystemExit(done.returncode)
    if not os.environ.get('CBH_K_BRIDGE_SSH'):
        raise SystemExit('bridge not set; no calls')
    mark('waiting_for_d7_completion')
    predecessor=a.root/'d7_source_review/d7_dev8/scored.json'
    deadline=time.monotonic()+1800
    while not predecessor.exists():
        if time.monotonic()>deadline:
            mark('needs_diagnosis',reason='D7 completion not recorded; no D8 calls sent')
            raise SystemExit(2)
        time.sleep(5)
    if not run_v2.read(predecessor)['summary']['complete']:
        mark('needs_diagnosis',reason='D7 incomplete; no D8 calls sent')
        raise SystemExit(2)
    for candidate in ('d8','d8plain'):
        stage=candidate+'_dev8';folder=out/stage
        mark('model_calls',stage=stage)
        run('run_concise8',['--candidate',candidate,'--run-dir',out,'--ledger',a.ledger,'--execute'],stage)
        mark('offline_audit',stage=stage)
        run('audit_repair8',['--out',folder,'--stage',stage,'--ledger',a.ledger,
                            '--before',a.root/'d6_prepared/d6_dev8/scored.json'],stage+'_audit')
        walked=folder/'engine_outputs_reused_v2.json'
        if not walked.exists():
            mark('offline_walk',stage=stage)
            run('walk_repair8',['--scored',folder/'scored.json','--reference-walks',a.reference_walks,
                '--frozen-backend',a.frozen_backend,'--map',a.map,'--output',walked],stage+'_walk')
    mark('comparison_complete_not_release_verdict')


if __name__=='__main__':
    main()
