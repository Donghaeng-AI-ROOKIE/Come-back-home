"""Six reproducible outdoor locations on the already verified KINTEX graph."""
import hashlib,json,math,socket,sys
from pathlib import Path
D=Path(__file__).resolve().parent;B=D.parents[1]/'개발/cbh-simulation-integration-20261004/backend';sys.path.insert(0,str(B))
def no_network(*a,**k):raise RuntimeError('offline map preparation forbids network')
socket.socket.connect=no_network
from app.geo.roadnet import verified_network
from app.geo.h3grid import haversine_km
from app.schemas.common import GeoPoint
path=D.parent/'MIND_completion_20261004/map_full_support/kintex_walk.graphml';net=verified_network(path)
meta=json.loads(path.with_suffix('.json').read_text());center=GeoPoint(**meta['center'])
# Compass-sector targets around the verified center. These names are test
# locations, not claims about real exhibition entrances or facility names.
offsets=[('C','중심 도로 분기',0,0,3),('NW','북서쪽 도로',-650,650,2),('NE','북동쪽 도로',650,650,2),('W','서쪽 도로',-1000,0,2),('E','동쪽 도로',1000,0,2),('S','남쪽 도로',0,-850,2)]
coords={n:net.node_location(n) for n in net.graph};neighbors={n:net.neighbors(n) for n in net.graph};sites=[]
for sid,label,dx,dy,degree in offsets:
 target=GeoPoint(lat=center.lat+dy/111320,lng=center.lng+dx/(111320*math.cos(math.radians(center.lat))))
 candidates=[n for n in coords if len(set(neighbors[n]))>=degree]
 node=min(candidates,key=lambda n:haversine_km(target,coords[n]));loc=coords[node]
 goals=[]
 for i,pname in enumerate(('느티공원','해든상가','솔빛쉼터')):
  target_goal=GeoPoint(lat=loc.lat+(i-1)*.0012,lng=loc.lng+(1 if i%2 else -1)*.0018)
  goal=net.nearest_node(target_goal);goals.append({'label':pname,'node':goal,'location':coords[goal].model_dump(),'synthetic_placement':True})
 sites.append({'site_id':sid,'label':label,'node':node,'location':loc.model_dump(),'out_neighbor_count':len(set(neighbors[node])),'meters_from_verified_center':haversine_km(center,loc)*1000,'meters_from_nominal_target':haversine_km(target,loc)*1000,'goals':goals})
assert len({r['node'] for r in sites})==6
out={'region':'KINTEX, Goyang','selection':'deterministic compass offsets + road degree, no geocoding','source_map':str(path.resolve()),'metadata':meta,'new_map_calls':0,'new_model_calls':0,'sites':sites,'limitations':['outdoor roads, not booth indoor routes','facility locations in goals are synthetic','noise/crowds/weather in scenarios are authored observations, not OSM measurements']}
(D/'sites.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'sites':[{k:r[k] for k in ('site_id','node','out_neighbor_count','meters_from_verified_center')} for r in sites],'new_external_calls':0},ensure_ascii=False))
