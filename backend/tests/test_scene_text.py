"""장면 텍스트 주입 (PR #21 과제2 1단계) — 외인성 자극을 마음 재해석에 공급.

원 아키텍처의 "인식범위 내 장면을 의미 텍스트로 EXAONE 에 공급"이 미구현이라,
envlayer 가 노드별 물·숲·시장 거리를 이미 갖고 있는데도 프롬프트에 안 들어갔다.
좌표는 여전히 불가침 — 위경도가 아니라 "무엇이 보이는가"만 준다.
"""

from pathlib import Path

import pytest

from app.geo.roadnet import OSMnxNetwork
from app.llm.exaone import _build_mind_input, build_scene_text
from app.phase2 import gauges, simulation
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, Persona, PersonaType
from app.schemas.prediction import LognormalParams, MindState, PriorParams

FIXTURE = Path(__file__).parent / "fixtures" / "jeongneung_walk_800m.graphml"
LKP = GeoPoint(lat=37.6061, lng=127.0106)
ATTRACTION = GeoPoint(lat=37.6095, lng=127.0140)


@pytest.fixture(scope="module")
def net() -> OSMnxNetwork:
    return OSMnxNetwork.from_graphml(FIXTURE)


def _persona() -> Persona:
    return Persona(
        id="t", type=PersonaType.dementia, name="테스트", age=78, home=LKP,
        attraction_points=[AttractionPoint(label="시장", location=ATTRACTION, weight=1.0)],
    )


# ── 장면 텍스트 조립 ────────────────────────────────────────────────
def test_scene_text_lists_only_nearby_features():
    """임계 이내 항목만 문장에 들어간다."""
    scene = build_scene_text({"water_m": 30.0, "forest_m": 411.0,
                              "market_m": 55.0, "park_m": None})
    assert "물가 30m" in scene
    assert "시장 55m" in scene
    assert "수풀" not in scene          # 411m — 임계(60m) 밖
    assert "공원" not in scene          # None


def test_scene_text_includes_landcover_and_handles_empty():
    assert "도로" in build_scene_text({"landcover_l3": "도로"})
    assert build_scene_text({}) is None
    assert build_scene_text(None) is None
    assert build_scene_text({"water_m": 5000.0}) is None   # 전부 임계 밖


def test_scene_text_has_no_coordinates():
    """좌표 불가침 — 장면 텍스트에 위경도가 섞이면 안 된다."""
    scene = build_scene_text({"water_m": 30.0, "landcover_l1": "시가화건조지역"})
    assert "37." not in scene and "127." not in scene


def test_water_reaches_prompt_after_child_removal():
    """water 소비처 복원 — 아동 제거(PR #47) 후 phase2 에서 물가가 완전히
    사라졌던 결손을 장면 텍스트 경로로 되살린다.

    방향(끌림/회피)은 알고리즘이 정하지 않는다 — 사실만 주고 해석은 페르소나를
    함께 보는 EXAONE 이 한다.
    """
    prompt = _build_mind_input(_persona(), "혼란도: 높음", ["시장"],
                               scene=build_scene_text({"water_m": 25.0}))
    assert "[주변 장면]" in prompt and "물가 25m" in prompt
    # 알고리즘이 방향을 박지 않았는지 — 회피/접근 지시어가 없어야 한다
    assert "피하" not in prompt and "다가가" not in prompt


def test_scene_omitted_when_absent():
    """장면이 없으면 섹션 자체가 안 붙는다(프롬프트 오염 방지)."""
    assert "[주변 장면]" not in _build_mind_input(_persona(), "혼란도: 낮음", ["시장"])


# ── 시뮬레이션 배선 ─────────────────────────────────────────────────
def test_walker_passes_scene_of_current_node(net, monkeypatch):
    """워커의 마음 재해석 호출에 그 시점 노드의 장면이 전달된다."""
    from app import llm

    received: list = []

    def fake(persona, current, report, labels, prior=None, scene=None):
        received.append(scene)
        return MindState(status="이동 중", confusion=0.3, changed=True), None

    monkeypatch.setattr(llm.exaone, "reinterpret_mind", fake)
    monkeypatch.setattr(gauges.Gauges, "mind_fired", lambda self, rng: "귀소")
    # 전 노드에 물가를 얹어 장면이 반드시 생기게 한다
    monkeypatch.setattr(type(net), "env", lambda self, node: {"water_m": 20.0})

    prior = PriorParams(strategy_probs={"direction_keeping": 1.0},
                        attraction_weights={"시장": 1.0},
                        radius_lognormal=LognormalParams(mu=1.0, sigma=0.1),
                        reasoning="t")
    simulation.run_monte_carlo(LKP, prior, _persona(), 4.0, mode="agent",
                               net=net, n_walkers=3, seed=5)
    assert received, "마음 재해석이 한 번도 발동하지 않음"
    assert all(s and "물가 20m" in s for s in received)
