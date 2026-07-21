"""예측기 유효반경 정렬 (PR #20 후속) — topdown p95 컷과 MC 표집 지원 일치.

이전 상태: topdown 만 원판을 p95 로 잘랐고, 그래프 MC 는 _MAX_STEPS(경로장
~15km) 부수 안전망뿐, 연속 공간 MC(기본값)는 상한이 아예 없었다. 이제 세
예측기가 radius.py 의 같은 p95 를 지원 경계로 쓴다.
"""

import math
import random
from pathlib import Path

import pytest

from app.geo import h3grid
from app.geo.roadnet import OSMnxNetwork
from app.phase2 import radius, simulation, topdown
from app.schemas.common import GeoPoint
from app.schemas.prediction import LognormalParams, PriorParams

FIXTURE = Path(__file__).parent / "fixtures" / "jeongneung_walk_800m.graphml"
LKP = GeoPoint(lat=37.6061, lng=127.0106)

# ISRID Dementia Urban 재교정값 (PR #20)
DEMENTIA = LognormalParams(mu=0.095, sigma=1.48)


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


def test_p95_matches_isrid_urban():
    """치매 Urban p95 ≈ 12.55km (t=1h) — PR #20 재교정 수치와 일치."""
    assert radius.p95_km(DEMENTIA, 1.0) == pytest.approx(12.55, abs=0.05)
    # 현행 √t 스케일: t=4h → 2배 (√t 결정이 바뀌면 time_multiplier 만 고친다)
    assert radius.p95_km(DEMENTIA, 4.0) == pytest.approx(2 * radius.p95_km(DEMENTIA, 1.0))


def test_sample_never_exceeds_p95():
    """절단 표집 — 어떤 표본도 p95 를 넘지 않고, 본체 분포는 훼손되지 않는다."""
    rng = random.Random(42)
    cap = radius.p95_km(DEMENTIA, 1.0)
    samples = [radius.sample_distance_km(rng, DEMENTIA, 1.0) for _ in range(5000)]
    assert max(samples) <= cap + 1e-9
    # 잘리는 건 상위 5% 꼬리뿐 — 중앙값은 exp(μ) 근방 유지
    med = sorted(samples)[len(samples) // 2]
    assert med == pytest.approx(math.exp(0.095), rel=0.15)


def test_both_mc_modes_use_truncated_sampler(net, monkeypatch):
    """그래프·연속 두 워커 모두 절단 표집기를 워커당 1회 호출한다 (배선 검증)."""
    calls: list[float] = []
    monkeypatch.setattr(radius, "sample_distance_km",
                        lambda rng, params, elapsed: calls.append(elapsed) or 0.2)

    prior = _prior()
    simulation.run_monte_carlo(LKP, prior, None, 2.0, mode="statistical",
                               net=net, n_walkers=7, seed=1)
    assert len(calls) == 7
    simulation.run_monte_carlo(LKP, prior, None, 2.0, mode="statistical",
                               n_walkers=5, seed=1)
    assert len(calls) == 12
    assert all(t == 2.0 for t in calls)


def test_continuous_walkers_within_p95():
    """연속 공간 모드(기본값) — 이전엔 상한이 아예 없던 경로.

    구 코드는 lognormal 꼬리(5%)가 12.55km 를 넘는 워커를 그대로 걸렸다
    (300 워커면 기대 ~15명). 이제 전 종착점이 p95 안이다.
    """
    poa = simulation.run_monte_carlo(LKP, _prior(), None, 1.0, mode="statistical",
                                     n_walkers=300, seed=13)
    cap = radius.p95_km(DEMENTIA, 1.0)
    worst = max(h3grid.haversine_km(LKP, h3grid.cell_center(c)) for c in poa)
    assert worst <= cap + 0.5   # 셀 중심 이산화 여유


def test_topdown_support_unchanged_by_refactor():
    """topdown 은 순수 리팩터링 — 원판 컷이 여전히 같은 p95 공식이다."""
    params = LognormalParams(mu=0.095, sigma=0.8)   # 테스트 속도용 작은 원판(~4.1km)
    prior = PriorParams(strategy_probs={s: 1 / 6 for s in simulation.STRATEGIES},
                        attraction_weights={}, radius_lognormal=params, reasoning="t")
    poa = topdown.topdown_poa(LKP, prior, None, 1.0)
    cap = radius.p95_km(params, 1.0)
    worst = max(h3grid.haversine_km(LKP, h3grid.cell_center(c)) for c in poa)
    assert worst <= cap + 0.3   # 셀 그리드 경계 여유
    assert abs(sum(poa.values()) - 1.0) < 1e-9
