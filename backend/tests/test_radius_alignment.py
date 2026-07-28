"""예측기 유효반경 — 통계 상한(ISRID p95) ∩ 물리 상한(v_max×t) 정렬.

PR #50: topdown 만 p95 컷이 있고 MC 는 상한이 없던 비대칭 해소.
PR(본): √t 폐기 + 물리 도달 상한 도입 (PR #20 후속 "이중계상" 결정).
"""

import math
import random
from pathlib import Path

import pytest

from app.config import settings
from app.geo import h3grid
from app.geo.roadnet import OSMnxNetwork
from app.phase2 import radius, simulation, topdown
from app.schemas.common import GeoPoint
from app.schemas.persona import Persona, PersonaType
from app.schemas.prediction import LognormalParams, PriorParams

FIXTURE = Path(__file__).parent / "fixtures" / "jeongneung_walk_800m.graphml"
LKP = GeoPoint(lat=37.6061, lng=127.0106)

# ISRID Dementia Urban 재교정값 (PR #20)
DEMENTIA = LognormalParams(mu=0.095, sigma=1.48)
V_WALK = settings.reach_vmax_dementia_kmh          # 4.32


@pytest.fixture(scope="module")
def net() -> OSMnxNetwork:
    return OSMnxNetwork.from_graphml(FIXTURE)


def _prior(mu: float = 0.095, sigma: float = 1.48) -> PriorParams:
    return PriorParams(
        strategy_probs={s: 1 / 6 for s in simulation.STRATEGIES},
        attraction_weights={},
        radius_lognormal=LognormalParams(mu=mu, sigma=sigma),
        reasoning="test",
    )


def _persona(ptype=PersonaType.dementia, **axis) -> Persona:
    return Persona(id="t", type=ptype, name="테스트", age=78, home=LKP,
                   axis_scores=axis)


# ── 통계 상한 ────────────────────────────────────────────────────────
def test_statistical_p95_matches_isrid_and_is_time_independent():
    """통계 상한 = ISRID Urban 12.55km, 경과시간과 무관(√t 폐기)."""
    assert radius.statistical_p95_km(DEMENTIA) == pytest.approx(12.55, abs=0.05)
    # v_max 를 안 주면 물리 상한 미적용 → 시각 무관 동일값
    assert radius.p95_km(DEMENTIA, 1.0) == radius.p95_km(DEMENTIA, 8.0)


# ── 물리 상한 ────────────────────────────────────────────────────────
def test_kinematic_cap_binds_early_statistical_binds_late():
    """반경은 v_max×t 로 자라다 통계 상한(12.55km)에서 멈춘다.

    회귀 배경: 구 √t 는 t=15분에 12.55km 를 줬는데 도보 물리한계는 1.12km —
    11.2배 초과였다. 골든타임 전 구간이 도달 불가능 영역이었다.
    """
    stat = radius.statistical_p95_km(DEMENTIA)
    assert radius.p95_km(DEMENTIA, 0.25, V_WALK) == pytest.approx(1.08)
    assert radius.p95_km(DEMENTIA, 1.0, V_WALK) == pytest.approx(4.32)
    assert radius.p95_km(DEMENTIA, 2.0, V_WALK) == pytest.approx(8.64)
    # 교차점(12.55/4.32 ≈ 2.90h) 이후는 통계 상한이 지배 — 무한 확장 없음
    assert radius.p95_km(DEMENTIA, 4.0, V_WALK) == pytest.approx(stat)
    assert radius.p95_km(DEMENTIA, 24.0, V_WALK) == pytest.approx(stat)


def test_cap_never_collapses_to_zero():
    """t≈0 에서도 하한이 있어 전 워커가 LKP 한 점에 뭉치지 않는다."""
    assert radius.p95_km(DEMENTIA, 0.0, V_WALK) == pytest.approx(radius._MIN_REACH_KM)


