"""Selected probability regions must survive coarse targeting and fanout."""
import h3
import pytest
from shapely.ops import unary_union
from app.config import settings
from app.geo.h3cover import _polygon
from app.phase3 import alerts, devices, push, webpush_entry
from app.schemas.device import Engagement, Platform


@pytest.fixture(autouse=True)
def reset():
    from app import storage
    storage.reset_for_tests()
    yield
    storage.reset_for_tests()


def test_cross_parent_boundary_is_covered():
    # A real KINTEX fine cell extends into a different direct res7 cell.
    center=h3.latlng_to_cell(37.6652142,126.7483258,9)
    chosen=None
    for c in sorted(h3.grid_disk(center,12)):
        direct={h3.latlng_to_cell(lat,lon,7) for lat,lon in h3.cell_to_boundary(c)}
        if direct-{h3.cell_to_parent(c,7)}:
            chosen=c;break
    assert chosen
    parents=alerts.target_parent_cells([chosen])
    fine=_polygon(chosen,h3.cell_to_latlng(chosen)[1])
    coarse=unary_union([_polygon(c,h3.cell_to_latlng(chosen)[1]) for c in parents])
    assert fine.difference(coarse).area < fine.area*1e-8
    assert len(parents)>1
    assert {h3.latlng_to_cell(lat,lon,7) for lat,lon in h3.cell_to_boundary(chosen)} <= parents


def test_selected_tail_reaches_all_levels_but_outside_does_not(monkeypatch):
    center=h3.latlng_to_cell(37.6652142,126.7483258,9)
    cells=sorted(h3.grid_disk(center,12))
    far=next(c for c in reversed(cells) if h3.cell_to_parent(c,7)!=h3.cell_to_parent(center,7))
    poa={center:.55,far:.3, cells[0]:.15}
    selected=alerts.select_alert_cells(poa)
    assert far in selected and .9*poa[far]/poa[center]<settings.push_prob_threshold['low']
    parents=alerts.target_parent_cells(selected)
    weak=next(c for c in alerts.target_parent_cells([far]) if c not in alerts.target_parent_cells([center]))
    tokens=[]
    for i,level in enumerate(Engagement):
        token=f'ExponentPushToken[coverage{i:020d}]';tokens.append(token)
        devices.register(token,Platform.android,weak,level)
    devices.register('ExponentPushToken[outside000000000000000]',Platform.android,h3.latlng_to_cell(35.18,129.08,7))
    captured=[]
    def send(tokens,**kw):
        captured.extend(tokens)
        return {'sent':len(tokens),'failed':0,'sent_tokens':tokens,'stub':True}
    monkeypatch.setattr(push,'send',send)
    result=alerts.send_alerts('unit',selected,'합성',poa=poa)
    assert set(captured)==set(tokens)
    assert result['below_threshold']==0 and set(result['target_cells'])==parents
