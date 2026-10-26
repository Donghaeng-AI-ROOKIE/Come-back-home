import threading
from datetime import datetime, timedelta

import pytest
from app import storage
from app.api import phase1, phase3
from app.config import settings
from app.phase3 import tip_flow, tip_receipts
from app.privacy import lifecycle
from app.schemas.case import Case, CaseStatus, CloseReason
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.report import MissingReport
from app.schemas.tip import Tip
from fastapi import BackgroundTasks, HTTPException


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    storage.reset_for_tests()
    monkeypatch.setattr(tip_receipts,'schedule',lambda *a:None)
    yield
    storage.reset_for_tests()

def make_case():
    point=GeoPoint(lat=37.5216,lng=126.9243);now=datetime.now()
    c=Case(id='tip-receipt-case',guardian_id='owner',report=MissingReport(id='r',missing_type=PersonaType.dementia,lkp=point,lkp_time=now-timedelta(hours=1)),lkp=point,lkp_time=now-timedelta(hours=1),status=CaseStatus.predicted,current_poa={'8930e1d80c3ffff':1.0})
    storage.cases.save(c.id,c);return c

def receive(c,identifier='submission-one',**kw):
    return phase3.submit_tip(c.id,phase3.TipIn(text='합성 제보 원문',background_analysis=True,submission_id=identifier,reporter_user_id='owner',**kw),BackgroundTasks())

def test_receipt_is_saved_without_model_or_prediction(monkeypatch):
    c=make_case();before=dict(c.current_poa)
    monkeypatch.setattr(tip_flow.tip_llm,'structure_tip',lambda *a:pytest.fail('LLM before acknowledgement'))
    monkeypatch.setattr(tip_flow.pipeline,'run_prediction',lambda *a:pytest.fail('prediction before acknowledgement'))
    result=receive(c)
    assert result.processing_status=='queued' and result.p is None
    assert storage.tip_receipts.get(result.id).text=='합성 제보 원문'
    assert storage.cases.get(c.id).current_poa==before
    assert phase1.get_case(c.id).tips[0].id==result.id
    assert c.tips==[]  # guardian projection cannot replace the live Case

def test_long_case_prediction_lock_does_not_block_receipt():
    c=make_case();entered=threading.Event();release=threading.Event()
    def hold():
        with storage.case_lock(c.id):entered.set();release.wait(3)
    thread=threading.Thread(target=hold);thread.start();assert entered.wait(1)
    try:
        result=receive(c)
        assert thread.is_alive()  # accepted while the prediction still holds the case lock
        assert result.processing_status=='queued'
    finally:release.set();thread.join(2)

def test_repeat_submission_is_one_tip_and_one_participation():
    c=make_case();first=receive(c);second=receive(c)
    assert first.id==second.id
    assert len(storage.tip_receipts.list())==1
    assert storage.walk_tip_counts.get('owner')==1
    with pytest.raises(HTTPException) as error:
        tip_receipts.receive(c.id,'different',None,None,first.id)
    assert error.value.status_code==409

def test_worker_transfers_one_copy_and_duplicate_worker_does_not_repeat_model(monkeypatch):
    c=make_case();receipt=receive(c);calls=[]
    monkeypatch.setattr(tip_flow.tip_llm,'structure_tip',lambda *a:calls.append(1) or {'specificity':'중'})
    monkeypatch.setattr(tip_flow,'needs_heavy',lambda *a:False)
    tip_receipts.process(receipt.id);tip_receipts.process(receipt.id)
    assert calls==[1]
    assert [t.id for t in c.tips]==[receipt.id]
    assert c.tips[0].processing_status=='processed'
    saved=storage.tip_receipts.get(receipt.id)
    assert saved.state=='processed' and saved.text==''
    assert phase1.get_case(c.id).tips==c.tips

def test_recovery_after_analysis_saved_never_adds_tip_twice(monkeypatch):
    c=make_case();receipt=receive(c)
    c.tips=[Tip(id=receipt.id,case_id=c.id,text=receipt.text,p=.1,decision='discard',processing_status='running')]
    storage.cases.save(c.id,c)
    monkeypatch.setattr(tip_flow.tip_llm,'structure_tip',lambda *a:pytest.fail('already analyzed'))
    tip_receipts.process(receipt.id)
    assert len(c.tips)==1 and storage.tip_receipts.get(receipt.id).state=='processed'

