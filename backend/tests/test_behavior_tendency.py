"""behavior_tendency 컴파일러(phase0.behavior_compiler) + guardrail 소비(전략확률
방향 틸트) 검증 — P1-3(lost_behavior/dementia_wandering_pattern 미소비 해소).

EXAONE 은 가짜 클라이언트로 대체(외부 API 안 침). quote 검증·다수결·우선순위
(dementia_wandering_pattern > lost_behavior) 및 guardrail 의 _tilt_by_tendency ·
apply_axis_scores 배선(branch4, branch2 elopement 와의 합성)을 함께 확인한다.
"""

import json

import pytest

from app.phase0 import axis_scoring
from app.phase0.behavior_compiler import compile_behavior_tendency
from app.phase2 import guardrail
from app.schemas.common import GeoPoint
from app.schemas.persona import Persona, PersonaType
from app.schemas.prediction import LognormalParams, PriorParams

HOME = GeoPoint(lat=37.6061, lng=127.0106)

DEFAULT_STRATEGY = {
    "route_following": 0.30, "direction_keeping": 0.25, "random_walk": 0.15,
    "backtracking": 0.05, "staying_put": 0.10, "landmark_seeking": 0.15,
}


class FakeExaone:
    """응답을 순서대로(라운드로빈) 돌려준다 — 단일 응답 문자열도 허용."""
    is_stub = False

    def __init__(self, responses):
        self.responses = [responses] if isinstance(responses, str) else list(responses)
        self.calls = 0

    def chat(self, messages, **kwargs):
        resp = self.responses[self.calls % len(self.responses)]
        self.calls += 1
        return resp


def _persona(quotes=None) -> Persona:
    return Persona(id="p1", type=PersonaType.dementia, name="김순자", age=78, home=HOME,
                   axis_quotes=quotes or {})


def _resp(tendency: str, quote: str = "") -> str:
    return json.dumps({"tendency": tendency, "quote": quote}, ensure_ascii=False)


# ── 컴파일러 본체 — 호출 스킵 조건 ────────────────────────────────────
def test_compile_returns_none_without_any_evidence():
    persona = _persona(quotes={})
    fake = FakeExaone(_resp("이동", "아무거나"))
    assert compile_behavior_tendency(persona, client=fake) is None
    assert fake.calls == 0


def test_compile_stub_client_skips_call():
    class StubExaone:
        is_stub = True

        def chat(self, *a, **k):
            raise AssertionError("스텁인데 호출됨")

    persona = _persona(quotes={"lost_behavior": ["길을 잃으면 계속 걸어갑니다"]})
    assert compile_behavior_tendency(persona, client=StubExaone()) is None


# ── 컴파일러 본체 — 정상 흐름·매핑 ────────────────────────────────────
def test_compile_maps_korean_label_to_tendency():
    persona = _persona(quotes={"lost_behavior": ["길을 잃으면 계속 걸어갑니다"]})
    fake = FakeExaone(_resp("이동", "길을 잃으면 계속 걸어갑니다"))
    assert compile_behavior_tendency(persona, client=fake, runs=1) == "move"


def test_compile_hallucinated_label_rejected():
    persona = _persona(quotes={"lost_behavior": ["길을 잃으면 계속 걸어갑니다"]})
    fake = FakeExaone(_resp("지어낸분류", "길을 잃으면 계속 걸어갑니다"))
    assert compile_behavior_tendency(persona, client=fake, runs=1) is None


def test_compile_quote_verification_rejects_hallucinated_evidence():
    persona = _persona(quotes={"lost_behavior": ["길을 잃으면 계속 걸어갑니다"]})
    fake = FakeExaone(_resp("이동", "발화에 전혀 없는 문구"))
    assert compile_behavior_tendency(persona, client=fake, runs=1) is None


def test_compile_no_signal_returns_none():
    """"해당없음"은 F 처럼 버려지지 않고 투표에 남아, 다수면 그대로 None(판정 불가)이 된다."""
    persona = _persona(quotes={"lost_behavior": ["오늘 날씨 얘기만 하셨어요"]})
    fake = FakeExaone(_resp("해당없음", ""))
    assert compile_behavior_tendency(persona, client=fake, runs=1) is None


def test_compile_transient_failure_retried(monkeypatch):
    """일시 장애는 1회 재시도 후 성공하면 그 run 이 살아남는다 — axis_scoring 과 동일 원칙."""
    monkeypatch.setattr(axis_scoring, "RETRY_WAIT_S", 0)

    class FlakyOnce:
        is_stub = False

        def __init__(self):
            self.calls = 0

        def chat(self, *a, **k):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("일시 장애")
            return _resp("머무름", "제자리에 가만히 서 있습니다")

    persona = _persona(quotes={"lost_behavior": ["제자리에 가만히 서 있습니다"]})
    assert compile_behavior_tendency(persona, client=FlakyOnce(), runs=1) == "stay"


