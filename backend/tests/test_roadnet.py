"""도로망(OSMnx) 테스트 — fixture GraphML 로드, 외부 네트워크 안 침.

fixture: 정릉동 데모 LKP(37.6061, 127.0106) 반경 800m 보행 그래프.
재생성: python scripts/make_roadnet_fixture.py
"""

from pathlib import Path

import pytest

from app.geo import h3grid
from app.geo.roadnet import OSMnxNetwork
from app.schemas.common import GeoPoint

FIXTURE = Path(__file__).parent / "fixtures" / "jeongneung_walk_800m.graphml"
DEMO_LKP = GeoPoint(lat=37.6061, lng=127.0106)


@pytest.fixture(scope="module")
def net() -> OSMnxNetwork:
    return OSMnxNetwork.from_graphml(FIXTURE)


def test_fixture_loads(net):
    assert net.graph is not None
    assert len(net.graph.nodes) > 100  # 정릉동 800m 이면 수백 노드


def test_nearest_node_is_close(net):
    node = net.nearest_node(DEMO_LKP)
    dist_km = h3grid.haversine_km(DEMO_LKP, net.node_location(node))
    assert dist_km < 0.2  # 도심이면 200m 안에 도로 노드가 있어야 함


def test_neighbors_walkable(net):
    node = net.nearest_node(DEMO_LKP)
    nbrs = net.neighbors(node)
    assert len(nbrs) >= 1
    # 이웃 노드는 그래프 안에 있고 위치 조회 가능
    for n in nbrs:
        loc = net.node_location(n)
        assert 37.5 < loc.lat < 37.7 and 126.9 < loc.lng < 127.1


def test_degree_and_edge_attrs(net):
    node = net.nearest_node(DEMO_LKP)
    assert net.degree(node) == len(net.neighbors(node))
    nbr = net.neighbors(node)[0]
    attrs = net.edge_attrs(node, nbr)
    assert "length" in attrs  # OSMnx 는 엣지 길이(m)를 항상 넣어줌


def test_env_empty_before_env_layer(net):
    # 환경 레이어 PR 전까지는 빈 dict — 시뮬레이션이 안전하게 .get() 할 수 있는 형태
    node = net.nearest_node(DEMO_LKP)
    assert net.env(node) == {}


def test_unloaded_network_raises():
    with pytest.raises(RuntimeError):
        OSMnxNetwork().nearest_node(DEMO_LKP)
