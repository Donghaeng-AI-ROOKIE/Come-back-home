"""게이지 계수 개인화 스키마 (PR #21 과제1) — 허용/금지 목록 강제.

인터뷰가 모은 개인 특성이 알고리즘 층에서 유형 기본값으로만 소비되던 문제.
축 채점(quote 검증 + 3회 다수결)을 거친 axis_scores 만 입력으로 받고, 배수
변환·클램프는 코드가 한다 — LLM 이 계수 숫자를 직접 정하지 않는다.
"""

import dataclasses

import pytest

from app.phase2 import gauges
from app.schemas.common import GeoPoint
from app.schemas.persona import Persona, PersonaType

HOME = GeoPoint(lat=37.6061, lng=127.0106)


def _persona(ptype=PersonaType.dementia, **axis) -> Persona:
    return Persona(id="t", type=ptype, name="테스트", age=78, home=HOME,
                   axis_scores=axis)


# ── 허용 목록이 실제로 작동하는가 ────────────────────────────────────
def test_wayfinding_axis_scales_confusion_accumulation():
    """길찾기 복구 취약성 ↑ → 낯섦이 혼란으로 전환되는 속도(k_c1) ↑."""
    base = gauges.config_for(_persona()).k_c1
    weak = gauges.config_for(_persona(wayfinding_error_recovery_deficit=0.9)).k_c1
    strong = gauges.config_for(_persona(wayfinding_error_recovery_deficit=0.1)).k_c1
    assert strong < base < weak
    assert weak == pytest.approx(base * 1.4)
    assert strong == pytest.approx(base * 0.6)


def test_distress_axis_scales_anxiety_derivation():
    base = gauges.config_for(_persona()).k_a1
    high = gauges.config_for(_persona(distress_induced_movement_reactivity=0.9)).k_a1
    assert high == pytest.approx(base * 1.4)


def test_removed_axes_do_not_personalize_anything():
    """삭제된 발달장애 축(2026-08-03)은 어떤 계수도 움직이지 않는다."""
    plain = gauges.config_for(_persona())
    for dead_axis in ("aversive_context_escape", "transition_routine_disruption",
                      "preferred_target_seeking", "elopement_pattern_consistency"):
        loaded = gauges.config_for(_persona(**{dead_axis: 0.9}))
        assert loaded == plain, dead_axis


def test_unmapped_axis_does_not_leak_into_other_coefficients():
    """허용 목록에 없는 축은 다른 계수로 새지 않는다 — 매핑은 1:1 만."""
    plain = gauges.config_for(_persona())
    loaded = gauges.config_for(_persona(hazard_awareness_vulnerability=0.9))
    assert loaded == plain


def test_out_of_range_scores_are_clamped():
    """축 채점이 범위를 벗어난 값을 줘도 배수는 명세 안에 갇힌다."""
    base = gauges.GaugeConfig().k_c1
    assert gauges.config_for(
        _persona(wayfinding_error_recovery_deficit=9.9)).k_c1 == pytest.approx(base * 1.4)
    assert gauges.config_for(
        _persona(wayfinding_error_recovery_deficit=-5.0)).k_c1 == pytest.approx(base * 0.6)


# ── 금지 목록이 실제로 지켜지는가 ────────────────────────────────────
def test_denied_fields_never_change():
    """금지 계수는 어떤 축 조합에도 흔들리지 않는다 (전수 비교)."""
    every_axis = {
        "wayfinding_error_recovery_deficit": 0.9,
        "distress_induced_movement_reactivity": 0.9,
        "hazard_awareness_vulnerability": 0.9,
        "communication_approach_vulnerability": 0.9,
        "mobility_transport_capacity": 0.9,
    }
    ptype = PersonaType.dementia
    plain = gauges.config_for(_persona(ptype))
    loaded = gauges.config_for(_persona(ptype, **every_axis))
    for field in gauges.DENIED_OVERRIDES:
        assert getattr(loaded, field) == pytest.approx(getattr(plain, field)), \
            f"{ptype.value}: 금지 계수 {field} 가 개인화로 변경됨"


def test_allow_and_deny_lists_cover_every_gauge_field():
    """GaugeConfig 의 모든 필드가 허용·금지 중 하나로 분류돼 있다.

    새 계수를 추가하면 이 테스트가 깨져서 '개인화 허용 여부'를 강제로 결정하게
    한다 — 분류 누락으로 조용히 개인화 밖에 남는 것을 막는다.
    """
    allowed = {s.field for s in gauges._GAUGE_OVERRIDES}
    classified = allowed | set(gauges.DENIED_OVERRIDES)
    actual = {f.name for f in dataclasses.fields(gauges.GaugeConfig)}
    assert actual == classified, f"미분류 계수: {actual - classified}"
    assert not (allowed & set(gauges.DENIED_OVERRIDES)), "허용·금지 양쪽에 있는 계수"


def test_every_override_has_a_reason():
    """허용·금지 모두 근거 문구가 비어있지 않다 (심사·리뷰 방어)."""
    assert all(len(s.why) > 20 for s in gauges._GAUGE_OVERRIDES)
    assert all(len(r) > 10 for r in gauges.DENIED_OVERRIDES.values())


# ── 폴백 ────────────────────────────────────────────────────────────
def test_no_axis_scores_is_a_noop():
    """축 채점이 꺼진 기본 구성에서 동작이 안 바뀐다."""
    assert gauges.config_for(_persona()) == gauges.config_for(
        Persona(id="t", type=PersonaType.dementia, name="x", age=78, home=HOME))
    assert gauges.config_for(None) == gauges.GaugeConfig()
