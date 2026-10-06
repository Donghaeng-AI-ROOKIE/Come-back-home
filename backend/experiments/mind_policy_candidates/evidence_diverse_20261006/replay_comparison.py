"""Replay prospectively chosen, actual model policies on cached KINTEX roads.

No network; no changes to model policies or production walking code. Can resume
finished slots while model comparison is still running. Missing responses are
pending, never replaced with authored reference policies.
"""
import argparse, hashlib, json, math, socket, statistics, sys, time
from collections import Counter
from copy import copy
from datetime import datetime, timedelta
from pathlib import Path

D=Path(__file__).resolve().parent
B=D.parents[1]/'개발/cbh-simulation-integration-20261004/backend'
sys.path.insert(0,str(B))
def no_network(*a,**k): raise RuntimeError('offline replay forbids network')
socket.socket.connect=no_network
from app.geo.roadnet import verified_network
from app.geo.h3grid import haversine_km
from app.llm.mind_policy import Policy
from app.phase2.person_walk import Population
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint
from app.schemas.environment import EnvironmentObservation,BehaviorObservation
from tests.test_mind_upgrade import person,prior

def write(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix(path.suffix+'.tmp')
 tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

PLAN=json.loads((D/'spatial_plan.json').read_text())
START=datetime.fromisoformat(PLAN['start_local'])

def observations(pid,start):
 schedules={fact:[(False,0,360)] for fact in ('lost_awareness','family_present','pain_observed','target_recognized','dark_observed','rain_observed')}
 if pid in ('P09','P21','P29'):schedules['lost_awareness']=[(True,0,360)]
 if pid in ('P09','P29'):schedules['family_present']=[(False,0,90),(True,90,360)]
 if pid=='P14':schedules['target_recognized']=[(True,0,360)]
 if pid=='P17':schedules['rain_observed']=[(True,0,75),(False,75,360)]
 obs=[BehaviorObservation(fact=f,value=v,valid_from=START+timedelta(minutes=a),valid_until=START+timedelta(minutes=b),source='synthetic_scenario') for f,segments in schedules.items() for v,a,b in segments]
 env=[]
 if pid=='P01':
  env=[EnvironmentObservation(feature='market',location=start,radius_m=500,valid_from=START+timedelta(minutes=a),valid_until=START+timedelta(minutes=b),noisy=v,crowded=v,source='synthetic_scenario') for v,a,b in [(True,0,30),(False,30,360)]]
 return obs,env

def goals_for(site,pid,personal):
 goals=[]
 for place,goal in zip(personal['places'],site['goals']):
  location=site['location'] if pid=='P01' and place['place_type']=='market' else goal['location']
  goals.append(AttractionPoint(label=place['label'],place_type=place['place_type'],location=GeoPoint(**location)))
 return goals

def synthetic_environment(net,start,goals):
 points={feature:[g.location for g in goals if g.place_type==feature] for feature in ('market','park')}
 points['forest']=[GeoPoint(lat=start.lat,lng=start.lng-800/(111000*math.cos(math.radians(start.lat))))]
 points['water']=[GeoPoint(lat=start.lat,lng=start.lng+800/(111000*math.cos(math.radians(start.lat))))]
 return {n:{feature+'_m':min(haversine_km(net.node_location(n),p)*1000 for p in ps) for feature,ps in points.items()} for n in net.graph}

def run_slot(net,site,profile,policy,arm,rep,seed):
 started=time.monotonic();pid=profile['person_id'];start=GeoPoint(**site['location'])
 p=person(start);p.onboarding_turns=[{'slot':'behavior','question':'합성 보호자 원문','answer':n['text']} for n in profile['personal']['notes']];p.behavior_notes=[]
 p.attraction_points=goals_for(site,pid,profile['personal'])
 base=prior();base.attraction_weights={a.label:1. for a in p.attraction_points}
 bo,eo=observations(pid,start)
 traces=[];action_minutes=Counter();prior_minutes={};previous_mode={}
 max_continuous=0.;max_since_rest=0.;first_personal_rest=[]
 def trace(part,loc):
  nonlocal max_continuous,max_since_rest
  previous=prior_minutes.get(part.seed,0.);dt=part.minute-previous;prior_minutes[part.seed]=part.minute
  action_minutes[part.mode]+=dt
  max_continuous=max(max_continuous,part.continuous_walk);max_since_rest=max(max_since_rest,part.distance_since_rest)
  if part.mode=='rest' and previous_mode.get(part.seed)!='rest' and part.hold_rule_id is not None:
   first_personal_rest.append({'minute':part.minute-dt,'rule_id':part.hold_rule_id})
  previous_mode[part.seed]=part.mode
  if part.seed==seed:
   row={'minute':part.minute,'lat':loc.lat,'lng':loc.lng,'mode':part.mode,'rule_id':part.hold_rule_id,'target':part.target,'arrived':part.arrived,'distance_m':part.distance,'uncertain':part.last_uncertain}
   if not traces or row['mode']!=traces[-1]['mode'] or part.minute-traces[-1]['minute']>=.99:traces.append(row)
 pop=Population(net,p,base,policy,start,START,count=PLAN['particles'],seed=seed,behavior_observations=bo,environment_observations=eo,trace_hook=trace)
 snapshots=[];previous=None;checkpoint_equal=None;checkpoint_error=None
 for minute in PLAN['times_minutes']:
  out=pop.advance_to(minute)
  row={'minute':minute,'quality':out['quality'],'cells':out['cells'],
    'mean_wait_minutes':statistics.mean(x.waiting for x in pop.particles),
    'mean_rest_minutes':statistics.mean(x.rest for x in pop.particles),
    'mean_personal_rest_minutes':statistics.mean(x.rest-x.population_rest_minutes for x in pop.particles),
    'mean_walk_minutes':statistics.mean(x.walking for x in pop.particles),
    'mean_path_km':statistics.mean(x.distance for x in pop.particles)/1000,
    'mean_displacement_km':statistics.mean(haversine_km(start,pop.position(x)) for x in pop.particles),
    'mean_market_distance_m':statistics.mean(haversine_km(p.attraction_points[1].location,pop.position(x))*1000 for x in pop.particles),
    'mean_park_distance_m':statistics.mean(haversine_km(p.attraction_points[0].location,pop.position(x))*1000 for x in pop.particles),
    'moved_particles':sum(x.distance>1e-8 for x in pop.particles),
    'arrived_particles':sum(x.arrived for x in pop.particles),
    'mode_counts':dict(Counter(x.mode for x in pop.particles)),
    'tv_change':None if previous is None else .5*sum(abs(out['cells'].get(k,0)-previous.get(k,0)) for k in set(out['cells'])|set(previous)),
    'endpoints':[pop.position(x).model_dump() for x in pop.particles]}
  snapshots.append(row);previous=out['cells']
  if minute==120 and site['site_id']=='C' and seed==17:
   try:
    cp=json.loads(json.dumps(pop.checkpoint()))
    restored=Population(net,p,base,policy,start,START,count=PLAN['particles'],seed=seed,behavior_observations=bo,environment_observations=eo,checkpoint=cp)
    restored.advance_to(121);pop.advance_to(121)
    checkpoint_equal=json.loads(json.dumps(pop.checkpoint()))==json.loads(json.dumps(restored.checkpoint()))
   except Exception as e:checkpoint_equal=False;checkpoint_error=type(e).__name__
 final=snapshots[-1]
 engineering={'mass_conserved':all(abs(sum(s['cells'].values())+s['quality']['unresolved_mass']-1)<1e-8 for s in snapshots),
  'clock_accounting':all(abs(x.walking+x.rest+x.waiting-x.minute)<1e-7 for x in pop.particles),
  'distance_matches_walk_time':all(abs(x.distance-x.walking*pop.speed)<1e-5 for x in pop.particles),
  'full_horizon_resolved':final['quality']['unresolved_mass']==0,
  'checkpoint_equal':checkpoint_equal,'checkpoint_error':checkpoint_error}
 # These are authored behavior diagnostics, never clinical ground truth.
 checks={}
 if pid in ('P09','P29','P17','P25'):
  wait={'P09':90,'P29':90,'P17':75,'P25':60}[pid]
  checks.update(wait_first_hour=abs(snapshots[0]['mean_wait_minutes']-60)<1e-7,
   waiting_released=abs(final['mean_wait_minutes']-wait)<1e-7,walking_after_release=final['mean_walk_minutes']>0)
 if pid in ('P05','P29'):
  minute_limit,distance_limit=(8,450) if pid=='P05' else (6,280)
  checks.update(personal_rest_executed=final['mean_personal_rest_minutes']>0,
    walking_time_limit_preserved=max_continuous<=minute_limit+1e-7,
    walking_distance_limit_preserved=max_since_rest<=distance_limit+1e-5)
 if pid=='P01':checks.update(avoid_executed=action_minutes['avoid']>0)
 if pid=='P14':checks.update(seek_executed=action_minutes['seek']>0)
 if pid=='P21':checks.update(no_invented_wait=final['mean_wait_minutes']==0,personal_walk_executed=any(r.action=='walk' and any(x.rule_minutes.get(r.id,0)>0 for x in pop.particles) for r in policy.rules))
 return {'person_id':pid,'family':profile['family'],'arm':arm,'rep':rep,'site_id':site['site_id'],'seed':seed,'status':'executed',
  'seconds':time.monotonic()-started,'snapshots':snapshots,'engineering':engineering,'authored_behavior_checks':checks,
  'max_continuous_walk_minutes':max_continuous,'max_distance_since_rest_m':max_since_rest,'total_action_minutes':dict(action_minutes),
  'personal_rest_onsets_first20':first_personal_rest[:20],'one_particle_trace':traces,'clinical_accuracy_measured':False}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--max-slots',type=int);args=ap.parse_args()
 sites=json.loads((D/'sites.json').read_text());profiles={r['person_id']:r for r in json.loads((D/'profiles.json').read_text())}
 out=D/'spatial';out.mkdir(exist_ok=True)
 signature={'plan':digest(D/'spatial_plan.json'),'sites':digest(D/'sites.json'),'runner':digest(Path(__file__)),
  'engine':digest(B/'app/phase2/person_walk.py'),'policy':digest(B/'app/llm/mind_policy.py'),'map':sites['metadata']['sha256']}
 manifest=out/'manifest.json'
 if manifest.exists():assert json.loads(manifest.read_text())==signature,'spatial sources changed'
 else:write(manifest,signature)
 net=None;done=0
 for site in sites['sites']:
  for pid in PLAN['representatives']:
   profile=profiles[pid];env_net=None
   for arm in PLAN['arms']:
    for rep in PLAN['model_repetitions']:
     source=D/'comparison'/arm/pid/str(rep);response_path=source/'result.json'
     if not response_path.exists():continue
     response=json.loads(response_path.read_text())
     for seed in PLAN['walking_seeds']:
      dest=out/f'{pid}_{arm}_{rep}_{site["site_id"]}_{seed}.json'
      if dest.exists():continue
      policy_path=source/'compiled_policy.json'
      if not response['valid']:
       write(dest,{'person_id':pid,'arm':arm,'rep':rep,'site_id':site['site_id'],'seed':seed,'status':'not_executable_model_output','model_error_type':response['error_type']});continue
      if net is None:net=verified_network(Path(sites['source_map']))
      if env_net is None:
       env_net=copy(net);start=GeoPoint(**site['location'])
       env_net.node_env=synthetic_environment(net,start,goals_for(site,pid,profile['personal']))
      policy=Policy.model_validate(json.loads(policy_path.read_text()))
      try:row=run_slot(env_net,site,profile,policy,arm,rep,seed)
      except Exception as e:
       row={'person_id':pid,'arm':arm,'rep':rep,'site_id':site['site_id'],'seed':seed,'status':'engine_error','error_type':type(e).__name__,'error_message':str(e)}
      row['source_policy_sha256']=digest(policy_path);write(dest,row);done+=1
      print(json.dumps({k:v for k,v in row.items() if k in ('person_id','arm','rep','site_id','seed','status','seconds','engineering','authored_behavior_checks','error_message')},ensure_ascii=False),flush=True)
      if args.max_slots and done>=args.max_slots:return
 print(json.dumps({'new_slots':done,'saved_slots':len(list(out.glob('P*.json'))),'planned_slots':PLAN['planned_slots']},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
