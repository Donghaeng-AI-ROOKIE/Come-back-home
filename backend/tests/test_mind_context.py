"""마음 재해석 프롬프트(_build_mind_input) — 취약성 축 텍스트 주입(작업 2-B) +
prior 컨텍스트 주입(작업 3) 검증. 출력 검증(sanitize_mind)은 안 건드리므로
여기서는 입력 텍스트 구성만 확인한다."""

from app.llm.exaone import ExaoneClient, _build_mind_input
from app.schemas.common import GeoPoint
from app.schemas.persona import Persona, PersonaType
from app.schemas.prediction import LognormalParams, MindState, PriorParams

HOME = GeoPoint(lat=37.6061, lng=127.0106)


def _persona(axis_scores=None) -> Persona:
    return Persona(id="t", type=PersonaType.dementia, name="테스트", age=78, home=HOME,
                   axis_scores=axis_scores or {})


def _prior() -> PriorParams:
    return PriorParams(
        strategy_probs={"route_following": 0.6, "direction_keeping": 0.4},
        attraction_weights={"시장": 0.7, "공원": 0.3},
        radius_lognormal=LognormalParams(mu=0.1, sigma=1.5))


# ── 2-B: 취약성 축 텍스트 ────────────────────────────────────────────
def test_vuln_axis_included_as_text():
    persona = _persona({"wayfinding_error_recovery_deficit": 0.85,
                        "hazard_awareness_vulnerability": 0.2})
    text = _build_mind_input(persona, "귀소충동 높음", ["시장"])
    assert "[특성]" in text
    assert "길찾기·경로회복: 높음" in text
    assert "위험 인식: 낮음" in text


def test_non_vuln_axis_excluded_from_text():
    """2-A 소비처(반경 등)로 이미 쓰인 축은 2-B 텍스트 목록에 없다 — 이중 반영 방지."""
    persona = _persona({"mobility_transport_capacity": 0.9})
    text = _build_mind_input(persona, "보고", [])
    assert "[특성]" not in text


def test_no_axis_scores_omits_section():
    persona = _persona()
    text = _build_mind_input(persona, "보고", [])
    assert "[특성]" not in text


# ── 작업 3: prior 컨텍스트 ───────────────────────────────────────────
# 2026-07-29 앵커 제거: "[유력 목적지 후보]"(argmax 한 줄)는 균형 가중치에서
# 순서 편향을 만들어 폐기 — 대신 후보 전체를 중요도 등급과 함께 나열한다.
def test_prior_context_included_when_given():
    persona = _persona()
    text = _build_mind_input(persona, "보고", ["시장", "공원"], _prior())
    assert "[예측된 이동 성향] 주 전략: route_following" in text
    assert "[유력 목적지 후보]" not in text          # argmax 앵커 없음
    assert "시장 — 중요도 상" in text                # 전 후보 + 등급 병기
    assert "공원 — 중요도 중" in text


def test_candidate_order_shuffled_by_rng():
    """같은 입력이라도 rng 에 따라 후보 나열 순서가 달라진다 (순서 편향 제거)."""
    import random

    persona = _persona()
    orders = set()
    for seed in range(8):
        text = _build_mind_input(persona, "보고", ["시장", "공원"], _prior(),
                                 rng=random.Random(seed))
        i, j = text.index("시장 — "), text.index("공원 — ")
        orders.add(i < j)
    assert orders == {True, False}


def test_prior_none_omits_context():
    text = _build_mind_input(_persona(), "보고", [], None)
    assert "[예측된 이동 성향]" not in text
    assert "[유력 목적지 후보]" not in text


def test_prior_default_omits_context():
    """prior 인자를 아예 안 준 기존 호출부(하위호환)도 그대로 동작."""
    text = _build_mind_input(_persona(), "보고", [])
    assert "[예측된 이동 성향]" not in text


def test_prior_with_no_attraction_weights_skips_destination_line():
    prior = PriorParams(strategy_probs={"staying_put": 1.0}, attraction_weights={},
                        radius_lognormal=LognormalParams(mu=0.1, sigma=1.5))
    text = _build_mind_input(_persona(), "보고", [], prior)
    assert "[예측된 이동 성향] 주 전략: staying_put" in text
    assert "[유력 목적지 후보]" not in text


# ── reinterpret_mind 통합 — prior 가 실제 프롬프트까지 전달되는지 ─────
def test_reinterpret_mind_threads_prior_into_prompt(monkeypatch):
    live = ExaoneClient()
    live.api_key, live.base_url, live.model = "k", "https://x", "m"
    captured = {}

    def fake_chat(messages, **kwargs):
        captured["user"] = messages[-1]["content"]
        return '{"status": "이동 중", "confusion_level": "중", "goal_label": null}'

    monkeypatch.setattr(live, "chat", fake_chat)
    live.reinterpret_mind(_persona(), MindState(), "보고", ["시장"], _prior())
    assert "[예측된 이동 성향] 주 전략: route_following" in captured["user"]
