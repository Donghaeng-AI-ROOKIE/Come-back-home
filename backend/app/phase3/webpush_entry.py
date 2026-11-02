"""Authenticated web subscriptions and on-device fine-cell entry receipts.

Only the current negotiated H3 res7/8/9 cell is retained, with a five-minute
eligibility TTL. Coordinates and movement history are not sent. A res9 cell
reveals a smaller location region. Entry is client observation, not GPS proof.
"""
import base64
import hashlib
import re
import threading
import time
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import h3
from fastapi import HTTPException

from app import storage
from app.config import settings
from app.phase3 import alerts, devices, webpush
from app.schemas.case import CaseStatus
from app.schemas.device import Platform

_lock=threading.RLock()
_recent_attempts={}
LOCATION_TTL=timedelta(minutes=5)
ENTRY_COOLDOWN=timedelta(hours=1)
MAX_DAILY=6

def valid_cell(cell):
    if cell is not None and (not h3.is_valid_cell(cell) or h3.get_resolution(cell) not in (7,8,9)):
        raise HTTPException(422,'올바른 위치 구역이 필요합니다.')
    return cell

def validate_subscription(sub):
    if not isinstance(sub,dict):raise HTTPException(422,'알림 구독이 필요합니다.')
    endpoint=sub.get('endpoint','')
    try:
        u=urlsplit(endpoint);host=u.hostname or ''
        allowed=(host in ('fcm.googleapis.com','web.push.apple.com','updates.push.services.mozilla.com')
                 or host.endswith(('.push.services.mozilla.com','.push.apple.com','.notify.windows.com')))
        if not (u.scheme=='https' and allowed and u.port in (None,443)
                and not u.username and not u.password and not u.fragment and len(endpoint)<=2048):
            raise ValueError()
        keys=sub.get('keys',{})
        decoded=[]
        for name,size in (('p256dh',65),('auth',16)):
            value=keys[name]
            if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]+={0,2}',value):raise ValueError()
            raw=base64.urlsafe_b64decode(value+'='*((-len(value))%4))
            if len(raw)!=size:raise ValueError()
            decoded.append(raw)
        from cryptography.hazmat.primitives.asymmetric import ec
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),decoded[0])
    except (ValueError,KeyError,TypeError):
        raise HTTPException(422,'지원되는 브라우저의 알림 구독을 사용해 주세요.')
    return {'endpoint':endpoint,'keys':{k:keys[k] for k in ('p256dh','auth')}}

def owned(owner,token):
    d=storage.devices.get(token)
    if d is None or d.owner_id!=owner:raise HTTPException(404,'내 알림 기기를 찾을 수 없습니다.')
    return d

def register(owner,sub,cell,engagement):
    if not webpush.enabled():raise HTTPException(503,'알림 서버를 준비 중입니다.')
    sub=validate_subscription(sub);valid_cell(cell)
    token='web-'+hashlib.sha256((owner+':'+sub['endpoint']).encode()).hexdigest()
    with _lock:
        # A browser can switch accounts; do not keep two owners for one endpoint.
        for old in devices.all_devices():
            if old.token!=token and old.web_subscription and old.web_subscription.get('endpoint')==sub['endpoint']:
                devices.unregister(old.token)
        if storage.devices.get(token) is None and sum(d.owner_id==owner for d in devices.all_devices())>=5:
            raise HTTPException(429,'알림 기기는 계정당 5개까지 등록할 수 있습니다.')
        d=devices.register(token,Platform.web,cell,engagement,web_subscription=sub)
        d.owner_id=owner;devices.set_location(d,cell)
        storage.devices.save(token,d)
    return {'device_id':token,'registered':True,'targetable':cell is not None}


def target_for_case(case):
    """Area an entry push may repeat: reflex(1차) before prediction, else the POA area.

    After a POA/D3 notification has been delivered, entry repeats **that announced
    area** (`last_alert_poa`), not the live POA. A tip's layer-1 update changes the
    live POA before its re-prediction finishes, and D3 decides afterwards whether
    the change is a new region. Following the live POA sent a 2차-worded push
    to a newly covered device ahead of the 3차 decision.
    """
    if not case.current_poa:
        return 'reflex',alerts.select_reflex_cells(case.lkp)
    return 'poa',alerts.select_alert_cells(getattr(case,'last_alert_poa',None) or case.current_poa)

def _stage_key(case_id,kind):
    """reflex(1차) is one stage; poa(2차) and new_region(3차) both announce the POA area."""
    stage='reflex' if kind=='reflex' else 'predicted'
    return hashlib.sha256(f'stage:{case_id}:{stage}'.encode()).hexdigest()

def _stage_notified(token,case_id,kind,now):
    """Has this device had a push for this case's current stage within ENTRY_COOLDOWN?

    Counts event fanout (2차 poa, 3차 new_region) and earlier entry pushes. An
    attempt still in flight counts for 60 seconds, as for event keys.
    """
    key=_stage_key(case_id,kind)
    with _lock:
        d=storage.devices.get(token)
        if d is None:return False
        if time.monotonic()-_recent_attempts.get((token,key),-1e30)<60:return True
        last=d.entry_sent_at.get(key)
        return bool(last and now-last<ENTRY_COOLDOWN)

