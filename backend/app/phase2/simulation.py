"""Phase 2-2 Bottom-up (에이전트+MC) / Phase 2-3 순수 통계 MC.

워커 n명이 LKP 에서 출발해 Hashimoto 전략에 따라 이동, 종착 셀을
히스토그램으로 집계해 POA 를 만든다.

- statistical 모드: 전략 확률·Koester 거리만 사용 (AI 없음) → 베이스라인.
  Bottom-up 과의 성능 차이 = AI 개인화 기여도.
- agent 모드: 마음 예측 훅 활성화 — 심리 상태가 바뀔 때만 EXAONE 호출
  (갈림길마다 호출 × n회 비용 문제 회피 원칙). 롤아웃 수는 실모델과 동일한
  config 값(mc_rollouts_agent)을 쓴다 — E2E 가 실운영 구성을 검증해야 하므로.

이동 공간 (net 인자로 선택):
- net 있음: OSMnx 도로망 그래프 위를 걷는다 — 갈림길마다
  P(next) ∝ exp(κ·cos(방위차)) (κ = 방향 집중도, 혼란↑ → κ↓ → 랜덤에 가깝게).
  목표(끌림점)가 있으면 목표 방위, direction_keeping 은 진행 방위 유지.
  종료: 목표 도달 / Koester 거리 소진 / 막다른 노드 / 최대 스텝.
- net 없음: 연속 공간 폴백 (도로망 캐시가 없는 오프라인 환경).
"""

import math
import random

from app.config import settings
from app.geo import h3grid
from app.geo.roadnet import RoadNetwork
from app.phase2 import gauges as gauge_mod
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

_MAX_STEPS = 300  # 그래프 워커 안전 상한 (평균 엣지 ~50m × 300 = 15km)


def run_monte_carlo(
    lkp: GeoPoint,
    prior: PriorParams,
    persona: Persona | None,
    elapsed_hours: float,
    *,
    mode: str,                      # "agent" | "statistical"
    net: RoadNetwork | None = None,
    n_walkers: int | None = None,
    mind: MindState | None = None,
    seed: int | None = None,
) -> dict[str, float]:
    rng = random.Random(seed)
    n = n_walkers or (settings.mc_rollouts_agent if mode == "agent" else settings.mc_num_walkers)

    names = list(prior.strategy_probs.keys())
    probs = list(prior.strategy_probs.values())

    attraction_locs: list[tuple[GeoPoint, float]] = []
    attraction_labels: list[str] = []
    if persona:
        for ap in persona.attraction_points:
            w = prior.attraction_weights.get(ap.label, 0.0)
            if w > 0:
                attraction_locs.append((ap.location, w))
                attraction_labels.append(ap.label)

    # 그래프 모드 준비물 — 워커 루프 밖에서 1회만 계산 (nearest_node 는 선형 탐색)
    start_node = None
    attraction_nodes: list[tuple[int, float]] = []
    label_nodes: dict[str, int] = {}   # 끌림점 라벨 → 노드 (마음 재해석의 목표 전환용)
    if net is not None:
        start_node = net.nearest_node(lkp)
        attraction_nodes = [(net.nearest_node(loc), w) for loc, w in attraction_locs]
        label_nodes = {label: node for label, (node, _)
                       in zip(attraction_labels, attraction_nodes)}

    counts: dict[str, int] = {}
    for _ in range(n):
        strategy = rng.choices(names, weights=probs)[0]
        if net is not None:
            # mind 는 롤아웃별 사본 — 한 워커의 재해석이 다른 워커·케이스에 새지 않게
            endpoint = _walk_graph(rng, net, start_node, strategy, prior,
                                   attraction_nodes, elapsed_hours,
                                   persona=persona, label_nodes=label_nodes,
                                   use_mind=(mode == "agent"),
                                   mind=mind.model_copy() if mind else None)
        else:
            endpoint = _walk(rng, lkp, strategy, prior, attraction_locs, elapsed_hours,
                             use_mind=(mode == "agent"), mind=mind)
        cell = h3grid.cell_of(endpoint)
        counts[cell] = counts.get(cell, 0) + 1

    total = sum(counts.values())
    return {c: v / total for c, v in counts.items()}


# ── 그래프 워커 (도로망 위) ─────────────────────────────────────────
def _kappa(confusion: float) -> float:
    """혼란도 → 방향 집중도 κ: 혼란할수록 갈림길 선택이 랜덤에 가까워진다."""
    return max(0.2, 2.5 * (1.0 - confusion))


