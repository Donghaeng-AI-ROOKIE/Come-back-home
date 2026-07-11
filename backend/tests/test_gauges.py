"""게이지·트리거·마음 재해석 테스트 — fixture 도로망, 외부 API 안 침."""

import random
from datetime import datetime
from pathlib import Path

import pytest

from app import llm
from app.geo import h3grid
from app.geo.roadnet import OSMnxNetwork
from app.llm.exaone import ExaoneClient
from app.phase2 import gauges, guardrail, simulation
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, Persona, PersonaType
from app.schemas.prediction import LognormalParams, MindState, PriorParams

FIXTURE = Path(__file__).parent / "fixtures" / "jeongneung_walk_800m.graphml"
LKP = GeoPoint(lat=37.6061, lng=127.0106)
ATTRACTION = GeoPoint(lat=37.6095, lng=127.0140)


@pytest.fixture(scope="module")
def net() -> OSMnxNetwork:
    return OSMnxNetwork.from_graphml(FIXTURE)


def _persona(ptype=PersonaType.dementia, age=78) -> Persona:
    return Persona(
        id="t", type=ptype, name="테스트", age=age, home=LKP,
        attraction_points=[AttractionPoint(label="시장", location=ATTRACTION, weight=1.0)],
        behavior_notes=["해질녘 옛집 방향 습관"],
    )


def _prior(strategy_probs, mu=0.0, sigma=0.5, attraction=None) -> PriorParams:
    return PriorParams(strategy_probs=strategy_probs,
                       attraction_weights=attraction or {},
                       radius_lognormal=LognormalParams(mu=mu, sigma=sigma))


# ── 누적·파생 공식 ───────────────────────────────────────────────────
def test_gauges_accumulate_and_derive():
    g = gauges.Gauges(gauges.GaugeConfig())
    g.step(10.0, terrain=0.5, fatigue_mult=1.3, unfamiliarity=1.0, hostile=1.0, dark=True)
    assert g.F == pytest.approx(0.03 * 0.5 * 1.3 * 10)
    assert g.C == pytest.approx((0.015 + 0.0015 + 0.01) * 10)
    assert g.E == pytest.approx(0.05 * 10)
    assert g.H == pytest.approx(0.006 * 10 + 0.5 * g.C)
    assert g.A == pytest.approx(0.6 * g.C + 0.5 * g.E)
    f_before = g.F
    g.rest()
    assert g.F < f_before  # 휴식 시 피로 회복


def test_persona_activation_mapping():
    """회의 종합 매핑 표 — 유형별로 켜지는 게이지가 다르다."""
    young = gauges.config_for(_persona(PersonaType.child, age=5))
    assert young.k_c1 == young.k_h1 == young.k_a1 == 0.0   # 7세 미만: F만

    mid = gauges.config_for(_persona(PersonaType.child, age=9))
    assert mid.h_capability == pytest.approx(0.4)           # 연령가중 귀소

    id_cfg = gauges.config_for(_persona(PersonaType.intellectual_disability, age=14))
    assert id_cfg.k_a1 == 0.0 and id_cfg.k_h1 == 0.0        # A 는 E 중심, H 는 외인성 대체
    assert id_cfg.k_c1 == pytest.approx(0.015 * 0.2)        # C 대폭 축소


def test_hazard_is_probabilistic_and_monotonic():
    assert gauges.p_trigger(0.0, 1.2, 6.0) < 0.01           # 게이지 낮으면 거의 안 터짐
    assert gauges.p_trigger(1.2, 1.2, 6.0) == pytest.approx(0.5)
    assert gauges.p_trigger(0.5, 1.2, 6.0) < gauges.p_trigger(1.0, 1.2, 6.0)


def test_terrain_and_unfamiliarity_and_hostile():
    assert gauges.terrain_difficulty({"highway": "footway"}) < gauges.terrain_difficulty({"highway": "steps"})
    assert gauges.terrain_difficulty({"highway": ["residential", "service"]}) == pytest.approx(0.25)
    assert gauges.terrain_difficulty({}) == pytest.approx(0.4)

    assert gauges.unfamiliarity(LKP, [LKP]) == pytest.approx(0.0)
    far = GeoPoint(lat=37.70, lng=127.10)
    assert gauges.unfamiliarity(far, [LKP]) == pytest.approx(1.0)
    assert gauges.unfamiliarity(LKP, []) == 1.0

    dementia = _persona()
    assert gauges.hostile_exposure({"forest_m": 10.0}, dementia) > 0
    assert gauges.hostile_exposure({"forest_m": 500.0}, dementia) == 0.0
    young = _persona(PersonaType.child, age=5)
    assert gauges.hostile_exposure({"forest_m": 10.0}, young) == 0.0  # 부호 반전 유형


# ── 마음 재해석 가드레일 ─────────────────────────────────────────────
def test_sanitize_mind_maps_levels_and_blocks_fabricated_goal():
    current = MindState()
    mind, goal = guardrail.sanitize_mind(
        {"status": "옛집으로 향함", "confusion_level": "상", "goal_label": "시장"},
        current, ["시장"])
    assert mind.confusion == pytest.approx(0.85) and mind.changed
    assert goal == "시장"

    _, goal2 = guardrail.sanitize_mind({"goal_label": "지어낸 곳"}, current, ["시장"])
    assert goal2 is None                                    # 실존 라벨만 인정


