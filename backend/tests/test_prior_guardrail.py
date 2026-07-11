"""목적지 예측 가드레일 테스트 — LLM 출력의 "택도 없는" 케이스 방어."""

import pytest

from app.llm.exaone import ExaoneClient
from app.phase2 import guardrail
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, Persona, PersonaType
from app.schemas.prediction import LognormalParams, PriorParams
from app.schemas.report import MissingReport

HOME = GeoPoint(lat=37.6061, lng=127.0106)

DEFAULT_STRATEGY = {
    "route_following": 0.30, "direction_keeping": 0.25, "random_walk": 0.15,
    "backtracking": 0.05, "staying_put": 0.10, "landmark_seeking": 0.15,
}


def _persona(n_attractions: int = 2) -> Persona:
    points = [
        AttractionPoint(label=f"장소{i}", location=HOME, weight=1.0)
        for i in range(n_attractions)
    ]
    return Persona(id="t", type=PersonaType.dementia, name="테스트", age=78,
                   home=HOME, attraction_points=points)


# ── 전략확률 ─────────────────────────────────────────────────────────
def test_strategy_unknown_keys_dropped_and_renormalized():
    raw = {"route_following": 0.5, "landmark_seeking": 0.5, "teleport": 99.0}
    probs = guardrail.sanitize_strategy_probs(raw, DEFAULT_STRATEGY)
    assert "teleport" not in probs
    assert abs(sum(probs.values()) - 1.0) < 1e-9
    # 빠진 전략도 ε-floor 로 살아 있어야 한다 (확률 0 금지)
    assert all(probs[s] > 0 for s in DEFAULT_STRATEGY)


def test_strategy_garbage_falls_back_to_default():
    assert guardrail.sanitize_strategy_probs("말도 안 되는 출력", DEFAULT_STRATEGY) == DEFAULT_STRATEGY
    assert guardrail.sanitize_strategy_probs({"route_following": -1}, DEFAULT_STRATEGY) == DEFAULT_STRATEGY
    assert guardrail.sanitize_strategy_probs({}, DEFAULT_STRATEGY) == DEFAULT_STRATEGY


# ── 끌림점 등급 ──────────────────────────────────────────────────────
def test_attraction_fabricated_label_dropped_and_missing_defaults_to_mid():
    weights = guardrail.sanitize_attraction_levels(
        {"장소0": "상", "지어낸곳": "상"}, _persona(2))
    assert set(weights) == {"장소0", "장소1"}          # 지어낸 라벨 제거
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert weights["장소0"] > weights["장소1"]          # 상 > 중(미평가 기본값)


def test_attraction_cap_prevents_single_point_dominance():
    weights = guardrail.sanitize_attraction_levels(
        {"장소0": "상", "장소1": "하"}, _persona(2))    # 고정 매핑이면 0.75 vs 0.25
    assert weights["장소0"] <= guardrail.ATTRACTION_CAP + 1e-9
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_attraction_no_persona_returns_empty():
    assert guardrail.sanitize_attraction_levels({"장소0": "상"}, None) == {}


# ── 반경 등급 ────────────────────────────────────────────────────────
def test_radius_level_adjusts_mu_within_bounds():
    profile = LognormalParams(mu=0.47, sigma=1.53)
    assert guardrail.sanitize_radius("상", profile).mu == pytest.approx(0.87)
    assert guardrail.sanitize_radius("하", profile).mu == pytest.approx(0.07)
    # 이상한 등급·수치는 무시 — 프로파일 그대로
    assert guardrail.sanitize_radius("초원거리", profile).mu == pytest.approx(0.47)
    assert guardrail.sanitize_radius(3.0, profile).mu == pytest.approx(0.47)
    # σ 는 항상 프로파일 값
    assert guardrail.sanitize_radius("상", profile).sigma == pytest.approx(1.53)


# ── reasoning 키 구제 ────────────────────────────────────────────────
def test_reasoning_recovered_from_mangled_key():
    """실측 사례: EXAONE 이 "reasoning" 을 "reason্ম" 로 어그러뜨림."""
    default = PriorParams(strategy_probs=DEFAULT_STRATEGY, attraction_weights={},
                          radius_lognormal=LognormalParams(mu=0.47, sigma=1.53))
    prior = guardrail.sanitize_prior({"reasonা": "옛집 지향 근거"}, None, default)
    assert prior.reasoning == "옛집 지향 근거"


# ── generate_prior 통합 (chat 모킹 — 외부 API 안 침) ────────────────
def _report() -> MissingReport:
    from datetime import datetime
    return MissingReport(id="r", missing_type=PersonaType.dementia,
                         lkp=HOME, lkp_time=datetime(2026, 7, 11, 18, 0))


def _live_client() -> ExaoneClient:
    client = ExaoneClient()
    client.api_key, client.base_url, client.model = "k", "https://x", "m"  # is_stub=False
    return client


def test_generate_prior_uses_sanitized_llm_output(monkeypatch):
    client = _live_client()
    monkeypatch.setattr(client, "chat", lambda *a, **k: (
        '설명 문장이 붙어도 {"strategy_probs": {"landmark_seeking": 1.0}, '
        '"attraction_levels": {"장소0": "상", "장소1": "하"}, '
        '"radius_level": "하", "reasoning": "옛집 지향 습관"} 이렇게 파싱된다'))
    prior = client.generate_prior(_persona(2), _report())
    assert prior.strategy_probs["landmark_seeking"] > 0.8      # ε-floor 몫 제외 최대
    assert abs(sum(prior.strategy_probs.values()) - 1.0) < 1e-9
    assert prior.attraction_weights["장소0"] <= guardrail.ATTRACTION_CAP + 1e-9
    assert prior.radius_lognormal.mu == pytest.approx(0.47 - 0.4)
    assert "옛집" in prior.reasoning


def test_generate_prior_falls_back_on_api_error(monkeypatch):
    client = _live_client()

    def boom(*a, **k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(client, "chat", boom)
    prior = client.generate_prior(_persona(2), _report())
    assert prior.strategy_probs == DEFAULT_STRATEGY            # 통계 기본값
    assert "[폴백]" in prior.reasoning


def test_generate_prior_falls_back_on_unparseable_json(monkeypatch):
    client = _live_client()
    monkeypatch.setattr(client, "chat", lambda *a, **k: "JSON 없이 수다만 떠는 응답")
    prior = client.generate_prior(_persona(2), _report())
    assert "[폴백]" in prior.reasoning


def test_generate_prior_stub_mode_unchanged():
    client = ExaoneClient()
    if not client.is_stub:
        pytest.skip("로컬 .env 에 키가 있어 스텁 모드 아님")
    prior = client.generate_prior(_persona(2), _report())
    assert "[스텁]" in prior.reasoning
