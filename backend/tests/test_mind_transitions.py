"""PR #21 과제3 "다회전환" — 워커당 마음 재해석 1회 → N회(기본 2).

핵심 불변식: 실호출 예산은 그대로다. 1회차 전환만 예산을 쓸 수 있고,
2회차부터는 풀 표집 전용이다. 전환 사이에는 불응기(_MIND_REFRACTORY_STEPS)를
둔다 — H·A 게이지는 발동 후 리셋되지 않아, 불응기가 없으면 2회차가 1회차
직후 거의 같은 상태로 발동해 다회전환이 무의미해지기 때문.
"""

from pathlib import Path

import pytest

from app.config import settings
from app.geo.roadnet import OSMnxNetwork
from app.phase2 import simulation
from app.schemas.common import GeoPoint
from app.schemas.debug import SimTrace
from app.schemas.persona import AttractionPoint, Persona, PersonaType
from app.schemas.prediction import LognormalParams, MindState, PriorParams

FIXTURE = Path(__file__).parent / "fixtures" / "jeongneung_walk_800m.graphml"
LKP = GeoPoint(lat=37.6061, lng=127.0106)
ATTRACTION = GeoPoint(lat=37.6095, lng=127.0140)


@pytest.fixture(scope="module")
def net() -> OSMnxNetwork:
    return OSMnxNetwork.from_graphml(FIXTURE)


def _prior(mu: float = 1.0) -> PriorParams:
    # mu 크게 — 워커가 불응기(30스텝)를 넘겨 오래 걷도록
    return PriorParams(strategy_probs={"direction_keeping": 1.0},
                       attraction_weights={"시장": 1.0},
                       radius_lognormal=LognormalParams(mu=mu, sigma=0.1),
                       reasoning="test")


def _persona() -> Persona:
    return Persona(
        id="t", type=PersonaType.dementia, name="테스트", age=78, home=LKP,
        attraction_points=[AttractionPoint(label="시장", location=ATTRACTION, weight=1.0)],
    )


def _force_fire(monkeypatch):
    from app.phase2 import gauges
    monkeypatch.setattr(gauges.Gauges, "mind_fired", lambda self, rng: "귀소")


def _fake_exaone(monkeypatch, calls: list):
    from app import llm

    def fake(persona, current, report, labels, prior=None, scene=None):
        calls.append(report)
        return MindState(status="옛집으로", confusion=0.4, changed=True), "시장"

    monkeypatch.setattr(llm.exaone, "reinterpret_mind", fake)


def test_second_transition_uses_pool_not_budget(net, monkeypatch):
    """1워커·매 스텝 발동 강제 — 전환은 2회지만 실호출은 정확히 1회."""
    calls: list = []
    _fake_exaone(monkeypatch, calls)
    _force_fire(monkeypatch)

    trace = SimTrace()
    simulation.run_monte_carlo(LKP, _prior(), _persona(), 1.0, mode="agent",
                               net=net, n_walkers=1, seed=21, trace=trace)
    events = trace.mind_events
    assert len(events) == settings.mind_transitions_per_walker == 2
    assert len(calls) == 1                       # 2회차는 예산 미소비
    assert events[0].source in ("exaone", "stub")
    assert events[1].source == "pool"            # 자기 1회차 결과의 풀 표집
    assert events[1].goal == "시장"              # 목표 재주입은 풀 경유로도 유지


def test_refractory_gap_between_transitions(net, monkeypatch):
    """전환 사이 간격 ≥ 불응기 — 연속 스텝 재발동 방지."""
    _fake_exaone(monkeypatch, [])
    _force_fire(monkeypatch)

    trace = SimTrace()
    simulation.run_monte_carlo(LKP, _prior(), _persona(), 1.0, mode="agent",
                               net=net, n_walkers=1, seed=21, trace=trace)
    steps = [e.step for e in trace.mind_events]
    assert len(steps) == 2
    assert steps[1] - steps[0] >= simulation._MIND_REFRACTORY_STEPS


def test_config_one_restores_legacy_single_transition(net, monkeypatch):
    """mind_transitions_per_walker=1 이면 PR #21 원래 동작(워커당 1회)."""
    _fake_exaone(monkeypatch, [])
    _force_fire(monkeypatch)
    monkeypatch.setattr(settings, "mind_transitions_per_walker", 1)

    trace = SimTrace()
    simulation.run_monte_carlo(LKP, _prior(), _persona(), 1.0, mode="agent",
                               net=net, n_walkers=6, seed=21, trace=trace)
    per_walker: dict[int, int] = {}
    for e in trace.mind_events:
        per_walker[e.walker_idx] = per_walker.get(e.walker_idx, 0) + 1
    assert per_walker and all(v == 1 for v in per_walker.values())


def test_budget_invariant_with_many_walkers(net, monkeypatch):
    """전 워커 발동 강제 + 다회전환에도 실호출 총량 == 예산 (PR #21 회귀 유지)."""
    calls: list = []
    _fake_exaone(monkeypatch, calls)
    _force_fire(monkeypatch)

    simulation.run_monte_carlo(LKP, _prior(), _persona(), 1.0, mode="agent",
                               net=net, n_walkers=60, seed=7)
    assert len(calls) == settings.mind_call_budget


def test_budget_zero_pool_empty_falls_back_to_heuristic(net, monkeypatch):
    """예산 0 + 풀 비어있음 — 1·2회차 모두 혼란 심화 휴리스틱으로 안전 폴백."""
    _fake_exaone(monkeypatch, [])
    _force_fire(monkeypatch)
    monkeypatch.setattr(settings, "mind_call_budget", 0)

    trace = SimTrace()
    simulation.run_monte_carlo(LKP, _prior(), _persona(), 1.0, mode="agent",
                               net=net, n_walkers=1, seed=21, trace=trace)
    assert len(trace.mind_events) == 2
    assert all(e.source == "heuristic" for e in trace.mind_events)
