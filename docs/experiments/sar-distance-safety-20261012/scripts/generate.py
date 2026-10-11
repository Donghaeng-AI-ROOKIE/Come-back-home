from pathlib import Path
import sys,json,hashlib,time,datetime,concurrent.futures,socket
from distance_prior import distance_map
O=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def blocked(*a,**k):raise RuntimeError("external calls forbidden")
def one(job):
 socket.socket.connect=blocked;socket.create_connection=blocked
 pid,lkp,hours,bbox=job;t=time.monotonic()
 maps=[]
 for hour in hours:
  cells,quality=distance_map(lkp['lat'],lkp['lng'],hour,coverage_bbox=bbox)
  maps.append({'hour':hour,'cells':cells,'quality':quality})
 p=O/f'results/distance_maps/{pid}.json';assert not p.exists();p.write_text(json.dumps({'person_id':pid,'seconds':time.monotonic()-t,'snapshots':maps},indent=1)+'\n')
 return {'person_id':pid,'seconds':time.monotonic()-t,'sha256':sha(p)}
if __name__=='__main__':
 p=O/'protocol/protocol.json';protocol=json.loads(p.read_text());frozen=sha(p)
 assert sha(O/'scripts/distance_prior.py')==protocol['distance_source_sha256']
 out=O/'results/distance_maps';out.mkdir(exist_ok=True)
 event_id='sar-distance-local-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')
 ledger=O/'results/local_usage.jsonl'
 start={'event_id':event_id,'phase':'start','timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':protocol['scope'],'protocol_sha256':frozen}
 with ledger.open('a') as f:f.write(json.dumps(start)+'\n')
 t=time.monotonic();jobs=[(pid,v['lkp'],protocol['hours'],protocol['map_manifest']['bbox_south_west_north_east']) for pid,v in protocol['inputs'].items()];done=[]
 try:
  with concurrent.futures.ProcessPoolExecutor(max_workers=2) as pool:
   for result in pool.map(one,jobs):done.append(result);print(result,flush=True)
 finally:
  end={'event_id':event_id,'phase':'end','timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'wall_seconds':time.monotonic()-t,'completed_people':len(done),'new_model_calls':0,'remote_runs':0,'map_requests':0,'actual_push':0,'cost_amount':None,'error':None if len(done)==len(jobs) else 'incomplete'}
  with ledger.open('a') as f:f.write(json.dumps(end)+'\n')
 assert len(done)==39 and sha(p)==frozen
 (O/'results/generation.json').write_text(json.dumps({'protocol_sha256':frozen,'source_sha256':sha(Path(__file__)),'results':done,'usage':end},indent=2)+'\n')
