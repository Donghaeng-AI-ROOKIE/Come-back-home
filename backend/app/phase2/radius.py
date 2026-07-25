"""Koester 반경의 유효 지원(p95) — 세 예측기의 단일 소스.

두 개의 상한이 겹친다.

1. **통계 상한** — ISRID 분위수 적합 lognormal 의 p95. 치매 Urban(μ=0.095,
   σ=1.48)에서 12.55km 로, Koester 경험적 95% 거리(12.6km)와 일치한다.
2. **물리 상한** — `v_max × 경과시간`. 도달 가능성 판정으로, Phase 3 제보
   신뢰도(`trust.py`)가 이미 쓰는 원칙·상수를 그대로 재사용한다.

`p95 = min(통계 상한, 물리 상한)`.

√t 스케일 폐기 (2026-07-21 결정, PR #20 후속 "이중계상"):
ISRID 거리는 **발견 시점 거리**를 경과시간 전반에 걸쳐 모은 종국 분포다.
여기에 ×√t 를 다시 곱하면 같은 시간 효과를 두 번 세는 것이고, 실제로
골든타임 전 구간에서 물리적으로 불가능한 반경이 나왔다 —
t=15분에 12.55km(도보 한계 1.12km 의 11.2배), t=1h 에 2.8배.
√t 가 물리적으로 타당해지는 시점은 t≥8h 로, 알림 가치가 가장 낮은 구간이다.

시간 의존성은 이제 물리 상한이 전담한다: 반경은 `v_max × t` 로 자라다가
통계 상한에 닿으면 멈춘다(치매 도보 기준 2.79h). "시간이 지나면 반경이
커진다"는 직관은 유지되면서, 커지는 근거가 임의 지수가 아니라 도달
가능성이 된다. T_ref 같은 자유 파라미터도 필요 없다.
"""

import math
import random

from app.config import settings
from app.schemas.persona import Persona, PersonaType
from app.schemas.prediction import LognormalParams

# 표준정규 95% 분위 — topdown 원판 컷과 동일한 z (PR #20).
Z_P95 = 1.645
# 표준정규 90% 분위 — 도로망 로딩 반경(P1-3)용. 로딩은 지원 전체(p95)가 아니라
# 질량 대부분(p90)을 덮으면 충분하고, 반경이 커질수록 다운로드·메모리가 비싸다.
Z_P90 = 1.2816
# 절단 표집 재시도 상한. 물리 상한이 낮은 초기 시각에는 절단 질량이 커질 수
# 있어(t=0.5h 에 31%) 넉넉히 잡는다. 초과 시 상한 클램프.
_TRUNC_MAX_RESAMPLE = 24
# 반경 하한 — t≈0 에서 상한이 0 으로 붕괴해 전 워커가 LKP 한 점에 뭉치는 것을
# 막는다. Phase 1 즉시 알림의 k-ring 2(약 600m)와 같은 스케일.
_MIN_REACH_KM = 0.5


def vmax_kmh(persona: Persona | None) -> float:
    """도달 가능 반경 계산용 최대 속도(km/h). 전부 도보(2026-07-24 안1).

    미확인 대중교통 이용으로 이 반경 밖에서 발견되는 경우는 Phase 3 가 흡수한다
    (고신뢰 제보 → 새 LKP 재예측 → D3 새 지역 알림) — 도보 상한만 쓰는 안전판.
    """
    if persona is not None and persona.type == PersonaType.intellectual_disability:
        return settings.reach_vmax_id_kmh
    # 유형 미상은 가장 느린 값 — 물리 상한은 보수적으로 잡는다.
    return settings.reach_vmax_dementia_kmh


def statistical_p95_km(params: LognormalParams) -> float:
    """시간 무관 통계 상한 = exp(μ + zσ). ISRID 종국 분포의 95% 거리."""
    return math.exp(params.mu + Z_P95 * params.sigma)


def p95_km(
    params: LognormalParams,
    elapsed_hours: float,
    v_max_kmh: float | None = None,
) -> float:
    """세 예측기 공통 지원 경계 = min(통계 상한, 물리 상한).

    `v_max_kmh` 를 안 주면 통계 상한만 — 물리 제약 없이 분포 자체를 볼 때
    (테스트·문서화)용.
    """
    stat = statistical_p95_km(params)
    if v_max_kmh is None:
        return stat
    reach = max(_MIN_REACH_KM, v_max_kmh * max(0.0, elapsed_hours))
    return min(stat, reach)


def p90_km(
    params: LognormalParams,
    elapsed_hours: float,
    v_max_kmh: float | None = None,
) -> float:
    """통계 p90 과 물리 상한의 min — p95_km 와 같은 구조, z 만 90% 분위."""
    stat = math.exp(params.mu + Z_P90 * params.sigma)
    if v_max_kmh is None:
        return stat
    reach = max(_MIN_REACH_KM, v_max_kmh * max(0.0, elapsed_hours))
    return min(stat, reach)


def roadnet_radius_m(
    params: LognormalParams,
    elapsed_hours: float,
    v_max_kmh: float | None = None,
) -> int:
    """도로망 로딩 반경(m) — P1-3.

    고정 3km 로딩은 치매 6h Koester 중앙값(3.9km)이 그래프 밖이라 이탈거리가
    체계적으로 미달했다(sim_testset 실측: 3h/6h dist_ratio 저하). p90 지원을
    덮도록 스케일하되,
      - 하한 = 기존 `roadnet_radius_m`(3km) — 반경이 절대 줄지 않는다
      - 상한 = `roadnet_radius_max_m` — 다운로드·메모리 폭주 방지
      - 1km 올림 양자화 — LKP당 캐시 항목을 최대 4개(3~6km)로 제한
    """
    dyn_m = p90_km(params, elapsed_hours, v_max_kmh) * 1000.0
    quantized = math.ceil(dyn_m / 1000.0) * 1000
    return int(max(settings.roadnet_radius_m,
                   min(settings.roadnet_radius_max_m, quantized)))


def sample_distance_km(
    rng: random.Random,
    params: LognormalParams,
    elapsed_hours: float,
    v_max_kmh: float | None = None,
) -> float:
    """p95 절단 lognormal 표집 — MC 가 topdown 원판 컷과 같은 지원을 갖게 한다.

    초과 표본은 재표집(절단 분포 — topdown 이 원판 밖 질량을 재정규화하는
    것과 동형). 연속 초과 시 상한 클램프.
    """
    cap = p95_km(params, elapsed_hours, v_max_kmh)
    for _ in range(_TRUNC_MAX_RESAMPLE):
        d = rng.lognormvariate(params.mu, params.sigma)
        if d <= cap:
            return d
    return cap
