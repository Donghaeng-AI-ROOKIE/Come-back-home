"""Negotiated res8/9 and legacy res7 parity, offline vendor stubs only."""
from datetime import datetime, timedelta
from types import SimpleNamespace
import base64
import h3
import pytest
from pydantic import ValidationError
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient
from app import storage
from app.config import Settings, settings
from app.main import app
from app.phase1 import intake
from app.phase3 import alerts, devices, webpush, webpush_entry as entry
from app.cloud_bridge.policy import authorize
from app.schemas.device import Platform
from app.schemas.persona import PersonaType
from app.schemas.common import GeoPoint
from app.api.phase3 import LocationCellIn

OWNER='11111111-1111-4111-8111-111111111111'
POINT=GeoPoint(lat=37.6688,lng=126.7457)
FINE=h3.latlng_to_cell(POINT.lat,POINT.lng,9)
client=TestClient(app)

@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    storage.reset_for_tests();devices.reset();entry._recent_attempts.clear()
    monkeypatch.setattr(webpush,'enabled',lambda:True)
    monkeypatch.setattr(webpush,'send_one',lambda *args:True)
    yield
    storage.reset_for_tests();devices.reset();entry._recent_attempts.clear()

def subscription():
    public=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(Encoding.X962,PublicFormat.UncompressedPoint)
    encode=lambda x:base64.urlsafe_b64encode(x).decode().rstrip('=')
    return {'endpoint':'https://web.push.apple.com/synthetic-resolution',
            'keys':{'p256dh':encode(public),'auth':encode(b'a'*16)}}

def active_case():
    case=intake.create_report(missing_type=PersonaType.dementia,lkp=POINT,lkp_time=datetime.now()-timedelta(hours=1))
    case.current_poa={FINE:1.0};storage.cases.save(case.id,case)
    return case

def test_final_defaults_are_not_the_legacy_regression_fixture(monkeypatch):
    for key in ('PUSH_TARGET_RES','PERSONAL_CHANNEL_WEIGHT','ALERT_COVERAGE',
                'STATISTICAL_CHANNEL_DEFINITION','ALERT_SELECTION_POLICY','MAX_ALERT_AREA_KM2'):
        monkeypatch.delenv(key,raising=False)
    cfg=Settings(_env_file=None)
    assert (cfg.push_target_res,cfg.personal_channel_weight,cfg.alert_coverage)==(9,.3,.95)
    assert (cfg.statistical_channel_definition,cfg.alert_selection_policy,cfg.max_alert_area_km2)==('literature_distance_prior','area_budget',5.8)
    for res in ('7','8','9'):
        monkeypatch.setenv('PUSH_TARGET_RES',res)
        assert Settings(_env_file=None).push_target_res==int(res)
    for weight in (0.,.1,.299999):
        with pytest.raises(ValidationError):Settings(personal_channel_weight=weight,_env_file=None)
    for weight in (.3,.7,.9,1.):
        assert Settings(personal_channel_weight=weight,_env_file=None).personal_channel_weight==weight
    for res in (6,10,8.5):
        with pytest.raises(ValidationError):Settings(push_target_res=res,_env_file=None)

@pytest.mark.parametrize('res',[7,8,9])
def test_native_registration_lookup_and_fanout_share_resolution(monkeypatch,res):
    monkeypatch.setattr(settings,'push_target_res',res)
    cell=h3.latlng_to_cell(POINT.lat,POINT.lng,res);case=active_case()
    response=client.post('/phase3/devices',json={'token':'ExponentPushToken[resolution-contract]',
                         'platform':'android','target_cell':cell})
    assert response.status_code==200 and response.json()['location_resolution']==res
    rows=client.get('/phase3/alerts',params={'target_cell':cell}).json()
    assert [r['case_id'] for r in rows]==[case.id]
    assert rows[0]['target_res']==res and cell in rows[0]['target_cells']
    policy=client.get('/phase3/targeting-policy').json()
    assert policy['target_res']==res and policy['location_ttl_seconds']==300
    calls=[]
    from app.phase3 import push
    monkeypatch.setattr(push,'send',lambda tokens,**kw:calls.extend(tokens) or {'sent':len(tokens),'failed':0,'stub':True})
    result=alerts.send_alerts(case.id,[FINE],'synthetic',poa=case.current_poa)
    assert result['sent']==1 and calls==['ExponentPushToken[resolution-contract]']
    outside=h3.latlng_to_cell(35.17,129.07,res)
    assert client.get('/phase3/alerts',params={'target_cell':outside}).json()==[]

