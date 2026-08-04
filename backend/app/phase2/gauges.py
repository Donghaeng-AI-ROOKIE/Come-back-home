"""내인성 게이지 + 확률적 hazard — 회의 "트리거 설계 최종본" 구현.

- 누적 게이지 (매 스텝 dt 만큼): 피로 F, 혼란 C, 혐오노출 E
- 파생 게이지 (매 스텝 재계산): 귀소 H = k_h1·집떠난시간 + k_h2·C,
  불안 A = k_a1·C + k_a2·E
- 발동은 결정론적 임계가 아니라 로지스틱 hazard — 롤아웃마다 발동 시점이
  흩어져야 POA 확률구름이 한 점으로 뭉개지지 않는다 (회의 결정).
- 라우팅 규칙: F 발동 → 알고리즘 처리(휴식, EXAONE 미호출) "습관→행동"
              H·A 발동 → EXAONE 호출(목표 재해석) "목표→마음"

이번주 더미 버전 결정사항 (회의록):
- 지형난이도는 highway 태그만 — 경사도·노면·토지피복 합산은 다음 단계
- 치매 M(보행실조) 게이지 제외 (회의 미결 항목)
- 계수·임계는 전부 잠정값 — 동선예측 테스트셋에서 Koester 발견거리
  분포 역산(그리드서치)으로 튜닝 대상
"""

import math
import random
from dataclasses import dataclass

from app.config import settings
from app.geo import h3grid
from app.schemas.common import GeoPoint
from app.schemas.persona import Persona, PersonaType

# 지형난이도 — highway 태그만 (더미 버전). 0=수월 ~ 1=험함
_HIGHWAY_DIFFICULTY = {
    "footway": 0.15, "pedestrian": 0.15, "residential": 0.25, "living_street": 0.25,
    "service": 0.3, "tertiary": 0.35, "secondary": 0.4, "primary": 0.5,
    "unclassified": 0.4, "path": 0.6, "track": 0.7, "steps": 0.9,
}
_DEFAULT_DIFFICULTY = 0.4

# 도로 위계 선호 — 갈림길 선택 확률의 곱셈 틸트 (1.0 = 중립).
# 근거: 치매 실종자는 소음·교통량이 많고 차량이 빠른 주간선·간선도로(trunk,
# primary)를 기피하고, 보행 인프라가 갖춰진 보조간선(secondary)·이면도로
# (residential)를 선호한다 — 특히 보조간선은 인도망 단절이 적고 횡단보도
# 시청각 신호가 갖춰져 장거리 이동의 축이 된다 (기획팀 「지도 인식 범위
# 논문 조사」 2번).
#
# terrain_difficulty(피로 게이지)와는 다른 축이다: 저쪽은 "얼마나 힘든가",
# 이쪽은 "어느 길을 고르는가". 이중계상이 아니라 서로 다른 소비처다.
# 문헌이 다루지 않은 위계(service/path/track/steps)는 중립으로 둔다 —
# steps 의 부담은 이미 terrain_difficulty 0.9 가 반영하므로 여기서 또
# 깎으면 이중계상이 된다.
_ROAD_PREFERENCE = {
    "trunk": 0.5, "trunk_link": 0.5,
    "primary": 0.6, "primary_link": 0.6,
    "secondary": 1.2, "secondary_link": 1.2,
    "tertiary": 1.1,
    "residential": 1.3, "living_street": 1.3,
    "footway": 1.3, "pedestrian": 1.3,
}

# 페르소나별 피로 체감 배수 (회의: persona_fatigue_mult)
_FATIGUE_MULT = {
    PersonaType.dementia: 1.3,
}

# 보행 속도 (m/분) — 연령별 보행속도 문헌 기반 잠정값 (고령자 데이터 공백은 회의록 명시)
WALK_SPEED_M_PER_MIN = {
    PersonaType.dementia: 48.0,                  # ~0.8 m/s
}

