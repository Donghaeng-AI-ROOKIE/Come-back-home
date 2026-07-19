"""route_familiarity 컴파일러(phase0.route_familiarity_compiler) — list 출력 패턴 +
quote 검증 + 다수결(axis_scoring 과 신뢰도 확보 방식 통일, 2026-07-20) 검증.

EXAONE 은 가짜 클라이언트로 대체(외부 API 안 침). 가드레일(sanitize_route_familiarity)의
실존 라벨·점수 검증도 같이 확인한다.
"""

import json

from app.phase0 import axis_scoring
from app.phase0.route_familiarity_compiler import compile_route_familiarity
from app.phase2 import guardrail
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, Persona, PersonaType

HOME = GeoPoint(lat=37.6061, lng=127.0106)


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


def _persona(attraction_points=None, quotes=None) -> Persona:
    return Persona(
        id="p1", type=PersonaType.dementia, name="김순자", age=78, home=HOME,
        attraction_points=attraction_points or [],
        axis_quotes=quotes or {},
    )


def _ap(label: str, origin_slot: str) -> AttractionPoint:
    return AttractionPoint(label=label, location=HOME, origin_slot=origin_slot)


def _resp(mapping: dict) -> str:
    """{"라벨": (등급, 근거문구)} → JSON 응답 문자열 헬퍼."""
    return json.dumps({k: {"choice": c, "quote": q} for k, (c, q) in mapping.items()},
                      ensure_ascii=False)


# ── 가드레일: sanitize_route_familiarity (다수결·quote 검증을 이미 거친 {라벨:점수} 입력) ──
def test_sanitize_route_familiarity_valid_mapping():
    targets = [_ap("옛집", "autobiographical_destination_pull"),
              _ap("옛 직장", "autobiographical_destination_pull")]
    out = guardrail.sanitize_route_familiarity({"옛집": 0.9, "옛 직장": 0.1}, targets)
    by_route = {r.route: r.score for r in out}
    assert by_route == {"옛집": 0.9, "옛 직장": 0.1}


def test_sanitize_route_familiarity_all_five_levels():
    targets = [_ap(f"장소{i}", "autobiographical_destination_pull") for i in range(5)]
    raw = {f"장소{i}": s for i, s in enumerate([0.1, 0.3, 0.5, 0.7, 0.9])}
    out = guardrail.sanitize_route_familiarity(raw, targets)
    by_route = {r.route: r.score for r in out}
    assert by_route == {"장소0": 0.1, "장소1": 0.3, "장소2": 0.5, "장소3": 0.7, "장소4": 0.9}


def test_sanitize_route_familiarity_drops_fabricated_label():
    targets = [_ap("옛집", "autobiographical_destination_pull")]
    out = guardrail.sanitize_route_familiarity({"옛집": 0.9, "지어낸곳": 0.9}, targets)
    assert [r.route for r in out] == ["옛집"]


def test_sanitize_route_familiarity_drops_invalid_score():
    """ROUTE_LEVEL_SCORES 5단계 값이 아닌 것(임의 실수·문자 등급·None)은 버려진다."""
    targets = [_ap("옛집", "autobiographical_destination_pull")]
    assert guardrail.sanitize_route_familiarity({"옛집": 0.42}, targets) == []
    assert guardrail.sanitize_route_familiarity({"옛집": "E"}, targets) == []
    assert guardrail.sanitize_route_familiarity({"옛집": None}, targets) == []


def test_sanitize_route_familiarity_non_dict_returns_empty():
    targets = [_ap("옛집", "autobiographical_destination_pull")]
    assert guardrail.sanitize_route_familiarity("헛소리", targets) == []
    assert guardrail.sanitize_route_familiarity(None, targets) == []


# ── 컴파일러 본체 — 호출 스킵 조건 ────────────────────────────────────
def test_compile_returns_empty_without_autobiographical_targets():
    """routine_destinations 유래 끌림점만 있으면 컴파일 대상 없음 — LLM 호출 안 함."""
    persona = _persona(
        attraction_points=[_ap("정릉시장", "routine_destinations")],
        quotes={"route_environment_familiarity": ["정릉시장에 자주 가세요"]},
    )
    fake = FakeExaone(_resp({"정릉시장": ("E", "정릉시장에 자주 가세요")}))
    out = compile_route_familiarity(persona, client=fake)
    assert out == []
    assert fake.calls == 0


def test_compile_returns_empty_without_evidence_text():
    """근거 발화가 아예 없으면 LLM 호출 없이 스킵 — 폴백(거리근사)에 맡김."""
    persona = _persona(
        attraction_points=[_ap("옛집", "autobiographical_destination_pull")],
        quotes={},
    )
    fake = FakeExaone(_resp({"옛집": ("E", "아무거나")}))
    out = compile_route_familiarity(persona, client=fake)
    assert out == []
    assert fake.calls == 0


def test_compile_stub_client_skips_call():
    class StubExaone:
        is_stub = True

        def chat(self, *a, **k):
            raise AssertionError("스텁인데 호출됨")

    persona = _persona(
        attraction_points=[_ap("옛집", "autobiographical_destination_pull")],
        quotes={"route_environment_familiarity": ["옛집 가는 길은 잘 아세요"]},
    )
    assert compile_route_familiarity(persona, client=StubExaone()) == []


