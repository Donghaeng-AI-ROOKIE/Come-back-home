"""Reuse 48 saved policies; no fresh responses or new accuracy score."""
from pathlib import Path
from datetime import datetime
from collections import Counter
import sys,json,socket,hashlib,time
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--product-backend',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--map',type=Path,required=True)
args=parser.parse_args()
out=args.output
if out.exists():raise SystemExit('refuse overwrite')
out.mkdir(parents=True)
sys.path.insert(0,str(args.product_backend))
def blocked(*a,**kw):raise RuntimeError('offline rule replay forbids network')
socket.socket.connect=blocked;socket.create_connection=blocked
from app.phase2.person_walk import Population
from app.phase2.persistent_context_walk import PersistentContextPopulation
from app.llm.mind_policy import Policy
from app.geo.roadnet import verified_network
from experiments.mind_contract_ab_20261007 import engine_outputs_v2 as e

scored_path=e.HERE/'evidence_20261008/continuation/d12_expansion/d12_dev24/scored.json'
rows=json.loads(scored_path.read_text())['rows']
inputs={x['id']:x for x in map(json.loads,(e.DEV128/'dev128_inputs.jsonl').read_text().splitlines())}
site=next(x for x in json.loads((e.scoring.ROOT/'sites.json').read_text())['sites'] if x['site_id']=='C')
mapping=args.map
assert hashlib.sha256(mapping.read_bytes()).hexdigest()==e.MAP_SHA256
net=verified_network(mapping)
first=inputs[rows[0]['input_id']]['personal']
env=e.environment_network(net,site,first,snapshot=True)
scene={'start':datetime(2026,10,9,8),'horizon':240,'strategy':{'random_walk':.5,'landmark_seeking':.5},
       'behavior':[],'environment':[]}
result={'source_sha256':hashlib.sha256(scored_path.read_bytes()).hexdigest(),'map_sha256':e.MAP_SHA256,
        'scope':'stored rule compatibility; fixed synthetic profile, not 48 full onboarding cases or clinical accuracy',
        'walkers':16,'minutes':240,'seed':17,'new_external_calls':0,'rows':[]}
for row in rows:
    item={k:row[k] for k in ('input_id','root_id','family','rep')}
    if row['policy'] is None:
        item['unusable_output']=True
    else:
        pol=Policy.model_validate(row['policy'])
        for name,cls in [('legacy',Population),('persistent',PersistentContextPopulation)]:
            e.Population=cls
            last={}
            def observe(p,loc):last[p.seed]=p.mode
            started=time.monotonic()
            try:
                metrics=e.walk(env,site,inputs[row['input_id']]['personal'],pol,scene,walkers=16,seed=17,observer=observe)
                item[name]={'metrics':metrics,'final_modes':dict(Counter(last.values()))}
            except (ValueError,RuntimeError) as error:
                item[name]={'error_type':type(error).__name__,'error':str(error)[:250]}
            item[name]['seconds']=round(time.monotonic()-started,3)
    result['rows'].append(item)
    (out/'diverse_rules.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'done':len(result['rows']),'input':item['input_id'],'rep':item['rep'],
                      'error':any('error' in item.get(n,{}) for n in ('legacy','persistent'))}),flush=True)