def test_compile_three_way_tie_returns_none_not_alphabetical():
    """3회 판정이 전부 다르면 과반이 없다 — axis_scoring._majority 의 "중앙값" 폴백을
    그대로 쓰면 명목형 tendency 에 알파벳순 타이브레이크가 생기므로, 이 경우는
    None(판정 불가)으로 처리해야 한다(2026-07-25 셀프리뷰에서 발견)."""
    persona = _persona(quotes={"lost_behavior": ["여러 행동이 뒤섞여 나타납니다"]})
    fake = FakeExaone([
        _resp("머무름", "여러 행동이 뒤섞여 나타납니다"),
        _resp("이동", "여러 행동이 뒤섞여 나타납니다"),
        _resp("은신", "여러 행동이 뒤섞여 나타납니다"),
    ])
    assert compile_behavior_tendency(persona, client=fake, runs=3) is None


def test_compile_majority_vote_across_runs():
    """기본 runs(3) — 과반이 동의한 분류가 채택된다."""
    persona = _persona(quotes={"lost_behavior": ["같은 곳을 계속 왔다갔다 합니다"]})
    fake = FakeExaone([
        _resp("왕복", "같은 곳을 계속 왔다갔다 합니다"),
        _resp("왕복", "같은 곳을 계속 왔다갔다 합니다"),
        _resp("이동", "같은 곳을 계속 왔다갔다 합니다"),   # 소수 의견
    ])
    assert compile_behavior_tendency(persona, client=fake) == "backtrack"
    assert fake.calls == 3


# ── 우선순위: dementia_wandering_pattern > lost_behavior ──────────────
def test_dementia_wandering_takes_priority_over_lost_behavior():
    persona = _persona(quotes={
        "dementia_wandering_pattern": ["발견 당시 숨어 있었습니다"],
        "lost_behavior": ["평소엔 계속 걸어다니십니다"],
    })
    fake = FakeExaone(_resp("은신", "발견 당시 숨어 있었습니다"))
    assert compile_behavior_tendency(persona, client=fake, runs=1) == "hide"
    assert fake.calls == 1   # lost_behavior 는 시도조차 안 함(우선순위 축 성공)


def test_falls_back_to_lost_behavior_when_wandering_inconclusive():
    persona = _persona(quotes={
        "dementia_wandering_pattern": ["장소만 언급되고 행동 묘사는 없습니다"],
        "lost_behavior": ["평소엔 계속 걸어다니십니다"],
    })
    fake = FakeExaone([
        _resp("해당없음", ""),                              # dementia_wandering 판정 불가
        _resp("이동", "평소엔 계속 걸어다니십니다"),         # lost_behavior 로 대체
    ])
    assert compile_behavior_tendency(persona, client=fake, runs=1) == "move"
    assert fake.calls == 2   # 두 소스 모두 호출됨(우선순위 축 실패 → 백업 시도)


# ── guardrail 소비: _tilt_by_tendency ─────────────────────────────────
def test_tilt_stay_boosts_staying_put():
    out = guardrail._tilt_by_tendency(DEFAULT_STRATEGY, "stay")
    assert out["staying_put"] > DEFAULT_STRATEGY["staying_put"]
    assert abs(sum(out.values()) - 1.0) < 1e-9
    assert all(v > 0 for v in out.values())   # ε-floor 유지(0 확률 금지 원칙)


def test_tilt_hide_weaker_than_stay():
    """은신은 짧게 이동한 뒤 정지 — staying_put 상승폭이 머무름보다 작아야 한다."""
    stay_out = guardrail._tilt_by_tendency(DEFAULT_STRATEGY, "stay")
    hide_out = guardrail._tilt_by_tendency(DEFAULT_STRATEGY, "hide")
    assert hide_out["staying_put"] > DEFAULT_STRATEGY["staying_put"]
    assert hide_out["staying_put"] < stay_out["staying_put"]


def test_tilt_move_boosts_random_walk():
    # move(길 잃으면 계속 이동)는 익숙함/목적지 정보가 없는 "안 멈추고 배회"이므로
    # route_following(=route_familiarity 소비 창구)이 아니라 random_walk 로 소비한다.
    out = guardrail._tilt_by_tendency(DEFAULT_STRATEGY, "move")
    assert out["random_walk"] > DEFAULT_STRATEGY["random_walk"]
    assert out["route_following"] < DEFAULT_STRATEGY["route_following"]  # 재정규화로 상대 하락
    assert abs(sum(out.values()) - 1.0) < 1e-9


