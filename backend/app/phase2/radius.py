"""Koester 반경 분포의 시간 스케일과 유효 지원(p95) — 세 예측기의 단일 소스.

PR #20 이 topdown 원판만 p95 로 잘라, MC 와 지원(support)이 어긋나 있었다:
그래프 모드는 _MAX_STEPS(경로장 ~15km)라는 부수적 안전망뿐이고, 기본값인
연속 공간 모드는 상한이 아예 없어 lognormal 꼬리가 그대로 살았다 (PR #20
후속 "예측기 유효반경 비대칭").

여기의 컷은 고정 km 가 아니라 "표집 분포 자체의 p95"로 정의한다 — √t 스케일
결정(이중계상 논의, 회의 안건)이 어느 쪽으로 나든 time_multiplier() 하나만
고치면 topdown·그래프 MC·연속 MC 가 함께 움직인다.
"""

import math
import random

from app.schemas.prediction import LognormalParams

# 표준정규 95% 분위 — topdown 원판 컷과 동일한 z (PR #20).
Z_P95 = 1.645
# 절단 표집 재시도 상한 — 초과 확률이 5% 라 연속 초과는 사실상 없다(0.05^8).
_TRUNC_MAX_RESAMPLE = 8


def time_multiplier(elapsed_hours: float) -> float:
    """경과시간 → 반경 배수. 현행 √t (최소 1h 앵커).

    ISRID 거리는 시간독립(발견 시점 거리) 통계라 ×√t 재확장은 이중계상
    의심이 있다 — 제거/앵커 명시/재설계는 회의 안건 (PR #20 후속).
    결정이 나면 이 함수만 고친다.
    """
    return max(1.0, elapsed_hours) ** 0.5


def p95_km(params: LognormalParams, elapsed_hours: float) -> float:
    """시간 반영 유효 반경 = exp(μ + zσ)·√t — 세 예측기 공통 지원 경계.

    치매 Urban(μ=0.095, σ=1.48) 기준 t=1h 에서 12.55km — ISRID 경험적
    95% 거리와 일치 (PR #20 재교정).
    """
    return math.exp(params.mu + Z_P95 * params.sigma) * time_multiplier(elapsed_hours)


def sample_distance_km(
    rng: random.Random,
    params: LognormalParams,
    elapsed_hours: float,
) -> float:
    """p95 절단 lognormal 표집 — MC 가 topdown 원판 컷과 같은 지원을 갖게 한다.

    초과 표본은 재표집(절단 분포 — topdown 이 원판 밖 질량을 재정규화하는
    것과 동형). 연속 초과 시 p95 클램프 — 잘리는 꼬리가 5% 라 편향은 무시
    가능한 수준.
    """
    cap = p95_km(params, elapsed_hours)
    mult = time_multiplier(elapsed_hours)
    for _ in range(_TRUNC_MAX_RESAMPLE):
        d = rng.lognormvariate(params.mu, params.sigma) * mult
        if d <= cap:
            return d
    return cap
