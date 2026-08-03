"""시공간 개연성 — kinematic 상한(도달 가능 반경).

제보 신뢰도 p 의 한 항. "이 시간 동안 이만큼 이동 가능한가"를 물리로 판정한다
(docs: "제보 신뢰도 p 계산 방식"). 거리·시간 계산은 알고리즘이 하고 LLM 은
쓰지 않는다 (프로젝트 핵심 원칙 — LLM calibration 한계).

핵심: 시간 Δt 동안 최대 속도 v_max 로 갈 수 있는 최대 거리 d_max = v_max·Δt.
제보가 그 반경 안이면 개연성 1, 밖이면 지수 감쇠(하드 컷 아님 — 물리적으로
좀 벗어난 사례도 낮은 확률로 남긴다).
"""

from __future__ import annotations

import math
from datetime import datetime

from app.config import settings
from app.geo.h3grid import haversine_km
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType

_VMAX_KMH = {
    PersonaType.dementia: lambda: settings.reach_vmax_dementia_kmh,
}


def vmax_kmh(persona_type: PersonaType) -> float:
    """페르소나별 도보 최대 속도(km/h). 전부 도보(2026-07-24 안1)."""
    getter = _VMAX_KMH.get(persona_type)
    return getter() if getter else settings.reach_vmax_dementia_kmh


def _naive(dt: datetime | None) -> datetime | None:
    """tz-aware → naive 로 통일 (프로젝트는 전부 naive 로컬 시각).
    API 로 +09:00 붙은 시각이 들어와 naive lkp_time 과 빼기하면 TypeError 나는 것 방지.
    """
    return dt.replace(tzinfo=None) if dt is not None and dt.tzinfo is not None else dt


def elapsed_hours(lkp_time: datetime, seen_at: datetime | None,
                  created_at: datetime) -> float:
    """개연성용 Δt(시간). 목격 시각(seen_at) 우선, 없으면 접수 시각(created_at)
    상한으로 fallback — created_at ≥ seen_at 이라 넉넉한(보수적) 반경이 나온다.
    하한(reach_min_dt_hours)으로 0 나누기·동시목격 붕괴 방지.
    """
    lkp_time, seen_at, created_at = _naive(lkp_time), _naive(seen_at), _naive(created_at)
    # 목격은 신고보다 늦을 수 없다 — 미래로 오추출된 seen_at 은 created_at 으로 캡.
    ref = created_at if seen_at is None else min(seen_at, created_at)
    dt_h = (ref - lkp_time).total_seconds() / 3600.0
    return max(dt_h, settings.reach_min_dt_hours)


def _distance_km(
    lkp: GeoPoint, tip_location: GeoPoint, use_roadnet: bool | None,
) -> tuple[float, str]:
    """개연성용 거리 산출. use_roadnet=True 면 도로망 최단경로를 시도하고,
    실패하거나 꺼져있으면 직선(haversine)으로 폴백한다.

    반환값의 두 번째 항(사유 코드)은 디버깅용 — 항상 직선으로 폴백하므로
    (직선은 실제거리의 하한이라 안전), plausibility() 판정 자체는 바뀌지 않는다.
    """
    if use_roadnet is None:
        use_roadnet = settings.use_roadnet
    if not use_roadnet:
        return haversine_km(lkp, tip_location), "straight"
    try:
        from app.geo import roadnet

        net = roadnet.get_network(lkp)  # 케이스 단위 캐시 재사용 — 제보마다 재로딩 안 함
        d = net.road_distance_km(lkp, tip_location)
        if d is not None:
            return d, "roadnet"
        return haversine_km(lkp, tip_location), "fallback_no_path"
    except Exception:  # noqa: BLE001 — 도로망 조회 실패(그래프 미로딩·osmnx 문제 등)가
        # 제보 신뢰도 계산 자체를 죽이면 안 됨 — 직선 폴백으로 격리
        return haversine_km(lkp, tip_location), "fallback_disabled"


def decay_factor(d: float, d_max: float, k: float) -> float:
    """d_max 초과분의 지수 감쇠 계수 exp(-k·(d-d_max)/d_max). d ≤ d_max 는 호출측(1.0)에서 처리.

    k 가 클수록 초과분에 더 가혹(급감쇠), 작을수록 관대(완만). P1-6 튜닝 대상 — 순수
    함수로 분리해 plausibility() 없이도(거리·시간 없이 비율만으로) 스윕 가능하게 한다.
    """
    if d_max <= 0:            # 방어 — dt 하한이 있어 정상 경로에선 도달 안 함
        return 0.0
    return math.exp(-k * (d - d_max) / d_max)


def plausibility(
    lkp: GeoPoint,
    lkp_time: datetime,
    tip_location: GeoPoint,
    persona_type: PersonaType,
    *,
    seen_at: datetime | None = None,
    created_at: datetime,
    use_roadnet: bool | None = None,
    decay_k: float | None = None,
) -> float:
    """제보 위치의 시공간 개연성 ∈ [0, 1].

    d ≤ d_max → 1.0, 아니면 decay_factor(d, d_max, k). 거리는 기본 직선(haversine).
    use_roadnet=True(또는 config.use_roadnet)면 도로망 최단경로를 쓰되, 그래프 밖·
    경로 없음 등으로 실패하면 직선으로 폴백한다 — 직선은 실제거리의 하한이라 폴백해도
    "직선으로도 상한을 넘으면 확실히 불가능"이라는 판정 안전성은 유지된다.

    decay_k: 미지정 시 config.reach_decay_k. 실험(P1-6 k 스윕)에서 전역 설정을
    건드리지 않고 값을 바꿔보기 위한 오버라이드 — use_roadnet 과 동일 패턴.
    """
    dt_h = elapsed_hours(lkp_time, seen_at, created_at)
    d_max = vmax_kmh(persona_type) * dt_h
    d, _dist_mode = _distance_km(lkp, tip_location, use_roadnet)
    if d <= d_max:
        return 1.0
    k = settings.reach_decay_k if decay_k is None else decay_k
    return decay_factor(d, d_max, k)
