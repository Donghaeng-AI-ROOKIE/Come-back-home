"""One metered K-EXAONE request through the deployed container, never resent.

Same bridge as MIND_diverse_comparison_20261006: the worker is detached inside
the container and polled from its durable file, so an SSH interruption cannot
resubmit the request. The SSH target comes from CBH_K_BRIDGE_SSH and is not
stored in the repository. Every start/finish/incomplete event goes to the
shared ledger with run_id; the ledger lock enforces the approved call cap.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone

from app.llm import usage_ledger

MODEL = 'depmkuykpfon9lg'
CONTAINER = 'come-back-home-backend-1'

REMOTE = r'''
import os,json,time,uuid
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
pack=json.loads(PACK)
D=Path('/tmp/'+pack['start']['run_id']);D.mkdir(exist_ok=True)
def event(x):
 with (D/'usage_events.jsonl').open('a') as f:f.write(json.dumps(x,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
start=pack['start'];event(start)
key=os.environ['KEXAONE_API_KEY'];base=os.environ['KEXAONE_BASE_URL'].rstrip('/');model=os.environ['KEXAONE_MODEL']
assert pack['body']['model']==model
t=time.monotonic();response=None
end={**{k:v for k,v in start.items() if k not in ['event_id','event_type','started_at']},'event_id':str(uuid.uuid4()),'event_type':'api_attempt_finished','usage':None,'actual_cost':None,'estimated_cost':None,'support_round':None,'gpu_billed_hours':None}
try:
 req=Request(base+'/chat/completions',data=json.dumps(pack['body'],ensure_ascii=False).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
 with urlopen(req,timeout=420) as r:response=json.loads(r.read());end['http_status']=r.status
 end.update(outcome='response_received',usage=response.get('usage'),provider_response_id=response.get('id'),finish_reason=response.get('choices',[{}])[0].get('finish_reason'))
except Exception as e:
 end.update(outcome='error',error_type=type(e).__name__,http_status=e.code if isinstance(e,HTTPError) else None)
end['duration_seconds']=time.monotonic()-t;event(end)
(D/(pack['id']+'.json')).write_text(json.dumps({'response':response,'end':end},ensure_ascii=False))
'''

LAUNCH = """import os,sys,json,subprocess
from pathlib import Path
D=Path('/tmp/'+RUN);D.mkdir(exist_ok=True)
job=JOB
fd=os.open(str(D/(job+'.launch')),os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
script=D/(job+'.worker.py');script.write_text(WORKER)
with (D/(job+'.stdout')).open('w') as out,(D/(job+'.stderr')).open('w') as err:
 subprocess.Popen([sys.executable,str(script)],stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True,close_fds=True)
print(json.dumps({'submitted':job}),flush=True)
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _ssh():
    target = os.environ.get('CBH_K_BRIDGE_SSH')
    if not target:
        raise RuntimeError('CBH_K_BRIDGE_SSH is not set; no request submitted')
    return ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', target,
            f'export PATH=/opt/homebrew/bin:$PATH; docker exec -i {CONTAINER} python -']


def invoke(body, job, *, run_id, role, ledger_path, max_started):
    assert body['model'] == MODEL
    start = {'event_type': 'api_attempt_started', 'attempt_id': str(uuid.uuid4()),
             'logical_request_id': job, 'attempt': 1, 'run_id': run_id, 'role': role,
             'provider': 'K_EXAONE_API', 'model_requested': MODEL, 'started_at': _now(),
             'actual_cost': None, 'support_round': None, 'billing_basis': 'API_rate_unconfirmed'}
    start = usage_ledger.append_event(start, ledger_path, max_started=max_started)
    pack = {'id': job, 'body': body, 'start': start}
    worker = REMOTE.replace('PACK', repr(json.dumps(pack, ensure_ascii=False)))
    launch = LAUNCH.replace('RUN', repr(run_id)).replace('JOB', repr(job)).replace('WORKER', repr(worker))
    incomplete = {**{k: v for k, v in start.items() if k not in ('event_id', 'recorded_at', 'schema_version')},
                  'event_type': 'api_transport_incomplete', 'remote_event_recovery_required': True}
    try:
        result = subprocess.run(_ssh(), input=launch, text=True, capture_output=True, timeout=20, check=False)
        if result.returncode or json.loads(result.stdout)['submitted'] != job:
            usage_ledger.append_event({**incomplete, 'error_type': 'SSHTransportError'}, ledger_path)
            raise RuntimeError('K_bridge_transport_failure')
        read = ('from pathlib import Path\np=Path(' + repr(f'/tmp/{run_id}/{job}.json')
                + ")\nprint(p.read_text() if p.exists() else '{\"pending\":true}')")
        deadline = time.monotonic() + 450
        while time.monotonic() < deadline:
            time.sleep(3)
            try:
                status = subprocess.run(_ssh(), input=read, text=True, capture_output=True, timeout=15, check=False)
                received = json.loads(status.stdout) if not status.returncode else {}
            except (subprocess.TimeoutExpired, json.JSONDecodeError):
                continue
            if 'end' in received:
                usage_ledger.append_event({k: v for k, v in received['end'].items()
                                           if k not in ('event_id', 'recorded_at', 'schema_version')},
                                          ledger_path)
                if received['response'] is None:
                    raise RuntimeError('K_API_' + str(received['end'].get('error_type')))
                return received['response']
        raise subprocess.TimeoutExpired('remote completion polling', 450)
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        usage_ledger.append_event({**incomplete, 'error_type': type(error).__name__}, ledger_path)
        raise


def public(response):
    """Final answer, finish reason and usage only; hidden reasoning is not kept."""
    choice = response['choices'][0]
    content = choice['message'].get('content') or ''
    if '</think>' in content:
        content = content.rsplit('</think>', 1)[-1].strip()
    if '<think>' in content:
        content = '[no separable final output]'
    return {'final_content': content, 'finish_reason': choice.get('finish_reason'),
            'usage': response.get('usage')}
