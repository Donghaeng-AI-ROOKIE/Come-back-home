"""축점수(phase0.axis_scoring) → Phase2 PriorParams 결정론적 반영 검증 (작업 2-A)."""

from datetime import datetime

import pytest

from app.llm.exaone import ExaoneClient, _KOESTER_PARAMS
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


def _prior(**overrides) -> PriorParams:
    base = dict(
        strategy_probs=dict(DEFAULT_STRATEGY),
        attraction_weights={"장소0": 0.55, "장소1": 0.45},  # cap(0.6) 아래에서 시작 — 쏠림 효과가 클램프에 가려지지 않게
        radius_lognormal=LognormalParams(mu=0.095, sigma=1.48),
        reasoning="",
    )
    base.update(overrides)
    return PriorParams(**base)


def _persona(ptype=PersonaType.dementia, n=2, axis_scores=None) -> Persona:
    points = [AttractionPoint(label=f"장소{i}", location=HOME, weight=1.0) for i in range(n)]
    return Persona(id="t", type=ptype, name="테스트", age=78, home=HOME,
                   attraction_points=points, axis_scores=axis_scores or {})


# ── 반경 override (mobility_transport_capacity) ─────────────────────
def test_mobility_high_score_shifts_radius_up():
    base = LognormalParams(mu=0.095, sigma=1.48)
    prior = guardrail.apply_axis_scores(
        _prior(), {"mobility_transport_capacity": 0.9}, _persona(), base)
    assert prior.radius_lognormal.mu == pytest.approx(base.mu + 0.4)


def test_mobility_low_score_shifts_radius_down():
    base = LognormalParams(mu=0.095, sigma=1.48)
    prior = guardrail.apply_axis_scores(
        _prior(), {"mobility_transport_capacity": 0.1}, _persona(), base)
    assert prior.radius_lognormal.mu == pytest.approx(base.mu - 0.4)


def test_mobility_mid_score_keeps_radius():
    base = LognormalParams(mu=0.095, sigma=1.48)
    prior = guardrail.apply_axis_scores(
        _prior(), {"mobility_transport_capacity": 0.5}, _persona(), base)
    assert prior.radius_lognormal.mu == pytest.approx(base.mu)


def test_no_axis_scores_is_identity():
    base = LognormalParams(mu=0.095, sigma=1.48)
    prior = _prior()
    out = guardrail.apply_axis_scores(prior, {}, _persona(), base)
    assert out is prior  # updates 없으면 원본 객체 그대로 반환(불필요한 복사 없음)


def test_unrelated_axis_only_is_identity():
    base = LognormalParams(mu=0.095, sigma=1.48)
    prior = _prior()
    out = guardrail.apply_axis_scores(
        prior, {"hazard_awareness_vulnerability": 0.9}, _persona(), base)
    assert out is prior  # 2-B 전용 축은 PriorParams 에 영향 없음


def test_mobility_overrides_llm_radius_no_double_counting():
    """LLM 이 이미 '상'(base+0.4)으로 조정한 prior가 들어와도, mobility=0.1(저이동성)이면
    axis 기준(base-0.4)으로 덮어써진다 — 두 신호가 각각 반경을 조정하는 이중계산 방지."""
    base = LognormalParams(mu=0.095, sigma=1.48)
    llm_adjusted = _prior(radius_lognormal=LognormalParams(mu=base.mu + 0.4, sigma=base.sigma))
    prior = guardrail.apply_axis_scores(
        llm_adjusted, {"mobility_transport_capacity": 0.1}, _persona(), base)
    assert prior.radius_lognormal.mu == pytest.approx(base.mu - 0.4)


# ── 전략확률 틸트 (elopement_pattern_consistency, 발달장애 전용) ──────
def test_elopement_pattern_sharpens_strategy_for_id_persona():
    base = LognormalParams(mu=0.89, sigma=1.50)
    persona = _persona(PersonaType.intellectual_disability)
    prior = guardrail.apply_axis_scores(
        _prior(), {"elopement_pattern_consistency": 0.9}, persona, base)
    top = max(DEFAULT_STRATEGY, key=DEFAULT_STRATEGY.get)  # route_following (0.30, 최댓값)
    assert prior.strategy_probs[top] > DEFAULT_STRATEGY[top]
    assert abs(sum(prior.strategy_probs.values()) - 1.0) < 1e-9
    assert all(v > 0 for v in prior.strategy_probs.values())  # ε-floor 유지(0 확률 금지 원칙)


