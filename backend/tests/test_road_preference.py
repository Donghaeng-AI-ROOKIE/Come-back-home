"""도로 위계 선호 (PR #21 과제2 3단계) — 간선 기피·이면 선호.

기획팀 「지도 인식 범위 논문 조사」 2번: 치매 실종자는 소음·교통량이 많은
주간선·간선(trunk/primary)을 기피하고 보조간선(secondary)·이면도로
(residential)를 선호한다. 기존엔 갈림길 선택이 방위각만 봤고 도로 위계는
피로 게이지(terrain_difficulty)에만 쓰여, "어느 길을 고르는가"에는 전혀
반영되지 않았다.
"""

from collections import Counter
from pathlib import Path

import pytest

from app.config import settings
from app.geo.roadnet import OSMnxNetwork
from app.phase2 import gauges, simulation
from app.schemas.common import GeoPoint
from app.schemas.debug import SimTrace
from app.schemas.persona import Persona, PersonaType
from app.schemas.prediction import LognormalParams, PriorParams

FIXTURE = Path(__file__).parent / "fixtures" / "jeongneung_walk_800m.graphml"
LKP = GeoPoint(lat=37.6061, lng=127.0106)


@pytest.fixture(scope="module")
def net() -> OSMnxNetwork:
    return OSMnxNetwork.from_graphml(FIXTURE)


def _persona(ptype=PersonaType.dementia) -> Persona:
    return Persona(id="t", type=ptype, name="테스트", age=78, home=LKP)


def _prior() -> PriorParams:
    # random_walk — 목표 방위가 없어야 도로 위계 효과가 순수하게 드러난다
    return PriorParams(strategy_probs={"random_walk": 1.0}, attraction_weights={},
                       radius_lognormal=LognormalParams(mu=1.0, sigma=0.3),
                       reasoning="t")


# ── 배수 표 ─────────────────────────────────────────────────────────
def test_arterial_penalised_and_residential_preferred():
    p = _persona()
    assert gauges.road_preference({"highway": "primary"}, p) < 1.0
    assert gauges.road_preference({"highway": "trunk"}, p) < 1.0
    assert gauges.road_preference({"highway": "residential"}, p) > 1.0
    assert gauges.road_preference({"highway": "secondary"}, p) > 1.0   # 장거리 축
    # 문헌 미언급 위계는 중립 — steps 는 terrain_difficulty 가 이미 반영(이중계상 금지)
    assert gauges.road_preference({"highway": "steps"}, p) == 1.0
    assert gauges.road_preference({"highway": "service"}, p) == 1.0
    assert gauges.road_preference({}, p) == 1.0


def test_applies_to_dementia_only():
    """문헌 근거가 치매 대상 — 발달장애·유형미상은 중립으로 남긴다."""
    assert gauges.road_preference(
        {"highway": "primary"}, _persona(PersonaType.intellectual_disability)) == 1.0
    assert gauges.road_preference({"highway": "primary"}, None) == 1.0


def test_osmnx_list_tag_handled():
    """OSMnx 는 highway 를 list 로 줄 때가 있다 (terrain_difficulty 와 같은 방어)."""
    assert gauges.road_preference(
        {"highway": ["primary", "secondary"]}, _persona()) < 1.0


def test_strength_knob_disables_and_amplifies(monkeypatch):
    """strength 는 ablation 노브 — 0 이면 기능 끔, 2 면 대비 강화."""
    p = _persona()
    base = gauges.road_preference({"highway": "primary"}, p)

    monkeypatch.setattr(settings, "road_preference_strength", 0.0)
    assert gauges.road_preference({"highway": "primary"}, p) == 1.0
    assert gauges.road_preference({"highway": "residential"}, p) == 1.0

    monkeypatch.setattr(settings, "road_preference_strength", 2.0)
    assert gauges.road_preference({"highway": "primary"}, p) == pytest.approx(base ** 2)


