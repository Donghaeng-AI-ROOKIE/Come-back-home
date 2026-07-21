"""Phase 2-2 Bottom-up (에이전트+MC) / Phase 2-3 순수 통계 MC.

워커 n명이 LKP 에서 출발해 Hashimoto 전략에 따라 이동, 종착 셀을
히스토그램으로 집계해 POA 를 만든다.

- statistical 모드: 전략 확률·Koester 거리만 사용 (AI 없음) → 베이스라인.
  Bottom-up 과의 성능 차이 = AI 개인화 기여도.
- agent 모드: 마음 예측 훅 활성화 — 심리 상태가 바뀔 때만 EXAONE 호출.
  워커 수는 두 모드 공통 500 (보행은 순수 알고리즘이라 공짜), EXAONE 실호출만
  예측당 예산(mind_call_budget)으로 제한한다: 예산 내 발동 = 실호출 + 풀 저장,
  소진 후 발동 = 풀에서 독립 표집 (_MindPool — 결정론적 마음 캐시 금지 원칙).
  워커당 전환은 최대 mind_transitions_per_walker 회(기본 2, 사이에 불응기) —
  2회차부터는 풀 표집 전용이라 실호출 예산은 그대로다 (PR #21 과제3 다회전환,
  마음 변화 시퀀스 "옛집→혼란→휴식" 복원).
  이전의 "워커 10명" 방식은 셀당 0.1 단위 분산의 히스토그램에 α=0.5 를 주는
  통계적 결함이라 폐기 (2026-07-12).

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
from app.phase2 import radius
from app.schemas.common import GeoPoint
from app.schemas.debug import MindEvent, SimTrace, WalkerTrace
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

# 마음 전환 사이 최소 스텝 (평균 엣지 ~50m × 30 ≈ 1.5km ≈ 도보 20분).
# H·A 게이지는 발동 후 리셋되지 않고 누적만 하므로, 불응기가 없으면 2회차
# 전환이 1회차 직후 몇 스텝 안에 거의 같은 게이지 상태로 발동해 다회전환이
# 무의미해진다. 계수 정밀 튜닝은 게이지 그리드서치(트랙 5)와 함께.
_MIND_REFRACTORY_STEPS = 30


class _MindPool:
    """EXAONE 마음 재해석의 호출 예산 + 결과 분포 공유 (예측 1회 스코프).

    예산 내 발동은 실호출하고 (MindState, goal) 을 풀에 저장, 예산 소진 후
    발동은 풀에서 rng 로 독립 표집한다 — 워커마다 같은 값을 박제하는
    결정론적 캐시가 아니라 "분포 저장 + 매 진입 독립 표집" (아키텍처 원칙).
    정밀화 여지: 지금은 게이지 상태와 무관하게 풀 전체에서 표집 —
    발동 사유(귀소/불안)별 풀 분리는 후속 튜닝 항목.
    """

    def __init__(self, budget: int) -> None:
        self.remaining = budget
        self.results: list[tuple[MindState, str | None]] = []

    def reinterpret(
        self,
        rng: random.Random,
        persona: Persona,
        current: MindState,
        gauge_report: str,
        labels: list[str],
        prior: PriorParams | None = None,
    ) -> tuple[MindState, str | None, str] | None:
        """(MindState, goal, source) 또는 None(예산 0 + 풀 비어있음 → 호출자 휴리스틱).

        source = "exaone"(실호출) / "stub"(예산 내 발동이나 키 없음) / "pool"(풀 표집)
        — 대시보드가 점 색을 구분하는 데 쓴다. 로직 분기에는 쓰지 않는다.
        """
        if self.remaining > 0:
            self.remaining -= 1
            from app import llm  # 지연 임포트 (테스트에서 모킹 지점)

            out = llm.exaone.reinterpret_mind(persona, current, gauge_report, labels, prior)
            self.results.append(out)
            return out[0], out[1], ("stub" if llm.exaone.is_stub else "exaone")
        return self.sample_only(rng)

    def sample_only(self, rng: random.Random) -> tuple[MindState, str | None, str] | None:
        """풀 표집 전용 — 워커의 2회차 이후 전환은 예산을 건드리지 않는다 (과제3).

        1회차만 reinterpret(예산 소비 가능)를 타게 해서, 예산 슬롯이 서로 다른
        워커의 첫 발동 문맥에 고르게 쓰이도록 유지한다 (풀 다양성 보존).
        """
        if self.results:
            mind, goal = rng.choice(self.results)
            return mind.model_copy(), goal, "pool"   # 표집된 상태도 워커별 사본
        return None


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
    trace: SimTrace | None = None,   # E2E 대시보드용 궤적·이벤트 수집 (결과 불변)
) -> dict[str, float]:
    rng = random.Random(seed)
    n = n_walkers or settings.mc_num_walkers
    # EXAONE 호출 예산은 예측 1회 스코프 — 모든 워커가 공유
    mind_pool = _MindPool(settings.mind_call_budget) if mode == "agent" else None

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
    for i in range(n):
        strategy = rng.choices(names, weights=probs)[0]
        if net is not None:
            # mind 는 롤아웃별 사본 — 한 워커의 재해석이 다른 워커·케이스에 새지 않게
            endpoint = _walk_graph(rng, net, start_node, strategy, prior,
                                   attraction_nodes, elapsed_hours,
                                   persona=persona, label_nodes=label_nodes,
                                   use_mind=(mode == "agent"),
                                   mind=mind.model_copy() if mind else None,
                                   mind_pool=mind_pool,
                                   trace=trace, walker_idx=i)
        else:
            endpoint = _walk(rng, lkp, strategy, prior, attraction_locs, elapsed_hours,
                             use_mind=(mode == "agent"), mind=mind,
                             trace=trace, walker_idx=i)
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
    mind_pool: "_MindPool | None" = None,
    trace: SimTrace | None = None,
    walker_idx: int = 0,
) -> GeoPoint:
    """워커 1명이 도로망 위를 걷고 종착 좌표를 반환한다.

    게이지·트리거 (회의 "트리거 설계 최종본"):
    - 매 스텝 F/C/E 누적 + H/A 파생 → 로지스틱 hazard 판정
    - F 발동 → 알고리즘 처리: 휴식(남은 순변위 감소), EXAONE 미호출
    - H·A 발동 → agent 모드에서만 마음 재해석
      (워커당 최대 mind_transitions_per_walker 회, 전환 사이 불응기):
      1회차만 mind_pool 예산 사용(예산 내 EXAONE 실호출, 소진 후 풀 표집),
      2회차부터는 풀 표집 전용 — 실호출 예산 불변 (PR #21 과제3 다회전환).
      응답의 혼란 등급 → κ 재계산, 목표 라벨 → target 전환 (자연어 재주입)
    """
    # Koester 분포는 LKP→발견지점 "직선 이탈거리" — 경로 길이가 아니라
    # 변위(displacement)가 이 값에 도달하면 종료한다 (테스트셋 dist_ratio 교정).
    # 표집은 p95 절단 — topdown 원판 컷과 지원 정렬 (radius.py, PR #20 후속).
    total_km = radius.sample_distance_km(rng, prior.radius_lognormal, elapsed_hours)
    if strategy == "staying_put":
        total_km *= 0.1
    elif strategy == "backtracking":
        total_km *= 0.3  # 나갔다 돌아오는 궤적의 순변위

    confusion = (mind.confusion if (use_mind and mind) else 0.5)
    kappa = _kappa(confusion)

    # route_familiarity(작업4) 폴백 준비 — 목표 끌림점의 라벨을 알아야 known_score 를
    # 찾을 수 있는데, 지금까지는 target_node(노드 ID)만 추적하고 라벨을 버리고 있었다.
    node_labels = {v: k for k, v in (label_nodes or {}).items()}   # node → label 역매핑
    route_scores = {r.route: r.score for r in (persona.route_familiarity if persona else [])}
    routine_labels = {ap.label for ap in (persona.attraction_points if persona else [])
                      if ap.origin_slot == "routine_destinations"}

    target_node: int | None = None
    target_label: str | None = None
    if strategy in ("landmark_seeking", "route_following") and attraction_nodes:
        nodes, weights = zip(*attraction_nodes)
        target_node = rng.choices(list(nodes), weights=list(weights))[0]
        target_label = node_labels.get(target_node)

    # 게이지 준비 — 롤아웃마다 독립 상태
    g = gauge_mod.Gauges(gauge_mod.config_for(persona))
    speed = gauge_mod.walk_speed(persona)
    f_mult = gauge_mod.fatigue_mult(persona)
    familiar = ([persona.home] + [ap.location for ap in persona.attraction_points]) \
        if persona else []
    mind_transitions = 0
    last_mind_step = -_MIND_REFRACTORY_STEPS   # 첫 발동은 즉시 허용

    node = start_node
    start_loc = net.node_location(start_node)
    prev: int | None = None
    heading = rng.uniform(-math.pi, math.pi)

    rec_path = trace is not None and trace.trace_path(walker_idx)
    path = [[start_loc.lat, start_loc.lng]] if rec_path else None

    for step in range(_MAX_STEPS):
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
        heading = _bearing(here, net.node_location(nxt))
        prev, node = node, nxt
        if rec_path:
            loc = net.node_location(node)
            path.append([loc.lat, loc.lng])

        # ── 게이지 누적·트리거 ──
        env = net.env(node)
        known = None
        if target_label in route_scores:
            known = route_scores[target_label]      # route_familiarity 컴파일 결과(작업5)
        elif target_label in routine_labels:
            known = gauge_mod.ROUTINE_DEFAULT_FAMILIARITY   # 자주 가는 곳 — 기본 익숙함
        g.step(edge_len_m / speed,
               terrain=gauge_mod.terrain_difficulty(net.edge_attrs(prev, node)),
               fatigue_mult=f_mult,
               unfamiliarity=gauge_mod.unfamiliarity(
                   net.node_location(node), familiar, known_score=known),
               hostile=gauge_mod.hostile_exposure(env, persona))
        displaced_km = h3grid.haversine_km(start_loc, net.node_location(node))
        if g.fatigue_fired(rng):
            g.rest()  # F 발동 — 쉬는 동안 시간이 흘러 남은 순변위가 준다 (EXAONE 미호출)
            total_km = displaced_km + (total_km - displaced_km) * 0.6
        if use_mind and persona is not None \
                and mind_transitions < settings.mind_transitions_per_walker \
                and step - last_mind_step >= _MIND_REFRACTORY_STEPS:
            fired = g.mind_fired(rng)
            if fired:
                mind_transitions += 1
                last_mind_step = step
                gauge_report = g.report(fired)
                if mind_pool is None:
                    result = None
                elif mind_transitions == 1:
                    # 1회차만 예산 소비 가능 — 풀 다양성(서로 다른 워커의 첫 문맥) 보존
                    result = mind_pool.reinterpret(
                        rng, persona, mind or MindState(), gauge_report,
                        list(label_nodes or {}), prior)
                else:
                    # 2회차부터 풀 표집 전용 — 실호출 예산 불변 (과제3 다회전환)
                    result = mind_pool.sample_only(rng)
                if result is None:
                    # 예산 0 + 풀 비어있음 — 스텁과 같은 혼란 심화 휴리스틱
                    base = mind.confusion if mind else 0.5
                    result = (MindState(status="혼란 심화",
                                        confusion=min(1.0, base + 0.2),
                                        changed=True), None, "heuristic")
                mind, goal, source = result
                kappa = _kappa(mind.confusion)
                if goal is not None:
                    target_node = (label_nodes or {})[goal]  # 목표 전환 — 자연어 재주입
                    target_label = goal
                if trace is not None:
                    trace.mind_events.append(_mind_event(
                        walker_idx, step, net.node_location(node),
                        gauge_report, source, mind, goal))

        if displaced_km >= total_km:
            break  # Koester 이탈거리(직선 변위) 도달

    if rec_path:
        trace.walkers.append(WalkerTrace(
            walker_idx=walker_idx, strategy=strategy, path=path,
            mind_fired=mind_transitions > 0))
    return net.node_location(node)


def _mind_event(
    walker_idx: int,
    step: int,
    loc: GeoPoint,
    trigger: str,
    source: str,
    mind: MindState,
    goal: str | None,
) -> MindEvent:
    """마음 재해석 이벤트 기록 — 실호출이면 EXAONE 입·출력 원문을 붙인다."""
    prompt = response = None
    if source == "exaone":
        from app import llm

        if llm.exaone.call_log and llm.exaone.call_log[-1]["kind"] == "mind":
            prompt = llm.exaone.call_log[-1]["prompt"]
            response = llm.exaone.call_log[-1]["response"]
    return MindEvent(
        walker_idx=walker_idx, step=step, location=loc, trigger=trigger,
        source=source, status=mind.status, confusion=mind.confusion, goal=goal,
        prompt=prompt, response_raw=response)


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
    trace: SimTrace | None = None,
    walker_idx: int = 0,
) -> GeoPoint:
    """워커 1명의 종착점 — 연속 공간 (도로 제약 없음).

    이전엔 이 경로(기본값)만 반경 상한이 전혀 없었다 — p95 절단으로 정렬.
    """
    total_km = radius.sample_distance_km(rng, prior.radius_lognormal, elapsed_hours)

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

    rec_path = trace is not None and trace.trace_path(walker_idx)
    path = [[pos.lat, pos.lng]] if rec_path else None

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
        if rec_path:
            path.append([pos.lat, pos.lng])

    if rec_path:
        if path[-1] != [pos.lat, pos.lng]:  # 목표 도달 break 시 마지막 점 보장
            path.append([pos.lat, pos.lng])
        trace.walkers.append(WalkerTrace(
            walker_idx=walker_idx, strategy=strategy, path=path))
    return pos
