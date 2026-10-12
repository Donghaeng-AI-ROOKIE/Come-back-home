from pathlib import Path
import sys,math,socket
import pytest,h3
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from distance_prior import distance_map,cdf,MU,SIGMA,P95_Z

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