# ── 컴파일러 본체 — 정상 흐름 ─────────────────────────────────────────
def test_compile_success_parses_verifies_quote_and_sanitizes():
    persona = _persona(
        attraction_points=[_ap("옛집", "autobiographical_destination_pull"),
                           _ap("옛 직장", "autobiographical_destination_pull")],
        quotes={"route_environment_familiarity": [
            "옛집 가는 길은 지금도 정확히 기억하세요. 옛 직장 쪽은 재개발돼서 잘 모르세요."]},
    )
    fake = FakeExaone(_resp({
        "옛집": ("E", "옛집 가는 길은 지금도 정확히 기억하세요"),
        "옛 직장": ("A", "옛 직장 쪽은 재개발돼서 잘 모르세요"),
    }))
    out = compile_route_familiarity(persona, client=fake, runs=1)
    assert fake.calls == 1
    by_route = {r.route: r.score for r in out}
    assert by_route == {"옛집": 0.9, "옛 직장": 0.1}


def test_compile_hallucinated_label_filtered():
    persona = _persona(
        attraction_points=[_ap("옛집", "autobiographical_destination_pull")],
        quotes={"route_environment_familiarity": ["옛집 얘기를 자주 하세요"]},
    )
    fake = FakeExaone(_resp({
        "옛집": ("E", "옛집 얘기를 자주 하세요"),
        "지어낸장소": ("E", "지어낸장소 얘기를 자주 하세요"),
    }))
    out = compile_route_familiarity(persona, client=fake, runs=1)
    assert [r.route for r in out] == ["옛집"]


def test_compile_f_grade_omitted_from_result():
    """언급은 됐지만 판정 불가(F)면 결과에서 빠진다 — 폴백(거리근사)에 맡김."""
    persona = _persona(
        attraction_points=[_ap("옛집", "autobiographical_destination_pull"),
                           _ap("옛 직장", "autobiographical_destination_pull")],
        quotes={"route_environment_familiarity": [
            "옛집 가는 길은 잘 아세요. 옛 직장 얘기는 하시는데 어느 정도인진 모르겠어요."]},
    )
    fake = FakeExaone(_resp({"옛집": ("E", "옛집 가는 길은 잘 아세요"), "옛 직장": ("F", "")}))
    out = compile_route_familiarity(persona, client=fake, runs=1)
    assert [r.route for r in out] == ["옛집"]


def test_compile_unparseable_response_falls_back_empty():
    persona = _persona(
        attraction_points=[_ap("옛집", "autobiographical_destination_pull")],
        quotes={"route_environment_familiarity": ["옛집 얘기를 자주 하세요"]},
    )
    fake = FakeExaone("JSON 없이 수다만 떠는 응답")
    out = compile_route_familiarity(persona, client=fake, runs=1)
    assert out == []


def test_compile_call_error_falls_back_empty(monkeypatch):
    monkeypatch.setattr(axis_scoring, "RETRY_WAIT_S", 0)

    class BoomExaone:
        is_stub = False

        def chat(self, *a, **k):
            raise RuntimeError("connection refused")

    persona = _persona(
        attraction_points=[_ap("옛집", "autobiographical_destination_pull")],
        quotes={"route_environment_familiarity": ["옛집 얘기를 자주 하세요"]},
    )
    assert compile_route_familiarity(persona, client=BoomExaone(), runs=1) == []


# ── 신뢰도 확보 장치 — quote 검증 + 다수결 (2026-07-20, axis_scoring 과 통일) ──
def test_compile_quote_verification_rejects_hallucinated_evidence():
    """근거 발화에 실제로 없는 quote 는 그 투표가 버려져 판정 불가로 이어진다(환각 방지)."""
    persona = _persona(
        attraction_points=[_ap("옛집", "autobiographical_destination_pull")],
        quotes={"route_environment_familiarity": ["옛집 가는 길은 잘 아세요"]},
    )
    fake = FakeExaone(_resp({"옛집": ("E", "발화에 전혀 없는 문구를 근거로 댐")}))
    out = compile_route_familiarity(persona, client=fake, runs=1)
    assert out == []   # 유일한 투표가 quote 검증에서 걸러져 다수결 불가


def test_compile_majority_vote_across_runs():
    """기본 runs(3) — 과반이 동의한 등급이 채택된다."""
    persona = _persona(
        attraction_points=[_ap("옛집", "autobiographical_destination_pull")],
        quotes={"route_environment_familiarity": ["옛집 가는 길은 잘 아세요"]},
    )
    fake = FakeExaone([
        _resp({"옛집": ("E", "옛집 가는 길은 잘 아세요")}),
        _resp({"옛집": ("E", "옛집 가는 길은 잘 아세요")}),
        _resp({"옛집": ("C", "옛집 가는 길은 잘 아세요")}),   # 소수 의견
    ])
    out = compile_route_familiarity(persona, client=fake)
    assert fake.calls == 3
    assert [r.score for r in out] == [0.9]   # 과반(E, 2/3) 채택


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
            return _resp({"옛집": ("E", "옛집 가는 길은 잘 아세요")})

    persona = _persona(
        attraction_points=[_ap("옛집", "autobiographical_destination_pull")],
        quotes={"route_environment_familiarity": ["옛집 가는 길은 잘 아세요"]},
    )
    out = compile_route_familiarity(persona, client=FlakyOnce(), runs=1)
    assert [r.score for r in out] == [0.9]