# 낯섦도 정규화 반경 (회의: D_max = 페르소나 생활권 또는 고정 1km)
_D_MAX_KM = 1.0

# routine_destinations(혼자 자주 가는 곳) 유래 끌림점의 기본 익숙함 — 보호자가
# "자주 다니는 곳"이라고 답한 것 자체가 이미 익숙함의 근거라, 컴파일러(작업5) 없이도
# 기본값으로 반영한다. autobiographical_destination_pull(과거 장소)은 다르다 — 가려는
# 끌림은 있어도 현재 그 경로를 실제로 아는지는 별개라 컴파일러가 채점해야 함(작업5).
ROUTINE_DEFAULT_FAMILIARITY = 0.8

# 혐오환경 — 유형별 (env 키, 임계 m, 심각도)
_AVERSION = {
    PersonaType.dementia: [("forest_m", 30.0, 0.5)],                  # 수풀 — 낯섦·위험
}


@dataclass
class GaugeConfig:
    """누적·파생 계수 + hazard 파라미터. 전부 잠정값 (역산 튜닝 대상)."""
    k_f: float = 0.03       # 피로 누적 (지형난이도 1.0, 1분당)
    k_c1: float = 0.015     # 혼란 — 낯섦도 항
    k_c2: float = 0.0015    # 혼란 — 경과시간 항 (1분당)
    k_c3: float = 0.01      # 혼란 — 어두움·악천후 항
    k_e: float = 0.05       # 혐오노출 누적
    k_h1: float = 0.006     # 귀소 — 집떠난시간 항 (1분당)
    k_h2: float = 0.5       # 귀소 — 혼란 항
    k_a1: float = 0.6       # 불안 — 혼란 항
    k_a2: float = 0.5       # 불안 — 혐오노출 항
    # 로지스틱 hazard: P = 1/(1+exp(-β(gauge-θ))). θ 를 게이지 상단보다 높게 둬
    # 스텝당 발동확률이 낮게 유지되고, 게이지가 찰수록 지수적으로 오른다.
    theta_f: float = 1.2
    beta_f: float = 6.0
    theta_mind: float = 1.1     # H·A 공용 임계
    beta_mind: float = 6.0


@dataclass(frozen=True)
class OverrideSpec:
    """개인화를 허용하는 게이지 계수 1개의 명세 (PR #21 과제1 스키마).

    LLM 이 숫자를 직접 정하지 않는다 — 축 채점(quote 검증 + 3회 다수결)을 거친
    `axis_scores` 만 입력으로 받고, 배수 변환·클램프는 코드가 한다. 기존
    가드레일 원칙("LLM 은 등급, 숫자는 우리")의 게이지 판이다.
    """
    field: str          # GaugeConfig 필드명
    axis: str           # 유래 축 (Persona.axis_scores 키)
    ptype: PersonaType  # 이 축이 채점되는 유형
    lo: float           # 유형 기본값 대비 배수 하한
    hi: float           # 상한
    why: str


# 허용 목록 — 축 정의와 계수 의미가 1:1 대응하는 것만 연다.
_GAUGE_OVERRIDES: tuple[OverrideSpec, ...] = (
    OverrideSpec(
        "k_c1", "wayfinding_error_recovery_deficit", PersonaType.dementia, 0.6, 1.4,
        "축 0.1='잘못 들어가도 스스로 알아차려 돌아옴' ↔ k_c1='낯섦이 혼란으로 "
        "전환되는 속도'. 길찾기 복구가 취약할수록 같은 낯선 환경이 더 빨리 혼란이 된다."),
    OverrideSpec(
        "k_a1", "distress_induced_movement_reactivity", PersonaType.dementia, 0.6, 1.4,
        "축 0.1='불안·초조가 나타나도 이동 행동 거의 변화 없음' ↔ k_a1='혼란이 "
        "불안으로 전환되는 속도'. 불안이 곧 이동으로 이어지는 사람일수록 크다."),
)

