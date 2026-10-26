"""KINTEX synthetic location tests; no vendor push/model/map calls."""
import asyncio
import base64
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4
import h3
import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import HTTPException
from app import storage
from app.main import app
from app.phase3 import alerts, devices, webpush, webpush_entry as entry
from app.cloud_bridge.policy import authorize
from app.cloud_bridge.worker import dispatch
from app.schemas.case import CaseStatus

OWNER=str(uuid4())
OTHER=str(uuid4())
FINE=h3.latlng_to_cell(37.6688,126.7457,9)
COARSE=h3.cell_to_parent(FINE,7)

@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    devices.reset(); entry._recent_attempts.clear()
    monkeypatch.setattr(webpush,'enabled',lambda:True)
    yield
    devices.reset(); entry._recent_attempts.clear()

def sub(endpoint='https://web.push.apple.com/test-only'):
    key=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(Encoding.X962,PublicFormat.UncompressedPoint)
    enc=lambda b:base64.urlsafe_b64encode(b).decode().rstrip('=')
    return {'endpoint':endpoint,'keys':{'p256dh':enc(key),'auth':enc(b'a'*16)}}

def registered(cell=COARSE):
    return entry.register(OWNER,sub(),cell,'normal')['device_id']

def case(monkeypatch,status=CaseStatus.predicted):
    row=SimpleNamespace(id='synthetic-case',status=status,current_poa={FINE:1.0},report=SimpleNamespace(appearance=None))
    monkeypatch.setattr(storage.cases,'list',lambda:[row])
    monkeypatch.setattr(storage.cases,'get',lambda id:row if id==row.id else None)
    return row

def test_authenticated_bridge_injects_owner_and_rejects_unlisted_routes():
    r=authorize(OWNER,'POST','/phase3/webpush/location',{'owner_id':OTHER,'device_id':'x'})
    assert r.body['owner_id']==OWNER
    for method,path in [('GET','/phase3/webpush/location'),('POST','/phase3/webpush/evil'),('GET','/phase3/webpush/public-key?owner_id=x')]:
        with pytest.raises(HTTPException):authorize(OWNER,method,path,None)

def test_foreign_account_cannot_update_send_or_delete(monkeypatch):
    token=registered()
    for fn in [lambda:entry.update_location(OTHER,token,COARSE),lambda:entry.enter(OTHER,token,'test',test=True),lambda:entry.unregister(OTHER,token)]:
        with pytest.raises(HTTPException) as err:fn()
        assert err.value.status_code==404

@pytest.mark.parametrize('url',[
    'http://web.push.apple.com/x','https://127.0.0.1/x',
    'https://web.push.apple.com.evil.test/x','https://web.push.apple.com:22/x',
    'https://u:p@web.push.apple.com/x','https://web.push.apple.com/x#fragment'
])
def test_endpoint_cannot_be_used_as_arbitrary_server_request(url):
    with pytest.raises(HTTPException):entry.register(OWNER,sub(url),None,'normal')

def test_rejects_bad_encryption_keys_and_unsupported_location_resolution():
    invalid=sub(); invalid['keys']['p256dh']='invalid'
    with pytest.raises(HTTPException):entry.register(OWNER,invalid,None,'normal')
    unsupported=h3.latlng_to_cell(37.6688,126.7457,6)
    with pytest.raises(HTTPException):entry.register(OWNER,sub(),unsupported,'normal')

def test_entry_send_is_deduplicated_even_after_restart(monkeypatch):
    row=case(monkeypatch); token=registered(); calls=[]
    monkeypatch.setattr(webpush,'send_one',lambda *a:calls.append(a) or True)
    now=datetime.now()
    assert entry.enter(OWNER,token,row.id,now=now)=={'status':'accepted','delivery_confirmed':False}
    entry._recent_attempts.clear() # durable timestamp survives process restart
    assert entry.enter(OWNER,token,row.id,now=now+timedelta(seconds=20))['status']=='cooldown'
    assert len(calls)==1
    assert calls[0][3]['kind']=='poa' and calls[0][3]['case_id']==row.id
    assert calls[0][3]['target_res']==7
    # Current cell is replaced; no coordinate or path fields exist.
    assert entry.update_location(OWNER,token,None)['targets']==[]
    assert storage.devices.get(token).cell_res7 is None

