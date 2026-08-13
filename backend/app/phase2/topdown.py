"""Phase 2-1 Top-down — EXAONE prior 를 직접 POA 분포로 변환 (MC 없음).

prior 의 반경 lognormal → LKP 중심 거리 링, 끌림점 가중치 → 가우시안 범프.
둘을 섞어 셀별 확률을 만든다.
"""

import math

from app.geo import h3grid
from app.phase2 import radius
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
    # ISRID 는 종국 분포라 중앙값을 경과시간으로 확장하지 않는다 (√t 폐기,
    # radius.py 참조). 시간 의존성은 아래 원판 컷의 물리 상한이 전담한다.
    median_km = math.exp(mu)
    # 원판 컷 = min(통계 p95, v_max×t). 통계 p95 는 경험적 95% 거리(치매 Urban
    # 12.6km)와 일치하고, 물리 상한은 도달 불가능한 원판을 잘라낸다.
    # MC 표집도 같은 경계로 절단해 세 예측기의 지원을 정렬한다 (radius.py).
    max_km = radius.p95_km(prior.radius_lognormal, elapsed_hours,
                           radius.vmax_kmh(persona))

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
