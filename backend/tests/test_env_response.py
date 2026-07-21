"""개인 환경 반응 컴파일·소비 (PR #21 과제1 페르소나 컴파일).

원 문제의식: 인터뷰에서 "물가만 보면 다가간다"를 받아도 코드의 물끌림은
7세 미만 아동 하드코딩이라 치매 노인의 정보가 죽는다. 아동 제거(PR #47)로
그 하드코딩마저 사라져 water 는 수집만 되고 소비처가 0건이 됐다.

축(axis_scores)은 "얼마나" 반응하는가의 눈금이라 "무엇에" 반응하는가를
담지 못한다 — 이 경로가 그 자리를 채운다.
"""

from pathlib import Path

import pytest

from app.config import settings
from app.geo.roadnet import OSMnxNetwork
from app.phase0.env_response_compiler import compile_env_responses
from app.phase2 import gauges, guardrail, simulation
from app.schemas.common import GeoPoint
from app.schemas.persona import EnvResponse, Persona, PersonaType
from app.schemas.prediction import LognormalParams, PriorParams

FIXTURE = Path(__file__).parent / "fixtures" / "jeongneung_walk_800m.graphml"
LKP = GeoPoint(lat=37.6061, lng=127.0106)

NOTES = ["물가만 보면 자꾸 다가가려고 하세요", "시장은 시끄러워서 늘 피해 다니세요"]


@pytest.fixture(scope="module")
def net() -> OSMnxNetwork:
    return OSMnxNetwork.from_graphml(FIXTURE)


def _persona(responses=None, notes=None) -> Persona:
    return Persona(id="t", type=PersonaType.dementia, name="테스트", age=78, home=LKP,
                   behavior_notes=notes or [], env_responses=responses or [])


class _FakeClient:
    """runs 회 같은 응답을 주는 EXAONE 대역."""
    is_stub = False

    def __init__(self, payload: str, fail_first: bool = False):
        self.payload, self.calls, self.fail_first = payload, 0, fail_first

    def chat(self, messages, **kw):
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise RuntimeError("일시 장애")
        return self.payload


# ── 소비처: 이동 확률 틸트 ──────────────────────────────────────────
def test_approach_raises_and_avoid_lowers_weight():
    approach = _persona([EnvResponse(feature="water", direction="접근", strength=0.9)])
    avoid = _persona([EnvResponse(feature="water", direction="회피", strength=0.9)])
    near = {"water_m": 20.0}
    assert gauges.env_response_weight(near, approach) > 1.0
    assert gauges.env_response_weight(near, avoid) < 1.0


def test_out_of_range_feature_is_ignored():
    """반응 대상이 인식 범위 밖이면 중립 — 지도 반대편 물가에 끌리지 않는다."""
    p = _persona([EnvResponse(feature="water", direction="접근", strength=0.9)])
    assert gauges.env_response_weight({"water_m": 5000.0}, p) == 1.0
    assert gauges.env_response_weight({"forest_m": 20.0}, p) == 1.0   # 다른 대상


def test_neutral_without_responses_or_env():
    assert gauges.env_response_weight({"water_m": 10.0}, _persona()) == 1.0
    assert gauges.env_response_weight(None, _persona(
        [EnvResponse(feature="water", direction="접근", strength=0.9)])) == 1.0
    assert gauges.env_response_weight({"water_m": 10.0}, None) == 1.0


def test_strength_knob_is_an_ablation_switch(monkeypatch):
    p = _persona([EnvResponse(feature="water", direction="접근", strength=0.9)])
    monkeypatch.setattr(settings, "env_response_strength", 0.0)
    assert gauges.env_response_weight({"water_m": 10.0}, p) == 1.0


def test_multiple_responses_compose():
    """여러 대상이 동시에 보이면 곱해진다 — 물가 접근 + 시장 회피가 상쇄."""
    p = _persona([EnvResponse(feature="water", direction="접근", strength=0.9),
                  EnvResponse(feature="market", direction="회피", strength=0.9)])
    both = gauges.env_response_weight({"water_m": 20.0, "market_m": 20.0}, p)
    only_water = gauges.env_response_weight({"water_m": 20.0}, p)
    assert both < only_water


