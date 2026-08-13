"""H3 육각격자 유틸.

100m 사각격자 대신 H3 를 쓰는 이유: 이웃 6개와의 거리가 동일해서
MC 시뮬레이션 확률 질량 집계에 왜곡이 없다 (아키텍처 결정사항).
"""

import math

import h3

from app.config import settings
from app.schemas.common import GeoPoint


def cell_of(point: GeoPoint, res: int | None = None) -> str:
    return h3.latlng_to_cell(point.lat, point.lng, res or settings.h3_resolution)


def cell_center(cell: str) -> GeoPoint:
    lat, lng = h3.cell_to_latlng(cell)
    return GeoPoint(lat=lat, lng=lng)


def cell_boundary(cell: str) -> list[GeoPoint]:
    """H3 셀의 육각형 경계 꼭짓점(위경도). 프론트 지도 폴리곤 렌더용."""
    return [GeoPoint(lat=lat, lng=lng) for lat, lng in h3.cell_to_boundary(cell)]


def parent_cells(cells: list[str], res: int) -> set[str]:
    """셀 목록을 상위 해상도의 부모 셀 집합으로 접는다.

    푸시 타겟팅에 쓴다(2026-08-05 확정). 폰은 자기 위치를 res7 셀 하나로 바꿔
    서버에 알리고, 서버는 예측 셀(res9)의 res7 부모 집합과 대조해 발송 대상을
    고른다. **폰이 좌표를 보내지 않으므로** 서버는 "어느 동네 칸"까지만 안다.

    셀 목록을 그대로 쓰지 않고 접는 이유: res9 는 ≈0.1km² 라 그 단위로 위치를
    받으면 사실상 좌표다. res7(≈5km²)이면 예측 구역(실측 17km²)을 구분하기에
    충분하면서 개인 위치는 안 드러난다 — 목적에 필요한 최소 해상도.
    """
    return {h3.cell_to_parent(c, res) for c in cells}


def cells_within_k(center: GeoPoint, k: int, res: int | None = None) -> list[str]:
    """중심 셀 포함 k-ring (grid_disk) — '격자 몇 칸' 단위 선택용 (1차 안전반경 등)."""
    return list(h3.grid_disk(cell_of(center, res), k))


def cells_within_km(center: GeoPoint, radius_km: float, res: int | None = None) -> list[str]:
    """중심점 반경 radius_km 를 덮는 H3 셀 목록."""
    res = res or settings.h3_resolution
    edge_km = h3.average_hexagon_edge_length(res, unit="km")
    k = max(1, math.ceil(radius_km / (edge_km * math.sqrt(3))))  # 육각형 중심 간격 ≈ edge·√3
    return list(h3.grid_disk(cell_of(center, res), k))


def likelihood_kernel(tip_cell: str, cells: list[str]) -> dict[str, float]:
    """제보 목격 지점 기준 셀별 L(제보|셀) 커널.

    목격 셀은 L_max, 거리에 따라 가우시안 감쇠, 먼 셀은 L_far(<1, 음의 증거).
    이 L 은 층1 혼합 likelihood `p·L + (1−p)·1` 의 입력이 된다.
    """
    l_max, l_far = settings.likelihood_l_max, settings.likelihood_l_far
    sigma = settings.likelihood_sigma_cells
    out: dict[str, float] = {}
    for cell in cells:
        try:
            d = h3.grid_distance(tip_cell, cell)
        except Exception:
            d = 10 ** 6  # 격자 거리 계산 불가 (너무 멂) → 먼 셀 취급
        out[cell] = l_far + (l_max - l_far) * math.exp(-(d ** 2) / (2 * sigma ** 2))
    return out


def haversine_km(a: GeoPoint, b: GeoPoint) -> float:
    r = 6371.0
    dlat = math.radians(b.lat - a.lat)
    dlng = math.radians(b.lng - a.lng)
    h = math.sin(dlat / 2) ** 2 + math.cos(math.radians(a.lat)) * math.cos(math.radians(b.lat)) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def move(point: GeoPoint, bearing_rad: float, dist_km: float) -> GeoPoint:
    """point 에서 bearing 방향으로 dist_km 이동한 좌표 (소반경 근사)."""
    dlat = (dist_km / 111.32) * math.cos(bearing_rad)
    dlng = (dist_km / (111.32 * math.cos(math.radians(point.lat)))) * math.sin(bearing_rad)
    return GeoPoint(lat=point.lat + dlat, lng=point.lng + dlng)
