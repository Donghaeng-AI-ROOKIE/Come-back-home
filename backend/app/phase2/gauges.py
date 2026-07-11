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

from app.geo import h3grid
from app.schemas.common import GeoPoint
from app.schemas.persona import Persona, PersonaType

# 아동은 연령대별 행동이 갈린다 (7세 미만: 공간인지 미형성 / 7~12세: 랜드마크 시퀀스)
CHILD_YOUNG_MAX_AGE = 6

# 지형난이도 — highway 태그만 (더미 버전). 0=수월 ~ 1=험함
_HIGHWAY_DIFFICULTY = {
    "footway": 0.15, "pedestrian": 0.15, "residential": 0.25, "living_street": 0.25,
    "service": 0.3, "tertiary": 0.35, "secondary": 0.4, "primary": 0.5,
    "unclassified": 0.4, "path": 0.6, "track": 0.7, "steps": 0.9,
}
_DEFAULT_DIFFICULTY = 0.4

# 페르소나별 피로 체감 배수 (회의: persona_fatigue_mult)
_FATIGUE_MULT = {
    PersonaType.dementia: 1.3,
    PersonaType.child: 0.8,
    PersonaType.intellectual_disability: 1.0,
}

# 보행 속도 (m/분) — 연령별 보행속도 문헌 기반 잠정값 (고령자 데이터 공백은 회의록 명시)
WALK_SPEED_M_PER_MIN = {
    PersonaType.dementia: 48.0,                  # ~0.8 m/s
    PersonaType.child: 60.0,                     # ~1.0 m/s
    PersonaType.intellectual_disability: 66.0,   # ~1.1 m/s
}

# 낯섦도 정규화 반경 (회의: D_max = 페르소나 생활권 또는 고정 1km)
_D_MAX_KM = 1.0

# 혐오환경 — 유형별 (env 키, 임계 m, 심각도). 아동 7세 미만은 물이 혐오가 아니라
# 끌림(부호 반전, Anderson 2012)이라 이 표에 없음 — water_attractor 규칙이 대신한다.
_AVERSION = {
    PersonaType.dementia: [("forest_m", 30.0, 0.5)],                  # 수풀 — 낯섦·위험
    PersonaType.child: [("forest_m", 30.0, 0.7)],                     # 7~12세
    PersonaType.intellectual_disability: [("market_m", 50.0, 1.0)],   # 혼잡·소음 (Rice 2016)
}

# 아동 7세 미만 물 끌림 — 물가 도달 시 체류 (수색에선 익사위험 지점, Anderson 2012)
WATER_ATTRACTOR_M = 30.0


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
    h_capability: float = 1.0   # 아동 age_return_capability (연령가중)
    # 로지스틱 hazard: P = 1/(1+exp(-β(gauge-θ))). θ 를 게이지 상단보다 높게 둬
    # 스텝당 발동확률이 낮게 유지되고, 게이지가 찰수록 지수적으로 오른다.
    theta_f: float = 1.2
    beta_f: float = 6.0
    theta_mind: float = 1.1     # H·A 공용 임계
    beta_mind: float = 6.0


def config_for(persona: Persona | None) -> GaugeConfig:
    """페르소나별 활성화 매핑 (회의 종합 매핑 표)."""
    if persona is None:
        return GaugeConfig()
    cfg = GaugeConfig()
    if persona.type == PersonaType.child:
        if persona.age <= CHILD_YOUNG_MAX_AGE:
            # 7세 미만: F만 유지. C·H 비활성(길 잃음 개념 없음), A 는 초기 고정
            # 상태(정지+울음)로 외인성 처리 — 게이지로는 안 굴린다.
            cfg.k_c1 = cfg.k_c2 = cfg.k_c3 = 0.0
            cfg.k_h1 = cfg.k_h2 = 0.0
            cfg.k_a1 = cfg.k_a2 = 0.0
        else:
            # 7~12세: C 감쇠, H 연령가중 (근거 약함 — 발표 시 한계 명시)
            cfg.k_c1 *= 0.5
            cfg.k_c2 *= 0.5
            age = persona.age
            cfg.h_capability = 0.4 if age <= 9 else 0.8
    elif persona.type == PersonaType.intellectual_disability:
        # ID: C 대폭 축소(이탈 53%가 혼란 무관 탐험, Rice 2016),
        # A 는 E(혼잡·소음) 중심, H 는 attractor 추구로 대체(외인성 → 게이지 밖)
        cfg.k_c1 *= 0.2
        cfg.k_c2 *= 0.2
        cfg.k_a1 = 0.0
        cfg.k_h1 = cfg.k_h2 = 0.0
    return cfg


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
        return c.h_capability * (c.k_h1 * self.elapsed_min + c.k_h2 * self.C)

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


def unfamiliarity(here: GeoPoint, familiar: list[GeoPoint]) -> float:
    """가장 가까운 익숙한 장소와의 거리 / D_max (회의 공식)."""
    if not familiar:
        return 1.0
    nearest = min(h3grid.haversine_km(here, p) for p in familiar)
    return min(1.0, nearest / _D_MAX_KM)


def hostile_exposure(env: dict, persona: Persona | None) -> float:
    """현 위치의 혐오환경 심각도 (0=없음). env 는 envlayer 가 노드에 얹은 dict."""
    if persona is None or not env:
        return 0.0
    if persona.type == PersonaType.child and persona.age <= CHILD_YOUNG_MAX_AGE:
        return 0.0  # 물·불빛은 혐오가 아니라 끌림 — water_attractor 규칙이 처리
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


def is_water_attracted(persona: Persona | None) -> bool:
    return (persona is not None and persona.type == PersonaType.child
            and persona.age <= CHILD_YOUNG_MAX_AGE)
