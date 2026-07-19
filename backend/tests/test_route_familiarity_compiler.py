"""route_familiarity 컴파일러(phase0.route_familiarity_compiler) — list 출력 패턴 검증.

EXAONE 은 가짜 클라이언트로 대체(외부 API 안 침). 가드레일(sanitize_route_familiarity)의
실존 라벨·등급 검증도 같이 확인한다.
"""

from app.phase0.route_familiarity_compiler import compile_route_familiarity
from app.phase2 import guardrail
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, Persona, PersonaType

HOME = GeoPoint(lat=37.6061, lng=127.0106)


class FakeExaone:
    is_stub = False

    def __init__(self, response):
        self.response = response
        self.calls = 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        return self.response


def _persona(attraction_points=None, quotes=None) -> Persona:
    return Persona(
        id="p1", type=PersonaType.dementia, name="김순자", age=78, home=HOME,
        attraction_points=attraction_points or [],
        axis_quotes=quotes or {},
    )


def _ap(label: str, origin_slot: str) -> AttractionPoint:
    return AttractionPoint(label=label, location=HOME, origin_slot=origin_slot)


# ── 가드레일: sanitize_route_familiarity ─────────────────────────────
def test_sanitize_route_familiarity_valid_mapping():
    targets = [_ap("옛집", "autobiographical_destination_pull"),
              _ap("옛 직장", "autobiographical_destination_pull")]
    out = guardrail.sanitize_route_familiarity(
        {"옛집": "상", "옛 직장": "하"}, targets)
    by_route = {r.route: r.score for r in out}
    assert by_route == {"옛집": 0.8, "옛 직장": 0.3}


def test_sanitize_route_familiarity_drops_fabricated_label():
    targets = [_ap("옛집", "autobiographical_destination_pull")]
    out = guardrail.sanitize_route_familiarity(
        {"옛집": "상", "지어낸곳": "상"}, targets)
    assert [r.route for r in out] == ["옛집"]


def test_sanitize_route_familiarity_drops_unknown_level():
    targets = [_ap("옛집", "autobiographical_destination_pull")]
    out = guardrail.sanitize_route_familiarity({"옛집": "매우잘앎"}, targets)
    assert out == []


def test_sanitize_route_familiarity_non_dict_returns_empty():
    targets = [_ap("옛집", "autobiographical_destination_pull")]
    assert guardrail.sanitize_route_familiarity("헛소리", targets) == []
    assert guardrail.sanitize_route_familiarity(None, targets) == []


# ── 컴파일러 본체 ─────────────────────────────────────────────────────
def test_compile_returns_empty_without_autobiographical_targets():
    """routine_destinations 유래 끌림점만 있으면 컴파일 대상 없음 — LLM 호출 안 함."""
    persona = _persona(
        attraction_points=[_ap("정릉시장", "routine_destinations")],
        quotes={"route_environment_familiarity": ["정릉시장에 자주 가세요"]},
    )
    fake = FakeExaone('{"정릉시장": "상"}')
    out = compile_route_familiarity(persona, client=fake)
    assert out == []
    assert fake.calls == 0


def test_compile_returns_empty_without_evidence_text():
    """근거 발화가 아예 없으면 LLM 호출 없이 스킵 — 폴백(거리근사)에 맡김."""
    persona = _persona(
        attraction_points=[_ap("옛집", "autobiographical_destination_pull")],
        quotes={},
    )
    fake = FakeExaone('{"옛집": "상"}')
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


def test_compile_success_parses_and_sanitizes():
    persona = _persona(
        attraction_points=[_ap("옛집", "autobiographical_destination_pull"),
                           _ap("옛 직장", "autobiographical_destination_pull")],
        quotes={"route_environment_familiarity": [
            "옛집 가는 길은 지금도 정확히 기억하세요. 옛 직장 쪽은 재개발돼서 잘 모르세요."]},
    )
    fake = FakeExaone('{"옛집": "상", "옛 직장": "하"}')
    out = compile_route_familiarity(persona, client=fake)
    assert fake.calls == 1
    by_route = {r.route: r.score for r in out}
    assert by_route == {"옛집": 0.8, "옛 직장": 0.3}


def test_compile_hallucinated_label_filtered():
    persona = _persona(
        attraction_points=[_ap("옛집", "autobiographical_destination_pull")],
        quotes={"route_environment_familiarity": ["옛집 얘기를 자주 하세요"]},
    )
    fake = FakeExaone('{"옛집": "상", "지어낸장소": "상"}')
    out = compile_route_familiarity(persona, client=fake)
    assert [r.route for r in out] == ["옛집"]


def test_compile_unparseable_response_falls_back_empty():
    persona = _persona(
        attraction_points=[_ap("옛집", "autobiographical_destination_pull")],
        quotes={"route_environment_familiarity": ["옛집 얘기를 자주 하세요"]},
    )
    fake = FakeExaone("JSON 없이 수다만 떠는 응답")
    out = compile_route_familiarity(persona, client=fake)
    assert out == []


def test_compile_call_error_falls_back_empty():
    class BoomExaone:
        is_stub = False

        def chat(self, *a, **k):
            raise RuntimeError("connection refused")

    persona = _persona(
        attraction_points=[_ap("옛집", "autobiographical_destination_pull")],
        quotes={"route_environment_familiarity": ["옛집 얘기를 자주 하세요"]},
    )
    assert compile_route_familiarity(persona, client=BoomExaone()) == []
