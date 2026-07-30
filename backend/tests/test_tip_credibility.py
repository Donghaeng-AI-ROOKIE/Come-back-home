"""Phase 3 제보 신뢰도 p — kinematic 개연성 + 가중평균 trust + 챗봇 질문.

docs: "제보 신뢰도 p 계산 방식". 외부 API 안 침 (structured 명시 전달·스텁 함수 직접 호출).
"""

import math
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.geo import reachability
from app.llm import tip_llm
from app.llm.tip_llm import _stub_structure_tip
from app.phase3 import trust
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.tip import Tip

LKP = GeoPoint(lat=37.6061, lng=127.0106)
T0 = datetime(2026, 7, 13, 12, 0, 0)


def _pt_km_north(km: float) -> GeoPoint:
    return GeoPoint(lat=LKP.lat + km / 111.32, lng=LKP.lng)


def _tip(location=None, seen_at=None, created_at=None):
    return Tip(id="t", case_id="c", text="목격", location=location,
               seen_at=seen_at,
               created_at=created_at or (T0 + timedelta(hours=1)))


# ── kinematic 개연성 ────────────────────────────────────────────────
def test_plausibility_within_envelope_is_one():
    # 치매 1h(seen_at) → d_max = 4.32km. 2km 제보는 반경 안 → 1.0
    p = reachability.plausibility(LKP, T0, _pt_km_north(2.0), PersonaType.dementia,
                                  seen_at=T0 + timedelta(hours=1), created_at=T0 + timedelta(hours=1))
    assert p == 1.0


def test_plausibility_beyond_envelope_decays():
    # 1h 에 10km 는 걷기 상한(4.32km) 초과 → 0 < p < 1
    p = reachability.plausibility(LKP, T0, _pt_km_north(10.0), PersonaType.dementia,
                                  seen_at=T0 + timedelta(hours=1), created_at=T0 + timedelta(hours=1))
    assert 0.0 < p < 1.0


# ── P1-6 감쇠계수 k (decay_factor, 2026-07-31 신설 — 셀프리뷰에서 테스트 부재 발견) ──
def test_decay_factor_k1_matches_legacy_formula():
    # k=1.0(기본값)은 옛 exp(-(d-d_max)/d_max) 공식과 수치가 완전히 같아야 함(회귀 방지)
    d, d_max = 8.0, 4.0  # d/d_max = 2.0
    assert reachability.decay_factor(d, d_max, k=1.0) == math.exp(-(d - d_max) / d_max)


def test_decay_factor_larger_k_is_stricter():
    # k 가 클수록 초과거리에 더 가혹(값이 작음), 작을수록 관대(값이 큼) — 단조성 확인
    d, d_max = 8.0, 4.0  # d/d_max = 2.0
    lenient = reachability.decay_factor(d, d_max, k=0.5)
    default = reachability.decay_factor(d, d_max, k=1.0)
    strict = reachability.decay_factor(d, d_max, k=2.0)
    assert lenient > default > strict
    # 설계문서 표(2026-07-30) 수치와 대조 — d/d_max=2.0 일 때 k=0.5→0.6065·k=1.0→0.3679·k=2.0→0.1353
    assert abs(lenient - 0.6065) < 1e-4
    assert abs(default - 0.3679) < 1e-4
    assert abs(strict - 0.1353) < 1e-4


def test_decay_factor_guards_zero_d_max():
    assert reachability.decay_factor(d=5.0, d_max=0.0, k=1.0) == 0.0


def test_plausibility_decay_k_override_changes_result():
    # plausibility() 의 decay_k 파라미터가 실제로 전역 설정과 다른 값으로 override 되는지 확인
    # (P1-6 스윕 실험에서 config 를 안 건드리고 값만 바꿔보는 용도 — 배관이 살아있는지 검증)
    far = _pt_km_north(10.0)  # 1h 상한(4.32km) 확실히 초과
    kwargs = dict(seen_at=T0 + timedelta(hours=1), created_at=T0 + timedelta(hours=1))
    p_strict = reachability.plausibility(LKP, T0, far, PersonaType.dementia, decay_k=3.0, **kwargs)
    p_lenient = reachability.plausibility(LKP, T0, far, PersonaType.dementia, decay_k=0.3, **kwargs)
    assert p_lenient > p_strict


def test_created_at_fallback_when_no_seen_at():
    # seen_at 없음 → created_at(2h) 상한 fallback → d_max 8.64km → 5km 제보 정상
    p = reachability.plausibility(LKP, T0, _pt_km_north(5.0), PersonaType.dementia,
                                  seen_at=None, created_at=T0 + timedelta(hours=2))
    assert p == 1.0


def test_past_sighting_or_zero_dt_low():
    # seen_at ≈ lkp_time → Δt 하한 → d_max 아주 작음 → 먼 제보 개연성 낮음
    p = reachability.plausibility(LKP, T0, _pt_km_north(3.0), PersonaType.dementia,
                                  seen_at=T0, created_at=T0)
    assert p < 0.1