def targets(cell,device=None):
    if cell is None:return []
    result=[]
    from app.test_scope import isolated
    for case in storage.cases.list():
        if isolated(case):continue
        if case.status in (CaseStatus.found,CaseStatus.closed):continue
        try:
            kind,cells=target_for_case(case)
            parents=alerts.target_parent_cells(cells)
            if not devices.location_in_targets(cell,parents):continue
            rel=alerts.relative_prob_by_parent(case.current_poa) if case.current_poa else {}
            if device is not None and not alerts.eligible_for_alert(device,kind,rel,parents):continue
            result.append({'case_id':case.id,'cells':sorted(parents),
                           'resolution':settings.push_target_res,'kind':kind})
        except (ValueError,TypeError):
            continue # corrupt one case must not suppress every other alert
    return result

def update_location(owner,token,cell):
    valid_cell(cell)
    with _lock:
        d=owned(owner,token)
        devices.set_location(d,cell)
        storage.devices.save(token,d)
    return {'targets':targets(cell,d),'location_ttl_seconds':int(LOCATION_TTL.total_seconds())}

def deliver(device,title,body,payload,*,test=False,now=None):
    """One duplicate guard shared by event fanout and entry; vendor acceptance only."""
    now=now or datetime.now()  # noqa: DTZ005 — 기기 기록(location_updated_at 등)과 같은 서버 지역 시각
    token=device.token
    if not test:
        case = storage.cases.get(payload.get('case_id'))
        from app.test_scope import isolated
        if isolated(case):return 'synthetic_isolated'
        if case is None or case.status in (CaseStatus.found, CaseStatus.closed):
            return 'closed'
    # A changed target area or D1 -> POA -> D3 is a different notification event.
    identity=str(payload.get('case_id',''))+':'+str(payload.get('kind',''))+':'+','.join(sorted(payload.get('target_cells',[])))
    event_key='test' if test else hashlib.sha256(identity.encode()).hexdigest()
    # Entry consults this per-stage stamp (enter); event fanout records it only.
    stage_key=None if test else _stage_key(payload.get('case_id',''),payload.get('kind',''))
    with _lock:
        d=storage.devices.get(token)
        if d is None:return 'unavailable'
        key=(token,event_key);stamp=time.monotonic()
        if stamp-_recent_attempts.get(key,-1e30)<60:return 'cooldown'
        last=d.entry_sent_at.get(event_key)
        if last and now-last<(timedelta(minutes=1) if test else ENTRY_COOLDOWN):return 'cooldown'
        # Trial notifications are limited; D1/POA/D3 retain the existing eligibility policy.
        if test and d.sent_count_24h(now)>=MAX_DAILY:return 'daily_limit'
        _recent_attempts[key]=stamp
        if stage_key:_recent_attempts[(token,stage_key)]=stamp
        for k,t in list(_recent_attempts.items()):
            if stamp-t>3600:_recent_attempts.pop(k,None)
    sent=webpush.send_one(d.web_subscription,title,body,payload)
    if sent:
        with _lock:
            current=storage.devices.get(token)
            if current is not None:
                current.entry_sent_at={k:t for k,t in current.entry_sent_at.items() if now-t<timedelta(hours=24)}
                current.entry_sent_at[event_key]=now
                if stage_key:current.entry_sent_at[stage_key]=now
                storage.devices.save(token,current)
    return 'accepted' if sent else 'failed'

def enter(owner,token,case_id,*,test=False,now=None):
    now=now or datetime.now()  # noqa: DTZ005 — 기기 기록(location_updated_at 등)과 같은 서버 지역 시각
    d=owned(owner,token)
    if not webpush.enabled():return {'status':'unavailable'}
    if test:
        status=deliver(d,'돌아오길 시험 알림','알림 연결을 확인했습니다.',{'kind':'test'},test=True,now=now)
        if status=='accepted':devices.record_sent([token],now)
        return {'status':status,'delivery_confirmed':False}
    case=storage.cases.get(case_id)
    if case is None or case.status in (CaseStatus.found,CaseStatus.closed):return {'status':'closed'}
    cell=devices.location_cell(d)
    if cell is None or d.location_updated_at is None or not timedelta(0)<=now-d.location_updated_at<=LOCATION_TTL:
        return {'status':'location_stale'}
    if not any(t['case_id']==case_id for t in targets(cell,d)):return {'status':'outside'}
    kind,cells=target_for_case(case)
    # One push per device per stage per ENTRY_COOLDOWN. The event key alone
    # changes with every new target area, so after a tip it re-sent a 2차-worded
    # `poa` push within one 15-second location tick of the 3차 `new_region` push.
    if _stage_notified(token,case.id,kind,now):return {'status':'cooldown','delivery_confirmed':False}
    look=case.report.appearance
    summary=look.summary if look and look.summary else '인상착의 정보 없음'
    result=alerts.send_alerts(case.id,cells,summary,kind=kind,poa=case.current_poa,only_tokens={token})
    return {'status':'accepted' if result['sent'] else ('cooldown' if result.get('suppressed') else 'failed'),
            'delivery_confirmed':False}

def unregister(owner,token):
    with _lock:
        owned(owner,token);devices.unregister(token)
    return {'unregistered':True}
