import os,sys,json,tempfile,time,threading,socket,statistics
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
for k in ('EXAONE_API_KEY','MIDM_API_KEY','KEXAONE_API_KEY','EMBED_API_KEY'): os.environ[k]=''
os.environ.update(PERSIST_STORAGE='false',USE_ROADNET='false',POA_REFRESH_ENABLED='false',PRIVACY_SCHEDULER_ENABLED='false')
def blocked(*a,**kw): raise RuntimeError('network disabled')
socket.socket.connect=blocked
from app import storage
from app.config import settings
from app.privacy import worker,lifecycle
from app.schemas.case import Case,CaseStatus
from app.schemas.report import MissingReport
from app.schemas.persona import PersonaType
from app.schemas.common import GeoPoint
from datetime import datetime,timedelta
results=[]
for repeat in range(3):
 with tempfile.TemporaryDirectory() as d:
  storage.reset_for_tests();settings.persist_storage=True;settings.storage_db_path=str(Path(d)/'test.db');settings.privacy_audit_path=str(Path(d)/'audit.jsonl');lifecycle._audit_loaded=False
  extra=storage.Repository(table='benchmark_payload')
  for i in range(200):extra.save(str(i),{'payload':'x'*2048})
  now=datetime.now();point=GeoPoint(lat=37.55,lng=126.94)
  for i in range(100):
   r=MissingReport(id=f'r{i}',missing_type=PersonaType.dementia,lkp=point,lkp_time=now)
   c=Case(id=f'c{i}',report=r,status=CaseStatus.closed,lkp=point,lkp_time=now,closed_at=now-timedelta(days=10))
   storage.cases.save(c.id,c)
  queries=[];storage._db().set_trace_callback(lambda s: queries.append(s) if s=='VACUUM' else None)
  lat=[];errors=[];barrier=threading.Barrier(2)
  def writes():
   try:
    barrier.wait()
    for i in range(200):
     t=time.perf_counter();extra.save(f'write{i}',{'count':i});extra.get(f'write{i}');lat.append((time.perf_counter()-t)*1000)
   except Exception as exc:errors.append(type(exc).__name__)
  th=threading.Thread(target=writes);th.start();barrier.wait();t=time.perf_counter();run=worker.run_once(now=now);duration=(time.perf_counter()-t)*1000;th.join(10)
  assert not th.is_alive() and not errors and run.success_count==100
  assert all(extra.get(f'write{i}')=={'count':i} for i in range(200))
  results.append({'purge_ms':round(duration,3),'vacuum_count':len(queries),'writes':len(lat),'write_p50_ms':round(statistics.median(lat),3),'write_p95_ms':round(sorted(lat)[189],3),'write_max_ms':round(max(lat),3),'errors':errors})
  storage.reset_for_tests()
print(json.dumps(results,indent=2))