def test_elopement_pattern_ignored_for_dementia_persona():
    base = LognormalParams(mu=0.095, sigma=1.48)
    persona = _persona(PersonaType.dementia)
    prior = guardrail.apply_axis_scores(
        _prior(), {"elopement_pattern_consistency": 0.9}, persona, base)
    assert prior.strategy_probs == DEFAULT_STRATEGY  # 치매엔 해당 없는 축(행동축 전용 매핑)


# ── 끌림점가중치 틸트 ────────────────────────────────────────────────
def test_autobiographical_pull_sharpens_attraction_for_dementia():
    base = LognormalParams(mu=0.095, sigma=1.48)
    persona = _persona(PersonaType.dementia)
    prior = guardrail.apply_axis_scores(
        _prior(), {"autobiographical_destination_pull": 0.9}, persona, base)
    assert prior.attraction_weights["장소0"] > 0.55     # 이미 우세한 쪽으로 더 쏠림
    assert prior.attraction_weights["장소0"] <= guardrail.ATTRACTION_CAP + 1e-9  # 상한 유지
    assert abs(sum(prior.attraction_weights.values()) - 1.0) < 1e-9


def test_preferred_target_seeking_sharpens_attraction_for_id():
    base = LognormalParams(mu=0.89, sigma=1.50)
    persona = _persona(PersonaType.intellectual_disability)
    prior = guardrail.apply_axis_scores(
        _prior(), {"preferred_target_seeking": 0.9}, persona, base)
    assert prior.attraction_weights["장소0"] > 0.55


def test_autobiographical_pull_ignored_for_id_persona():
    base = LognormalParams(mu=0.89, sigma=1.50)
    persona = _persona(PersonaType.intellectual_disability)
    prior = guardrail.apply_axis_scores(
        _prior(), {"autobiographical_destination_pull": 0.9}, persona, base)
    assert prior.attraction_weights == {"장소0": 0.55, "장소1": 0.45}  # 유형 불일치라 무변화


def test_empty_attraction_weights_skipped_no_crash():
    base = LognormalParams(mu=0.095, sigma=1.48)
    persona = _persona(PersonaType.dementia, n=0)
    prior = guardrail.apply_axis_scores(
        _prior(attraction_weights={}), {"autobiographical_destination_pull": 0.9}, persona, base)
    assert prior.attraction_weights == {}  # division by zero 없이 그대로 스킵


def test_persona_none_only_radius_applies():
    base = LognormalParams(mu=0.095, sigma=1.48)
    prior = guardrail.apply_axis_scores(
        _prior(), {"mobility_transport_capacity": 0.9, "autobiographical_destination_pull": 0.9},
        None, base)
    assert prior.radius_lognormal.mu == pytest.approx(base.mu + 0.4)
    assert prior.attraction_weights == {"장소0": 0.55, "장소1": 0.45}  # persona 없어 무변화


# ── generate_prior 통합 — 스텁 모드에서도 축점수가 적용되는지 ─────────
def test_generate_prior_stub_applies_axis_scores():
    """가드레일 안에만 넣으면 스텁 모드(로컬 개발 기본값)에서 효과가 안 보이는
    문제의 회귀 테스트 — generate_prior 끝에서 항상 실행돼야 한다."""
    client = ExaoneClient()
    if not client.is_stub:
        pytest.skip("로컬 .env 에 키가 있어 스텁 모드 아님")
    persona = _persona(PersonaType.dementia, axis_scores={"mobility_transport_capacity": 0.9})
    report = MissingReport(id="r", missing_type=PersonaType.dementia,
                           lkp=HOME, lkp_time=datetime(2026, 7, 20, 18, 0))
    prior = client.generate_prior(persona, report)
    base_mu = _KOESTER_PARAMS[PersonaType.dementia].mu
    assert prior.radius_lognormal.mu == pytest.approx(base_mu + 0.4)


def test_generate_prior_no_persona_skips_axis_scores():
    client = ExaoneClient()
    if not client.is_stub:
        pytest.skip("로컬 .env 에 키가 있어 스텁 모드 아님")
    report = MissingReport(id="r", missing_type=PersonaType.dementia,
                           lkp=HOME, lkp_time=datetime(2026, 7, 20, 18, 0))
    prior = client.generate_prior(None, report)
    base_mu = _KOESTER_PARAMS[PersonaType.dementia].mu
    assert prior.radius_lognormal.mu == pytest.approx(base_mu)
