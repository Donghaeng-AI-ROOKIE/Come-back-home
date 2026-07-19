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
        id="t", type=PersonaType.dementia, name="테스트", age=78, home=LKP,
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


def test_route_familiarity_known_score_reaches_gauge(net, monkeypatch):
    """route_familiarity 컴파일 결과가 있으면 unfamiliarity 게이지에 known_score 로
    전달된다 (작업4) — 거리 기반 근사 대신 사람-경로 관계 점수를 우선 사용."""
    from app.phase2 import gauges as gauge_mod
    from app.schemas.persona import RouteFamiliarity

    captured: list[float | None] = []
    real_unfamiliarity = gauge_mod.unfamiliarity

    def spy(here, familiar, known_score=None):
        captured.append(known_score)
        return real_unfamiliarity(here, familiar, known_score=known_score)

    monkeypatch.setattr(gauge_mod, "unfamiliarity", spy)

    persona = Persona(
        id="t", type=PersonaType.dementia, name="테스트", age=78, home=LKP,
        attraction_points=[AttractionPoint(label="시장", location=ATTRACTION, weight=1.0)],
        route_familiarity=[RouteFamiliarity(route="시장", score=0.9)],
    )
    prior = _prior({"landmark_seeking": 1.0}, mu=0.5, attraction={"시장": 1.0})
    simulation.run_monte_carlo(LKP, prior, persona, 2.0, mode="statistical",
                               net=net, n_walkers=5, seed=5)
    assert captured, "게이지 스텝이 한 번도 안 돎"
    assert all(k == pytest.approx(0.9) for k in captured)


def test_routine_destination_gets_default_familiarity(net, monkeypatch):
    """origin_slot=routine_destinations 유래 끌림점은 route_familiarity 컴파일 없이도
    기본 익숙함(ROUTINE_DEFAULT_FAMILIARITY)이 known_score 로 전달된다 (작업4)."""
    from app.phase2 import gauges as gauge_mod

    captured: list[float | None] = []
    real_unfamiliarity = gauge_mod.unfamiliarity

    def spy(here, familiar, known_score=None):
        captured.append(known_score)
        return real_unfamiliarity(here, familiar, known_score=known_score)

    monkeypatch.setattr(gauge_mod, "unfamiliarity", spy)

    persona = Persona(
        id="t", type=PersonaType.dementia, name="테스트", age=78, home=LKP,
        attraction_points=[AttractionPoint(label="시장", location=ATTRACTION, weight=1.0,
                                           origin_slot="routine_destinations")],
    )
    prior = _prior({"landmark_seeking": 1.0}, mu=0.5, attraction={"시장": 1.0})
    simulation.run_monte_carlo(LKP, prior, persona, 2.0, mode="statistical",
                               net=net, n_walkers=5, seed=5)
    assert captured
    assert all(k == pytest.approx(gauge_mod.ROUTINE_DEFAULT_FAMILIARITY) for k in captured)


def test_no_origin_slot_falls_back_to_distance(net, monkeypatch):
    """origin_slot 이 없으면(기존 데이터·다른 슬롯 유래) known_score 없이 거리 폴백 그대로."""
    from app.phase2 import gauges as gauge_mod

    captured: list[float | None] = []
    monkeypatch.setattr(gauge_mod, "unfamiliarity",
                        lambda here, familiar, known_score=None: captured.append(known_score) or 0.5)

    prior = _prior({"landmark_seeking": 1.0}, mu=0.5, attraction={"시장": 1.0})
    simulation.run_monte_carlo(LKP, prior, _persona(), 2.0, mode="statistical",
                               net=net, n_walkers=5, seed=5)
    assert captured
    assert all(k is None for k in captured)


def test_agent_mode_full_walkers_budgeted_mind_calls(net, monkeypatch):
    """agent MC: 워커는 두 모드 공통 500 전부 걷되, EXAONE 실호출은 예산 이내.

    회귀 배경: 워커 10명 히스토그램(셀당 0.1 단위 분산)에 α=0.5 를 주던
    통계적 결함 폐기 — 보행(공짜)과 LLM 호출(비싼 것)을 분리한다.
    예산 소진 후 발동은 풀에서 독립 표집되므로 목표 재주입 효과는 유지된다.
    """
    from app import llm
    from app.config import settings
    from app.phase2 import gauges
    from app.schemas.prediction import MindState

    calls = []

    def fake_reinterpret(persona, current, report, labels, prior=None):
        calls.append(report)
        return MindState(status="옛집으로", confusion=0.3, changed=True), "시장"

    monkeypatch.setattr(llm.exaone, "reinterpret_mind", fake_reinterpret)
    # 매 스텝 발동 강제 → 모든 워커가 마음 재해석을 시도 (최악 케이스)
    monkeypatch.setattr(gauges.Gauges, "mind_fired", lambda self, rng: "귀소")

    prior = _prior({"direction_keeping": 1.0}, mu=0.5, attraction={"시장": 1.0})
    poa = simulation.run_monte_carlo(LKP, prior, _persona(), 1.0,
                                     mode="agent", net=net, seed=5)
    # 워커 수 = 공통 500 → 셀 확률은 1/500 단위 (0.1 단위 분산 회귀 방지)
    assert settings.mc_num_walkers == 500
    for p in poa.values():
        assert abs(p * 500 - round(p * 500)) < 1e-6
    # 전 워커 발동에도 실호출은 예산까지만 — 나머지는 풀 표집
    assert len(calls) == settings.mind_call_budget
    # 풀 표집으로도 목표 재주입이 작동 — 질량이 끌림점 쪽으로 쏠린다
    near = sum(p for c, p in poa.items()
               if h3grid.haversine_km(h3grid.cell_center(c), ATTRACTION) < 0.25)
    assert near > 0.3


def test_mind_trigger_receives_prior_for_context(net, monkeypatch):
    """워커의 마음 재해석 호출에 이번 예측의 prior 가 그대로 전달된다 (작업 3)."""
    from app import llm
    from app.phase2 import gauges
    from app.schemas.prediction import MindState

    received = []

    def fake_reinterpret(persona, current, report, labels, prior=None):
        received.append(prior)
        return MindState(status="이동 중", confusion=0.3, changed=True), None

    monkeypatch.setattr(llm.exaone, "reinterpret_mind", fake_reinterpret)
    monkeypatch.setattr(gauges.Gauges, "mind_fired",
                        lambda self, rng: "귀소" if self.elapsed_min > 3 else None)

    prior = _prior({"direction_keeping": 1.0}, mu=1.2, attraction={"시장": 1.0})
    simulation.run_monte_carlo(LKP, prior, _persona(), 2.0, mode="agent",
                               net=net, n_walkers=8, seed=11)
    assert received, "트리거가 한 번도 발동하지 않음"
    assert all(p is prior for p in received)   # 워커 전원이 같은 prior 객체 공유(재계산 없음)


def test_continuous_fallback_without_net():
    """net=None 이면 기존 연속 공간 워커로 동작 (오프라인 폴백)."""
    prior = _prior({s: 1 / 6 for s in simulation.STRATEGIES})
    poa = simulation.run_monte_carlo(LKP, prior, None, 1.0, mode="statistical",
                                     n_walkers=50, seed=9)
    assert abs(sum(poa.values()) - 1.0) < 1e-9
