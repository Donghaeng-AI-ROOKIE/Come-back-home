"""Desired cross-component contracts. Regression coverage for the previously reproduced integration gaps.

Run explicitly: PYTHONPATH=backend python -m pytest docs/reviews/service-lifecycle-audit-20261009/test_contracts.py
These are outside the ordinary backend suite. Synthetic KINTEX cell, no network/model.
"""
import asyncio
from datetime import datetime,timedelta
from uuid import uuid4
import h3,httpx,pytest
from fastapi import HTTPException
from app import storage
from app.config import settings
from app.main import app
from app.cloud_bridge.policy import authorize
from app.cloud_bridge.worker import dispatch
from app.phase0 import persona_events
from app.phase2 import pipeline
from app.phase3 import alerts
from app.privacy import lifecycle,worker
from app.schemas.case import Case,CaseStatus,CloseReason
from app.schemas.common import GeoPoint
from app.schemas.report import MissingReport
from app.schemas.persona import Persona,PersonaType,InterviewSession

OWNER=str(uuid4());OTHER=str(uuid4())
POINT=GeoPoint(lat=37.6688,lng=126.7457)
CELL=h3.latlng_to_cell(POINT.lat,POINT.lng,9)

@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):
 storage.reset_for_tests()
 monkeypatch.setattr(settings,"privacy_audit_path",str(tmp_path/"audit.jsonl"))
 lifecycle._audit_loaded=False
 yield
 storage.reset_for_tests()

def make_case():
 now=datetime.now()
 report=MissingReport(id="audit-report",persona_id=None,missing_type=PersonaType.dementia,lkp=POINT,lkp_time=now-timedelta(hours=1))
 case=Case(id="audit-case",guardian_id=OWNER,report=report,status=CaseStatus.searching,lkp=POINT,lkp_time=report.lkp_time,current_poa={CELL:1.0})
 storage.cases.save(case.id,case)
 return case

def cloud(method,path,body=None,owner=OWNER):
 async def run():
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url="http://test") as api:
   return await dispatch(api,dict(owner_id=owner,method=method,path=path,body=body),enabled=True)
 return asyncio.run(run())

def test_guardian_can_close_their_case_through_public_transport():
 case=make_case()
 status,_=cloud("POST",f"/phase1/cases/{case.id}/close",{"reason":"found"})
 assert status==200, "Owner closure is blocked by the cloud allowlist"

def test_guardian_can_delete_their_inactive_persona_through_public_transport():
 p=Persona(id="audit-person",guardian_id=OWNER,type=PersonaType.dementia,name="Synthetic",age=75,home=POINT)
 storage.personas.save(p.id,p)
 status,_=cloud("DELETE",f"/phase0/personas/{p.id}")
 assert status==200, "Owner deletion is blocked by the cloud allowlist"

def test_closed_case_no_longer_returns_search_map_to_citizen():
 case=make_case()
 lifecycle.close_case(case,CloseReason.found)
 status,result=cloud("GET",f"/phase3/cases/{case.id}/poa",owner=OTHER)
 assert status in {404,409,410}, "Known case ID still returns closed search coordinates"

def test_persona_triggered_prediction_checks_new_alert_region(monkeypatch):
 case=make_case();seen=[]
 def predict(current,now=None):
  current.current_poa={CELL:1.0};storage.cases.save(current.id,current)
 monkeypatch.setattr(pipeline,"run_prediction",predict)
 monkeypatch.setattr(alerts,"notify_prediction",lambda c:seen.append(c.id))
 persona_events._rerun_case(case.id,1)
 assert seen==[case.id], "Persona rerun bypasses prediction notification"

def test_total_notification_failure_does_not_consume_retry_baseline(monkeypatch):
 case=make_case();calls=[]
 def fail(*args,**kwargs):
  calls.append(args);return {"sent":0,"failed":1,"stub":False}
 monkeypatch.setattr(alerts,"send_alerts",fail)
 alerts.notify_prediction(case, now=datetime.now())
 alerts.retry_pending_notifications(now=datetime.now()+timedelta(minutes=3))
 assert case.last_alert_at is None and len(calls)==2, "All-failed send is treated as alerted and identical POA cannot retry"

def test_late_notification_cannot_restore_purged_case(monkeypatch):
 case=make_case()
 def delayed_send(*args,**kwargs):
  lifecycle.close_case(case,CloseReason.found)
  lifecycle.request_case_deletion(case)
  assert storage.cases.get(case.id) is None
  return {"sent":1,"failed":0,"stub":False}
 monkeypatch.setattr(alerts,"send_alerts",delayed_send)
 alerts.notify_prediction(case)
 assert storage.cases.get(case.id) is None, "Notification saves old case after close+purge"

