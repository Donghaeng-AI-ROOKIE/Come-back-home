"""Phase 2-1 Top-down — EXAONE prior 를 직접 POA 분포로 변환 (MC 없음).

prior 의 반경 lognormal → LKP 중심 거리 링, 끌림점 가중치 → 가우시안 범프.
둘을 섞어 셀별 확률을 만든다.
"""

import math

from app.geo import h3grid
from app.schemas.common import GeoPoint
from app.schemas.persona import Persona
from app.schemas.prediction import PriorParams


def topdown_poa(
    lkp: GeoPoint,
    prior: PriorParams,
    persona: Persona | None,
    elapsed_hours: float,
) -> dict[str, float]:
    """prior 파라미터만으로 POA 생성. LLM은 prior 를 만들 때만 개입."""
    mu, sigma = prior.radius_lognormal.mu, prior.radius_lognormal.sigma
    # 경과 시간에 따라 중앙값 반경 확장 (Koester: 시간 경과 → 이동 반경 증가)
    median_km = math.exp(mu) * max(1.0, elapsed_hours) ** 0.5
    max_km = median_km * math.exp(2 * sigma)

    cells = h3grid.cells_within_km(lkp, max_km)
    scores: dict[str, float] = {}

    # 끌림점 위치 매핑
    attractions: list[tuple[GeoPoint, float]] = []
    if persona:
        for ap in persona.attraction_points:
            w = prior.attraction_weights.get(ap.label, 0.0)
            if w > 0:
                attractions.append((ap.location, w))

    for cell in cells:
        center = h3grid.cell_center(cell)
        d = max(h3grid.haversine_km(lkp, center), 1e-3)
        # lognormal pdf (거리 링)
        ring = math.exp(-((math.log(d) - math.log(median_km)) ** 2) / (2 * sigma ** 2)) / d
        # 끌림점 가우시안 범프 (σ=300m)
        bump = sum(w * math.exp(-(h3grid.haversine_km(center, loc) ** 2) / (2 * 0.3 ** 2))
                   for loc, w in attractions)
        scores[cell] = 0.6 * ring + 0.4 * bump * (ring + 1e-9)

    return _normalize(scores)


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    total = sum(scores.values())
    if total <= 0:
        n = len(scores)
        return {c: 1.0 / n for c in scores}
    return {c: v / total for c, v in scores.items()}