# ── 셀프리뷰 회귀: tz / NaN / 미래 seen_at ──────────────────────────
def test_tz_aware_seen_at_does_not_crash():
    # API 로 +09:00 붙은 tz-aware 시각이 와도 naive lkp_time 과 빼기 크래시 안 남
    aware = datetime(2026, 7, 13, 13, 0, 0, tzinfo=timezone.utc)
    p = reachability.plausibility(LKP, T0, _pt_km_north(2.0), PersonaType.dementia,
                                  seen_at=aware, created_at=T0 + timedelta(hours=2))
    assert 0.0 <= p <= 1.0


def test_nan_location_excluded_not_poisoning_p():
    nan_tip = GeoPoint(lat=float("nan"), lng=127.02)
    plaus = reachability.plausibility(LKP, T0, nan_tip, PersonaType.dementia,
                                      seen_at=T0 + timedelta(hours=1), created_at=T0 + timedelta(hours=1))
    assert math.isnan(plaus)   # 개연성 자체는 NaN 이지만
    tip = _tip(location=nan_tip, seen_at=T0 + timedelta(hours=1))
    p = trust.score_tip(tip, lkp=LKP, lkp_time=T0, persona_type=PersonaType.dementia,
                        structured={"specificity": "중"})
    assert math.isfinite(p)    # trust 는 NaN 개연성 항을 빼고 유한한 p 반환


def test_future_seen_at_capped_at_created_at():
    # seen_at 이 신고 시각보다 미래(오추출) → created_at 으로 캡 → 게이트 무력화 방지
    far = GeoPoint(lat=38.5, lng=128.0)   # 약 110km
    p = reachability.plausibility(LKP, T0, far, PersonaType.dementia,
                                  seen_at=T0 + timedelta(days=1), created_at=T0 + timedelta(hours=1))
    assert p < 0.01   # created_at(1h) 기준이면 110km 는 사실상 불가능


# ── 가중평균 trust ──────────────────────────────────────────────────
def test_score_weighted_average():
    tip = _tip(location=_pt_km_north(2.0), seen_at=T0 + timedelta(hours=1))
    p = trust.score_tip(tip, lkp=LKP, lkp_time=T0, persona_type=PersonaType.dementia,
                        structured={"specificity": "상"})
    # 개연성1·구체성0.9 의 가중평균. 가중치는 config.py 값 그대로 참조(하드코딩하면
    # P1-5 실험으로 r 이 바뀔 때마다 깨짐 — 2026-07-31 r=1.6→2.3 반영 때 실제로 깨졌었음).
    w1, w2 = settings.trust_weight_plausibility, settings.trust_weight_specificity
    expected = (w1 * 1.0 + w2 * 0.9) / (w1 + w2)
    assert abs(p - expected) < 1e-9


def test_missing_location_renormalizes():
    tip = _tip(location=None, seen_at=None)
    p = trust.score_tip(tip, lkp=LKP, lkp_time=T0, persona_type=PersonaType.dementia,
                        structured={"specificity": "상"})
    # 위치 없어 개연성 항 빠짐 → 구체성 단독(재정규화 결과 = 구체성 값 그대로)
    expected = trust.SPECIFICITY_LEVELS["상"]
    assert abs(p - expected) < 1e-9


def test_no_signals_returns_base_p():
    tip = _tip(location=None)   # 위치 없음
    p = trust.score_tip(tip, lkp=LKP, lkp_time=T0, persona_type=PersonaType.dementia,
                        structured={"specificity": None})   # 구체성 등급도 무효
    assert p == settings.trust_base_p


def test_specificity_levels_ordered():
    tip = _tip(location=_pt_km_north(2.0), seen_at=T0 + timedelta(hours=1))
    scores = [
        trust.score_tip(tip, lkp=LKP, lkp_time=T0, persona_type=PersonaType.dementia,
                        structured={"specificity": lv})
        for lv in ("하", "중", "상")
    ]
    assert scores[0] < scores[1] < scores[2]   # 하 < 중 < 상


# ── 제보 챗봇 질문 순서 ─────────────────────────────────────────────
def test_next_question_fixed_order():
    empty = {"location_text": None, "time_text": None, "appearance_cues": [], "direction": None}
    assert tip_llm.next_tip_question(empty) == "어디서 보셨어요? 근처 건물이나 가게 이름을 알려주세요."
    got_loc = {**empty, "location_text": "대흥역 앞"}
    assert "몇 시" in tip_llm.next_tip_question(got_loc)


def test_stub_structure_specificity_grades():
    rich = _stub_structure_tip("대흥역 앞에서 방금 파란 셔츠 입은 사람을 봤어요")
    poor = _stub_structure_tip("아까 비슷한 사람 봤어요")
    assert rich["specificity"] == "상"
    assert poor["specificity"] == "하"
