"""Phase 3 제보 신뢰도 p — kinematic 개연성 + 가중평균 trust + 챗봇 질문.

docs: "제보 신뢰도 p 계산 방식". 외부 API 안 침 (structured 명시 전달·스텁 함수 직접 호출).
"""

from datetime import datetime, timedelta

from app.config import settings
from app.geo import reachability
from app.llm import midm
from app.llm.midm import _stub_structure_tip
from app.phase3 import trust
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.report import Appearance
from app.schemas.tip import Tip

LKP = GeoPoint(lat=37.6061, lng=127.0106)
T0 = datetime(2026, 7, 13, 12, 0, 0)


def _pt_km_north(km: float) -> GeoPoint:
    return GeoPoint(lat=LKP.lat + km / 111.32, lng=LKP.lng)


def _tip(location=None, seen_at=None, has_photo=False, created_at=None):
    return Tip(id="t", case_id="c", text="목격", location=location,
               seen_at=seen_at, has_photo=has_photo,
               created_at=created_at or (T0 + timedelta(hours=1)))


# ── kinematic 개연성 ────────────────────────────────────────────────
def test_plausibility_within_envelope_is_one():
    # 치매 1h(seen_at) → d_max = 4.5km. 2km 제보는 반경 안 → 1.0
    p = reachability.plausibility(LKP, T0, _pt_km_north(2.0), PersonaType.dementia,
                                  seen_at=T0 + timedelta(hours=1), created_at=T0 + timedelta(hours=1))
    assert p == 1.0


def test_plausibility_beyond_envelope_decays():
    # 1h 에 10km 는 걷기 상한(4.5km) 초과 → 0 < p < 1
    p = reachability.plausibility(LKP, T0, _pt_km_north(10.0), PersonaType.dementia,
                                  seen_at=T0 + timedelta(hours=1), created_at=T0 + timedelta(hours=1))
    assert 0.0 < p < 1.0


def test_transit_lifts_far_tip():
    far = _pt_km_north(10.0)
    walk = reachability.plausibility(LKP, T0, far, PersonaType.dementia,
                                     seen_at=T0 + timedelta(hours=1), created_at=T0 + timedelta(hours=1))
    transit = reachability.plausibility(LKP, T0, far, PersonaType.dementia,
                                        seen_at=T0 + timedelta(hours=1), created_at=T0 + timedelta(hours=1),
                                        transit=True)
    assert transit == 1.0 and transit > walk   # 대중교통이면 10km 도 반경 안


def test_created_at_fallback_when_no_seen_at():
    # seen_at 없음 → created_at(2h) 상한 fallback → d_max 9km → 5km 제보 정상
    p = reachability.plausibility(LKP, T0, _pt_km_north(5.0), PersonaType.dementia,
                                  seen_at=None, created_at=T0 + timedelta(hours=2))
    assert p == 1.0


def test_past_sighting_or_zero_dt_low():
    # seen_at ≈ lkp_time → Δt 하한 → d_max 아주 작음 → 먼 제보 개연성 낮음
    p = reachability.plausibility(LKP, T0, _pt_km_north(3.0), PersonaType.dementia,
                                  seen_at=T0, created_at=T0)
    assert p < 0.1


# ── 가중평균 trust ──────────────────────────────────────────────────
def test_score_all_signals_weighted_average():
    tip = _tip(location=_pt_km_north(2.0), seen_at=T0 + timedelta(hours=1), has_photo=True)
    ref = Appearance(summary="파란 점퍼")
    p = trust.score_tip(tip, ref, lkp=LKP, lkp_time=T0, persona_type=PersonaType.dementia,
                        tip_image=b"img", structured={"specificity": "상", "travel_mode": None})
    # 개연성1·사진0.85·구체성0.9 의 가중평균 (0.4/0.35/0.25) ≈ 0.9175
    expected = (0.4 * 1.0 + 0.35 * 0.85 + 0.25 * 0.9) / (0.4 + 0.35 + 0.25)
    assert abs(p - expected) < 1e-9


def test_missing_photo_renormalizes():
    tip = _tip(location=_pt_km_north(2.0), seen_at=T0 + timedelta(hours=1), has_photo=False)
    p = trust.score_tip(tip, None, lkp=LKP, lkp_time=T0, persona_type=PersonaType.dementia,
                        structured={"specificity": "상", "travel_mode": None})
    # 사진 항 빠지고 개연성·구체성만 재정규화 → (0.4·1 + 0.25·0.9)/(0.4+0.25)
    expected = (0.4 * 1.0 + 0.25 * 0.9) / (0.4 + 0.25)
    assert abs(p - expected) < 1e-9


def test_no_signals_returns_base_p():
    tip = _tip(location=None, has_photo=False)   # 위치·사진 없음
    p = trust.score_tip(tip, None, lkp=LKP, lkp_time=T0, persona_type=PersonaType.dementia,
                        structured={"specificity": None})   # 구체성 등급도 무효
    assert p == settings.trust_base_p


def test_specificity_levels_ordered():
    tip = _tip(location=_pt_km_north(2.0), seen_at=T0 + timedelta(hours=1))
    scores = [
        trust.score_tip(tip, None, lkp=LKP, lkp_time=T0, persona_type=PersonaType.dementia,
                        structured={"specificity": lv, "travel_mode": None})
        for lv in ("하", "중", "상")
    ]
    assert scores[0] < scores[1] < scores[2]   # 하 < 중 < 상


# ── 제보 챗봇 질문 순서 ─────────────────────────────────────────────
def test_next_question_fixed_order():
    empty = {"location_text": None, "time_text": None, "appearance_cues": [], "direction": None}
    assert midm.next_tip_question(empty) == "어디서 보셨어요? 근처 건물이나 가게 이름을 알려주세요."
    got_loc = {**empty, "location_text": "대흥역 앞"}
    assert "몇 시" in midm.next_tip_question(got_loc)


def test_travel_mode_only_when_flagged_and_over_ceiling():
    full = {"location_text": "역앞", "time_text": "방금", "appearance_cues": ["셔츠"], "direction": "북쪽"}
    assert midm.next_tip_question(full, ask_travel_mode=False) is None       # 걷기 범위 내 → 안 물음
    assert "버스" in midm.next_tip_question(full, ask_travel_mode=True)       # 상한 초과 → 이동수단 질문


def test_stub_structure_specificity_grades():
    rich = _stub_structure_tip("대흥역 앞에서 방금 파란 셔츠 입은 사람을 봤어요")
    poor = _stub_structure_tip("아까 비슷한 사람 봤어요")
    assert rich["specificity"] == "상"
    assert poor["specificity"] == "하"
    assert _stub_structure_tip("버스 타는 걸 봤어요")["travel_mode"] == "transit"