def test_tilt_backtrack_boosts_backtracking():
    out = guardrail._tilt_by_tendency(DEFAULT_STRATEGY, "backtrack")
    assert out["backtracking"] > DEFAULT_STRATEGY["backtracking"]


def test_tilt_none_or_unknown_is_identity():
    assert guardrail._tilt_by_tendency(DEFAULT_STRATEGY, None) == DEFAULT_STRATEGY
    assert guardrail._tilt_by_tendency(DEFAULT_STRATEGY, "지어낸값") == DEFAULT_STRATEGY


# ── apply_axis_scores 배선 — branch4 단독 + branch2(elopement)와의 합성 ──
def _prior(**overrides) -> PriorParams:
    base = dict(strategy_probs=dict(DEFAULT_STRATEGY), attraction_weights={},
                radius_lognormal=LognormalParams(mu=0.095, sigma=1.48), reasoning="")
    base.update(overrides)
    return PriorParams(**base)


def _persona_full(ptype=PersonaType.dementia, tendency=None) -> Persona:
    return Persona(id="t", type=ptype, name="테스트", age=78, home=HOME,
                   behavior_tendency=tendency)


def test_apply_axis_scores_applies_behavior_tendency_tilt():
    base = LognormalParams(mu=0.095, sigma=1.48)
    persona = _persona_full(tendency="stay")
    prior = guardrail.apply_axis_scores(_prior(), {}, persona, base)
    assert prior.strategy_probs["staying_put"] > DEFAULT_STRATEGY["staying_put"]


def test_apply_axis_scores_no_tendency_is_identity():
    base = LognormalParams(mu=0.095, sigma=1.48)
    persona = _persona_full(tendency=None)
    prior = guardrail.apply_axis_scores(_prior(), {}, persona, base)
    assert prior.strategy_probs == DEFAULT_STRATEGY


def test_apply_axis_scores_composes_with_elopement_sharpen():
    """ID + elopement(branch2) + behavior_tendency(branch4) — 둘 다 strategy_probs 를
    건드리고 곱셈 합성된다(덮어쓰기 아님)."""
    base = LognormalParams(mu=0.89, sigma=1.50)
    persona = _persona_full(ptype=PersonaType.intellectual_disability, tendency="stay")
    prior = guardrail.apply_axis_scores(
        _prior(), {"elopement_pattern_consistency": 0.9}, persona, base)
    assert abs(sum(prior.strategy_probs.values()) - 1.0) < 1e-9
    assert all(v > 0 for v in prior.strategy_probs.values())

    elopement_only = guardrail.apply_axis_scores(
        _prior(), {"elopement_pattern_consistency": 0.9},
        _persona_full(ptype=PersonaType.intellectual_disability, tendency=None), base)
    # branch4 가 branch2 결과 위에 추가로 얹어져 staying_put 이 더 강하게 밀린다
    assert prior.strategy_probs["staying_put"] > elopement_only.strategy_probs["staying_put"]


def test_strategy_tilt_order_is_fixed_by_design_and_not_commutative():
    """power-law 쏠림(_sharpen)과 곱셈 틸트(_tilt_by_tendency)는 수학적으로 교환되지
    않는다 — apply_axis_scores 가 고정한 순서(elopement 먼저 → behavior_tendency
    나중)를 문서화하는 회귀 테스트. 순서를 바꾸면 staying_put 최종 확률이 거의
    2배 차이 난다(2026-07-25 셀프리뷰 실측) — 이 테스트가 깨지면 순서가 바뀐 것."""
    forward = guardrail._floor_renormalize(
        guardrail._tilt_by_tendency(
            guardrail._sharpen(DEFAULT_STRATEGY, 0.9, floor=0.0), "stay", floor=0.0),
        guardrail.EPSILON)
    reverse = guardrail._floor_renormalize(
        guardrail._sharpen(
            guardrail._tilt_by_tendency(DEFAULT_STRATEGY, "stay", floor=0.0), 0.9, floor=0.0),
        guardrail.EPSILON)
    assert forward["staying_put"] < reverse["staying_put"] * 0.6   # 순서 고정 확인(≈2배 차이)
    # apply_axis_scores 가 실제로 forward(elopement→tendency) 순서를 쓰는지 재확인
    composed = guardrail.apply_axis_scores(
        _prior(), {"elopement_pattern_consistency": 0.9},
        _persona_full(ptype=PersonaType.intellectual_disability, tendency="stay"),
        LognormalParams(mu=0.89, sigma=1.50))
    assert composed.strategy_probs["staying_put"] == pytest.approx(forward["staying_put"])