# 금지 목록 — 왜 안 여는지까지 코드에 남긴다 (테스트가 이 목록을 강제한다).
DENIED_OVERRIDES: dict[str, str] = {
    "theta_f": "피로 hazard 임계 — 시스템 튜닝 축이라 개인화하면 계수 그리드서치가 "
               "사람마다 다른 좌표계를 갖게 되어 역산 불능",
    "beta_f": "피로 hazard 기울기 — theta_f 와 짝을 이루는 곡선 형태라 같은 이유로 고정",
    "theta_mind": "마음 재해석 hazard 임계 — 발동 빈도가 사람마다 다르면 실호출 예산 "
                  "배분이 흔들려 마음 풀의 다양성 비교가 불가능해진다",
    "beta_mind": "마음 hazard 기울기 — theta_mind 와 짝이라 같이 고정해야 곡선이 의미를 유지",
    "k_h2": "귀소의 혼란 교차항 — 개인화하면 C 를 키우는 축(길찾기)과 곱해져 "
            "같은 특성이 H 에 두 번 반영된다",
    "k_a2": "불안의 혐오 교차항 — 개인화하면 E 를 키우는 축(회피성)과 곱해져 "
            "같은 특성이 A 에 두 번 반영된다",
    "k_c2": "혼란의 경과시간 항 — 시간이 흐르면 누구나 혼란이 쌓인다는 시간의 성질이지 "
            "개인차가 아니다",
    "k_c3": "혼란의 어둠 항 — 조도는 환경 변수다. 개인의 야간 취약성을 다루려면 "
            "별도 축이 필요하고 현재 기준표에 없다",
    "k_f": "피로 누적 — mobility_transport_capacity 축이 이미 반경과 v_max 로 "
           "두 번 소비 중이라 여기까지 열면 같은 축이 세 곳에 반영된다",
    "k_h1": "귀소의 경과시간 항 — 개인화하려면 '귀가 욕구' 축이 따로 있어야 하는데 "
            "현재 기준표 6축에 해당 항목이 없다",
    "k_e": "혐오노출 누적 — 대응하던 축(aversive_context_escape)이 발달장애 전용이라 "
           "치매 단독 스코프(2026-08-03)로 좁히면서 함께 삭제됐다. 치매 기준표 6축에 "
           "'혐오 자극 민감도'에 해당하는 축이 없어 근거 없는 개인화가 되므로 고정한다",
}


def _score_to_mult(score: float, lo: float, hi: float) -> float:
    """축점수(0.1~0.9) → 계수 배수. 0.5 를 중립(1.0)으로 두고 선형, 양끝 클램프."""
    return max(lo, min(hi, 1.0 + (score - 0.5)))


def apply_personal_overrides(cfg: GaugeConfig, persona: Persona | None) -> GaugeConfig:
    """축점수를 게이지 계수에 곱셈으로 반영 (유형 기본값 위에, 파괴적 아님).

    유형 특례(ID 의 k_c1 ×0.2 등)를 덮지 않고 그 위에 곱하므로 유형 구조는
    보존된다. 축이 없거나 유형이 안 맞으면 그대로 둔다 — 축 채점이 꺼져 있는
    기본 구성에서 동작이 안 바뀌는 것이 의도된 폴백이다.
    """
    if persona is None or not persona.axis_scores:
        return cfg
    for spec in _GAUGE_OVERRIDES:
        if persona.type != spec.ptype:
            continue
        score = persona.axis_scores.get(spec.axis)
        if score is None:
            continue
        base = getattr(cfg, spec.field)
        setattr(cfg, spec.field, base * _score_to_mult(score, spec.lo, spec.hi))
    return cfg


def config_for(persona: Persona | None) -> GaugeConfig:
    """페르소나별 활성화 매핑 (회의 종합 매핑 표) + 축점수 개인화."""
    if persona is None:
        return GaugeConfig()
    return apply_personal_overrides(GaugeConfig(), persona)


