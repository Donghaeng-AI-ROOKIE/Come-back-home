"""Phase 2-2 Bottom-up (에이전트+MC) / Phase 2-3 순수 통계 MC.

워커 n명이 LKP 에서 출발해 Hashimoto 전략에 따라 이동, 종착 셀을
히스토그램으로 집계해 POA 를 만든다.

- statistical 모드: 마음 재해석만 끈 베이스라인. **"AI 없음"이 아니다** —
  prior(전략 확률·끌림점 가중치·거리 분포)는 EXAONE 이 만든 값이고 pipeline 이
  두 모드에 같은 객체를 넘긴다. 따라서 bottom-up 과의 차이는 "AI 개인화
  기여도"가 아니라 **마음 재해석 층의 기여도**다. 대외 서술에서 전자로 쓰면
  과대 주장이 된다 (2026-08-04 정정).
- agent 모드: 마음 예측 훅 활성화 — 심리 상태가 바뀔 때만 EXAONE 호출.
  워커 수는 두 모드 공통 500 (보행은 순수 알고리즘이라 공짜), EXAONE 실호출만
  예측당 예산(mind_call_budget)으로 제한한다: 예산 내 발동 = 실호출 + 풀 저장,
  소진 후 발동 = 풀에서 독립 표집 (_MindPool — 결정론적 마음 캐시 금지 원칙).
  워커당 전환은 최대 mind_transitions_per_walker 회(기본 2, 사이에 불응기) —
  **회차는 층 축의 하나이고 2회차 이상도 later 층의 예산을 쓴다.** 총량만
  mind_call_budget 으로 고정된다 (2026-08-05 변경, 그 전에는 2회차가 풀 표집
  전용이라 실호출을 한 번도 못 받았다 — _MindPool 독스트링 D1).
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

# 귀소 시도의 목적지가 될 수 있는 장소 유형 (AttractionPoint.place_type).
# 근거: Rowe et al. 2011(DEM-31) — 지역사회 실종 사건에서 명시적 귀소 의도를 밝힌
# 8% 는 "과거 거주지·직장·친척 집"으로 가려 했다고 진술했다. 현재 집이 아니다.
#   "A small percentage of individuals (8%) indicated they were trying to get to
#    a former residence or work location or a relative's home."
# 그래서 현재 집(persona.home)은 여기 넣지 않는다. 해당 장소가 등록돼 있지 않으면
# 귀소 매핑을 적용하지 않는다 — 근거가 가리키지 않는 대상에 임의 폴백을 걸지 않는다.
_HOMING_PLACE_TYPES = frozenset({"past_residence", "past_home", "workplace", "relative_home"})


# ── 마음 호출 예산의 층화 배분 ───────────────────────────────────────
# 층(stratum) = 트리거 문맥을 거칠게 묶은 근사 구간. **동치류가 아니다** — 프롬프트에는
# 3등급 게이지 말고도 경과분(gauges.py 의 report 가 분 단위로 싣는다)과 장면 텍스트가
# 들어가므로, 층 하나가 서로 다른 질의 수백 건을 대표한다(실측 2026-08-06: 트리거
# 2,527건 → 고유 프롬프트 1,164건, later 층 하나가 628건). 재사용은 근사이고,
# 이 근사의 크기는 test_mind_pool_strata 가 기록한다.
#
# 축 선택 근거:
#   사유(귀소/불안) — report 의 사유 한 단어가 응답을 몰아가는 것이 실측됐다
#     (2026-08-04: 4h 워커의 88.7% 가 "귀소 시도"). 게이지 층은 독립 판정으로
#     고쳤지만 풀이 균등 표집이면 그 편향이 풀 층에서 원상복구된다.
#   혼란 등급(고/저) — C 는 스텝마다 단조 누적이라 이 축이 "얼마나 오래·낯선 곳을
#     걸었는가"의 대리 축을 겸한다. 축을 늘리지 않고 경과를 흡수한다.
#   전환 회차(1회차 / 2회차+) — 구버전은 2회차의 실호출 확률이 구조적으로 0이었다.
#     층에 넣어 그 배제를 없앤다.
#
# **순서 = 관측 빈도 내림차순.** 쿼터는 divmod 로 선언 순서대로 나가므로 순서가
# 곧 예산 부족 시의 우선순위다. 정릉·500워커·seed 42~53 실측 빈도:
#   귀소저 0.441 > later 0.405 > 불안저 0.110 > 귀소고 0.030 > 불안고 0.005
# 알파벳·정의 순서로 두면 최빈 층(later, 트리거의 40%)이 맨 뒤로 밀려 budget 3·4 에서
# 쿼터 0 이 되고, 이 배분이 없애려던 2회차 구조적 배제가 그대로 재발한다
# (적대검증 2026-08-06: budget 3 에서 12 seed 중 8개가 2회차 실호출 0건).
# config.py 가 budget 3 을 "더 조일 때의 예비 카드"로 명시하고 있어 실사용 구간이다.
_STRATA: tuple[tuple, ...] = (("귀소", 0), ("later",), ("불안", 0), ("귀소", 1), ("불안", 1))

_LATER = ("later",)


def _confusion_level(value: float) -> int:
    """Gauges.report 와 같은 눈금(0.4/0.7) — 층 키가 프롬프트 문장과 어긋나지 않게."""
    return 2 if value >= 0.7 else (1 if value >= 0.4 else 0)


def stratum_key(confusion_gauge: float, reason: str, transitions: int) -> tuple:
    """트리거 문맥의 층. transitions 는 이번 전환을 포함한 회차(1부터)."""
    if transitions >= 2:
        return _LATER
    return (reason, 1 if _confusion_level(confusion_gauge) == 2 else 0)


def _stratum_distance(a: tuple, b: tuple) -> float:
    """층 사이 거리 — 재사용 가중치의 입력. 값의 서열만 의미가 있다."""
    if a == b:
        return 0.0
    a_late, b_late = a[0] == "later", b[0] == "later"
    if a_late != b_late:
        return 2.0          # 마음이 바뀌기 전/후 — 가장 먼 축
    if a_late:
        return 0.0
    return (2.0 if a[0] != b[0] else 0.0) + (1.0 if a[1] != b[1] else 0.0)


class _MindPool:
    """EXAONE 마음 재해석의 호출 예산 + 결과 분포 공유 (예측 1회 스코프).

    예산 내 발동은 실호출하고 (층키, MindState, goal) 을 풀에 저장, 예산이 없는
    발동은 풀에서 rng 로 독립 표집한다 — 워커마다 같은 값을 박제하는 결정론적
    캐시가 아니라 "분포 저장 + 매 진입 독립 표집" (아키텍처 원칙).

    ## 선착순 배분을 층화로 바꾼 이유 (2026-08-05 실측)

    구버전은 예산을 **도착 순서대로** 내줬다. 워커는 i.i.d. 라 "앞쪽 워커라서
    초기 시간대만 본다"는 서술은 정확하지 않다 — 워커 0 도 자기 궤적의 끝까지
    걷는다. 실제 결함은 셋이었다 (정릉·500워커·seed 42/43/44, LLM 스텁):

      D1 구조적 배제 — 1회차 전환만 예산을 쓸 수 있어 **실호출의 100% 가 1회차**인데
         소비의 38~42% 는 2회차다. 2회차는 정의상 게이지가 더 찬 문맥이라,
         실호출 문맥의 혼란 등급이 체계적으로 낮다(18런 중 "높음" 1건, 전체는 13~24%).
      D2 꼬리 층 누락 — 5개는 편향된 주변분포에서의 i.i.d. 표본이다. H 는 경과에
         정비례해 자라고 A 는 E 가 없으면 작아서, 5표본에 "불안"이 한 건도 안
         들어가는 seed 가 나온다.
      D3 매칭 부재 — sample_only 가 균등 표집이라 불안으로 발동한 워커가 귀소
         문맥의 답을 받는다. 게이지 층에서 고친 유도신문 편향의 원상복구다.

    ## 효과 귀속 — 무엇이 무엇을 고치는가 (적대검증 2026-08-06 반영)

    ⚠ **"예산을 늘려도 안 줄어드니 예산 문제가 아니다"라고 쓰지 말 것.** 구버전은
    D1 때문에 2회차(트리거의 40%)가 정의상 영구 미커버라, 미커버 지표의 바닥이
    그 비중에 고정된다. 예산을 100배로 올려도 그 아래로 안 내려간다 — 지표가
    예산에 무반응인 것은 예산이 무의미해서가 아니라 D1 이 바닥을 박아놨기
    때문이다. 층 정의와 독립인 축(피로등급 × 경과구간)으로 재면 구버전도 예산에
    강하게 반응한다(b5 37% → b100 4~7%). 이 PR 이 PR #103 에 제기한 비판이
    같은 형태로 이 PR 에 적용된다.

    실측 귀속 (정릉·500워커·seed 42~53 = n12, LLM 스텁, experiments/mind_strata):
      - 미커버(회차×혼란) 축: 구버전 45.6% → D1 게이트 제거만 27.9% → 층화 27.8%.
        **층화의 순증은 노이즈 안(-0.1%p ±3.5).** 이 축의 개선은 전부 D1 몫이다.
      - 꼬리 층 축: "불안 층 실호출 0건" seed 비율 42% → **67%(게이트 제거만,
        악화)** → **0%(층화)**. 2회차가 예산 경쟁에 들어오면 희소한 불안 층을
        밀어내므로, D2 보장은 **층화만의 고유 기여**다. 층화가 사는 근거는 이쪽이다.

    D1 은 회차를 층 축에 넣은 것이, D2 는 층당 쿼터가, D3 는 거리 가중 표집이
    고친다. D3 의 효과는 **아직 미측정** — 스텁은 층과 무관하게 같은 MindState
    (goal=None, behavior="")를 반환하므로 배달되는 마음이 상수다(exaone.py 참조).
    정확일치·기대 층거리 수치는 마음이 아니라 **층 라벨의 통계**다.
    """

    def __init__(self, budget: int, n_walkers: int = 1) -> None:
        # 층별 전용 쿼터. 예산이 층 수보다 적으면 앞쪽 층만 전용 슬롯을 갖고,
        # 나머지 층은 회수된 공용 예비(free)로 커버된다.
        base, extra = divmod(max(0, budget), len(_STRATA))
        self.quota = {s: base + (1 if i < extra else 0) for i, s in enumerate(_STRATA)}
        self.free = 0
        self.n_walkers = max(1, n_walkers)
        self.entries: list[tuple[tuple, MindState, str | None]] = []

    @property
    def remaining(self) -> int:
        """남은 실호출 슬롯 총량 — 기존 계측·테스트가 읽는 이름을 유지한다."""
        return sum(self.quota.values()) + self.free

    # ── 배분 ────────────────────────────────────────────────────────
    def _reclaim(self, progress: float) -> None:
        """미사용 전용 쿼터를 공용 예비로 회수 — 예산을 남기지 않기 위해.

        워커가 i.i.d. 라 층 도착은 정상과정이다. 진행률 임계 이후까지 나타나지
        않은 층을 계속 기다리면 얻는 것은 거의 없고 남은 워커가 쓸 풀만 얇아진다.
        """
        if progress < settings.mind_pool_release_p:
            return
        for s, q in self.quota.items():
            if q > 0:
                self.free += q
                self.quota[s] = 0

    def _grant(self, key: tuple, progress: float) -> bool:
        """슬롯을 내줄지 판정. 회수는 여기서 한다 — 슬롯 배분의 유일한 입구라
        호출자가 _reclaim 을 빠뜨려 예산이 남는 경로를 만들 수 없다."""
        self._reclaim(progress)
        if self.quota.get(key, 0) > 0:
            self.quota[key] -= 1
            return True
        if self.free > 0:
            covered = any(k == key for k, _, _ in self.entries)
            # 미커버 층이면 즉시. 이미 대표가 있는 층의 2번째 표본은 진행률
            # 임계 이후에만 — 빈발 층이 예비를 먼저 삼키는 것을 늦춘다.
            if not covered or progress >= settings.mind_pool_widen_p:
                self.free -= 1
                return True
        return False

    def reinterpret(
        self,
        rng: random.Random,
        persona: Persona,
        current: MindState,
        gauge_report: str,
        labels: list[str],
        prior: PriorParams | None = None,
        scene: str | None = None,
        *,
        key: tuple | None = None,
        walker_idx: int = 0,
    ) -> tuple[MindState, str | None, str] | None:
        """(MindState, goal, source) 또는 None(예산 0 + 풀 비어있음 → 호출자 휴리스틱).

        source = "exaone"(실호출) / "stub"(예산 내 발동이나 키 없음) / "pool"(풀 표집)
        — 대시보드가 점 색을 구분하는 데 쓴다. 로직 분기에는 쓰지 않는다.

        key=None 이면 층화 없이 총량만 보는 구버전 동작으로 떨어진다(하위호환).
        """
        stratum = key if key is not None else _STRATA[0]
        if self._grant(stratum, walker_idx / self.n_walkers):
            from app import llm  # 지연 임포트 (테스트에서 모킹 지점)

            # rng 전달 — 후보 나열 순서를 풀 엔트리마다 섞는다(순서 편향 제거,
            # 시드 재현성은 롤아웃 rng 로 유지).
            out = llm.exaone.reinterpret_mind(persona, current, gauge_report, labels,
                                              prior, scene, rng=rng)
            self.entries.append((stratum, out[0], out[1]))
            return out[0], out[1], ("stub" if llm.exaone.is_stub else "exaone")
        return self.sample_only(rng, key=key)

    # ── 재사용 매칭 ─────────────────────────────────────────────────
    def sample_only(
        self, rng: random.Random, *, key: tuple | None = None,
    ) -> tuple[MindState, str | None, str] | None:
        """풀 표집 — 현재 문맥과 가까운 층의 엔트리에 더 큰 확률을 준다.

        가중치 w = exp(-λ·거리), λ = settings.mind_pool_match_strength.
        λ=0 이면 구버전(문맥 무관 균등)과 완전히 같아 ablation 끔 상태가 된다.
        λ 를 무한대(하드 매칭)로 두지 않는 것이 아키텍처 원칙 준수다 — 층당
        엔트리가 1개일 때 하드 매칭은 사실상 결정론적 마음 캐시가 된다. 유한 λ 는
        "분포 저장 + 매 진입 독립 표집"을 유지하면서 기대값만 문맥에 맞춘다.
        표집된 값에 노이즈를 주입하지 않는다(LLM 출력 위조 금지).
        """
        if not self.entries:
            return None
        lam = settings.mind_pool_match_strength
        if key is None or lam <= 0.0:
            _, mind, goal = rng.choice(self.entries)
        else:
            weights = [math.exp(-lam * _stratum_distance(key, k))
                       for k, _, _ in self.entries]
            _, mind, goal = rng.choices(self.entries, weights=weights)[0]
        return mind.model_copy(), goal, "pool"   # 표집된 상태도 워커별 사본


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
    mind_pool = (_MindPool(settings.mind_call_budget, n)
                 if mode == "agent" else None)   # n = 진행률 기반 쿼터 회수의 분모

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

    # 물리 도달 상한용 v_max — 워커마다 같으므로 루프 밖에서 1회 (radius.py)
    v_max = radius.vmax_kmh(persona)

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
                                   mind_pool=mind_pool, v_max_kmh=v_max,
                                   trace=trace, walker_idx=i)
        else:
            endpoint = _walk(rng, lkp, strategy, prior, attraction_locs, elapsed_hours,
                             use_mind=(mode == "agent"), mind=mind,
                             v_max_kmh=v_max, trace=trace, walker_idx=i)
        cell = h3grid.cell_of(endpoint)
        counts[cell] = counts.get(cell, 0) + 1

    total = sum(counts.values())
    return {c: v / total for c, v in counts.items()}


# ── 그래프 워커 (도로망 위) ─────────────────────────────────────────
def _kappa(confusion: float) -> float:
    """혼란도 → 방향 집중도 κ: 혼란할수록 갈림길 선택이 랜덤에 가까워진다.

    ⚠ 이 경로만으로는 집계 POA 가 안 움직인다 (2026-08-04 채널별 ablation,
    500워커×seed5): 혼란 "상"(κ=0.375)과 "하"(κ=1.625)의 종착 분포 차이가
    seed 노이즈의 1.12배 — 각도 집중도는 워커를 모으면 상쇄되고, 종료는
    prior 가 뽑은 직선 변위가 정하기 때문이다. 그래서 문헌이 실제로 지지하는
    소비처(_recognizes_destination)를 따로 뒀다. κ 는 개별 궤적의 사실성
    담당으로 남긴다 — 대시보드 궤적과 시연 설명이 이 값에 걸려 있다.
    """
    return max(0.2, 2.5 * (1.0 - confusion))


def _recognizes_destination(rng: random.Random, confusion: float) -> bool:
    """끌림점에 닿았을 때 그곳을 목적지로 알아보는가.

    근거(코퍼스 원문 대조):
    - CLM-0023 (DEM-34 p6) — "if a PWD was driving a routine route but became
      distracted and drove past their destination, they might have a difficult
      time recognizing their destination when they turned around and approached
      the location from a different direction." 즉 도착이 곧 인지가 아니다.
    - CLM-0022 (DEM-34 p6) — 진행되면 익숙한 주변에서도 길찾기가 어려워진다.
    - CLM-0008 (DEM-24 p6) — 익숙한 장소에서도 길찾기 표시를 못 알아볼 수 있다.
    호출부는 실패 시 목표를 되찾지 않는다 — CLM-0015 (DEM-31 p6) "unable to
    recover from way finding errors".

    파생 효과로 DEM-32 p8 의 "길찾기 효과 저하 → 지속 보행(PW) 증가"(CLM-0028)
    가 별도 계수 없이 따라온다: 목적지를 못 알아본 워커는 변위 상한까지 계속
    걷는다. 그래서 지속 보행을 위한 파라미터를 따로 두지 않는다(이중계상 방지).

    실패확률 = confusion × strength. 인식 실패율을 보고한 연구가 코퍼스 13편에
    없어 "혼란도를 그대로 실패확률로 읽는다"는 최소가정을 쓴다 — κ 계수 2.5 와
    같은 지위의 잠정값이다(docs/혼란도_수치_근거_정리.md 2절). 최적값 주장 금지,
    settings.confusion_miss_strength 는 민감도 노브다.
    """
    strength = settings.confusion_miss_strength
    if strength <= 0.0:
        return True
    return rng.random() >= min(1.0, confusion * strength)


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
    v_max_kmh: float | None = None,
    trace: SimTrace | None = None,
    walker_idx: int = 0,
) -> GeoPoint:
    """워커 1명이 도로망 위를 걷고 종착 좌표를 반환한다.

    게이지·트리거 (회의 "트리거 설계 최종본"):
    - 매 스텝 F/C/E 누적 + H/A 파생 → 로지스틱 hazard 판정
    - F 발동 → 알고리즘 처리: 휴식(남은 순변위 감소), EXAONE 미호출
    - H·A 발동 → agent 모드에서만 마음 재해석
      (워커당 최대 mind_transitions_per_walker 회, 전환 사이 불응기):
      **회차 분기 없음** — 매 전환이 자기 층(stratum_key)으로 예산을 신청하고,
      층 쿼터가 남아 있으면 EXAONE 실호출, 아니면 풀에서 문맥거리 가중 표집한다.
      2회차 이상은 later 층을 쓴다 (2026-08-05, 그 전에는 1회차만 예산을 썼다).
      응답의 혼란 등급 → κ 재계산, 목표 라벨 → target 전환 (자연어 재주입)
    """
    # Koester 분포는 LKP→발견지점 "직선 이탈거리" — 경로 길이가 아니라
    # 변위(displacement)가 이 값에 도달하면 종료한다 (테스트셋 dist_ratio 교정).
    # 표집은 p95 절단 — topdown 원판 컷과 지원 정렬 (radius.py, PR #20 후속).
    # 상한 = min(통계 p95, v_max×경과시간) 이라 도달 불가능한 변위는 안 나온다.
    total_km = radius.sample_distance_km(rng, prior.radius_lognormal,
                                         elapsed_hours, v_max_kmh)
    if strategy == "staying_put":
        total_km *= 0.1
    elif strategy == "backtracking":
        total_km *= 0.3  # 나갔다 돌아오는 궤적의 순변위

    confusion = (mind.confusion if (use_mind and mind) else 0.5)
    kappa = _kappa(confusion)

    # 혼란도가 "실제 판단에서 나온 값"인가. MindState 기본값 0.5 는 신호가 아니라
    # 중립 플레이스홀더라, 그 값으로 도달 실패를 걸면 근거 없는 페널티가 된다.
    #   실측(2026-08-04, dem3 실호출): 전 워커에 걸면 알림셀 1h 14.0→19.3 / 4h
    #   16.7→23.0 인데, 발동한 워커에만 걸면 15.7 / 17.3 이다. 즉 증가분의 2/3 이상이
    #   플레이스홀더가 만든 가짜였다. statistical 모드를 제외한 것과 같은 이유다.
    # changed=True 는 (a) 마음 재해석이 실제로 판정했거나 (b) 상류가 페르소나 단위
    # 혼란도를 채워 넣은 경우다. 혼란도 규칙 산정이 들어오면 (b) 로 전 워커·전 구간
    # 적용이 자동으로 정당해진다 — 그때 이 게이트를 손댈 필요가 없다.
    confusion_known = bool(use_mind and mind and mind.changed)

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

    # 마음 재해석의 behavior 가 켜졌을 때만 쓰는 보행 모드 (settings.mind_behavior_enabled).
    # 매핑 근거는 아래 각 분기 주석 참조 — 근거가 없는 라벨은 매핑하지 않는다.
    #   homing  — 과거 거주지·직장 방향으로 걷되 **도달 판정을 걸지 않는다**.
    #   roaming — 목표를 해제하고 매 스텝 무작위 방위.
    homing_loc: GeoPoint | None = None
    roaming = False

    # 귀소 후보 좌표 — 등록된 끌림점 중 과거 장소 유형만. 없으면 None 이고,
    # 그 경우 "귀소 시도" 라벨이 와도 보행을 바꾸지 않는다(사용자 결정 2026-08-02).
    homing_candidate: GeoPoint | None = None
    if persona is not None:
        for ap in persona.attraction_points:
            if ap.place_type in _HOMING_PLACE_TYPES:
                homing_candidate = ap.location
                break

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
            # 인식 판정은 혼란도가 실제 판단일 때만 건다(confusion_known 주석 참조).
            # statistical 모드가 빠지는 것도 같은 이유다 — 그쪽 confusion 은 신호가
            # 아니라 중립 기본값이고, 걸면 두 모드의 비교 자체가 무의미해진다.
            # (실측: 기준선에 걸면 route_familiarity 의 known_score 가 게이지에
            # 도달하지 못해 기존 계약 2건이 깨진다.)
            if not confusion_known or _recognizes_destination(rng, confusion):
                break  # 끌림점 도달 — 알아보고 멈춘다
            # 못 알아보고 지나친다 (CLM-0023). 목표를 되찾지 않는 것이 핵심 —
            # CLM-0015 "스스로 회복하지 못한다". target_label 도 함께 비워
            # 익숙함 점수(known_score) 조회도 끊는다: 목적지를 잃은 워커에게
            # 그 경로가 익숙하다는 가정을 계속 줄 근거가 없다. 부작용으로
            # 낯섦도가 올라 혼란 게이지 C 가 빨리 차고 다음 재해석이 앞당겨진다.
            target_node = target_label = None
        nbrs = net.neighbors(node)
        if not nbrs:
            break  # 막다른 노드
        here = net.node_location(node)

        if homing_loc is not None:
            # 귀소 시도 — 과거 장소 방위로 걷되 도달 판정은 없다. 문헌이 기술하는 것은
            # 귀가의 성공이 아니라 실패다(DEM-34: "the PWD can fail to return home and
            # require a search to be located"). 판정 지시서의 라벨 정의도 "길을 제대로
            # 찾는지는 무관 — 의도 기준"이다. 방향만 기울이고, 얼마나 빗나가는지는
            # 기존 혼란도 커널(kappa)이 결정한다.
            desired = _bearing(here, homing_loc)
        elif target_node is not None:
            desired = _bearing(here, net.node_location(target_node))
        elif roaming or strategy == "random_walk":
            desired = rng.uniform(-math.pi, math.pi)
        else:  # direction_keeping / staying_put / backtracking — 진행 방위 유지
            desired = heading

        weights = []
        for nb in nbrs:
            b = _bearing(here, net.node_location(nb))
            w = math.exp(kappa * math.cos(b - desired))
            # 도로 위계 선호 — 간선 기피·이면 선호 (치매 한정, 기획팀 논문조사 2번)
            w *= gauge_mod.road_preference(net.edge_attrs(node, nb), persona)
            # 개인 환경 반응 — "물가만 보면 다가간다" 같은 축 밖 특성 (과제1 컴파일)
            w *= gauge_mod.env_response_weight(net.env(nb), persona)
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
                # 층 = 이 트리거 문맥의 동치류. 회차를 층 축에 넣었으므로 2회차도
                # 예산 경쟁에 참여한다 — 구버전은 여기서 회차로 분기해 2회차의
                # 실호출 확률을 구조적으로 0 으로 만들었다(_MindPool 독스트링 D1).
                stratum = stratum_key(g.C, fired, mind_transitions)
                if mind_pool is None:
                    result = None
                else:
                    # 장면 텍스트: 지금 이 노드에서 무엇이 보이는가 (외인성 자극)
                    from app.llm.exaone import build_scene_text  # 지연 — 순환 임포트

                    result = mind_pool.reinterpret(
                        rng, persona, mind or MindState(), gauge_report,
                        list(label_nodes or {}), prior, build_scene_text(env),
                        key=stratum, walker_idx=walker_idx)
                if result is None:
                    # 예산 0 + 풀 비어있음 — 스텁과 같은 혼란 심화 휴리스틱
                    base = mind.confusion if mind else 0.5
                    result = (MindState(status="혼란 심화",
                                        confusion=min(1.0, base + 0.2),
                                        changed=True), None, "heuristic")
                mind, goal, source = result
                # confusion 을 함께 갱신한다 — κ 뿐 아니라 목적지 인식 판정
                # (_recognizes_destination)도 이 값을 읽는다. 예전엔 κ 만
                # 다시 계산하고 이 지역변수는 초기값에 머물러 있었다.
                confusion = mind.confusion
                confusion_known = True   # 이제부터는 실제 판정값이다
                kappa = _kappa(confusion)
                if goal is not None:
                    target_node = (label_nodes or {})[goal]  # 목표 전환 — 자연어 재주입
                    target_label = goal
                if settings.mind_behavior_enabled and mind.behavior:
                    # 닫힌 4종 → 보행 모드. 각 매핑의 문헌 근거를 분기마다 남긴다.
                    # "끌림점 접근"은 위 goal 경로가 이미 처리하므로 모드만 해제한다.
                    if mind.behavior == "귀소 시도":
                        if homing_candidate is not None:
                            homing_loc, roaming = homing_candidate, False
                            target_node = target_label = None
                        # 과거 장소 미등록이면 아무것도 하지 않는다 — 현재 집으로 폴백하면
                        # 문헌(DEM-31)이 말한 대상과 다른 곳을 가리키게 된다.
                    elif mind.behavior == "계속 배회":
                        # DEM-33(Algase Wandering Scale)의 random 패턴 정의 —
                        #   "walking in a haphazard fashion using multiple changes in
                        #    direction, and no obvious route to the eventual stopping point"
                        # 매 스텝 무작위 방위가 이 정의에 대응한다.
                        # ⚠ 인용 정정(2026-08-04 원문 재확인): DEM-32 p8 의
                        # r=0.19~0.33 / -0.23~-0.27 은 **각도 분산이 아니라**
                        # "percent of cycles per hour, mean cycles per hour,
                        #  proportion of time locomoting" 과 direct ambulation
                        # 파라미터에 대한 상관이다. 즉 이 논문은 κ(방향 집중도)의
                        # 근거가 될 수 없다 — 빈도·이동시간·패턴 유형의 근거다.
                        # 혼란도의 문헌 정합 소비처는 _recognizes_destination 쪽이다.
                        homing_loc, roaming = None, True
                        target_node = target_label = None
                    elif mind.behavior == "은신·멈춤":
                        # DEM-31 — 26% 가 최종 목격지 0.5마일 이내 자연 공간에서
                        # 발견되었고 발견될 때까지 거의 이동하지 않았다. 체류가 아니라
                        # 이동 종료로 옮긴다(그 자리가 곧 발견 지점이 된다).
                        # 끌림점·집과 달리 은신 지점은 워커마다 흩어져 있으므로 종료를
                        # 걸어도 특정 셀로 뭉치지 않는다.
                        break
                    elif mind.behavior == "끌림점 접근":
                        homing_loc, roaming = None, False
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
        source=source, status=mind.status, confusion=mind.confusion,
        behavior=mind.behavior, goal=goal,
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
    v_max_kmh: float | None = None,
    trace: SimTrace | None = None,
    walker_idx: int = 0,
) -> GeoPoint:
    """워커 1명의 종착점 — 연속 공간 (도로 제약 없음).

    이전엔 이 경로(기본값)만 반경 상한이 전혀 없었다 — p95 절단으로 정렬.
    """
    total_km = radius.sample_distance_km(rng, prior.radius_lognormal,
                                         elapsed_hours, v_max_kmh)

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
