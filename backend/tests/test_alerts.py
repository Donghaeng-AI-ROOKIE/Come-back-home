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


def test_explicit_zero_not_swallowed_by_falsy_default():
    """coverage=0.0 / max_cells=0 을 명시하면 그 값이 존중돼야 한다.

    회귀: `x or default` 는 0 을 falsy 로 보고 기본값으로 치환했다
    (max_cells=0 → 500). `is None` 검사로 교정.
    """
    poa = {f"cell{i}": 1.0 / 100 for i in range(100)}
    # max_cells=0 → 한 셀도 선택 안 함 (기본값 500 으로 새지 않음)
    assert alerts.select_alert_cells(poa, max_cells=0) == []
    # coverage=0.0 → 첫 셀 담고 즉시 커버리지 충족 → 정확히 1셀 (500 아님)
    assert len(alerts.select_alert_cells(poa, coverage=0.0)) == 1


def test_nonfinite_cells_excluded():
    """POA 에 NaN/inf 셀이 있어도 유한값만 선택, acc 오염 없이 커버리지 도달."""
    poa = {"a": 0.5, "bad_nan": float("nan"), "b": 0.3,
           "bad_inf": float("inf"), "c": 0.2}
    cells = alerts.select_alert_cells(poa)
    assert "bad_nan" not in cells and "bad_inf" not in cells
    assert cells == ["a", "b"]  # 0.5+0.3 ≥ 0.8, NaN 이 acc 를 망치지 않음


class TestSelectNewRegionCells:
    """D3 최종판정 — 집합차(현재 − 마지막알림) 중 **합산** 질량이 임계를 넘을 때만,
    그 안에서 상위 커버리지(기본 80%, select_alert_cells 와 같은 로직)만 타겟팅.
    KL이 아니라 집합차인 이유·질량임계가 셀 하나가 아니라 합산인 이유는
    select_new_region_cells docstring 참고."""

    def test_no_new_cells_returns_empty(self):
        last_alert = {"a": 0.5, "b": 0.5}
        current = {"a": 0.4, "b": 0.6}  # 같은 셀 집합, 질량만 재배분
        assert alerts.select_new_region_cells(current, last_alert) == []

    def test_new_cell_above_threshold_returned(self):
        last_alert = {"a": 0.5, "b": 0.5}
        current = {"a": 0.4, "b": 0.4, "c": 0.2}  # c 는 last_alert 에 없던 셀
        assert alerts.select_new_region_cells(current, last_alert) == ["c"]

    def test_new_cells_below_aggregate_threshold_ignored(self):
        last_alert = {"a": 1.0}
        current = {"a": 0.99, "tiny": 0.01}  # 새 셀 합산 질량(0.01)이 임계(기본 0.05) 미달
        assert alerts.select_new_region_cells(current, last_alert) == []

    def test_explicit_mass_threshold_overrides(self):
        last_alert = {"a": 1.0}
        current = {"a": 0.99, "tiny": 0.01}
        assert alerts.select_new_region_cells(current, last_alert, mass_threshold=0.005) == ["tiny"]

    def test_multiple_new_cells_sorted_by_mass_desc(self):
        last_alert = {"a": 1.0}
        current = {"a": 0.5, "big": 0.3, "small": 0.2}
        assert alerts.select_new_region_cells(current, last_alert) == ["big", "small"]

    def test_aggregate_mass_triggers_despite_tiny_individual_cells(self):
        """실측 회귀 배경: 층2 재실행 직후 새 지역 확률은 셀 하나가 아니라
        수십~수백 개에 얇게 퍼진다(실측: 새 셀 149개, 최대 단일 셀 1.3%).
        셀 단위 임계였다면 이 상황(D3 가 원래 잡으려던 바로 그 상황)에서
        영원히 무반응이었다 — 합산 질량 기준으로 고쳐 이 케이스를 잡는다."""
        new_keys = [f"new{i}" for i in range(30)]
        last_alert = {"old": 0.79}
        current = {"old": 0.79, **{k: 0.007 for k in new_keys}}  # 합산 0.21, 개별 0.007
        result = alerts.select_new_region_cells(current, last_alert)
        assert result  # 개별 질량(0.007) < 임계(0.05)여도 합산 초과로 발동
        assert set(result) <= set(new_keys)

    def test_max_cells_caps_new_region_target(self):
        new_keys = [f"new{i}" for i in range(30)]
        last_alert = {"old": 0.5}
        current = {"old": 0.5, **{k: 0.5 / 30 for k in new_keys}}
        assert len(alerts.select_new_region_cells(current, last_alert, max_cells=5)) == 5


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