# ── 워커가 실제로 밟은 도로 ──────────────────────────────────────────
def _traversed_highways(net, trace: SimTrace) -> Counter:
    """워커 궤적 좌표열 → 통과한 엣지의 highway 태그 분포."""
    loc2node = {}
    for n in net.graph.nodes:
        loc = net.node_location(n)
        loc2node[(round(loc.lat, 7), round(loc.lng, 7))] = n

    c: Counter = Counter()
    for w in trace.walkers:
        nodes = [loc2node.get((round(lat, 7), round(lng, 7))) for lat, lng in w.path]
        for u, v in zip(nodes, nodes[1:]):
            if u is None or v is None:
                continue
            hw = net.edge_attrs(u, v).get("highway")
            if isinstance(hw, list) and hw:
                hw = hw[0]
            c[hw] += 1
    return c


def _run(net, monkeypatch, strength: float) -> Counter:
    monkeypatch.setattr(settings, "road_preference_strength", strength)
    trace = SimTrace()
    simulation.run_monte_carlo(LKP, _prior(), _persona(), 2.0, mode="statistical",
                               net=net, n_walkers=60, seed=99, trace=trace)
    return _traversed_highways(net, trace)


def test_walkers_avoid_arterials_and_favour_residential(net, monkeypatch):
    """실제 보행 궤적에서 간선 통과 비중이 줄고 이면도로 비중이 는다.

    기능 끔(strength=0) 대비 켬(strength=1)을 같은 시드로 비교한다.
    """
    off = _run(net, monkeypatch, 0.0)
    on = _run(net, monkeypatch, 1.0)

    def share(c: Counter, keys) -> float:
        total = sum(c.values())
        return sum(c[k] for k in keys) / total if total else 0.0

    arterial = ("primary", "primary_link", "trunk", "trunk_link")
    assert sum(off.values()) > 500, "궤적 표본이 너무 적어 비교 무의미"
    assert share(on, arterial) < share(off, arterial)
    assert share(on, ("residential",)) > share(off, ("residential",))


def test_strength_zero_is_a_true_ablation_switch(net, monkeypatch):
    """strength=0 이면 보행 중 단 한 번도 1.0 이외의 배수가 안 나온다.

    평가 하네스가 이 노브로 "위계 선호 없음" 대조군을 만들 수 있어야 하므로,
    끔 상태에서 확률식이 실제로 도입 이전과 동일함을 보장한다.
    (유형 간 비교로는 검증할 수 없다 — 치매·발달장애는 게이지 계수·보행속도·
    v_max 가 모두 달라 위계 외 요인으로도 결과가 갈린다.)
    """
    seen: list[float] = []
    real = gauges.road_preference
    monkeypatch.setattr(
        gauges, "road_preference",
        lambda attrs, persona: seen.append(real(attrs, persona)) or seen[-1])

    monkeypatch.setattr(settings, "road_preference_strength", 0.0)
    simulation.run_monte_carlo(LKP, _prior(), _persona(), 2.0, mode="statistical",
                               net=net, n_walkers=20, seed=3)
    assert seen, "갈림길 가중치 계산이 한 번도 안 돎"
    assert set(seen) == {1.0}

    # 켜면 실제로 1.0 아닌 값이 섞인다 (노브가 죽어있지 않다는 반대 방향 확인)
    seen.clear()
    monkeypatch.setattr(settings, "road_preference_strength", 1.0)
    simulation.run_monte_carlo(LKP, _prior(), _persona(), 2.0, mode="statistical",
                               net=net, n_walkers=20, seed=3)
    assert any(v != 1.0 for v in seen)


def test_wiring_called_per_neighbour(net, monkeypatch):
    """갈림길마다 이웃 수만큼 호출된다 — 한 엣지만 보고 끝내지 않는지."""
    calls: list = []
    real = gauges.road_preference
    monkeypatch.setattr(
        gauges, "road_preference",
        lambda attrs, persona: calls.append(attrs.get("highway")) or real(attrs, persona))

    simulation.run_monte_carlo(LKP, _prior(), _persona(), 2.0, mode="statistical",
                               net=net, n_walkers=5, seed=3)
    # 실제 도로 태그가 전달되는지 (빈 dict 만 오면 배선이 틀린 것)
    assert calls and any(h is not None for h in calls)