def test_actual_expiry_worker_removes_case_and_abandoned_interview():
 case=make_case()
 now=datetime.now()
 lifecycle.close_case(case,CloseReason.found,now=now-timedelta(days=6))
 s=InterviewSession(id="audit-abandoned",guardian_name="Synthetic",last_active_at=now-timedelta(hours=49))
 storage.interviews.save(s.id,s)
 run=worker.run_once(now=now)
 assert run.success_count==2
 assert storage.cases.get(case.id) is None and storage.interviews.get(s.id) is None

def test_closed_case_is_absent_from_active_alerts_and_tips_blocked():
 case=make_case();lifecycle.close_case(case,CloseReason.found)
 status,out=cloud("GET","/phase3/alerts?cell_res7="+h3.cell_to_parent(CELL,7),owner=OTHER)
 assert status==200 and out==[]
 status,_=cloud("POST",f"/phase3/cases/{case.id}/tips",{"text":"synthetic"},owner=OTHER)
 assert status==409

def test_hourly_refresh_preserves_existing_tip_evidence(monkeypatch):
 from app.phase2 import refresher
 from app.phase3 import poa_update
 from app.schemas.tip import Tip,TipDecision
 from app.llm import exaone
 case=make_case()
 other=h3.latlng_to_cell(37.676,126.755,9)
 baseline={CELL:0.5,other:0.5}
 tip=Tip(id="audit-tip",case_id=case.id,text="synthetic observation",location=POINT,
         seen_at=case.lkp_time+timedelta(minutes=10),p=0.6,decision=TipDecision.layer1)
 case.tips=[tip];case.baseline_poa=baseline
 case.current_poa=poa_update.reapply_tips(baseline,case.tips,since=case.lkp_time)
 expected=dict(case.current_poa)
 assert expected!=baseline, "Control must have a real tip effect"
 monkeypatch.setattr(pipeline.situation_link,"cached",lambda *a:{})
 monkeypatch.setattr(pipeline,"_initial_prior",lambda p,r,l:exaone._default_prior(p,r))
 monkeypatch.setattr(pipeline,"_load_roadnet",lambda *a:(None,"audit_fixed_output"))
 monkeypatch.setattr(pipeline.topdown,"topdown_poa",lambda *a:dict(baseline))
 monkeypatch.setattr(pipeline.continuous_prediction,"run_pair",lambda *a,**kw:(dict(baseline),dict(baseline),{}))
 monkeypatch.setattr(alerts,"notify_prediction",lambda *a:None)
 refresher.refresh_due_cases(now=datetime.now())
 assert storage.cases.get(case.id).current_poa==pytest.approx(expected), "Hourly rerun erased already accepted tip weighting"


def test_owner_lifecycle_rejects_other_accounts_and_lists_only_mine():
 case=make_case()
 status,rows=cloud('GET','/phase1/cases?guardian_id='+OTHER)
 assert status==200 and [r['id'] for r in rows]==[case.id]
 assert 'alert_delivery' not in rows[0]
 assert cloud('GET','/phase1/cases',owner=OTHER)==(200,[])
 assert cloud('POST',f'/phase1/cases/{case.id}/close',{'reason':'found','owner_id':OWNER},owner=OTHER)[0]==404
 assert cloud('DELETE',f'/phase1/cases/{case.id}',owner=OTHER)[0]==404
 assert cloud('DELETE',f'/phase1/cases/{case.id}')[0]==409
 assert cloud('POST',f'/phase1/cases/{case.id}/close',{'reason':'found'})[0]==200
 assert cloud('POST',f'/phase1/cases/{case.id}/close',{'reason':'found'})[0]==200
 assert cloud('DELETE',f'/phase1/cases/{case.id}')[0]==200
 assert storage.cases.get(case.id) is None

def test_confirmation_is_explicit_and_does_not_reinterpret(monkeypatch):
 p=Persona(id='confirm-person',guardian_id=OWNER,type=PersonaType.dementia,name='Synthetic',age=75,home=POINT)
 storage.personas.save(p.id,p)
 before=p.version
 assert cloud('POST',f'/phase0/personas/{p.id}/confirm',owner=OTHER)[0]==404
 status,out=cloud('POST',f'/phase0/personas/{p.id}/confirm')
 assert status==200 and out['last_confirmed_at'] and out['version']==before
 assert cloud('DELETE',f'/phase0/personas/{p.id}',owner=OTHER)[0]==404

def test_linked_active_persona_cannot_be_deleted():
 case=make_case()
 p=Persona(id='linked-person',guardian_id=OWNER,type=PersonaType.dementia,name='Synthetic',age=75,home=POINT)
 storage.personas.save(p.id,p);case.report.persona_id=p.id
 assert cloud('DELETE',f'/phase0/personas/{p.id}')[0]==409
 lifecycle.close_case(case,CloseReason.found)
 assert cloud('DELETE',f'/phase0/personas/{p.id}')[0]==200
 assert storage.cases.get(case.id) is None and storage.personas.get(p.id) is None

