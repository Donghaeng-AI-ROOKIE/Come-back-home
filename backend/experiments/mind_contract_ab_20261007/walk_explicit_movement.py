"""Reveal an observed-walk omission hidden by an already-walking baseline.

An engine-isolation diagnostic with a declared synthetic all-staying prior,
not a calibrated population and not an actual onboarding replay. Original
three-scenario benchmark scores are not changed.
"""
import argparse
from datetime import datetime
from pathlib import Path
import socket

from app.llm.mind_policy import Policy
from experiments.mind_contract_ab_20261007 import run_v2 as r, engine_outputs_v2 as e


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--scored',type=Path,required=True)
    p.add_argument('--map',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise SystemExit('preserve completed diagnostic')
    saved=r.read(a.scored)
    if not saved['summary']['complete']:raise SystemExit('wait for complete candidate batch')
    inputs,_,refs,_=r._split(r.DEV128,'dev128');key='DEV_P21_original'
    personal=next(x['personal'] for x in inputs if x['id']==key)
    rows=[x for x in saved['rows'] if x['input_id']==key]
    if len(rows)!=2:raise ValueError('exactly two P21 repeats required')
    policies={'author_reference':Policy.model_validate(refs[key]),'empty_policy':Policy(rules=[],unrepresented=[])}
    policies.update({f"rep{x['rep']}":Policy.model_validate(x['policy']) if x['policy'] else None for x in rows})
    scenario={'start':datetime(2026,10,9,8),'horizon':30,'strategy':{'staying_put':1.0},
        'behavior':[('lost_awareness',False,0,10),('lost_awareness',True,10,20),('lost_awareness',False,20,30)],
        'environment':[]}
    site=next(x for x in r.read(e.scoring.ROOT/'sites.json')['sites'] if x['site_id']==e.SITE)
    if r.digest(a.map)!=e.MAP_SHA256:raise ValueError('wrong KINTEX cache')
    socket.socket.connect=e._offline
    net=e.verified_network(a.map);env=e.environment_network(net,site,personal)
    results={}
    for name,policy in policies.items():
        results[name]=e.walk(env,site,personal,policy,scenario,walkers=150,seed=17) if policy is not None else None
    r.write(a.output,{'scope':'P21 engine-isolation stress check, not an actual onboarding or prevalence estimate',
        'scored_sha256':r.digest(a.scored),'harness_sha256':r.digest(Path(__file__)),
        'map_sha256':r.digest(a.map),'strategy_assumption':{'staying_put':1.0},
        'walkers':150,'minutes':30,'lost_true_minutes':[10,20],'results':results,
        'original_benchmark_unchanged':True,'new_external_calls':0,'release_qualified':False})
    print({k:None if v is None else {'mean_path_km':v['mean_path_km'],'mean_wait':v['mean_wait']} for k,v in results.items()})


if __name__=='__main__':main()
