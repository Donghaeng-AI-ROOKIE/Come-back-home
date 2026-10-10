from datetime import datetime
from uuid import uuid4
import h3
import pytest
from fastapi import HTTPException
from app import storage
from app.config import settings
from app.phase1 import intake
from app.phase3 import alerts, push, webpush_entry
from app.api import phase3
from app.cloud_bridge.policy import authorize
from app.schemas.case import CaseStatus
from app.schemas.common import GeoPoint
from app.test_scope import synthetic_owner
OWNER=str(uuid4());OTHER=str(uuid4())
POINT=GeoPoint(lat=37.6652142,lng=126.7483258)
@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    storage.reset_for_tests()
    for name,value in dict(synthetic_guardian_ids=OWNER,reflex_alert_on_intake=True,roadnet_preload=False,reverse_geocode_on_intake=False).items():monkeypatch.setattr(settings,name,value)
    monkeypatch.setattr(push,'send',lambda *a,**k:pytest.fail('Synthetic incident reached push dispatch'))
    yield
    storage.reset_for_tests()
def new_case(owner=OWNER):
    return intake.create_report(guardian_id=owner,missing_type='dementia',lkp=POINT,lkp_time=datetime.now())
def test_server_scopes_owner_and_persists_marker(monkeypatch):
    c=new_case();assert c.synthetic_test and not c.alert_delivery
    monkeypatch.setattr(settings,'synthetic_guardian_ids','')
    assert not synthetic_owner(OWNER) and storage.cases.get(c.id).synthetic_test
    assert alerts.notify_prediction(c,reflex=True)['status']=='synthetic_isolated'
    result=alerts.send_alerts(c.id,alerts.select_reflex_cells(POINT),'test',kind='reflex')
    assert result['status']=='synthetic_isolated' and result['sent']==0 and not result['stub']
def test_normal_owner_not_isolated(monkeypatch):
    monkeypatch.setattr(push,'send',lambda *a,**k:{'sent':0,'failed':0,'stub':False})
    c=new_case(OTHER);assert not c.synthetic_test
    assert alerts.notify_prediction(c,reflex=True).get('status')!='synthetic_isolated'
@pytest.mark.parametrize('status',[CaseStatus.intake,CaseStatus.predicted,CaseStatus.found])
def test_not_in_public_lists_or_entry_targets(status):
    c=new_case();c.status=status;c.closed_at=datetime.now();storage.cases.save(c.id,c)
    cell=h3.latlng_to_cell(POINT.lat,POINT.lng,7)
    assert phase3.list_active_alerts(cell)==[] and phase3.list_resolved_alerts(cell)==[]
    assert webpush_entry.targets(cell)==[]
    assert webpush_entry.deliver(type('Device',(),{'token':'not-used'})(),'x','x',{'case_id':c.id})=='synthetic_isolated'
def test_other_citizen_cannot_query_test_map_or_submit_tip():
    c=new_case()
    for action,method in [('poa','GET'),('guidance','GET'),('tips','POST'),('presence','POST')]:
        with pytest.raises(HTTPException) as exc:authorize(OTHER,method,f'/phase3/cases/{c.id}/{action}',{})
        assert exc.value.status_code==404
    assert authorize(OWNER,'GET',f'/phase3/cases/{c.id}/poa',None)
def test_client_cannot_set_isolation_flag():
    from app.api.phase1 import CreateReportIn
    request=CreateReportIn(missing_type='dementia',lkp=POINT,lkp_time=datetime.now(),synthetic_test=True)
    assert 'synthetic_test' not in request.model_dump()
