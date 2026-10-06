"""Read and reconcile the existing remote usage ledger; no model submission."""
import importlib.util,json,subprocess
from pathlib import Path
D=Path(__file__).resolve().parent
remote="from pathlib import Path\np=Path('/tmp/MIND_diverse_comparison_20261006/usage_events.jsonl')\nprint(p.read_text() if p.exists() else '',end='')"
ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','damisoda@<REMOTE_HOST>','export PATH=/opt/homebrew/bin:$PATH; docker exec -i come-back-home-backend-1 python -']
r=subprocess.run(ssh,input=remote,text=True,capture_output=True,timeout=25)
if r.returncode:raise SystemExit('Read-only remote usage retrieval failed; no model retry performed')
remote_rows=[json.loads(line) for line in r.stdout.splitlines() if line.strip()]
assert all(row['run_id']==D.name for row in remote_rows)
(D/'remote_usage_events.jsonl').write_text(r.stdout)
ledger=D.parents[1]/'연구지원_사용기록/usage_events.jsonl'
local=[json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
local={r['event_id']:r for r in local if r.get('run_id')==D.name}
seen=set();duplicate=[];mismatch=[];missing=[]
core=lambda r:{k:v for k,v in r.items() if k not in ('recorded_at','schema_version')}
for row in remote_rows:
 eid=row['event_id']
 if eid in seen:duplicate.append(eid)
 seen.add(eid)
 if eid not in local:missing.append(row)
 elif core(row)!=core(local[eid]):mismatch.append(eid)
if mismatch or duplicate:raise SystemExit('Remote/local event mismatch; inspect durable ledgers before syncing')
if missing:
 spec=importlib.util.spec_from_file_location('usage_ledger',D.parents[1]/'개발/cbh-simulation-integration-20261004/backend/app/llm/usage_ledger.py')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 for row in missing:module.append_event(row,ledger_path=ledger)
out={'remote_events':len(remote_rows),'remote_unique_events':len(seen),'matching_existing_local_events':len(remote_rows)-len(missing),'synced_missing_events':len(missing),'mismatches':mismatch,'duplicates':duplicate,'new_model_calls':0}
(D/'ledger_reconciliation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(out,ensure_ascii=False))
