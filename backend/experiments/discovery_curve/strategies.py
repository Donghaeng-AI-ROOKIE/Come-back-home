"""발견율 곡선 — 비교군 4종의 알림 셀 선정.

네 전략은 **같은 타임라인(같은 진짜 궤적·같은 제보열)** 위에서 평가된다.
바뀌는 것은 "누구에게 보낼 셀을 어떻게 고르는가" 하나뿐이다.

| 전략 | 확률 모델 | 제보 반영 | 커버리지 노브 |
|---|---|---|---|
| `none` | 없음 | — | 없음(항상 0셀) |
| `blanket` | 없음(물리 도달 반경 전체) | 없음 | 없음(항상 전체) |
| `stat_only` | Koester 로그정규 거리 × 균등 방향 | **없음** | 있음 |
| `ours` | Phase2 파이프라인 POA | **있음** | 있음 |

`stat_only` 가 거리 표집에 `radius.sample_distance_km` 을 그대로 쓰는 것은
의도된 것이다. 우리 예측기와 **거리 분포를 공유**시켜야 두 전략의 차이가
"동역학(6전략 보행·도로망)과 제보 반영이 있는가" 하나로 좁혀진다. 거리 분포까지
다르게 두면 무엇이 이득의 원인인지 분해되지 않는다.

`blanket` 이 통계 상한(Koester p95)을 쓰지 않는 이유: 확률 모델을 전혀 쓰지
않는 것이 무차별 발송의 정의다. 물리 도달 반경(v_max×t)만 쓴다 — 이 실험이
다루는 공간 범위 안에서의 최대 발송, 즉 비용 상한선 역할이다.
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.geo import h3grid
from app.phase2 import radius
from app.phase3 import alerts
from app.schemas.common import GeoPoint
from app.schemas.persona import Persona
from app.schemas.prediction import LognormalParams

# 통계 POA 표집 수 — Phase2 MC 워커 수(기본 500)보다 넉넉히 잡는다. 이 분포는
# 등방이라 셀당 기대 표본이 얇아지기 쉬운데(반경 10km 면 3,000셀 이상), 표집
# 노이즈가 커버리지 스윕의 셀 순위를 흔들면 곡선이 계단처럼 튄다.
_STAT_SAMPLES = 20_000

_TWO_PI = 2.0 * math.pi


def none_cells() -> list[str]:
    """알림 없음 — 곡선의 원점(비용 0, hit 0). 비교의 바닥선."""
    return []


def blanket_cells(lkp: GeoPoint, persona: Persona | None, elapsed_hours: float) -> list[str]:
    """무차별 — 물리 도달 반경 안의 모든 셀. 커버리지·셀 상한을 쓰지 않는다."""
    v_max = radius.vmax_kmh(persona)
    # 하한은 radius 의 것을 그대로 참조 — 값을 복제하면 한쪽만 바뀔 때 어긋난다.
    reach_km = max(radius._MIN_REACH_KM, v_max * max(0.0, elapsed_hours))
    return h3grid.cells_within_km(lkp, reach_km)


def statistical_poa(
    lkp: GeoPoint,
    params: LognormalParams,
    persona: Persona | None,
    elapsed_hours: float,
    rng: random.Random,
    n_samples: int = _STAT_SAMPLES,
) -> dict[str, float]:
    """통계예측만 — 고전 SAR 링 모델의 POA.

    거리는 절단 로그정규(우리 예측기와 동일), 방향은 균등. 보행 동역학도
    도로망도 제보도 쓰지 않는다. 표집 히스토그램을 정규화해 POA 로 만든다.
    """
    v_max = radius.vmax_kmh(persona)
    counts: dict[str, int] = {}
    for _ in range(n_samples):
        d_km = radius.sample_distance_km(rng, params, elapsed_hours, v_max)
        bearing = rng.uniform(0.0, _TWO_PI)
        cell = h3grid.cell_of(h3grid.move(lkp, bearing, d_km))
        counts[cell] = counts.get(cell, 0) + 1
    total = float(sum(counts.values())) or 1.0
    return {cell: n / total for cell, n in counts.items()}


def top_k_cells(poa: dict[str, float], k: int) -> list[str]:
    """확률 상위 k 셀 — **비용 정합 비교 전용**(운영 경로 아님).

    커버리지 격자로 비용을 맞추면 격자 간격만큼 오차가 생기고, 그 오차는 비교
    대상 쪽에 불리하게 쏠린다(k 이하 중 가장 큰 커버리지를 쓰므로 항상 과소).
    셀 수를 직접 맞춰야 "같은 비용을 줬을 때"의 비교가 성립한다.
    """
    ranked = sorted(
        ((c, p) for c, p in poa.items() if math.isfinite(p)),
        key=lambda kv: kv[1], reverse=True,
    )
    return [c for c, _ in ranked[:max(0, k)]]


def coverage_cells(
    poa: dict[str, float],
    coverage: float,
    max_cells: int,
) -> list[str]:
    """POA 기반 두 전략(`stat_only`·`ours`)의 공용 선정 — 운영 함수를 그대로 쓴다.

    실험용으로 다시 구현하지 않는다. 운영에서 쓰는 것과 다른 선정 규칙으로
    잰 곡선은 제안서에 인용할 수 없다.
    """
    return alerts.select_alert_cells(poa, coverage=coverage, max_cells=max_cells)
