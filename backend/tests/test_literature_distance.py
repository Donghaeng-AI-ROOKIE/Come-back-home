from pathlib import Path
import sys,math,socket
import pytest,h3
from app.phase2.literature_distance import distance_map,cdf,MU,SIGMA,P95_Z

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def blocked(*a,**k):raise AssertionError('external call forbidden')
    monkeypatch.setattr(socket.socket,'connect',blocked)
    monkeypatch.setattr(socket,'create_connection',blocked)

def test_legacy_median_p95_and_physical_truncation_are_explicit():
    assert cdf(math.exp(MU))==pytest.approx(.5)
    assert cdf(math.exp(MU+P95_Z*SIGMA))==pytest.approx(.95,abs=2e-5)
    cells,q=distance_map(37.6652142,126.7483258,0)
    assert sum(cells.values())==pytest.approx(1)
    assert q['radius_cap_km']==.5 and q['excluded_distance_tail_mass']>0
    assert all(h3.get_resolution(c)==9 for c in cells)

def test_quad_converges_and_band_mass_is_not_cell_count_weighted():
    a,qa=distance_map(37.6652142,126.7483258,.25,bands=64)
    b,qb=distance_map(37.6652142,126.7483258,.25,bands=128)
    tv=.5*sum(abs(a.get(c,0)-b.get(c,0)) for c in set(a)|set(b))
    assert tv<.006
    assert qa['integrated_mass_before_roundoff_normalization']==pytest.approx(1,abs=1e-6)
    near=sum(v for c,v in b.items() if h3.great_circle_distance((37.6652142,126.7483258),h3.cell_to_latlng(c),unit='km')<.3)
    assert near>.25 # conditioning onto a small reachable disk raises near mass.

def test_map_boundary_never_becomes_a_silent_conditioning_filter():
    with pytest.raises(ValueError,match='exceeds verified KINTEX'):
        distance_map(37.6652142,126.7483258,4,coverage_bbox=[37.66,126.74,37.67,126.75])

@pytest.mark.parametrize('args',[(float('nan'),126.7,1),(37.6,126.7,-1),(90,126.7,1)])
def test_bad_context_fails(args):
    with pytest.raises(ValueError):distance_map(*args)

from datetime import datetime
from app.config import settings
from app.phase2 import continuous_prediction as cp
from app.schemas.case import Case
from app.schemas.report import MissingReport
from app.schemas.common import GeoPoint

def case(kind='dementia'):
    report=MissingReport(id='literature-report',missing_type=kind,lkp=GeoPoint(lat=37.6652,lng=126.7483),lkp_time=datetime(2026,10,10))
    return Case(id='literature-case',report=report,lkp=report.lkp,lkp_time=report.lkp_time)

def test_literature_channel_ignores_persona_prior_and_does_not_reuse_stat_checkpoint(monkeypatch):
    monkeypatch.setattr(settings,'statistical_channel_definition','literature_distance_prior');c=case();c.continuous_state={'statistical':{'old':1}}
    fine=h3.latlng_to_cell(c.lkp.lat,c.lkp.lng,9)
    def personal(staged,*a,**k):
        staged.continuous_state={'personal-marker':1,'statistical':{'old':1}}
        return {fine:1.},{'unresolved_mass':0}
    monkeypatch.setattr(cp,'run',personal)
    monkeypatch.setattr(cp,'_executable_policy',lambda *a:pytest.fail('statistical must not access mind program'))
    a,b,q=cp.run_pair(c,object(),object(),None,.1,seed=1)
    assert a!=b and q['channel_total_variation']>0
    assert q['statistical_definition']=='literature_distance_prior'
    assert not q['statistical_uses_onboarding_prior'] and not q['both_channels_continuous']
    assert c.continuous_state=={'personal-marker':1}
    before=c.model_dump(mode='json');cp.run_pair(c,None,None,None,.1,persist=False)
    assert c.model_dump(mode='json')==before

def test_statistical_boundary_failure_rolls_back_personal_checkpoint(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(settings,'statistical_channel_definition','literature_distance_prior');c=case();c.continuous_state={'old':1}
    def personal(staged,*a,**k):
        staged.continuous_state={'new':1};return {'personal':1.},{'unresolved_mass':0}
    monkeypatch.setattr(cp,'run',personal)
    net=SimpleNamespace(coverage_bbox=[37.66,126.74,37.67,126.75]);a,b,q=cp.run_pair(c,None,None,net,4)
    assert b=={} and q['unresolved_mass']>0 and not q['checkpoint_committed']
    assert c.continuous_state=={'old':1}

def test_three_tips_do_not_collapse_literature_only_support(monkeypatch):
    from app import storage
    from app.phase2 import pipeline
    from app.schemas.tip import Tip
    from tests.kintex_fixtures import prior
    monkeypatch.setattr(settings,'statistical_channel_definition','literature_distance_prior');monkeypatch.setattr(settings,'personal_channel_weight',.9)
    storage.reset_for_tests();c=case();c.prior=prior();c.prior_context_key=cp.prior_key(c,None)
    c.tips=[Tip(id=str(i),case_id=c.id,text='synthetic discarded tip',decision='discard') for i in range(3)]
    cells=sorted(h3.grid_disk(h3.latlng_to_cell(c.lkp.lat,c.lkp.lng,9),1));a,b=cells[:2]
    monkeypatch.setattr(pipeline.situation_link,'cached',lambda *a:[])
    monkeypatch.setattr(pipeline,'_load_roadnet',lambda *a:(None,''))
    monkeypatch.setattr(pipeline.topdown,'topdown_poa',lambda *a:{})
    monkeypatch.setattr(cp,'run_pair',lambda *a,**kw:({a_cell:1.},{b_cell:1.},{'unresolved_mass':0}))
    a_cell,b_cell=a,b
    from datetime import timedelta
    pipeline.run_prediction(c,now=c.lkp_time+timedelta(hours=1))
    assert c.baseline_poa[a]==pytest.approx(.9) and c.baseline_poa[b]==pytest.approx(.1)
    storage.reset_for_tests()
