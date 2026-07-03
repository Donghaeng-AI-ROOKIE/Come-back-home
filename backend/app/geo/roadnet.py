"""도로망 로딩 인터페이스.

백본 단계에서는 도로망 없이 연속 공간 워커로 시뮬레이션한다 (simulation.py).
정확도를 올릴 때 OSMnxNetwork 를 구현해서 워커가 도로 그래프 위를 걷게 교체:

    pip install osmnx networkx
    G = osmnx.graph_from_point((lat, lng), dist=3000, network_type="walk")

교체 지점: phase2/simulation.py 의 _step() 이 이 모듈의 RoadNetwork 를 쓰도록.
"""

from abc import ABC, abstractmethod

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
    """OSMnx 도로망 — 미구현 스텁. 위 docstring 참고."""

    def load(self, center: GeoPoint, radius_m: int) -> None:
        raise NotImplementedError("OSMnx 연동 미구현 — geo/roadnet.py docstring 참고")

    def nearest_node(self, point: GeoPoint) -> int:
        raise NotImplementedError

    def neighbors(self, node: int) -> list[int]:
        raise NotImplementedError

    def node_location(self, node: int) -> GeoPoint:
        raise NotImplementedError
