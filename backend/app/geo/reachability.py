"""시공간 개연성 — kinematic 상한(도달 가능 반경).

제보 신뢰도 p 의 한 항. "이 시간 동안 이만큼 이동 가능한가"를 물리로 판정한다
(docs: "제보 신뢰도 p 계산 방식"). 거리·시간 계산은 알고리즘이 하고 LLM 은
쓰지 않는다 (프로젝트 핵심 원칙 — LLM calibration 한계).

핵심: 시간 Δt 동안 최대 속도 v_max 로 갈 수 있는 최대 거리 d_max = v_max·Δt.
제보가 그 반경 안이면 개연성 1, 밖이면 지수 감쇠(하드 컷 아님 — 대중교통으로
멀리 간 사례를 낮은 확률로 남긴다).
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
    PersonaType.child: lambda: settings.reach_vmax_child_kmh,
    PersonaType.intellectual_disability: lambda: settings.reach_vmax_id_kmh,
}


def vmax_kmh(persona_type: PersonaType, transit: bool = False) -> float:
    """페르소나별 도보 최대 속도(km/h). transit=True 면 대중교통 상한."""
    if transit:
        return settings.reach_vmax_transit_kmh
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


def plausibility(
    lkp: GeoPoint,
    lkp_time: datetime,
    tip_location: GeoPoint,
    persona_type: PersonaType,
    *,
    seen_at: datetime | None = None,
    created_at: datetime,
    transit: bool = False,
) -> float:
    """제보 위치의 시공간 개연성 ∈ [0, 1].

    d ≤ d_max → 1.0, 아니면 exp(−(d−d_max)/d_max).
    거리는 직선(haversine) — 실제 도로거리는 더 길어 보수적 하한이다
    (직선으로도 상한을 넘으면 확실히 불가능).
    """
    dt_h = elapsed_hours(lkp_time, seen_at, created_at)
    d_max = vmax_kmh(persona_type, transit) * dt_h
    d = haversine_km(lkp, tip_location)
    if d <= d_max:
        return 1.0
    if d_max <= 0:            # 방어 — dt 하한이 있어 정상 경로에선 도달 안 함
        return 0.0
    return math.exp(-(d - d_max) / d_max)
