"""E2E 대시보드 트레이스 — 궤적·마음 이벤트 수집과 debug API (스텁, 키 불필요)."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.geo.roadnet import OSMnxNetwork
from app.main import app
from app.phase0 import interview
from app.phase1 import intake
from app.phase2 import simulation
from app.schemas.common import GeoPoint
from app.schemas.debug import SimTrace
from app.schemas.persona import AttractionPoint, PersonaType
from app.schemas.prediction import LognormalParams, MindState, PriorParams

FIXTURE = Path(__file__).parent / "fixtures" / "jeongneung_walk_800m.graphml"
LKP = GeoPoint(lat=37.6061, lng=127.0106)
ATTRACTION = GeoPoint(lat=37.6095, lng=127.0140)


@pytest.fixture(scope="module")
def net() -> OSMnxNetwork:
    return OSMnxNetwork.from_graphml(FIXTURE)


def _persona():
    return interview.register_persona(
        None,
        name="김추적", age=78, ptype=PersonaType.dementia,
        home=LKP,
        attraction_points=[AttractionPoint(label="시장", location=ATTRACTION, weight=1.0)],
        behavior_notes=["해질녘 시장 방향으로 걷는 습관"],
    )


def _prior() -> PriorParams:
    return PriorParams(
        strategy_probs={s: 1 / 6 for s in simulation.STRATEGIES},
        attraction_weights={"시장": 1.0},
        radius_lognormal=LognormalParams(mu=0.0, sigma=0.5),
        reasoning="test",
    )


def test_trace_collects_paths_and_result_unchanged(net):
    """트레이스는 궤적을 수집하되 POA 결과를 바꾸지 않는다."""
    trace = SimTrace(max_paths=30)
    poa_traced = simulation.run_monte_carlo(
        LKP, _prior(), None, 1.0, mode="statistical",
        net=net, n_walkers=100, seed=42, trace=trace)
    poa_plain = simulation.run_monte_carlo(
        LKP, _prior(), None, 1.0, mode="statistical",
        net=net, n_walkers=100, seed=42)
    assert poa_traced == poa_plain          # 수집이 rng 소비·로직에 영향 없음
    assert len(trace.walkers) == 30          # max_paths 만큼만 경로 기록
    for w in trace.walkers:
        assert len(w.path) >= 1
        assert all(len(pt) == 2 for pt in w.path)


def test_trace_records_mind_events(net, monkeypatch):
    """agent 모드에서 마음 재해석 이벤트가 위치·트리거·응답과 함께 기록된다."""
    from app import llm

    def fake_reinterpret(persona, current, report, labels):
        return MindState(status="옛집으로 가려 함", confusion=0.8, changed=True), "시장"

    monkeypatch.setattr(llm.exaone, "reinterpret_mind", fake_reinterpret)
    persona = _persona()
    trace = SimTrace()
    simulation.run_monte_carlo(
        LKP, _prior(), persona, 3.0, mode="agent",
        net=net, n_walkers=100, seed=7, trace=trace)
    assert trace.mind_events, "3시간 경과 100워커면 H/A 트리거가 발동해야 함"
    ev = trace.mind_events[0]
    assert ev.trigger and "임계" in ev.trigger
    assert ev.source in ("exaone", "stub", "pool")
    assert ev.status == "옛집으로 가려 함"
    assert ev.goal == "시장"
    fired_walkers = {e.walker_idx for e in trace.mind_events}
    for w in trace.walkers:
        assert w.mind_fired == (w.walker_idx in fired_walkers)


def test_debug_api_bundle_and_interview_get():
    """POST /debug/.../predict → GET /debug/.../bundle, GET /phase0/interviews/{id}."""
    client = TestClient(app)
    persona = _persona()
    case = intake.create_report(
        missing_type=PersonaType.dementia,
        lkp=LKP,
        lkp_time=datetime.now() - timedelta(hours=1),
        persona_id=persona.id,
    )

    r = client.post(f"/debug/cases/{case.id}/predict?seed=42")
    assert r.status_code == 200
    debug = r.json()
    assert debug["walkers"] and debug["exaone_stub"] is True

    r = client.get(f"/debug/cases/{case.id}/bundle")
    assert r.status_code == 200
    b = r.json()
    assert b["persona"]["id"] == persona.id
    assert b["prior"]["strategy_probs"]
    assert set(b["poa_layers"]) == {"combined", "topdown", "bottomup", "statistical"}
    layer = b["poa_layers"]["combined"]
    assert layer["cells"] and len(layer["cells"][0]["polygon"]) >= 5
    assert sum(c["prob"] for c in layer["cells"]) == pytest.approx(layer["coverage"])
    assert b["debug"]["walkers"]

    r = client.get("/debug/overview")
    assert r.status_code == 200
    assert any(c["id"] == case.id and c["has_trace"] for c in r.json()["cases"])

    # 인터뷰 transcript GET
    session = interview.start_interview("보호자", PersonaType.dementia)
    r = client.get(f"/phase0/interviews/{session.id}")
    assert r.status_code == 200
    assert r.json()["messages"], "첫 질문이 transcript 에 있어야 함"
    assert client.get("/phase0/interviews/none").status_code == 404
