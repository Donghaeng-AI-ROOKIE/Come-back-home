"""Offline geometry checks; no map acquisition or model calls."""
import networkx as nx
import pytest
from shapely.geometry import LineString
from app.geo.roadnet import OSMnxNetwork
from app.geo.road_anchors import connect_anchors
from app.schemas.common import GeoPoint


def network(two_way=True):
    net=OSMnxNetwork();net.graph=nx.MultiDiGraph()
    net.coverage_bbox=[37.64,126.72,37.69,126.78]
    net.graph.add_node(1,x=126.74,y=37.66)
    net.graph.add_node(2,x=126.75,y=37.66)
    line=LineString([(126.74,37.66),(126.745,37.6605),(126.75,37.66)])
    net.graph.add_edge(1,2,length=910.,geometry=line,highway='footway')
    if two_way:
        net.graph.add_edge(2,1,length=910.,geometry=LineString(list(line.coords)[::-1]),highway='footway')
    return net


def test_long_edge_connects_without_relaxing_limit_or_shortening_path():
    net=network();point=GeoPoint(lat=37.6606,lng=126.745)
    assert net.road_distance_km(point,point) is None
    adapted=connect_anchors(net,[point])
    assert adapted is not net
    assert adapted.road_distance_km(point,point)==0
    assert len(net.graph)==2 and net.graph.number_of_edges()==2
    assert len(adapted.graph)==3 and adapted.graph.number_of_edges()==4
    assert nx.shortest_path_length(adapted.graph,1,2,weight='length')==pytest.approx(910)
    assert nx.shortest_path_length(adapted.graph,2,1,weight='length')==pytest.approx(910)
    assert adapted.anchor_connections[0]['snap_distance_m']<150
    assert connect_anchors(net,[point]) is adapted


def test_one_way_is_not_made_bidirectional():
    net=connect_anchors(network(False),[GeoPoint(lat=37.6606,lng=126.745)])
    assert nx.has_path(net.graph,1,2)
    assert not nx.has_path(net.graph,2,1)


def test_far_away_point_is_not_snapped_to_map():
    net=network();point=GeoPoint(lat=37.665,lng=126.745)
    assert connect_anchors(net,[point]) is net
    assert net.road_distance_km(point,point) is None


def test_outside_bbox_cannot_create_anchor():
    net=network();net.coverage_bbox=[37.64,126.72,37.6601,126.78]
    assert connect_anchors(net,[GeoPoint(lat=37.6606,lng=126.745)]) is net


def test_crossing_roads_do_not_gain_a_junction():
    net=network()
    net.graph.add_node(3,x=126.745,y=37.657)
    net.graph.add_node(4,x=126.745,y=37.664)
    net.graph.add_edge(3,4,length=800.,highway='service')
    adapted=connect_anchors(net,[GeoPoint(lat=37.6606,lng=126.7451)])
    assert not nx.has_path(adapted.graph,1,4)
    assert not nx.has_path(adapted.graph,3,2)
