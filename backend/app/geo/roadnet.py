"""OSMnx 도로망 — 몬테카를로 워커가 걷는 그래프.

Phase 1(신고 접수)에서 LKP 반경 보행(walk) 도로망을 내려받아 캐시하고,
Phase 2 시뮬레이션이 "도로 위에서만 이동" 제약으로 사용한다.

- 다운로드는 OpenStreetMap Overpass API 1회 → GraphML 파일로 디스크 캐시.
  같은 중심/반경 재요청은 파일에서 즉시 로드한다 (신고마다 API 안 침).
- 테스트는 tests/fixtures/*.graphml 을 from_graphml() 로 직접 로드 (네트워크 불필요).
  fixture 재생성: python scripts/make_roadnet_fixture.py
- 환경 레이어(후속 PR): OSM 태그(features_from_point)·토지피복지도에서 뽑은
  속성(물가/숲/시장 인접 등)을 node_env 에 얹는다. 시뮬레이션 확률식은 이 dict 만
  바라보게 해서, 환경 데이터 소스가 바뀌어도 시뮬레이션 코드는 안 바뀐다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.config import settings
from app.geo import h3grid
from app.schemas.common import GeoPoint


class RoadNetwork(ABC):
    @abstractmethod
    def load(self, center: GeoPoint, radius_m: int) -> None: ...

    @abstractmethod
    def nearest_node(self, point: GeoPoint) -> int: ...

    @abstractmethod
    def neighbors(self, node: int) -> list[int]: ...

    @abstractmethod
    def node_location(self, node: int) -> GeoPoint: ...


class OSMnxNetwork(RoadNetwork):
    """OSMnx 보행 도로망. load() 또는 from_graphml() 후 사용."""

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        self.cache_dir = Path(cache_dir or settings.roadnet_cache_dir)
        self.graph = None                      # networkx.MultiDiGraph
        self.node_env: dict[int, dict] = {}    # 환경 레이어 부착 지점 (후속 PR)

    # ── 로딩 ────────────────────────────────────────────────────────
    def load(self, center: GeoPoint, radius_m: int) -> None:
        """LKP 중심 반경 보행 그래프 로딩 — 디스크 캐시 우선, 없으면 Overpass 다운로드."""
        import osmnx as ox

        cache = self.cache_dir / f"walk_{center.lat:.4f}_{center.lng:.4f}_{radius_m}.graphml"
        if cache.exists():
            self.graph = ox.load_graphml(cache)
            return
        self.graph = ox.graph_from_point(
            (center.lat, center.lng), dist=radius_m, network_type="walk",
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        ox.save_graphml(self.graph, cache)

    @classmethod
    def from_graphml(cls, path: str | Path) -> "OSMnxNetwork":
        """저장된 GraphML 로드 — 테스트 fixture 용 (네트워크 불필요)."""
        import osmnx as ox

        net = cls()
        net.graph = ox.load_graphml(path)
        return net

    # ── 그래프 조회 ─────────────────────────────────────────────────
    def _require_graph(self):
        if self.graph is None:
            raise RuntimeError("도로망 미로딩 — load() 또는 from_graphml() 먼저 호출")
        return self.graph

    def nearest_node(self, point: GeoPoint) -> int:
        """point 에서 가장 가까운 노드. 반경 3km 그래프는 수천 노드라 선형 탐색으로 충분
        (케이스당 소수 호출 — LKP·끌림점 스냅 용도)."""
        g = self._require_graph()
        return min(
            g.nodes,
            key=lambda n: h3grid.haversine_km(point, self._loc(g, n)),
        )

    def neighbors(self, node: int) -> list[int]:
        return list(self._require_graph().neighbors(node))

    def node_location(self, node: int) -> GeoPoint:
        return self._loc(self._require_graph(), node)

    def degree(self, node: int) -> int:
        """무방향 기준 이웃 수 — 갈림길 판정(≥3)·막다른 길 판정(1)에 사용."""
        return len(self.neighbors(node))

    def edge_attrs(self, u: int, v: int) -> dict:
        """u→v 엣지 속성 (highway 등급, length[m] 등). 멀티엣지면 첫 번째."""
        g = self._require_graph()
        data = g.get_edge_data(u, v)
        return dict(data[next(iter(data))]) if data else {}

    def env(self, node: int) -> dict:
        """노드의 환경 속성 (물가/숲/시장 인접 등) — 환경 레이어 PR 전까지는 빈 dict."""
        return self.node_env.get(node, {})

    @staticmethod
    def _loc(g, node: int) -> GeoPoint:
        d = g.nodes[node]
        return GeoPoint(lat=d["y"], lng=d["x"])


# ── 케이스 단위 공유 캐시 ───────────────────────────────────────────
_networks: dict[str, OSMnxNetwork] = {}


def get_network(center: GeoPoint, radius_m: int | None = None) -> OSMnxNetwork:
    """같은 중심/반경이면 메모리에 로딩된 그래프를 재사용한다."""
    r = radius_m or settings.roadnet_radius_m
    key = f"{center.lat:.4f}_{center.lng:.4f}_{r}"
    if key not in _networks:
        net = OSMnxNetwork()
        net.load(center, r)
        _networks[key] = net
    return _networks[key]