def test_reinterpret_mind_stub_and_fallback(monkeypatch):
    stub = ExaoneClient()
    if not stub.is_stub:
        stub.api_key = ""                                   # 강제 스텁
    mind, goal = stub.reinterpret_mind(_persona(), MindState(confusion=0.5), "보고", ["시장"])
    assert mind.confusion == pytest.approx(0.7) and goal is None

    live = ExaoneClient()
    live.api_key, live.base_url, live.model = "k", "https://x", "m"
    monkeypatch.setattr(live, "chat", lambda *a, **k: (
        '{"status": "옛집으로 돌아가려 함", "confusion_level": "중", "goal_label": "시장"}'))
    mind2, goal2 = live.reinterpret_mind(_persona(), MindState(), "보고", ["시장"])
    assert mind2.status == "옛집으로 돌아가려 함" and goal2 == "시장"


# ── 워커 통합 ────────────────────────────────────────────────────────
def test_mind_trigger_switches_target_and_calls_once(net, monkeypatch):
    """H/A 발동 → reinterpret_mind 1회 호출, 목표가 재주입한 끌림점으로 전환."""
    calls = []

    def fake_reinterpret(persona, current, report, labels):
        calls.append(report)
        return MindState(status="옛집으로", confusion=0.3, changed=True), "시장"

    monkeypatch.setattr(llm.exaone, "reinterpret_mind", fake_reinterpret)
    monkeypatch.setattr(gauges.Gauges, "mind_fired",
                        lambda self, rng: "귀소" if self.elapsed_min > 3 else None)

    prior = _prior({"direction_keeping": 1.0}, mu=1.2, attraction={"시장": 1.0})
    poa = simulation.run_monte_carlo(LKP, prior, _persona(), 2.0, mode="agent",
                                     net=net, n_walkers=8, seed=11)
    assert calls, "트리거가 한 번도 발동하지 않음"
    assert len(calls) <= 8                                  # 워커당 최대 1회
    assert "귀소" in calls[0]                               # 게이지 자연어 보고 포함
    # 목표 전환 재주입 → 상당수 워커가 끌림점 근처에서 종료
    target_cell = h3grid.cell_of(ATTRACTION)
    near = sum(p for c, p in poa.items()
               if h3grid.haversine_km(h3grid.cell_center(c), ATTRACTION) < 0.25)
    assert near > 0.3


def test_statistical_mode_never_calls_exaone(net, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("statistical 모드에서 EXAONE 호출됨")

    monkeypatch.setattr(llm.exaone, "reinterpret_mind", forbidden)
    monkeypatch.setattr(gauges.Gauges, "mind_fired", lambda self, rng: "귀소")
    prior = _prior({s: 1 / 6 for s in simulation.STRATEGIES}, mu=0.5)
    simulation.run_monte_carlo(LKP, prior, _persona(), 1.0, mode="statistical",
                               net=net, n_walkers=30, seed=2)


def test_case_mind_not_mutated_by_rollouts(net, monkeypatch):
    """롤아웃별 mind 사본 — 케이스의 MindState 가 시뮬레이션 부작용으로 안 바뀐다."""
    monkeypatch.setattr(llm.exaone, "reinterpret_mind",
                        lambda *a: (MindState(status="바뀜", confusion=0.99, changed=True), None))
    monkeypatch.setattr(gauges.Gauges, "mind_fired", lambda self, rng: "불안")
    case_mind = MindState(confusion=0.5)
    prior = _prior({"random_walk": 1.0}, mu=0.8)
    simulation.run_monte_carlo(LKP, prior, _persona(), 1.0, mode="agent",
                               net=net, n_walkers=5, mind=case_mind, seed=3)
    assert case_mind.confusion == pytest.approx(0.5)
    assert case_mind.status != "바뀜"


def test_fatigue_shortens_walk(net, monkeypatch):
    """F 발동(휴식) — 같은 seed 에서 피로가 잦을수록 순변위가 줄어든다."""
    prior = _prior({"direction_keeping": 1.0}, mu=1.5, sigma=0.1)

    def mean_dist(poa):
        return sum(h3grid.haversine_km(LKP, h3grid.cell_center(c)) * p for c, p in poa.items())

    monkeypatch.setattr(gauges.Gauges, "fatigue_fired", lambda self, rng: False)
    d_fresh = mean_dist(simulation.run_monte_carlo(
        LKP, prior, _persona(), 2.0, mode="statistical", net=net, n_walkers=60, seed=5))
    monkeypatch.setattr(gauges.Gauges, "fatigue_fired",
                        lambda self, rng: rng.random() < 0.3)
    d_tired = mean_dist(simulation.run_monte_carlo(
        LKP, prior, _persona(), 2.0, mode="statistical", net=net, n_walkers=60, seed=5))
    assert d_tired < d_fresh


def test_young_child_stays_at_water_if_present(net):
    """7세 미만 물 끌림 — 물가 노드(env)가 있으면 그 근처에서 종료 가능해야 한다."""
    # fixture 에는 env 가 없으므로 수동 주입: 시작점에서 몇 노드 떨어진 곳을 물가로
    node = net.nearest_node(GeoPoint(lat=37.6075, lng=127.0120))
    net.node_env = {node: {"water_m": 5.0}}
    try:
        prior = _prior({"random_walk": 1.0}, mu=1.0, sigma=0.1)
        child = _persona(PersonaType.child, age=5)
        poa = simulation.run_monte_carlo(LKP, prior, child, 1.0, mode="statistical",
                                         net=net, n_walkers=100, seed=7)
        water_cell = h3grid.cell_of(net.node_location(node))
        assert poa.get(water_cell, 0.0) > 0.0
    finally:
        net.node_env = {}
