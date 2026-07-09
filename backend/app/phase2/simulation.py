"""Phase 2-2 Bottom-up (에이전트+MC) / Phase 2-3 순수 통계 MC.

워커 n명이 LKP 에서 출발해 Hashimoto 전략에 따라 이동, 종착 셀을
히스토그램으로 집계해 POA 를 만든다.

- statistical 모드: 전략 확률·Koester 거리만 사용 (AI 없음) → 베이스라인.
  Bottom-up 과의 성능 차이 = AI 개인화 기여도.
- agent 모드: 마음 예측 훅 활성화 — 심리 상태가 바뀔 때만 EXAONE 호출
  (갈림길마다 호출 × 500회 비용 문제 회피 원칙).

현재는 연속 공간 워커. OSMnx 도로망 연동 시 _walk() 를
geo/roadnet.RoadNetwork 위의 그래프 탐색으로 교체한다.
"""

import math
import random

from app.config import settings
from app.geo import h3grid
from app.schemas.common import GeoPoint
from app.schemas.persona import Persona
from app.schemas.prediction import MindState, PriorParams

STRATEGIES = [
    "route_following",   # 익숙한 경로 추종
    "direction_keeping", # 한 방향 유지
    "random_walk",       # 무작위 배회
    "backtracking",      # 되돌아가기
    "staying_put",       # 제자리 머무름
    "landmark_seeking",  # 끌림점(랜드마크) 지향
]


def run_monte_carlo(
    lkp: GeoPoint,
    prior: PriorParams,
    persona: Persona | None,
    elapsed_hours: float,
    *,
    mode: str,                      # "agent" | "statistical"
    n_walkers: int | None = None,
    mind: MindState | None = None,
    seed: int | None = None,
) -> dict[str, float]:
    rng = random.Random(seed)
    n = n_walkers or settings.mc_num_walkers

    names = list(prior.strategy_probs.keys())
    probs = list(prior.strategy_probs.values())

    attraction_locs: list[tuple[GeoPoint, float]] = []
    if persona:
        for ap in persona.attraction_points:
            w = prior.attraction_weights.get(ap.label, 0.0)
            if w > 0:
                attraction_locs.append((ap.location, w))

    counts: dict[str, int] = {}
    for _ in range(n):
        strategy = rng.choices(names, weights=probs)[0]
        endpoint = _walk(rng, lkp, strategy, prior, attraction_locs, elapsed_hours,
                         use_mind=(mode == "agent"), mind=mind)
        cell = h3grid.cell_of(endpoint)
        counts[cell] = counts.get(cell, 0) + 1

    total = sum(counts.values())
    return {c: v / total for c, v in counts.items()}


def _walk(
    rng: random.Random,
    lkp: GeoPoint,
    strategy: str,
    prior: PriorParams,
    attractions: list[tuple[GeoPoint, float]],
    elapsed_hours: float,
    *,
    use_mind: bool,
    mind: MindState | None,
) -> GeoPoint:
    """워커 1명의 종착점. 도로망 연동 시 이 함수를 그래프 탐색으로 교체."""
    mu, sigma = prior.radius_lognormal.mu, prior.radius_lognormal.sigma
    total_km = rng.lognormvariate(mu, sigma) * max(1.0, elapsed_hours) ** 0.5

    # agent 모드: 혼란도가 높을수록 방향 유지력이 떨어짐 (마음 예측 반영 지점)
    confusion = (mind.confusion if (use_mind and mind) else 0.5)
    wobble = 0.3 + confusion * 0.9  # 스텝별 방향 노이즈 (rad)

    if strategy == "staying_put":
        total_km *= 0.1
    elif strategy == "backtracking":
        total_km *= 0.3  # 나갔다 돌아오는 궤적의 순변위

    pos = lkp
    heading = rng.uniform(0, 2 * math.pi)
    target: GeoPoint | None = None
    if strategy in ("landmark_seeking", "route_following") and attractions:
        locs, weights = zip(*attractions)
        target = rng.choices(list(locs), weights=list(weights))[0]

    steps = 20
    step_km = total_km / steps
    for _ in range(steps):
        if target is not None:
            # 목표 방향 + 혼란 노이즈
            dlat = target.lat - pos.lat
            dlng = (target.lng - pos.lng) * math.cos(math.radians(pos.lat))
            heading = math.atan2(dlng, dlat) + rng.gauss(0, wobble * 0.5)
            if h3grid.haversine_km(pos, target) < step_km:
                pos = target
                break
        elif strategy == "direction_keeping":
            heading += rng.gauss(0, wobble * 0.3)
        elif strategy == "random_walk":
            heading = rng.uniform(0, 2 * math.pi)
        else:
            heading += rng.gauss(0, wobble)
        pos = h3grid.move(pos, heading, step_km)

        # TODO(agent 모드): 마음 예측 훅 — 상태 변화 단서가 생겼을 때만
        # exaone.predict_mind() 호출해 strategy/target 갱신.
        # 매 스텝 호출 금지 (LLM 호출 × 500회 비용 문제).

    return pos