def _walk_graph(
    rng: random.Random,
    net: RoadNetwork,
    start_node: int,
    strategy: str,
    prior: PriorParams,
    attraction_nodes: list[tuple[int, float]],
    elapsed_hours: float,
    *,
    persona: Persona | None = None,
    label_nodes: dict[str, int] | None = None,
    use_mind: bool,
    mind: MindState | None,
) -> GeoPoint:
    """워커 1명이 도로망 위를 걷고 종착 좌표를 반환한다.

    게이지·트리거 (회의 "트리거 설계 최종본"):
    - 매 스텝 F/C/E 누적 + H/A 파생 → 로지스틱 hazard 판정
    - F 발동 → 알고리즘 처리: 휴식(남은 순변위 감소), EXAONE 미호출
    - H·A 발동 → agent 모드에서만 EXAONE reinterpret_mind 호출(워커당 최대 1회),
      응답의 혼란 등급 → κ 재계산, 목표 라벨 → target 전환 (자연어 재주입)
    """
    mu, sigma = prior.radius_lognormal.mu, prior.radius_lognormal.sigma
    total_km = rng.lognormvariate(mu, sigma) * max(1.0, elapsed_hours) ** 0.5
    if strategy == "staying_put":
        total_km *= 0.1
    elif strategy == "backtracking":
        total_km *= 0.3  # 나갔다 돌아오는 궤적의 순변위

    confusion = (mind.confusion if (use_mind and mind) else 0.5)
    kappa = _kappa(confusion)

    target_node: int | None = None
    if strategy in ("landmark_seeking", "route_following") and attraction_nodes:
        nodes, weights = zip(*attraction_nodes)
        target_node = rng.choices(list(nodes), weights=list(weights))[0]

    # 게이지 준비 — 롤아웃마다 독립 상태
    g = gauge_mod.Gauges(gauge_mod.config_for(persona))
    speed = gauge_mod.walk_speed(persona)
    f_mult = gauge_mod.fatigue_mult(persona)
    familiar = ([persona.home] + [ap.location for ap in persona.attraction_points]) \
        if persona else []
    mind_called = False

    node = start_node
    prev: int | None = None
    heading = rng.uniform(-math.pi, math.pi)
    walked_km = 0.0

    for _ in range(_MAX_STEPS):
        if target_node is not None and node == target_node:
            break  # 끌림점 도달
        nbrs = net.neighbors(node)
        if not nbrs:
            break  # 막다른 노드
        here = net.node_location(node)

        if target_node is not None:
            desired = _bearing(here, net.node_location(target_node))
        elif strategy == "random_walk":
            desired = rng.uniform(-math.pi, math.pi)
        else:  # direction_keeping / staying_put / backtracking — 진행 방위 유지
            desired = heading

        weights = []
        for nb in nbrs:
            b = _bearing(here, net.node_location(nb))
            w = math.exp(kappa * math.cos(b - desired))
            if nb == prev and len(nbrs) > 1:
                w *= 0.2  # 왔던 길 즉시 회귀 억제 (backtracking 도 새 경로로 돌아가게)
            weights.append(w)
        nxt = rng.choices(nbrs, weights=weights)[0]

        edge_len_m = float(net.edge_attrs(node, nxt).get("length", 30.0))
        walked_km += edge_len_m / 1000.0
        heading = _bearing(here, net.node_location(nxt))
        prev, node = node, nxt

        # ── 게이지 누적·트리거 ──
        env = net.env(node)
        if gauge_mod.is_water_attracted(persona):
            water = env.get("water_m")
            if isinstance(water, (int, float)) and water <= gauge_mod.WATER_ATTRACTOR_M:
                break  # 7세 미만 물 끌림 — 물가 체류 (Anderson 2012, 익사위험 지점)
        g.step(edge_len_m / speed,
               terrain=gauge_mod.terrain_difficulty(net.edge_attrs(prev, node)),
               fatigue_mult=f_mult,
               unfamiliarity=gauge_mod.unfamiliarity(net.node_location(node), familiar),
               hostile=gauge_mod.hostile_exposure(env, persona))
        if g.fatigue_fired(rng):
            g.rest()  # F 발동 — 쉬는 동안 시간이 흘러 남은 순변위가 준다 (EXAONE 미호출)
            total_km = walked_km + (total_km - walked_km) * 0.6
        if use_mind and not mind_called and persona is not None:
            fired = g.mind_fired(rng)
            if fired:
                mind_called = True  # 비용 원칙 — 워커당 EXAONE 최대 1회
                from app import llm  # 지연 임포트 (테스트에서 모킹 지점)

                mind, goal = llm.exaone.reinterpret_mind(
                    persona, mind or MindState(), g.report(fired),
                    list(label_nodes or {}))
                kappa = _kappa(mind.confusion)
                if goal is not None:
                    target_node = (label_nodes or {})[goal]  # 목표 전환 — 자연어 재주입

        if walked_km >= total_km:
            break  # Koester 거리 소진

    return net.node_location(node)


def _bearing(a: GeoPoint, b: GeoPoint) -> float:
    """a→b 방위각 (rad). 국지 평면 근사 — 수 km 스케일에서 충분."""
    dlat = b.lat - a.lat
    dlng = (b.lng - a.lng) * math.cos(math.radians(a.lat))
    return math.atan2(dlng, dlat)


# ── 연속 공간 워커 (도로망 없는 환경 폴백) ──────────────────────────
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
    """워커 1명의 종착점 — 연속 공간 (도로 제약 없음)."""
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

    return pos