def test_unknown_stale_future_outside_and_closed_do_not_send(monkeypatch):
    row=case(monkeypatch); token=registered()
    monkeypatch.setattr(webpush,'send_one',lambda *a:pytest.fail('Must not send'))
    now=datetime.now()
    assert entry.enter(OWNER,token,row.id,now=now+timedelta(minutes=6))['status']=='location_stale'
    assert entry.enter(OWNER,token,row.id,now=now-timedelta(seconds=10))['status']=='location_stale'
    assert entry.enter(OWNER,token,'missing')['status']=='closed'
    far=h3.latlng_to_cell(37.70,126.80,7)
    entry.update_location(OWNER,token,far)
    assert entry.enter(OWNER,token,row.id)['status']=='outside'
    row.status=CaseStatus.found
    assert entry.enter(OWNER,token,row.id)['status']=='closed'

def test_subscription_refresh_keeps_cooldown_and_owner_switch_removes_old():
    token=registered(); d=storage.devices.get(token)
    d.entry_sent_at={'case':datetime.now()};storage.devices.save(token,d)
    same=entry.register(OWNER,d.web_subscription,COARSE,'normal')
    assert same['device_id']==token and 'case' in storage.devices.get(token).entry_sent_at
    new=entry.register(OTHER,d.web_subscription,None,'normal')['device_id']
    assert storage.devices.get(token) is None and storage.devices.get(new).owner_id==OTHER

def test_stale_locations_are_excluded_from_new_incident_fanout():
    token=registered()
    assert len(devices.devices_in_cells({COARSE}))==1
    d=storage.devices.get(token);d.location_updated_at=datetime.now()-timedelta(minutes=6)
    storage.devices.save(token,d)
    assert devices.devices_in_cells({COARSE})==[]

def test_failed_send_is_retryable_but_not_a_burst(monkeypatch):
    row=case(monkeypatch);token=registered()
    monkeypatch.setattr(webpush,'send_one',lambda *a:False)
    assert entry.enter(OWNER,token,row.id)['status']=='failed'
    assert not storage.devices.get(token).sent_at
    assert entry.enter(OWNER,token,row.id)['status']=='cooldown'
    entry._recent_attempts.clear()
    monkeypatch.setattr(webpush,'send_one',lambda *a:True)
    assert entry.enter(OWNER,token,row.id)['status']=='accepted'

def test_daily_limit_and_test_notification_need_no_location(monkeypatch):
    token=registered(None)
    monkeypatch.setattr(webpush,'send_one',lambda *a:True)
    assert entry.enter(OWNER,token,'test',test=True)['status']=='accepted'
    entry._recent_attempts.clear()
    d=storage.devices.get(token);d.sent_at=[datetime.now()]*6;d.entry_sent_at={}
    storage.devices.save(token,d)
    assert entry.enter(OWNER,token,'test',test=True)['status']=='daily_limit'

def test_bridge_public_key_reaches_real_api(monkeypatch):
    monkeypatch.setattr(webpush,'public_key',lambda:'synthetic-public')
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test') as client:
            return await dispatch(client,dict(owner_id=OWNER,method='GET',path='/phase3/webpush/public-key'),enabled=True)
    status,out=asyncio.run(run())
    assert status==200 and out['key']=='synthetic-public' and out['enabled'] is True
    assert out['target_res']==7 and out['supported_location_resolutions']==[7,8,9]

def test_expired_subscription_is_removed_and_log_contains_no_payload(monkeypatch):
    token=registered();events=[]
    class Gone(Exception):
        response=SimpleNamespace(status_code=410)
    def gone(**kwargs):raise Gone()
    monkeypatch.setattr(webpush,'webpush',gone)
    monkeypatch.setattr(webpush,'append_event',lambda record,path:events.append(record))
    assert not webpush.send_one(storage.devices.get(token).web_subscription,'private-title','private-body',{})
    assert storage.devices.get(token) is None
    assert len(events)==2 and events[-1]['http_status']==410
    assert 'private' not in str(events) and 'endpoint' not in str(events)



