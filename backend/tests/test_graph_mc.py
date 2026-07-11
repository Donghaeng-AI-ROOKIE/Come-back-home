"""그래프 위 몬테카를로 테스트 — fixture 도로망 주입, 외부 API 안 침."""

from pathlib import Path

import pytest

from app.geo import h3grid
from app.geo.roadnet import OSMnxNetwork
from app.phase2 import simulation
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, Persona, PersonaType
from app.schemas.prediction import LognormalParams, PriorParams

FIXTURE = Path(__file__).parent / "fixtures" / "jeongneung_walk_800m.graphml"
LKP = GeoPoint(lat=37.6061, lng=127.0106)
# fixture 영역 안의 끌림점 (정릉동 북동쪽 ~500m)
ATTRACTION = GeoPoint(lat=37.6095, lng=127.0140)


@pytest.fixture(scope="module")
def net() -> OSMnxNetwork:
    return OSMnxNetwork.from_graphml(FIXTURE)


def _prior(strategy_probs: dict, mu=0.0, sigma=0.5, attraction=None) -> PriorParams:
    return PriorParams(
        strategy_probs=strategy_probs,
        attraction_weights=attraction or {},
        radius_lognormal=LognormalParams(mu=mu, sigma=sigma),
        reasoning="test",
    )


def _persona() -> Persona:
    return Persona(
        id="t", type=PersonaType.dementia, name="테스트", age=78,
        attraction_points=[AttractionPoint(label="시장", location=ATTRACTION, weight=1.0)],
    )


def test_poa_sums_to_one_and_deterministic(net):
    prior = _prior({s: 1 / 6 for s in simulation.STRATEGIES})
    poa1 = simulation.run_monte_carlo(LKP, prior, None, 1.0, mode="statistical",
                                      net=net, n_walkers=100, seed=42)
    poa2 = simulation.run_monte_carlo(LKP, prior, None, 1.0, mode="statistical",
                                      net=net, n_walkers=100, seed=42)
    assert abs(sum(poa1.values()) - 1.0) < 1e-9
    assert poa1 == poa2  # 같은 seed → 같은 결과


def test_endpoints_are_on_road_nodes(net):
    """그래프 워커의 종착점은 항상 도로망 노드 좌표여야 한다 (허공 금지)."""
    node_cells = {h3grid.cell_of(net.node_location(n)) for n in net.graph.nodes}
    prior = _prior({s: 1 / 6 for s in simulation.STRATEGIES}, sigma=1.0)
    poa = simulation.run_monte_carlo(LKP, prior, _persona(), 2.0, mode="statistical",
                                     net=net, n_walkers=200, seed=7)
    assert set(poa.keys()) <= node_cells


def test_staying_put_stays_close(net):
    stay = _prior({"staying_put": 1.0})
    roam = _prior({"random_walk": 1.0}, mu=0.5)

    def mean_dist(poa):
        # 셀 중심까지 평균 거리 (확률 가중)
        return sum(h3grid.haversine_km(LKP, h3grid.cell_center(c)) * p for c, p in poa.items())

    d_stay = mean_dist(simulation.run_monte_carlo(LKP, stay, None, 1.0, mode="statistical",
                                                  net=net, n_walkers=100, seed=1))
    d_roam = mean_dist(simulation.run_monte_carlo(LKP, roam, None, 1.0, mode="statistical",
                                                  net=net, n_walkers=100, seed=1))
    assert d_stay < d_roam


def test_landmark_seeking_pulls_toward_attraction(net):
    """끌림점 지향 워커는 무작위 배회보다 끌림점 근처에 몰려야 한다."""
    seek = _prior({"landmark_seeking": 1.0}, mu=0.5, attraction={"시장": 1.0})
    rand = _prior({"random_walk": 1.0}, mu=0.5)

    def mean_dist_to_attraction(poa):
        return sum(h3grid.haversine_km(ATTRACTION, h3grid.cell_center(c)) * p
                   for c, p in poa.items())

    d_seek = mean_dist_to_attraction(simulation.run_monte_carlo(
        LKP, seek, _persona(), 2.0, mode="statistical", net=net, n_walkers=150, seed=3))
    d_rand = mean_dist_to_attraction(simulation.run_monte_carlo(
        LKP, rand, _persona(), 2.0, mode="statistical", net=net, n_walkers=150, seed=3))
    assert d_seek < d_rand


def test_agent_mode_uses_config_rollouts(net):
    """에이전트 MC 는 실운영 config 값(10)으로 돈다 — E2E 유효성 결정사항."""
    from app.config import settings

    prior = _prior({s: 1 / 6 for s in simulation.STRATEGIES})
    poa = simulation.run_monte_carlo(LKP, prior, None, 1.0, mode="agent", net=net, seed=5)
    # 롤아웃 10회면 셀 확률은 0.1 의 배수
    assert settings.mc_rollouts_agent == 10
    for p in poa.values():
        assert abs(p * 10 - round(p * 10)) < 1e-9


def test_continuous_fallback_without_net():
    """net=None 이면 기존 연속 공간 워커로 동작 (오프라인 폴백)."""
    prior = _prior({s: 1 / 6 for s in simulation.STRATEGIES})
    poa = simulation.run_monte_carlo(LKP, prior, None, 1.0, mode="statistical",
                                     n_walkers=50, seed=9)
    assert abs(sum(poa.values()) - 1.0) < 1e-9
