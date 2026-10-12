"""Independent authored road futures. Does not import prediction/alert code or maps."""
from pathlib import Path
import hashlib,json,random,math,re,socket
import networkx as nx,numpy as np,osmnx as ox
from scipy.spatial import cKDTree
O=Path(__file__).resolve().parents[1];R=O.parents[2];E=R/'결선/실험/EFFICIENCY_KINTEX_v1_20261009'
def blocked(*a,**k):raise RuntimeError('network forbidden')
socket.socket.connect=blocked;socket.create_connection=blocked
p=json.loads((O/'protocol.json').read_text());path=R/'결선/실험/MIND_completion_20261004/map_full_support/kintex_walk.graphml'
assert hashlib.sha256(path.read_bytes()).hexdigest()==p['map_sha256']
g=ox.load_graphml(path);nodes=sorted(max(nx.strongly_connected_components(g),key=len));scale=np.array([88000.,111000.]);xy=np.array([[g.nodes[n]['x'],g.nodes[n]['y']] for n in nodes]);tree=cKDTree(xy*scale)
inputs={r['person_id']:r for r in json.loads((E/'inputs.json').read_text())};anchors={r['person_id']:r for r in json.loads((E/'dataset_manifest.json').read_text())}
def nearest(pos):return nodes[int(tree.query(np.array([pos['lng'],pos['lat']])*scale)[1])]
def road(a,b,salt):
 def weight(u,v,edges):return min(float(d['length']) for d in edges.values())*(1+0.55*random.Random(f'{salt}:{u}:{v}').random())
 ns=nx.shortest_path(g,a,b,weight=weight);segments=[]
 for u,v in zip(ns,ns[1:]):
  e=min(g[u][v].values(),key=lambda d:float(d['length']));geom=e.get('geometry');cs=list(geom.coords) if geom is not None else [(g.nodes[u]['x'],g.nodes[u]['y']),(g.nodes[v]['x'],g.nodes[v]['y'])]
  if math.dist(cs[-1],(g.nodes[u]['x'],g.nodes[u]['y']))<math.dist(cs[0],(g.nodes[u]['x'],g.nodes[u]['y'])):cs.reverse()
  lens=[math.dist(np.array(a)*scale,np.array(b)*scale) for a,b in zip(cs,cs[1:])];total=sum(lens)
  segments.extend((a,b,float(e['length'])*d/total,v) for (a,b),d in zip(zip(cs,cs[1:]),lens) if d>0)
 if not segments:raise ValueError('empty road')
 return segments
def at(segs,d):
 for a,b,length,_ in segs:
  if d<=length:return {'lat':a[1]+(b[1]-a[1])*max(0,d)/length,'lng':a[0]+(b[0]-a[0])*max(0,d)/length}
  d-=length
 b=segs[-1][1];return {'lat':b[1],'lng':b[0]}
def reroute(segs,d,destination,salt):
 # Continue from the exact point along the current directed edge to its end.
 # Snapping to a nearest graph node creates nonphysical movement jumps.
 for i,(a,b,length,end_node) in enumerate(segs):
  if d<length-1e-9:
   here=at([segs[i]],d);prefix=[((here['lng'],here['lat']),b,length-d,end_node)]
   for next_segment in segs[i+1:]:
    if next_segment[3]!=end_node:break
    prefix.append(next_segment)
   return prefix+(road(end_node,destination,salt) if end_node!=destination else [])
  d-=length
 end_node=segs[-1][3]
 return road(end_node,destination,salt) if end_node!=destination else segs[-1:]

truth=[]
for seed in [p['truth_seed_development'],*p['truth_seeds_validation']]:
 for ix,pid in enumerate(p['people']):
  inp=inputs[pid];a=anchors[pid];start=a['start_node'];goal=a['goal_node'];home=a['home_node'];usual=a['quiet_node'] if inp['family']=='avoid' and any(x.get('noisy') for x in inp['report']['environment_observations']) else goal
  rng=random.Random(f'{seed}:{pid}');quote=inp['persona']['onboarding_quotes']['mobility_transport_capacity'][0];bout,rest=map(int,re.findall(r'(\d+)분',quote)[:2]);waits=re.findall(r'(\d+)분',inp['persona']['onboarding_quotes']['lost_behavior'][0]);wait=int(waits[0]) if waits else 0
  speed=rng.uniform(28,49);depart=rng.randint(60,150);dwell=rng.randint(20,100);band=(ix+[p['truth_seed_development'],*p['truth_seeds_validation']].index(seed))%3
  center=xy[nodes.index(start)];uv=np.array([g.nodes[usual]['x'],g.nodes[usual]['y']])-center;angle=math.atan2(*(uv*scale)[::-1]);radius=rng.uniform(*[(500,1500),(1500,3000),(3000,5000)][band]);theta=angle+math.pi+rng.uniform(-.55,.55);wanted=center*scale+radius*np.array([math.cos(theta),math.sin(theta)]);unrelated=next(nodes[int(i)] for i in np.atleast_1d(tree.query(wanted,k=32)[1]) if nodes[int(i)] not in [start,goal,home,usual,a['unrelated_node']])
  forward=road(start,usual,f'{seed}:{pid}:usual');back=road(usual,home,f'{seed}:{pid}:back');again=road(home,usual,f'{seed}:{pid}:again')
  for future in p['futures']:
   segs=road(start,unrelated,f'{seed}:{pid}:counter') if future=='contradictory' else forward;total=sum(s[2] for s in segs);d=0.;leave=None;leg=0;snapshots=[];positions=[]
   for minute in range(361):
    if minute:
     elapsed=minute-1
     if future=='departure' and elapsed==depart:
      segs=reroute(segs,d,unrelated,f'{seed}:{pid}:depart');total=sum(s[2] for s in segs);d=0.;leave=None
     waiting=future!='contradictory' and elapsed<wait;resting=(elapsed%(bout+rest))>=bout
     if not waiting and not resting:
      if d<total:d=min(total,d+speed)
      elif future=='habitual':
       if leave is None:leave=elapsed+dwell
       if elapsed>=leave:leg+=1;segs=back if leg%2 else again;total=sum(s[2] for s in segs);d=0.;leave=None
    pos=at(segs,d)
    if minute%5==0:positions.append({'minute':minute,**pos})
    if minute in [60,120,240,360]:snapshots.append({'hour':minute//60,'position':pos})
   truth.append({'person_id':pid,'truth_seed':seed,'split':'development' if seed==p['truth_seed_development'] else 'validation','future':future,'distance_band':['near','mid','far'][band],'snapshots':snapshots,'path':positions,'assumptions':{'speed_m_min':speed,'walk_bout_min':bout,'rest_min':rest,'initial_wait_min':wait if future!='contradictory' else 0,'departure_min':depart,'habitual_dwell_min':dwell,'unrelated_node':unrelated,'new_route_weight_jitter':.55}})
  print(seed,pid,flush=True)
(O/'truth_private.json').write_text(json.dumps(truth,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
(O/'truth_manifest.json').write_text(json.dumps({'routes':len(truth),'truth_sha256':hashlib.sha256((O/'truth_private.json').read_bytes()).hexdigest(),'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'protocol_sha256':hashlib.sha256((O/'protocol.json').read_bytes()).hexdigest(),'prediction_outputs_read':False,'new_people':False,'clinical':False},indent=2)+'\n')
