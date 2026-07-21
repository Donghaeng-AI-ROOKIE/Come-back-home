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
    # 경과 시간에 따라 중앙값 반경 확장 (√t 스케일은 radius.py 단일 소스)
    median_km = math.exp(mu) * radius.time_multiplier(elapsed_hours)
    # 원판 컷 = 분포의 p95. ISRID 분위수 적합 파라미터라 p95 가 곧 경험적
    # 95% 거리(치매 Urban 12.6km)와 일치한다. e^{2σ}(p97.7) 컷은 σ=1.48 기준
    # 원판 21km — 얇은 꼬리가 수만 셀로 퍼지는 알림 폭주의 한 축이었다.
    # MC 표집도 같은 p95 로 절단해 세 예측기의 지원을 정렬한다 (radius.py).
    max_km = radius.p95_km(prior.radius_lognormal, elapsed_hours)

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