class Gauges:
    """워커 1명의 게이지 상태 — 롤아웃마다 새로 만든다."""

    def __init__(self, cfg: GaugeConfig) -> None:
        self.cfg = cfg
        self.F = 0.0
        self.C = 0.0
        self.E = 0.0
        self.elapsed_min = 0.0   # 집떠난시간 (시뮬 내부 누적)

    def step(self, dt_min: float, *, terrain: float, fatigue_mult: float,
             unfamiliarity: float, hostile: float, dark: bool = False) -> None:
        c = self.cfg
        self.elapsed_min += dt_min
        self.F += c.k_f * terrain * fatigue_mult * dt_min
        self.C += (c.k_c1 * unfamiliarity + c.k_c2 + c.k_c3 * (1.0 if dark else 0.0)) * dt_min
        self.E += c.k_e * hostile * dt_min

    def rest(self) -> None:
        """F 발동 시 알고리즘 처리 — 쉬면서 피로가 일부 빠진다."""
        self.F *= 0.4

    @property
    def H(self) -> float:
        c = self.cfg
        return c.k_h1 * self.elapsed_min + c.k_h2 * self.C

    @property
    def A(self) -> float:
        return self.cfg.k_a1 * self.C + self.cfg.k_a2 * self.E

    def fatigue_fired(self, rng: random.Random) -> bool:
        return rng.random() < p_trigger(self.F, self.cfg.theta_f, self.cfg.beta_f)

    def mind_fired(self, rng: random.Random) -> str | None:
        """H·A 중 발동한 게이지 이름 (EXAONE 호출 사유). 없으면 None."""
        for name, value in (("귀소", self.H), ("불안", self.A)):
            if value > 0 and rng.random() < p_trigger(value, self.cfg.theta_mind, self.cfg.beta_mind):
                return name
        return None

    def report(self, reason: str) -> str:
        """게이지를 자연어로 번역 — EXAONE 프롬프트용 (좌표 없음, 회의 원칙)."""
        def level(v: float) -> str:
            return "높음" if v >= 0.7 else ("중간" if v >= 0.4 else "낮음")
        return (f"집을 나선 지 {self.elapsed_min:.0f}분 경과. "
                f"피로도: {level(self.F)}, 혼란도: {level(self.C)}, "
                f"귀소 충동: {level(self.H)}, 불안: {level(self.A)}. "
                f"방금 {reason} 게이지가 임계를 넘었다.")


def p_trigger(gauge: float, theta: float, beta: float) -> float:
    """로지스틱 hazard — 게이지가 높을수록 스텝당 발동 확률이 오른다."""
    return 1.0 / (1.0 + math.exp(-beta * (gauge - theta)))


def terrain_difficulty(edge_attrs: dict) -> float:
    """highway 태그만으로 0~1 (더미 버전). OSMnx 는 태그를 list 로 줄 때가 있다."""
    hw = edge_attrs.get("highway")
    if isinstance(hw, list) and hw:
        hw = hw[0]
    return _HIGHWAY_DIFFICULTY.get(hw, _DEFAULT_DIFFICULTY)


# 개인 환경 반응이 "보인다"고 볼 거리 — 이 안에 들어와야 이동 확률이 기운다.
# 물가는 익사 위험이라 더 멀리서도 반영한다(장면 텍스트 임계와 같은 기준).
_ENV_RESPONSE_RANGE_M = {"water": 100.0, "forest": 60.0, "park": 60.0, "market": 60.0}