def test_reserved_expiry_does_not_run_before_deadline():
 case=make_case();now=datetime.now();lifecycle.close_case(case,CloseReason.found,now=now)
 due=lifecycle.purge_due_at(case)
 assert worker.run_once(now=due-timedelta(seconds=1),discover=False).target_count==0
 assert storage.cases.get(case.id)
 assert worker.run_once(now=due,discover=False).success_count==1
 assert storage.cases.get(case.id) is None

def test_partial_push_retries_only_failed_recipient(monkeypatch):
 case=make_case();calls=[];now=datetime.now()
 def send(*args,**kwargs):
  calls.append(kwargs.get('only_tokens'))
  return {'sent':1,'failed':1,'failed_tokens':['retry-me'],'sent_tokens':['accepted'],'stub':False} if len(calls)==1 else {'sent':1,'failed':0,'sent_tokens':['retry-me'],'failed_tokens':[],'stub':False}
 monkeypatch.setattr(alerts,'send_alerts',send)
 alerts.notify_prediction(case,now=now)
 alerts.retry_pending_notifications(now=now+timedelta(minutes=1))
 assert len(calls)==1
 alerts.retry_pending_notifications(now=now+timedelta(minutes=3))
 assert calls==[None,{'retry-me'}]
 assert case.alert_delivery['status']=='complete'
 assert 'sent_tokens' not in cloud('GET',f'/phase1/cases/{case.id}')[1]

def test_retry_exhaustion_is_bounded_and_closed_case_not_retried(monkeypatch):
 case=make_case();calls=[];now=datetime.now()
 monkeypatch.setattr(alerts,'send_alerts',lambda *a,**kw:calls.append(kw) or {'sent':0,'failed':1,'stub':False})
 alerts.notify_prediction(case,now=now)
 for n in range(1,8):alerts.retry_pending_notifications(now=now+timedelta(hours=n))
 assert len(calls)==5 and case.alert_delivery['status']=='failed'
 alerts.notify_prediction(case,now=now+timedelta(hours=10))
 assert len(calls)==5 and case.last_alert_at is None
 lifecycle.close_case(case,CloseReason.found)
 alerts.retry_pending_notifications(now=now+timedelta(hours=11))
 assert len(calls)==5

def test_closed_case_cannot_finish_queued_tip(monkeypatch):
 from app.phase3 import tip_flow
 from app.schemas.tip import Tip
 case=make_case();tip=Tip(id='queued-tip',case_id=case.id,text='synthetic')
 case.tips.append(tip);lifecycle.close_case(case,CloseReason.found)
 monkeypatch.setattr(tip_flow,'_apply_heavy',lambda *a:pytest.fail('closed work executed'))
 tip_flow.finish_tip(case.id,tip.id)
 assert storage.cases.get(case.id).status==CaseStatus.found


def test_deleted_snapshot_cannot_restart_prediction(monkeypatch):
 case=make_case();snapshot=case.model_copy(deep=True)
 lifecycle.close_case(case,CloseReason.found);lifecycle.request_case_deletion(case)
 with pytest.raises(lifecycle.AlreadyClosed):
  pipeline.run_prediction(snapshot)
 assert storage.cases.get(case.id) is None

def test_expo_failed_batch_has_nonnegative_counts_and_only_accepted_receipts(monkeypatch):
 from app.phase3 import push,devices
 from app.schemas.device import Platform
 monkeypatch.setattr(settings,'push_enabled',True)
 devices.reset()
 tokens=[f'ExponentPushToken[test-{n}]' for n in range(102)]
 calls=[]
 class Response:
  def raise_for_status(self):pass
  def json(self):return {'data':[{'status':'ok'},{'status':'error'}]}
 def post(*args,**kwargs):
  calls.append(1)
  if len(calls)==1:raise httpx.ConnectError('synthetic')
  return Response()
 monkeypatch.setattr(push.httpx,'post',post)
 result=push.send(tokens,'synthetic','synthetic',{})
 assert result['sent']==1 and result['failed']==101
 assert result['sent_tokens']==[tokens[100]]
 assert set(result['failed_tokens'])==set(tokens)-{tokens[100]}


def test_deleted_persona_cannot_be_relinked_after_cloud_authorization():
 from app.phase1 import intake
 p=Persona(id='deleted-owner-person',guardian_id=OWNER,type=PersonaType.dementia,name='Synthetic',age=75,home=POINT)
 storage.personas.save(p.id,p)
 lifecycle.purge_persona(p.id)
 with pytest.raises(HTTPException) as exc:
  intake.create_report(guardian_id=OWNER,missing_type=PersonaType.dementia,lkp=POINT,lkp_time=datetime.now(),persona_id=p.id)
 assert exc.value.status_code==404 and storage.cases.list()==[]