def test_entry_preserves_selected_coverage_and_reflex_exemption(monkeypatch):
    row=case(monkeypatch); token=registered()
    far=h3.latlng_to_cell(37.70,126.80,9)
    row.current_poa={far:0.5,FINE:0.25,h3.latlng_to_cell(37.72,126.79,9):0.25}
    from app.schemas.device import Engagement
    d=storage.devices.get(token);d.engagement=Engagement.low;storage.devices.save(token,d)
    assert entry.update_location(OWNER,token,COARSE)['targets']
    d.engagement=Engagement.high;storage.devices.save(token,d)
    targets=entry.update_location(OWNER,token,COARSE)['targets']
    assert targets and targets[0]['resolution']==7
    assert set(targets[0]['cells'])==alerts.target_parent_cells(alerts.select_alert_cells(row.current_poa))
    row.current_poa=None;row.lkp=SimpleNamespace(lat=37.6688,lng=126.7457)
    d.engagement=Engagement.low;storage.devices.save(token,d)
    assert entry.update_location(OWNER,token,COARSE)['targets'][0]['kind']=='reflex'

def test_event_fanout_then_walk_entry_does_not_send_twice(monkeypatch):
    row=case(monkeypatch);token=registered();calls=[]
    monkeypatch.setattr(webpush,'send_one',lambda *a:calls.append(a) or True)
    alerts.send_alerts(row.id,[FINE],'',poa=row.current_poa)
    assert entry.enter(OWNER,token,row.id)['status']=='cooldown'
    assert len(calls)==1
    # A newly announced area is eligible immediately; same-case guard must not hide D3.
    result=alerts.send_alerts(row.id,[FINE],'',kind='new_region')
    assert result['sent']==1 and len(calls)==2


def test_completed_prediction_seeds_alert_and_unchanged_refresh_is_quiet(monkeypatch):
    monkeypatch.setattr(storage.cases, '_save', lambda _, row: row)
    row=case(monkeypatch);row.alert_delivery={};row.last_alert_poa=None;row.last_alert_at=None
    monkeypatch.setattr(storage.cases,'save',lambda *a:None)
    calls=[]
    monkeypatch.setattr(alerts,'send_alerts',lambda *a,**k:calls.append((a,k)) or {'sent':1,'failed':0,'stub':False})
    alerts.notify_prediction(row)
    assert len(calls)==1 and calls[0][1]['kind']=='poa'
    assert row.last_alert_poa==row.current_poa
    alerts.notify_prediction(row)
    assert len(calls)==1
    row.status=CaseStatus.found
    alerts.notify_prediction(row)
    assert len(calls)==1

def test_notification_failure_does_not_invalidate_prediction(monkeypatch):
    monkeypatch.setattr(storage.cases, '_save', lambda _, row: row)
    row=case(monkeypatch);row.alert_delivery={};row.last_alert_poa=None
    def fail(*a,**k):raise RuntimeError('test')
    monkeypatch.setattr(alerts,'send_alerts',fail)
    alerts.notify_prediction(row)
    assert row.status==CaseStatus.predicted and row.last_alert_poa is None


def test_synthetic_profile_verification_restricts_every_delivery_path(monkeypatch):
    import hashlib
    from app.config import settings
    row=case(monkeypatch);row.report.persona_id='e2e-profile'
    first=registered(FINE)
    second=entry.register(OWNER,sub('https://web.push.apple.com/second-device'),FINE,'normal')['device_id']
    monkeypatch.setattr(settings,'verification_push_persona_id','e2e-profile')
    monkeypatch.setattr(settings,'verification_push_device_sha256',hashlib.sha256(first.encode()).hexdigest())
    accepted=[]
    monkeypatch.setattr(webpush,'send_one',lambda subscription,*a:accepted.append(subscription['endpoint']) or True)
    # A client cannot widen the server restriction by using fine-cell entry.
    assert entry.enter(OWNER,second,row.id)['status']!='accepted'
    assert accepted==[]
    assert entry.enter(OWNER,first,row.id)['status']=='accepted'
    assert len(accepted)==1
    # Ordinary profiles retain their eligibility.
    row.report.persona_id='ordinary-profile'
    assert entry.enter(OWNER,second,row.id)['status']=='accepted'
    assert len(accepted)==2


def test_verification_without_a_valid_recipient_fails_closed(monkeypatch):
    from app.config import settings
    row=case(monkeypatch);row.report.persona_id='e2e-profile'
    token=registered(FINE)
    monkeypatch.setattr(settings,'verification_push_persona_id','e2e-profile')
    monkeypatch.setattr(settings,'verification_push_device_sha256','')
    monkeypatch.setattr(webpush,'send_one',lambda *a:pytest.fail('Unrestricted verification push'))
    assert entry.enter(OWNER,token,row.id)['status']!='accepted'
