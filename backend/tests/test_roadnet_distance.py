"""신뢰도 p 거리 계산 — 직선(haversine) vs 도로망 최단경로 테스트.

fixture: 정릉동 데모 LKP(37.6061, 127.0106) 반경 800m 보행 그래프
(jeongneung_walk_800m.graphml). 외부 네트워크 안 침.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

import networkx as nx
import pytest

from app.config import settings
from app.geo import h3grid, reachability
from app.geo.roadnet import OSMnxNetwork
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType

FIXTURE = Path(__file__).parent / "fixtures" / "jeongneung_walk_800m.graphml"
DEMO_LKP = GeoPoint(lat=37.6061, lng=127.0106)


@pytest.fixture(scope="module")
def net() -> OSMnxNetwork:
    return OSMnxNetwork.from_graphml(FIXTURE)


def _sample_pairs(net: OSMnxNetwork, n: int, seed: int = 1, min_km: float = 0.05):
    """그래프 내 임의 노드쌍 n개(직선거리 min_km 이상)를 좌표쌍으로 반환."""
    rng = random.Random(seed)
    nodes = list(net.graph.nodes)
    pairs = []
    attempts = 0
    while len(pairs) < n and attempts < n * 20:
        attempts += 1
        a, b = rng.sample(nodes, 2)
        la, lb = net.node_location(a), net.node_location(b)
        if h3grid.haversine_km(la, lb) >= min_km:
            pairs.append((la, lb))
    return pairs


# ── road_distance_km (roadnet.py) ────────────────────────────────────

def test_road_ge_haversine(net):
    """도로거리는 직선거리보다 짧을 수 없다(부동소수 오차만 여유)."""
    for a, b in _sample_pairs(net, n=40):
        hv = h3grid.haversine_km(a, b)
        rd = net.road_distance_km(a, b)
        assert rd is not None
        assert rd >= hv * 0.98


def test_urban_detour_ratio(net):
    """도심 우회계수(road/haversine)는 1보다 커야 하고(도로가 직선보다 짧을
    수 없음), 합리적 범위(1.0~3.0) 안이어야 노드 스냅·단위(m/km) 버그가
    없다고 볼 수 있다. 서울 도심 문헌값(중앙값 ≈1.3)은 참고용 주석으로만
    남긴다 — fixture 를 다른 지형(예: 성긴 외곽 도로망)으로 재생성하면
    중앙값 자체는 달라질 수 있어 하드 임계값으로 단정하지 않는다.
    """
    ratios = []
    for a, b in _sample_pairs(net, n=60):
        hv = h3grid.haversine_km(a, b)
        rd = net.road_distance_km(a, b)
        assert rd is not None
        ratios.append(rd / hv)
    ratios.sort()
    median = ratios[len(ratios) // 2]
    assert 1.0 <= median <= 3.0, f"우회계수 중앙값 이상치(스냅/단위 버그 의심): {median:.3f}"
    # 참고: 이 fixture(정릉동 800m) 의 실측 중앙값은 약 1.33 — 문헌상 서울
    # 도심 우회계수(≈1.3)와 정합. 하드 단정은 안 하지만 크게 벗어나면 확인할 것.


def test_road_distance_same_point_is_zero(net):
    p = net.node_location(next(iter(net.graph.nodes)))
    assert net.road_distance_km(p, p) == pytest.approx(0.0, abs=1e-6)


def test_road_distance_out_of_coverage_returns_none(net):
    """그래프 로딩 반경(800m) 밖의 좌표는 nearest_node()가 bbox 체크 없이
    조용히 가장 가까운 노드로 스냅해버려, 스냅을 검증 안 하면 실제보다
    훨씬 짧은 '거리'가 나온다(회귀 확인: LKP서 4km 떨어진 좌표가 0.9km로
    계산됐던 버그). 스냅 오차 안전장치가 이 경우 None 을 반환해야 한다."""
    lkp = DEMO_LKP
    far_tip = GeoPoint(lat=DEMO_LKP.lat + 0.036, lng=DEMO_LKP.lng)  # 약 4km 떨어짐
    hv = h3grid.haversine_km(lkp, far_tip)
    assert hv > 3.0, "테스트 전제 — 그래프 커버리지(800m)를 확실히 벗어나야 함"
    assert net.road_distance_km(lkp, far_tip) is None


def test_road_distance_no_path_returns_none():
    """연결 안 된 두 컴포넌트 사이는 경로가 없어 None(폴백 신호)을 반환해야 한다."""
    g = nx.MultiDiGraph()
    g.add_node(1, y=37.60, x=127.01)
    g.add_node(2, y=37.61, x=127.02)
    g.add_node(3, y=37.62, x=127.03)  # 1·2 와 연결 없는 별도 컴포넌트
    g.add_edge(1, 2, length=100.0)

    isolated_net = OSMnxNetwork()
    isolated_net.graph = g
    a = isolated_net.node_location(1)
    c = isolated_net.node_location(3)
    assert isolated_net.road_distance_km(a, c) is None


# ── reachability._distance_km 폴백 분기 ──────────────────────────────

def test_distance_km_disabled_returns_straight():
    """use_roadnet=False → 직선거리, 사유 'straight'."""
    a = GeoPoint(lat=37.60, lng=127.01)
    b = GeoPoint(lat=37.61, lng=127.02)
    d, mode = reachability._distance_km(a, b, use_roadnet=False)
    assert mode == "straight"
    assert d == pytest.approx(h3grid.haversine_km(a, b))


def test_distance_km_no_path_falls_back_to_haversine(monkeypatch):
    """도로망 조회는 되지만 경로가 없는 경우 → 직선으로 폴백, 사유 'fallback_no_path'."""

    class _StubNet:
        def road_distance_km(self, a, b):
            return None

    monkeypatch.setattr(
        "app.geo.roadnet.get_network", lambda center, radius_m=None: _StubNet()
    )
    a = GeoPoint(lat=37.60, lng=127.01)
    b = GeoPoint(lat=37.61, lng=127.02)
    d, mode = reachability._distance_km(a, b, use_roadnet=True)
    assert mode == "fallback_no_path"
    assert d == pytest.approx(h3grid.haversine_km(a, b))


def test_distance_km_disabled_network_falls_back(monkeypatch):
    """도로망 조회 자체가 예외를 던지면(그래프 미로딩 등) → 직선으로 폴백,
    사유 'fallback_disabled'."""

    def _boom(center, radius_m=None):
        raise RuntimeError("도로망 미로딩")

    monkeypatch.setattr("app.geo.roadnet.get_network", _boom)
    a = GeoPoint(lat=37.60, lng=127.01)
    b = GeoPoint(lat=37.61, lng=127.02)
    d, mode = reachability._distance_km(a, b, use_roadnet=True)
    assert mode == "fallback_disabled"
    assert d == pytest.approx(h3grid.haversine_km(a, b))


def test_distance_km_uses_roadnet_when_available(net, monkeypatch):
    monkeypatch.setattr("app.geo.roadnet.get_network", lambda center, radius_m=None: net)
    nodes = list(net.graph.nodes)
    a = net.node_location(nodes[0])
    b = net.node_location(nodes[10])
    d, mode = reachability._distance_km(a, b, use_roadnet=True)
    assert mode == "roadnet"
    assert d == pytest.approx(net.road_distance_km(a, b))


def test_distance_km_out_of_coverage_falls_back_to_haversine(net, monkeypatch):
    """그래프 커버리지 밖 좌표는 road_distance_km 이 None 을 반환하고,
    _distance_km 은 그걸 받아 haversine 으로 안전하게 폴백해야 한다."""
    monkeypatch.setattr("app.geo.roadnet.get_network", lambda center, radius_m=None: net)
    far_tip = GeoPoint(lat=DEMO_LKP.lat + 0.036, lng=DEMO_LKP.lng)
    d, mode = reachability._distance_km(DEMO_LKP, far_tip, use_roadnet=True)
    assert mode == "fallback_no_path"
    assert d == pytest.approx(h3grid.haversine_km(DEMO_LKP, far_tip))


# ── plausibility() 회귀 + 장벽 플립 ───────────────────────────────────

def test_plausibility_default_does_not_touch_roadnet(monkeypatch):
    """use_roadnet 기본값(False)일 때는 도로망을 아예 조회하지 않아야 한다(회귀 방지)."""

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("use_roadnet=False 인데 도로망이 호출됨")

    monkeypatch.setattr("app.geo.roadnet.get_network", _fail_if_called)
    now = datetime(2026, 1, 1, 12, 0, 0)
    p = reachability.plausibility(
        DEMO_LKP, now, DEMO_LKP, PersonaType.dementia,
        seen_at=now, created_at=now,
    )
    assert p == 1.0


def test_plausibility_barrier_flip(net, monkeypatch):
    """직선으로는 d_max 이내(개연성 1.0)지만, 도로망 최단경로로는 d_max를
    넘어서는(개연성 하락) 케이스 — 도로망 반영이 실제로 판정을 바꾸는지 확인.
    """
    monkeypatch.setattr("app.geo.roadnet.get_network", lambda center, radius_m=None: net)

    pairs = _sample_pairs(net, n=40, min_km=0.05)
    chosen = None
    for a, b in pairs:
        hv = h3grid.haversine_km(a, b)
        rd = net.road_distance_km(a, b)
        if rd is not None and rd > hv * 1.3:
            chosen = (a, b, hv, rd)
            break
    if chosen is None:
        # fixture 재생성 등으로 이 배율의 쌍이 안 나올 수 있음 — 이 테스트가
        # 검증하려는 건 "도로거리가 직선보다 유의미하게 길 때 판정이 실제로
        # 바뀌는가"이지 이 특정 fixture 의 지형이 아니므로 스킵으로 처리.
        pytest.skip("이 fixture 에서 우회계수 1.3배 이상 쌍을 못 찾음")
    a, b, hv, rd = chosen

    vmax = settings.reach_vmax_dementia_kmh
    target_d_max = (hv + rd) / 2  # 직선은 통과, 도로는 초과하도록 그 사이값 사용
    elapsed_h = target_d_max / vmax
    assert elapsed_h > settings.reach_min_dt_hours, "elapsed_h 가 하한에 눌리면 d_max 왜곡됨"

    lkp_time = datetime(2026, 1, 1, 12, 0, 0)
    seen_at = lkp_time + timedelta(hours=elapsed_h)

    p_straight = reachability.plausibility(
        a, lkp_time, b, PersonaType.dementia,
        seen_at=seen_at, created_at=seen_at, use_roadnet=False,
    )
    p_road = reachability.plausibility(
        a, lkp_time, b, PersonaType.dementia,
        seen_at=seen_at, created_at=seen_at, use_roadnet=True,
    )
    assert p_straight == 1.0
    assert p_road < 1.0