@pytest.mark.parametrize('res',[8,9])
def test_web_subscription_update_and_entry_share_resolution(monkeypatch,res):
    monkeypatch.setattr(settings,'push_target_res',res)
    case=active_case();cell=h3.latlng_to_cell(POINT.lat,POINT.lng,res)
    response=client.post('/phase3/webpush/subscription',json={'owner_id':OWNER,'subscription':subscription(),'target_cell':cell})
    assert response.status_code==200;token=response.json()['device_id']
    result=client.post('/phase3/webpush/location',json={'owner_id':OWNER,'device_id':token,'target_cell':cell})
    assert result.status_code==200 and result.json()['targets'][0]['resolution']==res
    sent=[]
    monkeypatch.setattr(webpush,'send_one',lambda *a:sent.append(a) or True)
    response=client.post('/phase3/webpush/enter',json={'owner_id':OWNER,'device_id':token,'case_id':case.id})
    assert response.status_code==200 and response.json()['status']=='accepted'
    assert len(sent)==1 and sent[0][3]['target_res']==res
    assert storage.devices.get(token).cell_res7 is None
    assert storage.devices.get(token).location_cell==cell
    assert client.post('/phase3/webpush/location',json={'owner_id':OWNER,'device_id':token,'target_cell':None}).json()['targets']==[]
    assert devices.location_cell(storage.devices.get(token)) is None

def test_old_cell_is_overwritten_and_history_is_not_created():
    coarse=h3.latlng_to_cell(POINT.lat,POINT.lng,7)
    devices.register('synthetic-native',Platform.android,coarse)
    devices.record_sent(['synthetic-native'])
    d=devices.register('synthetic-native',Platform.android,FINE)
    assert d.location_cell==FINE and d.cell_res7 is None
    assert coarse not in repr(d.model_dump()) and len(d.sent_at)==1

@pytest.mark.parametrize('age',[timedelta(minutes=6),timedelta(seconds=-10)])
def test_fine_cell_stale_or_future_is_not_targetable(age):
    d=devices.register('synthetic-native',Platform.android,FINE)
    d.location_updated_at=datetime.now()-age;storage.devices.save(d.token,d)
    assert devices.devices_in_cells({FINE})==[]

def test_legacy_res7_is_supported_as_overlap_without_inventing_fine_position(monkeypatch):
    monkeypatch.setattr(settings,'push_target_res',9)
    case=active_case();coarse=h3.latlng_to_cell(POINT.lat,POINT.lng,7)
    response=client.post('/phase3/devices',json={'token':'ExponentPushToken[legacy-resolution]',
                         'platform':'android','cell_res7':coarse})
    assert response.status_code==200
    assert client.get('/phase3/alerts',params={'cell_res7':coarse}).json()[0]['case_id']==case.id
    device=storage.devices.get('ExponentPushToken[legacy-resolution]')
    assert devices.location_cell(device)==coarse and h3.get_resolution(device.location_cell)==7
    assert len(devices.devices_in_cells({FINE}))==1
    assert alerts.eligible_for_alert(device,'poa',{}, {FINE})

@pytest.mark.parametrize('body',[{'cell_res7':FINE},{'target_cell':'invalid'},
    {'target_cell':h3.latlng_to_cell(POINT.lat,POINT.lng,6)},
    {'target_cell':FINE,'cell_res7':h3.latlng_to_cell(POINT.lat,POINT.lng,7)}])
def test_invalid_conflicting_and_mislabeled_cells_are_rejected(body):
    with pytest.raises(ValidationError):LocationCellIn(**body)
    payload={'token':'ExponentPushToken[invalid-resolution]','platform':'android',**body}
    assert client.post('/phase3/devices',json=payload).status_code==422
    assert storage.devices.list()==[]

def test_invalid_lookup_and_metadata_bridge_contract():
    assert client.get('/phase3/alerts',params={'target_cell':'invalid'}).status_code==422
    assert client.get('/phase3/alerts/resolved',params={'cell_res7':FINE}).status_code==422
    r=authorize(OWNER,'GET','/phase3/targeting-policy',None)
    assert r.path=='/phase3/targeting-policy' and r.body is None

def test_tied_probability_selection_is_stable():
    cells=sorted(h3.grid_disk(FINE,1));poa={c:1/len(cells) for c in reversed(cells)}
    assert alerts.select_alert_cells(poa,coverage=.2)==cells[:2]