def test_vmax_is_walk_only_regardless_of_mobility_score():
    """전부 도보(2026-07-24 안1) — mobility 축 점수는 반경 v_max 에 영향 없음."""
    assert radius.vmax_kmh(None) == V_WALK                       # 유형 미상 → 보수적
    assert radius.vmax_kmh(_persona()) == V_WALK                 # 축 없음 → 도보
    assert radius.vmax_kmh(_persona(mobility_transport_capacity=0.5)) == V_WALK
    assert radius.vmax_kmh(_persona(mobility_transport_capacity=0.9)) == V_WALK
    assert radius.vmax_kmh(
        _persona(PersonaType.intellectual_disability)) == settings.reach_vmax_id_kmh


# ── 절단 표집 ────────────────────────────────────────────────────────
def test_sample_never_exceeds_cap_and_keeps_body():
    """절단 표집 — 상한 초과 0, 본체 분포는 훼손되지 않는다."""
    rng = random.Random(42)
    samples = [radius.sample_distance_km(rng, DEMENTIA, 4.0) for _ in range(5000)]
    assert max(samples) <= radius.statistical_p95_km(DEMENTIA) + 1e-9
    med = sorted(samples)[len(samples) // 2]
    assert med == pytest.approx(math.exp(0.095), rel=0.15)


def test_sample_respects_kinematic_cap():
    """t=1h 도보면 4.32km 초과 표본이 나오지 않는다."""
    rng = random.Random(7)
    cap = radius.p95_km(DEMENTIA, 1.0, V_WALK)
    samples = [radius.sample_distance_km(rng, DEMENTIA, 1.0, V_WALK)
               for _ in range(2000)]
    assert max(samples) <= cap + 1e-9


# ── 예측기 배선 ──────────────────────────────────────────────────────
def test_both_mc_modes_use_truncated_sampler(net, monkeypatch):
    """그래프·연속 두 워커 모두 절단 표집기를 워커당 1회, v_max 와 함께 호출."""
    calls: list[tuple] = []
    monkeypatch.setattr(
        radius, "sample_distance_km",
        lambda rng, params, elapsed, v_max=None: calls.append((elapsed, v_max)) or 0.2)

    prior = _prior()
    simulation.run_monte_carlo(LKP, prior, None, 2.0, mode="statistical",
                               net=net, n_walkers=7, seed=1)
    assert len(calls) == 7
    simulation.run_monte_carlo(LKP, prior, None, 2.0, mode="statistical",
                               n_walkers=5, seed=1)
    assert len(calls) == 12
    assert all(t == 2.0 and v == V_WALK for t, v in calls)


def test_continuous_walkers_within_kinematic_cap():
    """연속 공간 모드(기본값) — 종착점 전부가 도달 가능 범위 안.

    구 코드는 상한이 아예 없어 t=1h 에도 12.55km 밖 종착이 나왔다.
    """
    poa = simulation.run_monte_carlo(LKP, _prior(), None, 1.0, mode="statistical",
                                     n_walkers=300, seed=13)
    cap = radius.p95_km(DEMENTIA, 1.0, V_WALK)      # 4.32km
    worst = max(h3grid.haversine_km(LKP, h3grid.cell_center(c)) for c in poa)
    assert worst <= cap + 0.5                        # 셀 중심 이산화 여유


def test_topdown_disc_follows_same_cap():
    """topdown 원판도 같은 경계 — 세 예측기 지원 정렬."""
    prior = _prior()
    poa = topdown.topdown_poa(LKP, prior, None, 1.0)
    cap = radius.p95_km(DEMENTIA, 1.0, V_WALK)
    worst = max(h3grid.haversine_km(LKP, h3grid.cell_center(c)) for c in poa)
    assert worst <= cap + 0.5
    assert abs(sum(poa.values()) - 1.0) < 1e-9


def test_high_mobility_score_no_longer_widens_disc():
    """전부 도보(2026-07-24 안1) — mobility 축 점수가 높아도 반경 v_max 는 그대로라
    topdown 원판 크기가 달라지지 않는다(과거엔 대중교통으로 넓어졌음)."""
    walk = topdown.topdown_poa(LKP, _prior(), _persona(), 1.0)
    high_mobility = topdown.topdown_poa(
        LKP, _prior(), _persona(mobility_transport_capacity=0.9), 1.0)
    assert len(high_mobility) == len(walk)
