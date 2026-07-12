"""알림 셀 선택 — 커버리지 + 셀 수 상한(타겟팅 가드레일).

실측 회귀 배경: topdown 해석적 분포의 얇은 꼬리(수천 셀) 탓에 누적 80%
커버리지 선택이 21,950셀(σ 오교정) / 3,684셀(경과 20h)까지 폭주 —
"타겟 알림" 전제 붕괴. 상한 가드가 이를 차단해야 한다.
"""

import math

import pytest

from app.config import settings
from app.llm.exaone import _KOESTER_PARAMS
from app.phase3 import alerts
from app.schemas.persona import PersonaType


def test_coverage_reached_before_cap():
    """집중된 분포 — 상한에 안 걸리고 80% 커버리지에서 멈춘다."""
    poa = {"a": 0.5, "b": 0.3, "c": 0.1, "d": 0.05, "e": 0.05}
    cells = alerts.select_alert_cells(poa)
    assert cells == ["a", "b"]  # 0.5+0.3 = 0.8 ≥ 0.8 — 최소 셀에서 즉시 멈춤


def test_cap_stops_fat_tail():
    """얇은 꼬리 수천 셀 — 커버리지 미달이어도 상한에서 끊는다."""
    n = 5000
    poa = {f"cell{i}": 1.0 / n for i in range(n)}  # 완전 균일 = 최악의 꼬리
    cells = alerts.select_alert_cells(poa)
    assert len(cells) == settings.max_alert_cells


def test_explicit_max_cells_overrides():
    poa = {f"cell{i}": 0.01 for i in range(100)}
    assert len(alerts.select_alert_cells(poa, max_cells=10)) == 10


def test_koester_dementia_matches_isrid_urban():
    """치매 lognormal 이 ISRID Urban 원표 분위수와 정합해야 한다.

    원표 (Koester LPB / Laing 2013 Table 1, n=336): 50%=1.1km, 95%=12.6km.
    회귀 배경: 이전 값(μ=0.47, σ=1.53)은 Dry 지형 값 + 잘못된 95% 해석 —
    topdown 원판 34km + 워커 이탈거리 20km+ (알림 21,950셀 폭주)의 뿌리였다.
    """
    p = _KOESTER_PARAMS[PersonaType.dementia]
    median_km = math.exp(p.mu)
    p95_km = math.exp(p.mu + 1.645 * p.sigma)
    assert median_km == pytest.approx(1.1, rel=0.05)
    assert p95_km == pytest.approx(12.6, rel=0.05)