# ── 가드레일 ────────────────────────────────────────────────────────
def test_guardrail_rejects_fabricated_vocabulary():
    ok = guardrail.sanitize_env_responses({"water": ("접근", 0.9)})
    assert len(ok) == 1 and ok[0].feature == "water"
    # 어휘 밖 대상·방향·규정 밖 강도는 전부 버린다
    assert guardrail.sanitize_env_responses({"편의점": ("접근", 0.9)}) == []
    assert guardrail.sanitize_env_responses({"water": ("좋아함", 0.9)}) == []
    assert guardrail.sanitize_env_responses({"water": ("접근", 0.77)}) == []
    assert guardrail.sanitize_env_responses({"water": ("접근", True)}) == []
    assert guardrail.sanitize_env_responses("문자열") == []


# ── 컴파일러 ────────────────────────────────────────────────────────
def test_compiles_direction_and_strength_from_notes():
    payload = ('{"water": {"direction": "접근", "strength": "상", '
               '"quote": "물가만 보면 자꾸 다가가려고 하세요"}, '
               '"market": {"direction": "회피", "strength": "중", '
               '"quote": "시장은 시끄러워서 늘 피해 다니세요"}}')
    out = compile_env_responses(_persona(notes=NOTES), client=_FakeClient(payload), runs=3)
    got = {r.feature: (r.direction, r.strength) for r in out}
    assert got == {"water": ("접근", 0.9), "market": ("회피", 0.5)}


def test_hallucinated_quote_is_dropped():
    """입력에 없는 근거로 판정하면 그 투표를 버린다 (환각 차단)."""
    payload = ('{"water": {"direction": "접근", "strength": "상", '
               '"quote": "보호자가 한 적 없는 말"}}')
    assert compile_env_responses(
        _persona(notes=NOTES), client=_FakeClient(payload), runs=3) == []


def test_fabricated_feature_is_dropped():
    payload = ('{"편의점": {"direction": "접근", "strength": "상", '
               '"quote": "물가만 보면 자꾸 다가가려고 하세요"}}')
    assert compile_env_responses(
        _persona(notes=NOTES), client=_FakeClient(payload), runs=3) == []


def test_retries_once_on_transient_failure():
    payload = ('{"water": {"direction": "접근", "strength": "하", '
               '"quote": "물가만 보면 자꾸 다가가려고 하세요"}}')
    client = _FakeClient(payload, fail_first=True)
    out = compile_env_responses(_persona(notes=NOTES), client=client, runs=1)
    assert len(out) == 1 and out[0].strength == 0.3
    assert client.calls == 2   # 실패 1 + 재시도 1


def test_no_llm_call_when_nothing_to_compile():
    """근거 없음·스텁 모드면 호출 자체를 안 한다 (비용 낭비 방지)."""
    client = _FakeClient("{}")
    assert compile_env_responses(_persona(notes=[]), client=client) == []
    assert client.calls == 0

    stub = _FakeClient("{}")
    stub.is_stub = True
    assert compile_env_responses(_persona(notes=NOTES), client=stub) == []
    assert stub.calls == 0


# ── 통합 ────────────────────────────────────────────────────────────
def test_water_reaches_walker_movement(net, monkeypatch):
    """컴파일 결과가 실제 갈림길 확률까지 도달한다 — 결손 복원 확인."""
    seen: list[float] = []
    real = gauges.env_response_weight
    monkeypatch.setattr(
        gauges, "env_response_weight",
        lambda env, persona: seen.append(real(env, persona)) or seen[-1])
    # 전 노드에 물가를 얹어 반응이 반드시 걸리게 한다
    monkeypatch.setattr(type(net), "env", lambda self, node: {"water_m": 15.0})

    persona = _persona([EnvResponse(feature="water", direction="접근", strength=0.9)])
    prior = PriorParams(strategy_probs={"random_walk": 1.0}, attraction_weights={},
                        radius_lognormal=LognormalParams(mu=1.0, sigma=0.3),
                        reasoning="t")
    simulation.run_monte_carlo(LKP, prior, persona, 2.0, mode="statistical",
                               net=net, n_walkers=10, seed=5)
    assert seen and any(v > 1.0 for v in seen), "환경 반응이 이동 확률에 반영 안 됨"