def env_response_weight(env: dict | None, persona: Persona | None) -> float:
    """개인 환경 반응 → 이동 확률 배수 (1.0 = 중립).

    "물가만 보면 다가간다" 같은, 축 기준표에 없는 개인 특성의 소비처
    (PR #21 과제1 페르소나 컴파일). 축은 "얼마나" 반응하는지의 눈금이라
    "무엇에" 반응하는지를 못 담는다.

    도로 위계 선호(road_preference)와 같은 계열 — 게이지 누적이 아니라 갈림길
    선택 확률을 기울인다. 끌림/회피는 "얼마나 지치는가"가 아니라 "어디로
    가는가"의 문제이기 때문.

    마음 재해석의 장면 텍스트(PR #53)와는 층이 다르다: 저쪽은 트리거 발동 시
    LLM 이 맥락으로 해석하는 희소·비결정 경로이고, 이쪽은 매 스텝 전 워커에
    적용되는 알고리즘 경로다 (realism 무게중심 = 알고리즘 원칙).
    """
    if not env or persona is None or not persona.env_responses:
        return 1.0
    strength_mult = settings.env_response_strength
    if strength_mult <= 0.0:
        return 1.0
    weight = 1.0
    for r in persona.env_responses:
        dist = env.get(f"{r.feature}_m")
        if not isinstance(dist, (int, float)):
            continue
        if dist > _ENV_RESPONSE_RANGE_M.get(r.feature, 60.0):
            continue
        tilt = r.strength * strength_mult
        weight *= (1.0 + tilt) if r.direction == "접근" else 1.0 / (1.0 + tilt)
    return weight


def road_preference(edge_attrs: dict, persona: Persona | None) -> float:
    """도로 위계 선호 배수 — 갈림길 선택 확률에 곱한다 (1.0 = 중립).

    근거 문헌(_ROAD_PREFERENCE 주석)이 치매 실종자 대상이라 치매 페르소나에만
    적용한다 — 근거 없이 확장하면 "그럴듯하지만 틀린 확신"이 된다.

    `road_preference_strength` 는 지수로 들어가 ablation 노브가 된다:
    0 이면 전부 1.0(기능 끔), 1 이면 표 그대로, 2 이면 대비 강화.
    평가 하네스의 그리드서치가 이 한 값만 쓸어보면 된다.
    """
    if persona is None or persona.type != PersonaType.dementia:
        return 1.0
    strength = settings.road_preference_strength
    if strength <= 0.0:
        return 1.0
    hw = edge_attrs.get("highway")
    if isinstance(hw, list) and hw:
        hw = hw[0]
    base = _ROAD_PREFERENCE.get(hw, 1.0)
    return base if strength == 1.0 else base ** strength


def unfamiliarity(
    here: GeoPoint, familiar: list[GeoPoint], known_score: float | None = None,
) -> float:
    """낯섦도 — known_score 가 주어지면(route_familiarity 컴파일 결과 또는
    routine_destinations 기본값) 그걸 최우선으로 쓰고, 없으면 기존 거리 기반
    근사(가장 가까운 익숙한 장소와의 거리 / D_max, 회의 공식)로 폴백한다.

    known_score 는 0.0 도 유효한 값이므로 `is not None` 으로 체크한다(falsy 체크 금지).
    """
    if known_score is not None:
        return max(0.0, min(1.0, 1.0 - known_score))
    if not familiar:
        return 1.0
    nearest = min(h3grid.haversine_km(here, p) for p in familiar)
    return min(1.0, nearest / _D_MAX_KM)


def hostile_exposure(env: dict, persona: Persona | None) -> float:
    """현 위치의 혐오환경 심각도 (0=없음). env 는 envlayer 가 노드에 얹은 dict."""
    if persona is None or not env:
        return 0.0
    total = 0.0
    for key, threshold_m, severity in _AVERSION.get(persona.type, []):
        dist = env.get(key)
        if isinstance(dist, (int, float)) and dist <= threshold_m:
            total += severity
    return min(1.0, total)


def fatigue_mult(persona: Persona | None) -> float:
    return _FATIGUE_MULT.get(persona.type, 1.0) if persona else 1.0


def walk_speed(persona: Persona | None) -> float:
    return WALK_SPEED_M_PER_MIN.get(persona.type, 60.0) if persona else 60.0