def test_closure_cancels_pending_and_purge_removes_receipt(monkeypatch):
    c=make_case();receipt=receive(c)
    monkeypatch.setattr(tip_flow.tip_llm,'structure_tip',lambda *a:pytest.fail('closed case'))
    lifecycle.close_case(c,CloseReason.withdrawn)
    tip_receipts.process(receipt.id)
    assert storage.tip_receipts.get(receipt.id).state=='cancelled'
    assert storage.tip_receipts.get(receipt.id).text==''
    lifecycle.request_case_deletion(c)
    assert storage.tip_receipts.get(receipt.id) is None

def test_close_while_model_is_inflight_prevents_late_tip_or_reprediction(monkeypatch):
    c=make_case();receipt=receive(c);entered=threading.Event();release=threading.Event()
    def model(*a):entered.set();assert release.wait(3);return {'specificity':'상'}
    monkeypatch.setattr(tip_flow.tip_llm,'structure_tip',model)
    monkeypatch.setattr(tip_flow.pipeline,'run_prediction',lambda *a:pytest.fail('late prediction'))
    thread=threading.Thread(target=tip_receipts.process,args=(receipt.id,));thread.start();assert entered.wait(1)
    try:lifecycle.close_case(c,CloseReason.withdrawn)
    finally:release.set();thread.join(3)
    assert c.tips==[] and c.status==CaseStatus.closed
    assert storage.tip_receipts.get(receipt.id).state=='cancelled'

def test_bounded_retry_preserves_original_when_analysis_fails(monkeypatch):
    c=make_case();receipt=receive(c);calls=[]
    monkeypatch.setattr(tip_flow.tip_llm,'structure_tip',lambda *a:calls.append(1) or {})
    def fail(*a,**k):raise RuntimeError('example')
    monkeypatch.setattr(tip_flow,'process_tip',fail)
    for _ in range(3):tip_receipts.process(receipt.id)
    saved=storage.tip_receipts.get(receipt.id)
    assert saved.state=='failed' and saved.attempts==2 and len(calls)==2
    assert saved.text=='합성 제보 원문'

def test_receipt_survives_storage_reload_without_running_model(monkeypatch,tmp_path):
    monkeypatch.setattr(settings,'persist_storage',True)
    monkeypatch.setattr(settings,'storage_db_path',str(tmp_path/'state.db'))
    c=make_case();receipt=receive(c)
    storage.reset_for_tests()
    assert storage.tip_receipts.get(receipt.id).text=='합성 제보 원문'
    scheduled=[];monkeypatch.setattr(tip_receipts,'_enqueue',scheduled.append)
    tip_receipts.recover();assert scheduled==[receipt.id]


def test_cloud_transport_delivers_receipt_before_background_work(monkeypatch):
    import asyncio

    import httpx
    from app.cloud_bridge.worker import EarlyResponseTransport
    from app.main import app
    c=make_case();release=threading.Event();started=threading.Event()
    def slow_schedule(*args):started.set();release.wait(3)
    monkeypatch.setattr(tip_receipts,'schedule',slow_schedule)
    async def run():
        transport=EarlyResponseTransport(app)
        async with httpx.AsyncClient(transport=transport,base_url='http://test') as client:
            try:
                response=await asyncio.wait_for(client.post(f'/phase3/cases/{c.id}/tips',json={
                    'text':'합성 제보','background_analysis':True,'submission_id':'transport-receipt'}),timeout=1)
                assert response.status_code==200
                assert response.json()['processing_status']=='queued'
                assert storage.tip_receipts.get('transport-receipt') is not None
            finally:
                release.set()
                if transport.pending:await asyncio.wait_for(asyncio.gather(*list(transport.pending)),2)
    asyncio.run(run())


def test_badge_failure_cannot_turn_saved_tip_into_failed_submission(monkeypatch):
    c=make_case()
    def failed_badge(*args):raise RuntimeError('counter unavailable')
    monkeypatch.setattr(storage.walk_tip_counts,'save',failed_badge)
    receipt=receive(c)
    assert storage.tip_receipts.get(receipt.id).state=='queued'


def test_new_tip_for_closed_case_is_rejected_without_saving():
    c=make_case();lifecycle.close_case(c,CloseReason.withdrawn)
    from app.privacy.lifecycle import AlreadyClosed
    with pytest.raises((AlreadyClosed,HTTPException)):receive(c)
    assert storage.tip_receipts.list()==[]
