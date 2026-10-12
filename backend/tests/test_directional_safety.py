"""Pure direction/selection contracts; not a spatial performance experiment."""
import h3,networkx as nx,pytest
from app.schemas.common import GeoPoint
from app.phase3.directional_safety import (heading, reachable_features, opposite_scores,
    select_with_safety, reachable_place_guards, add_safety_to_core)
from app.phase3.area_budget import cell_area_km2
from app.geo.h3cover import cover
ORIGIN=GeoPoint(lat=37.6652,lng=126.7483)
def cell(lat):return h3.latlng_to_cell(lat,ORIGIN.lng,9)
def test_opposite_direction_uses_reachable_roads_without_inventing_unreachable_cells():
    g=nx.MultiDiGraph()
    for node,lat in [(0,ORIGIN.lat),(1,37.672),(2,37.681),(3,37.655)]:
        g.add_node(node,x=ORIGIN.lng,y=lat)
    g.add_edge(0,1,length=800);g.add_edge(1,2,length=1000)
    # South node3 exists on this contract graph, but there is no directed route.
    features,meta=reachable_features(g,ORIGIN,2000,source_node=0)
    assert cell(37.655) not in {z[0] for z in features}
    scores,info=opposite_scores({cell(37.655):1.},ORIGIN,features,2,20,10)
    assert scores and all(z!=cell(37.655) for z in scores)
    assert abs(info['reverse_heading_deg'])<10
    assert not info['truth_used'] and not info['calibrated_probability']
    assert sum(scores.values())==pytest.approx(1.)
    unreachable=opposite_scores({cell(37.655):1.},ORIGIN,features[:1],2,20,10)[0]
    assert unreachable=={}
def test_no_heading_yields_no_guessed_direction_and_onboarding_fallback_is_explicit():
    point=h3.latlng_to_cell(ORIGIN.lat,ORIGIN.lng,9)
    assert heading({point:1.},ORIGIN)[0] is None
    direction,source=heading({point:1.},ORIGIN,[(GeoPoint(lat=37.655,lng=ORIGIN.lng),1.)])
    assert abs(abs(direction)-180)<10 and source=='onboarding_attractions'
@pytest.mark.parametrize('res',[8,9])
def test_directional_island_is_added_without_erasing_core_and_union_is_charged(res):
    center=cell(ORIGIN.lat);north=cell(37.681);poa={center:1.};safety={north:1.}
    # Enough area for a separate coarse cell and its complete geographic cover.
    selected,meta=select_with_safety(poa,safety,5.8,500,res,fraction=.2,mode='additional')
    assert center in selected and north in selected and north not in poa
    core_targets=cover(meta['core_cells'],res);targets=cover(selected,res)
    assert core_targets<=targets
    assert sum(cell_area_km2(c) for c in targets-core_targets)<=1.16+1e-9
    assert meta['total_area_km2']<=6.96+1e-9
    assert poa=={center:1.} and safety=={north:1.}
    reserved,meta=select_with_safety(poa,safety,5.8,500,res,fraction=.2,mode='reserved')
    assert meta['total_area_km2']<=5.8+1e-9
def test_invalid_parameters_and_empty_scores_fail_closed():
    p={cell(ORIGIN.lat):1.}
    with pytest.raises(ValueError):select_with_safety(p,{},5.8,500,9,fraction=float('nan'),mode='additional')
    with pytest.raises(ValueError):select_with_safety(p,{},5.8,500,9,fraction=.2,mode='unknown')
    assert select_with_safety(p,{},5.8,500,9,fraction=.2,mode='additional')[0]==list(p)
    for kw in ({'planning_speed_m_min':0},{'angular_sigma_deg':0},{'progress':2}):
        with pytest.raises(ValueError):opposite_scores(p,ORIGIN,[],2,20,10,**kw)

def test_reachable_place_across_h3_boundary_is_preserved_but_unreachable_place_is_not():
    boundary = h3.cell_to_boundary(cell(ORIGIN.lat))
    a, b = boundary[0], boundary[1]
    mid = ((a[0]+b[0])/2, (a[1]+b[1])/2)
    place = GeoPoint(lat=mid[0]+.00001, lng=mid[1])
    node_lat = mid[0]-.00001
    assert h3.latlng_to_cell(place.lat,place.lng,9) != h3.latlng_to_cell(node_lat,place.lng,9)
    graph = nx.MultiDiGraph()
    graph.add_node(0,x=place.lng,y=node_lat)
    selected, diagnostics = reachable_place_guards(graph,[place],{0:100.},200.,9)
    assert diagnostics[0]['reachable']
    assert set(selected) == {h3.latlng_to_cell(place.lat,place.lng,9),
                             h3.latlng_to_cell(node_lat,place.lng,9)}
    assert reachable_place_guards(graph,[place],{},200.,9)[0] == []

def test_outside_score_gate_avoids_spending_area_for_mostly_covered_scores():
    core = [cell(ORIGIN.lat)]
    north = cell(37.681)
    result, meta = add_safety_to_core(core,{core[0]:.9,north:.1},.29,500,9,
                                    min_outside_score_mass=.5)
    assert result == core and meta['gate_skipped']
    result, meta = add_safety_to_core(core,{core[0]:.1,north:.9},.29,500,9,
                                    min_outside_score_mass=.5)
    assert north in result and not meta['gate_skipped']
