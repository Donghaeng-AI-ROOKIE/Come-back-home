from datetime import datetime,timedelta
import h3,pytest
from fastapi.testclient import TestClient
from app import storage
from app.config import settings
from app.main import app
from app.phase3 import alerts,devices,webpush_entry
from app.phase3.area_budget import cell_area_km2
from app.schemas.report import MissingReport
from app.schemas.case import Case
from app.schemas.common import GeoPoint
from app.schemas.device import Platform,Engagement
@pytest.fixture(autouse=True)
def isolate():
    storage.reset_for_tests();devices.reset()
    yield
    storage.reset_for_tests();devices.reset()
def surface():
    cells=sorted(h3.grid_disk(h3.latlng_to_cell(37.6652,126.7483,9),3));n=len(cells)
    return {c:(n-i)/(n*(n+1)/2) for i,c in enumerate(cells)}
@pytest.mark.parametrize('res',[7,8,9])
def test_budget_charges_geographic_delivery_cover(res):
    p=surface();budget=1.1;chosen=alerts.select_alert_cells(p,policy='area_budget',max_area_km2=budget,target_res=res)
    assert sum(cell_area_km2(c) for c in alerts.target_parent_cells(chosen,res=res))<=budget+1e-9
    if res==9:assert chosen
    else:assert all(sum(cell_area_km2(t) for t in alerts.target_parent_cells([c],res=res))<=budget+1e-9 for c in chosen)
def test_zero_caps_bad_scores_and_deterministic_ties():
    p=surface();c=next(iter(p))
    assert alerts.select_alert_cells(p,policy='area_budget',max_area_km2=0)==[]
    assert alerts.select_alert_cells(p,policy='area_budget',max_area_km2=1,max_cells=0)==[]
    assert alerts.select_alert_cells({c:float('nan')},policy='area_budget')==[]
    assert alerts.select_alert_cells({c:-1},policy='area_budget')==[]
    with pytest.raises(ValueError):alerts.select_alert_cells(p,policy='area_budget',max_area_km2=float('nan'))
    with pytest.raises(ValueError):alerts.select_alert_cells(p,policy='unknown')
    equal={c:cell_area_km2(c) for c in p};assert alerts.select_alert_cells(equal,policy='area_budget',max_area_km2=.5,target_res=9)==alerts.select_alert_cells(dict(reversed(list(equal.items()))),policy='area_budget',max_area_km2=.5,target_res=9)
def test_d3_sees_new_selected_area_even_when_support_is_identical(monkeypatch):
    cells=list(surface());a,b=cells[0],cells[-1];monkeypatch.setattr(settings,'alert_selection_policy','area_budget');monkeypatch.setattr(settings,'push_target_res',9);monkeypatch.setattr(settings,'max_alert_area_km2',1.1*max(cell_area_km2(a),cell_area_km2(b)))
    before={a:.99,b:.01};after={a:.01,b:.99}
    assert alerts.select_new_region_cells(after,before,mass_threshold=.05)==[b]
    assert alerts.select_new_region_cells(before,before,mass_threshold=.05)==[]
@pytest.mark.parametrize('res',[8,9])
def test_api_web_entry_and_push_use_same_area_selection(monkeypatch,res):
    monkeypatch.setattr(settings,'alert_selection_policy','area_budget');monkeypatch.setattr(settings,'push_target_res',res);monkeypatch.setattr(settings,'max_alert_area_km2',1.1)
    poa=surface();report=MissingReport(id='area-r',missing_type='dementia',lkp=GeoPoint(lat=37.6652,lng=126.7483),lkp_time=datetime.now()-timedelta(hours=1));case=Case(id='area-c',report=report,lkp=report.lkp,lkp_time=report.lkp_time,current_poa=poa);storage.cases.save(case.id,case);chosen=alerts.select_alert_cells(poa);targets=alerts.target_parent_cells(chosen);assert targets
    assert set(alerts.describe_alert(case)['target_cells'])==targets
    assert webpush_entry.target_for_case(case)[1]==chosen
    client=TestClient(app);policy=client.get('/phase3/targeting-policy').json();assert policy['coverage'] is None and policy['max_area_km2']==1.1;assert policy['targeting_policy']=='selected_area_budget_geographic_cover_v1'
    captured=[];monkeypatch.setattr(alerts.push,'send',lambda tokens,**kw:captured.extend(tokens) or {'sent':len(tokens),'failed':0,'stub':True,'sent_tokens':tokens})
    for level in Engagement:
        cell=next(iter(targets));d=devices.register(f'area-{level.value}',Platform.android,cell,level)
        assert client.get('/phase3/alerts',params={'target_cell':cell}).json()[0]['case_id']==case.id
        assert webpush_entry.targets(cell,d)[0]['case_id']==case.id
    assert alerts.send_alerts(case.id,chosen,'synthetic',poa=poa)['sent']==3 and len(captured)==3

