"""Offline actual-app synthetic persona -> initial compilation -> KINTEX walking.

Uses the complete captured Persona, never replaces it with a test persona.
No model call. Profile numeric baseline is explicit: production SAR numeric
inference and onboarding axes scoring are NOT covered. Facilities and timed
observations are synthetic; roads are the existing verified KINTEX cache.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import socket
import statistics
import sys
from zoneinfo import ZoneInfo


def read(p): return json.loads(Path(p).read_text())
def save(p, value):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n")
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def scenarios():
    common = [('rain_observed',False,0,360),('pain_observed',False,0,360),
              ('dark_observed',False,0,360)]
    return {
        'rest_cycle': {'description':'기다림 조건 없음. 6분 또는 280m 뒤 5분 휴식과 재출발 확인',
            'start':datetime(2026,10,9,8),'start_place':None,'horizon':360,
            'behavior':common+[('lost_awareness',False,0,360),('family_present',True,0,360)],
            'environment':[('market',0,360,False,False)]},
        'wait_release': {'description':'40분에 길 잃음 인지·가족 부재, 90분에 가족 귀환; 210~230분 다시 기다림 조건',
            'start':datetime(2026,10,9,8),'start_place':None,'horizon':360,
            'behavior':common+[('lost_awareness',False,0,40),('lost_awareness',True,40,150),
                ('lost_awareness',False,150,210),('lost_awareness',True,210,260),('lost_awareness',False,260,360),
                ('family_present',False,0,90),('family_present',True,90,210),
                ('family_present',False,210,230),('family_present',True,230,360)],
            'environment':[('market',0,360,False,False)]},
        'place_noise': {'description':'해든상가에서 출발. 소음 0~20분·80~130분만 관측, 다른 시간은 조용함',
            'start':datetime(2026,10,9,8),'start_place':'해든상가','horizon':360,
            'behavior':common+[('lost_awareness',False,0,360),('family_present',True,0,360)],
            'environment':[('market',0,20,True,False),('market',20,80,False,False),
                ('market',80,130,True,False),('market',130,360,False,False)]}}


def metrics(pop, out, track):
    parts=pop.particles
    wait_rules={r.id for r in pop.policy.rules if r.action=='wait'}
    return {'mass':sum(out['cells'].values())+out['quality']['unresolved_mass'],
        'mean_path_km':statistics.mean(p.distance for p in parts)/1000,
        'mean_wait_minutes':statistics.mean(p.waiting for p in parts),
        'mean_personal_wait_minutes':statistics.mean(sum(p.rule_minutes.get(r,0) for r in wait_rules) for p in parts),
        'mean_personal_rest_minutes':statistics.mean(p.rest-p.population_rest_minutes for p in parts),
        'mean_population_rest_minutes':statistics.mean(p.population_rest_minutes for p in parts),
        'avoid_walkers':sum(bool(x['avoid_labels']) for x in track.values()),
        'avoid_targets':dict(Counter(label for x in track.values() for label in x['avoid_labels'])),
        'mean_max_continuous_walk':statistics.mean(x['max_continuous_walk'] for x in track.values()),
        'mode':dict(Counter(p.mode for p in parts)),
        'unresolved_mass':out['quality']['unresolved_mass'],
        'unresolved_reasons':out['quality']['unresolved_reasons'],
        'rule_minutes':{key:sum(p.rule_minutes.get(key,0) for p in parts)
                        for key in sorted({k for p in parts for k in p.rule_minutes})}}


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--capture',type=Path,required=True); a.add_argument('--policies',type=Path,required=True)
    a.add_argument('--map',type=Path,required=True); a.add_argument('--output',type=Path,required=True)
    a.add_argument('--product-backend',type=Path,required=True)
    a.add_argument('--walkers',type=int,default=500)
    args=a.parse_args()
    if args.output.exists(): raise SystemExit('refuse overwrite; use a new evidence directory')
    sys.path.insert(0,str(args.product_backend.resolve()))
    from app.config import settings
    from app.geo.roadnet import verified_network
    from app.schemas.persona import Persona
    from app.schemas.report import MissingReport
    from app.phase0 import person_preparation as pp
    from app.phase2.person_walk import Population
    from app.llm.exaone import ExaoneClient
    from app.llm.mind_policy import Policy
    from experiments.mind_contract_ab_20261007 import engine_outputs_v2 as e
    def blocked(*a,**k): raise RuntimeError('offline walking forbids network')
    socket.create_connection=blocked; socket.socket.connect=blocked
    persona_file=args.capture/'persona_prepared.json'
    persona=Persona.model_validate_json(persona_file.read_text())
    settings.kexaone_model=read(args.capture/'calls/k_001.request.json')['body']['model']
    if pp.fingerprint(persona)!=persona.prepared_initial['fingerprint']:
        raise ValueError('saved initial preparation fingerprint differs')
    scored=read(args.policies)
    if len(scored['results'])!=4: raise ValueError('actual-source comparison incomplete')
    candidates={'author_reference':Policy.model_validate(scored['author_reference']),
                'empty_policy':Policy(rules=[],unrepresented=[])}
    for row in scored['results']:
        candidates[f"{row['candidate']}_rep{row['rep']}"]=Policy.model_validate(row['policy']) if row['policy'] is not None else None
    facilities={f:[] for f in e.FEATURES}
    # These two known fixture labels were authored with the fixture, not inferred
    # from a guardian keyword. They are NOT real OSM facility observations.
    labels={'느티공원':'park','해든상가':'market'}
    for p in persona.attraction_points:
        if p.label in labels: facilities[labels[p.label]].append({'label':p.label,**p.location.model_dump(),
            'source':'synthetic fixture facility; captured registered coordinate'})
    apps={str(p.relative_to(args.product_backend)):digest(p)
          for p in sorted((args.product_backend/'app').rglob('*.py'))}
    manifest={'source_persona_sha256':digest(persona_file),'source_policy_sha256':digest(args.policies),
        'map_sha256':digest(args.map),'harness_sha256':digest(__file__),'app_sha256':apps,
        'full_actual_captured_persona':True,'walkers':args.walkers,'seed':17,
        'candidate_names':list(candidates),'scenarios':{k:{**v,'start':v['start'].isoformat()} for k,v in scenarios().items()},
        'facilities':facilities,'numeric_baseline':'offline profile default + saved initial K interpretation; not SAR inference',
        'limits':['one synthetic guardian','author reference not expert approved','axes scoring not captured',
                  'three synthetic scenes on real roads','full production API not exercised',
                  'no clinical/path accuracy measured'],'new_external_calls':0,'release_qualified':False}
    save(args.output/'manifest.json',manifest)
    save(args.output/'status.json',{'state':'loading_verified_map'})
    if digest(args.map)!=e.MAP_SHA256: raise ValueError('unexpected KINTEX map hash')
    net=verified_network(args.map)
    env=e.SyntheticEnvNetwork(net,facilities,support_km=None)
    runs={}; cache={}
    for scene_name,scene in scenarios().items():
        start=next((p.location for p in persona.attraction_points if p.label==scene['start_place']),persona.home)
        report=MissingReport(id='offline_synthetic_'+scene_name,persona_id=persona.id,
            missing_type=persona.type,lkp=start,lkp_time=scene['start'].replace(tzinfo=ZoneInfo('Asia/Seoul')))
        baseline=ExaoneClient()._default_prior(persona,report)
        baseline.strategy_before_behavior=dict(baseline.strategy_probs)
        # Source enum remains unchanged; explicit experiment metadata labels the
        # numeric baseline so it cannot be mistaken for a live SAR response.
        base=pp.apply_prepared(persona,report,baseline,baseline)
        save(args.output/'priors'/f'{scene_name}.json',base.model_dump(mode='json'))
        if base.initial_interpretation.get('status')!='applied':
            raise ValueError('initial interpretation not injected: '+str(base.initial_interpretation))
        for name,policy in candidates.items():
            key=scene_name+'/'+name
            save(args.output/'status.json',{'state':'walking','scene':scene_name,'candidate':name,'completed':len(runs)})
            if policy is None:
                runs[key]={'status':'unusable_model_output'};continue
            identity=json.dumps([scene_name,policy.model_dump(mode='json')],sort_keys=True,ensure_ascii=False)
            if identity in cache:
                runs[key]={'status':'reused_identical_policy','reference_run':cache[identity]};continue
            track={}; traces={}; timeline=[]
            def hook(part,loc):
                t=track.setdefault(part.seed,{'avoid_labels':set(),'max_continuous_walk':0.0})
                if part.mode=='avoid': t['avoid_labels'].update(part.avoid_labels or [part.avoid_feature])
                t['max_continuous_walk']=max(t['max_continuous_walk'],part.continuous_walk)
                index=(part.seed-17)//100003
                if index<5:
                    traces.setdefault(str(index),[]).append({'minute':round(part.minute,6),**loc.model_dump(),
                        'mode':part.mode,'rule_id':part.hold_rule_id,'target':part.target,
                        'distance_m':round(part.distance,5),'continuous_walk':round(part.continuous_walk,5),
                        'rest':round(part.rest,5),'wait':round(part.waiting,5),
                        'uncertain':part.last_uncertain,'baseline':part.last_baseline})
            pop=Population(env,persona,base,policy,start,scene['start'],count=args.walkers,seed=17,
                environment_observations=e.environment_observations(scene,facilities),
                behavior_observations=e.behavior_observations(scene),trace_hook=hook)
            for part in pop.particles:
                track.setdefault(part.seed,{'avoid_labels':set(),'max_continuous_walk':0.0})
            # Keep a single population/RNG state through 1/2/4/6 h; never restart.
            for minute in (60,120,240,360):
                out=pop.advance_to(minute)
                timeline.append({'minute':minute,'metrics':metrics(pop,out,track),'distribution':out})
            result={'status':'walked','timeline':timeline,'traces':traces,
                'persona_axes_used':dict(pop.persona.axis_scores),
                'route_familiarity_used':[r.model_dump(mode='json') for r in pop.persona.route_familiarity],
                'policy':policy.model_dump(mode='json')}
            target=args.output/scene_name/(name+'.json');save(target,result)
            runs[key]={'status':'walked','path':str(target),'final':timeline[-1]['metrics']};cache[identity]=key
            save(args.output/'summary.json',{'runs':runs,'release_qualified':False})
            print(json.dumps({'scene':scene_name,'candidate':name,'final':timeline[-1]['metrics']},ensure_ascii=False),flush=True)
    save(args.output/'summary.json',{'runs':runs,'release_qualified':False})
    save(args.output/'status.json',{'state':'offline_walk_complete','runs':len(runs),'release_qualified':False})


if __name__=='__main__':main()
