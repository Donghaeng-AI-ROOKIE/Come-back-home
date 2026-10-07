"""Read saved traces to distinguish an action label from its spatial effects.

These diagnostics use one prespecified particle per population, not all walkers.
No new simulation, external query or alteration of model outputs.
"""
import json,math
from pathlib import Path
D=Path(__file__).resolve().parent
sites={s['site_id']:s for s in json.loads((D/'sites.json').read_text())['sites']}
def distance(a,b):
 lat1,lat2=math.radians(a['lat']),math.radians(b['lat'])
 dlat=lat2-lat1;dlon=math.radians(b['lng']-a['lng'])
 h=math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
 return 6371000*2*math.asin(min(1,math.sqrt(h)))
rows=[]
for path in sorted((D/'spatial').glob('P*.json')):
 r=json.loads(path.read_text())
 if r['status']!='executed' or r['person_id'] not in ('P01','P14'):continue
 site=sites[r['site_id']];trace=r['one_particle_trace'];checks={}
 if r['person_id']=='P01':
  early=[x for x in trace if x['minute']<=30+1e-8]
  checks={'avoid_action_seen':any(x['mode']=='avoid' for x in early),
   'left_60m_market_scope_before_noise_ended':any(distance(site['location'],x)>60 for x in early),
   'no_avoid_after_explicit_quiet':all(x['mode']!='avoid' for x in trace if x['minute']>30+1e-8)}
 else:
  goal=site['goals'][0]['location'];initial=distance(site['location'],goal)
  minimum=min((distance(x,goal) for x in trace),default=initial)
  checks={'named_goal_assigned':any(x['target']=='느티공원' for x in trace),
   'seek_action_seen':any(x['mode']=='seek' for x in trace),
   'approached_named_goal_or_started_there':initial<=1e-8 or minimum<initial-1,
   'physical_arrival_recorded':any(x['arrived'] and x['target']=='느티공원' for x in trace),
   'initial_goal_distance_m':initial,'minimum_traced_goal_distance_m':minimum}
 rows.append({k:r[k] for k in ('person_id','arm','rep','site_id','seed')}|{'checks':checks})
out={'scope':'first particle of each recorded population; chosen by walking seed before running','model_calls':0,'new_simulations':0,'clinical_accuracy_measured':False,'results':rows}
(D/'spatial_behavior_audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'traces_audited':len(rows)},ensure_ascii=False))