def test_d3_coarse_overlap_does_not_resend_old_delivery_cover(monkeypatch):
    monkeypatch.setattr(settings,'alert_selection_policy','area_budget');monkeypatch.setattr(settings,'push_target_res',8);monkeypatch.setattr(settings,'max_alert_cells',1);monkeypatch.setattr(settings,'max_alert_area_km2',3.)
    cells=list(surface());pairs=[(a,b) for a in cells for b in cells if a!=b and alerts.target_parent_cells([a])&alerts.target_parent_cells([b]) and alerts.target_parent_cells([b])-alerts.target_parent_cells([a])];a,b=pairs[0];old=alerts.target_parent_cells([a]);new=alerts.target_parent_cells([b])-old
    report=MissingReport(id='d3-r',missing_type='dementia',lkp=GeoPoint(lat=37.6652,lng=126.7483),lkp_time=datetime.now()-timedelta(hours=1));c=Case(id='d3-c',report=report,lkp=report.lkp,lkp_time=report.lkp_time,current_poa={a:.01,b:.99},last_alert_poa={a:.99,b:.01});storage.cases.save(c.id,c)
    for cell in old|new:devices.register('coarse-'+cell,Platform.android,cell)
    captured=[]
    def stub(tokens,**kw):
        captured.extend(tokens);assert set(kw['data']['target_cells'])==new
        return {'sent':len(tokens),'failed':0,'stub':True,'sent_tokens':tokens,'failed_tokens':[]}
    monkeypatch.setattr(alerts.push,'send',stub)
    result=alerts.notify_prediction(c)
    assert set(captured)=={'coarse-'+cell for cell in new}
    assert storage.cases.get(c.id).alert_delivery['exclude_targets']==sorted(old)


def test_literature_only_safety_cell_reaches_all_notification_surfaces(monkeypatch):
    """Independent statistical mass must become delivery at zero personal support."""
    from app.phase2.combine import alpha_pool
    from app.config import Settings
    cfg=Settings(_env_file=None,statistical_channel_definition='literature_distance_prior',
                 alert_selection_policy='area_budget',max_alert_area_km2=6.368199998062131,push_target_res=9)
    for key in ('alert_selection_policy','max_alert_area_km2','push_target_res'):
        monkeypatch.setattr(settings,key,getattr(cfg,key))
    center=h3.latlng_to_cell(37.6652,126.7483,9)
    counter=sorted(h3.grid_ring(center,4))[0]
    personal={center:1.};statistical={counter:1.}
    mixed=alpha_pool([personal,statistical],[.1,.9])
    report=MissingReport(id='safety-r',missing_type='dementia',lkp=GeoPoint(lat=37.6652,lng=126.7483),lkp_time=datetime.now()-timedelta(hours=1))
    case=Case(id='safety-c',report=report,lkp=report.lkp,lkp_time=report.lkp_time,current_poa=mixed)
    storage.cases.save(case.id,case)
    device=devices.register('stat-only',Platform.android,counter,Engagement.low)
    targets=set(alerts.describe_alert(case)['target_cells'])
    assert counter in targets and counter not in personal
    assert webpush_entry.targets(counter,device)[0]['case_id']==case.id
    client=TestClient(app)
    assert client.get('/phase3/alerts',params={'target_cell':counter}).json()[0]['case_id']==case.id
    policy=client.get('/phase3/targeting-policy').json()
    assert policy['coverage'] is None and policy['max_area_km2']==6.368199998062131
    captured=[]
    monkeypatch.setattr(alerts.push,'send',lambda tokens,**kw:captured.extend(tokens) or {'sent':len(tokens),'failed':0,'stub':True,'sent_tokens':tokens})
    result=alerts.notify_prediction(case)
    assert result['sent']==1 and captured==['stat-only']
    assert sum(cell_area_km2(c) for c in targets)<=6.368199998062131
