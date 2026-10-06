"""Local-only incremental replay of newly completed responses; no model calls."""
import json,subprocess,sys,time
from pathlib import Path
D=Path(__file__).resolve().parent
seen=None;deadline=time.monotonic()+4*3600
while time.monotonic()<deadline:
 responses=tuple(sorted(str(p.relative_to(D)) for p in (D/'comparison').glob('*/*/*/result.json')))
 if responses!=seen:
  subprocess.run([sys.executable,str(D/'replay_comparison.py')],check=True)
  seen=responses
 slots=len(list((D/'spatial').glob('P*.json')))
 if slots==384:
  print('All384 planned spatial slots recorded; invalid policies not substituted.',flush=True);break
 if (D/'comparison/summary.json').exists():
  print(json.dumps({'comparison_finished':True,'spatial_slots':slots,'incomplete':slots!=384}),flush=True);break
 time.sleep(30)
else:raise SystemExit('Local replay watch elapsed; existing results preserved')
