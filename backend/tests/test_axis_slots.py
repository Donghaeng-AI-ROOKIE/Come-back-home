"""Phase 0 축 기반 슬롯 카탈로그 — 회의록(2026-07 페르소나 축 고도화) 반영 검증.

검증 항목:
  1) 카탈로그 무결성 — 16개, 키 유일, 필수 필드, 유형별 세트(치매 12 / 발달 12 / 아동=공통 8)
  2) 회의록 「실제 질문 형식」 원문이 씨앗 질문에 그대로 들어갔는지 (팀 결정 사항)
  3) 하위변수 → probes 이관 (꼬리질문 각도로 내려간 회의록 하위변수)
  4) 검색 피벗 — 보호자 발화가 해당 축 슬롯을 꼬리질문으로 끌어오는지 (해시 임베더)
  5) answer_example 은 꼬리질문 모드 프롬프트에만 포함 (첫 질문 낭독 금지 정책)
  6) finalize — 슬롯별 노트가 축 DB 필드명(axis_evidence)으로 묶이는지
  7) 가드레일 폴백 — 차단 시 회의록 원문(씨앗 질문)으로 폴백
"""

from app.geo.geocode import GazetteerGeocoder
from app.phase0 import interview, prompts, retrieval, safety
from app.phase0.slots import SLOTS, Axis, slot_by_key, slots_for
from app.schemas.persona import InterviewSession, PersonaType

EMB = retrieval.HashingEmbedder()   # 결정적 스텁 — 어휘 중첩 기반


# ── 1) 카탈로그 무결성 ───────────────────────────────────────────────

def test_catalog_size_and_unique_keys():
    assert len(SLOTS) == 16
    keys = [s.key for s in SLOTS]
    assert len(keys) == len(set(keys))


def test_every_slot_has_required_surfaces():
    for s in SLOTS:
        assert s.question and s.filled_when and s.why, s.key
        assert s.probes, f"{s.key}: probes(꼬리질문 각도) 비어 있음"


def test_axis_slots_have_axis_field():
    """축 슬롯은 컴파일 대상 DB 필드명을 가져야 한다 (예외: medication=축 밖 보조)."""
    for s in SLOTS:
        if s.axis in (Axis.mind, Axis.behavior):
            assert s.axis_field, f"{s.key}: axis_field 누락"
    assert slot_by_key("mobility_transport_capacity").axis_field == "mobility_transport_capacity"
    assert slot_by_key("medication").axis_field == ""   # 회의록 축 밖 — 의도된 공백


def test_type_specific_sets():
    dem = {s.key for s in slots_for(PersonaType.dementia)}
    dd = {s.key for s in slots_for(PersonaType.intellectual_disability)}
    child = {s.key for s in slots_for(PersonaType.child)}

    common = {
        "identity", "home", "routine_destinations", "mobility_transport_capacity",
        "hazard_awareness_vulnerability", "communication_approach_vulnerability",
        "medication", "lost_behavior",
    }
    assert child == common                      # 아동 특화 세트 제외 — 공통만
    assert dem == common | {
        "autobiographical_destination_pull", "dementia_wandering_pattern",
        "wayfinding_error_recovery_deficit", "distress_induced_movement_reactivity",
    }
    assert dd == common | {
        "preferred_target_seeking", "elopement_pattern_consistency",
        "aversive_context_escape", "transition_routine_disruption",
    }


def test_risk_boost_placement():
    assert slot_by_key("preferred_target_seeking").risk == 0.15   # 물가 접근 (구 sensory_attraction 이관)
    assert slot_by_key("lost_behavior").risk == 0.10
    assert slot_by_key("hazard_awareness_vulnerability").risk == 0.10


# ── 2) 회의록 「실제 질문 형식」 원문 유지 ───────────────────────────

_MEETING_QUESTIONS = {
    "mobility_transport_capacity":
        "대상자는 평소 보호자의 도움 없이 얼마나 오래 또는 멀리 걸을 수 있나요? "
        "버스나 지하철 같은 교통수단을 혼자 이용할 수 있는지도 함께 알려주세요.",
    "hazard_awareness_vulnerability":
        "대상자는 차도, 횡단보도, 물가, 계단처럼 위험한 장소를 스스로 알아보고 피할 수 있나요?",
    "communication_approach_vulnerability":
        "대상자는 이름을 부르거나 간단한 질문을 했을 때 어떻게 반응하나요? "
        "자신의 이름, 주소 또는 보호자 연락처를 말할 수 있는지도 알려주세요.",
    "wayfinding_error_recovery_deficit":
        "대상자는 익숙한 동네에서도 길을 잘못 들거나 목적지를 잊는 경우가 있나요? "
        "길을 잘못 들었을 때 스스로 알아차리고 돌아올 수 있는지도 알려주세요.",
    "autobiographical_destination_pull":
        "대상자가 반복해서 찾거나 가려고 하는 과거의 장소가 있나요? "
        "옛집, 예전 직장, 시장, 병원, 약국, 종교시설처럼 구체적인 장소를 알려주세요.",
    "distress_induced_movement_reactivity":
        "대상자가 불안하거나 초조해지거나, 누군가 자신을 해친다고 의심할 때 "
        "이동 행동이 어떻게 달라지나요?",
    "dementia_wandering_pattern":
        "과거에 길을 잃거나 실종된 적이 있다면, 어디에서 발견됐고 "
        "어떤 행동을 하고 있었는지 알려주세요.",
    "preferred_target_seeking":
        "대상자가 보호자와 떨어져서라도 찾아가려고 할 만큼 강하게 좋아하는 "
        "장소, 사람, 물건, 교통수단 또는 활동이 있나요?",
    "aversive_context_escape":
        "대상자가 큰 소리, 밝은 빛, 많은 사람, 낯선 접촉, 요구받는 상황 또는 "
        "혼나는 상황을 피하려고 자리를 벗어나나요? 그럴 때 주로 어디로 이동하는지도 알려주세요.",
    "transition_routine_disruption":
        "예정된 일정이나 이동 경로가 바뀌거나, 활동이 끝나거나, 보호자와 갑자기 "
        "분리될 때 어떤 행동을 보이나요?",
    "elopement_pattern_consistency":
        "과거 이탈이나 실종에서 같은 장소, 경로, 교통수단 또는 행동이 반복됐나요?",
}


def test_meeting_questions_verbatim():
    for key, expected in _MEETING_QUESTIONS.items():
        assert slot_by_key(key).question == expected, f"{key}: 회의록 원문과 다름"


# ── 3) 하위변수 → probes 이관 ────────────────────────────────────────

def test_subvariables_moved_to_probes():
    mob = " ".join(slot_by_key("mobility_transport_capacity").probes)
    for sub in ("walking_endurance", "walking_speed", "outdoor_independence",
                "transit_use", "vehicle_use", "physical_limitations"):
        assert sub in mob, f"mobility probes 에 {sub} 없음"

    way = " ".join(slot_by_key("wayfinding_error_recovery_deficit").probes)
    for sub in ("destination_retention", "landmark_recognition", "intersection_decision",
                "route_error_awareness", "route_recovery_ability"):
        assert sub in way, f"wayfinding probes 에 {sub} 없음"


def test_absorbed_legacy_slots_survive_as_probes_or_keywords():
    """흡수된 기존 슬롯의 핵심 각도가 새 슬롯 probes/keywords 에 남아 있는지."""
    autobio = slot_by_key("autobiographical_destination_pull")
    surface = autobio.embed_text
    assert "고향" in surface           # 구 recurring_place/repeated_phrases 키워드
    assert "남의 집" in surface        # 구 home_recognition
    assert "젊은 시절" in surface      # 구 time_perception

    pref = slot_by_key("preferred_target_seeking")
    assert "수영장" in pref.embed_text  # 구 sensory_attraction 물가 키워드
    comm = slot_by_key("communication_approach_vulnerability")
    assert "경찰" in comm.embed_text    # 구 uniform_response
    assert "따라가" in comm.embed_text  # 구 follows_strangers


# ── 4) 검색 피벗 — 발화가 축 슬롯을 꼬리질문으로 끌어오는가 ─────────
# 주의: PIVOT_SIM(0.32)은 실제 한국어 임베더 기준 캘리브레이션. 해시 스텁은
# 어휘 중첩만 잡아 절대값이 낮으므로(≈0.2), 여기서는 **상대 랭킹**을 검증한다:
# 의도 슬롯이 유사도 상위 2위 안 + 시뮬레이터 기준선(0.20) 이상 + 템플릿
# 기본값(routine_destinations)보다 위. 절대 임계 통과는 실임베더 E2E 몫.

_STUB_FOLLOWUP_SIM = 0.20   # scripts/sim_elicitation.py 와 동일한 스텁 기준선


def _sims_by_key(ptype: PersonaType, turns: list[str], filled: set[str]) -> dict[str, float]:
    ranked, _ = retrieval.rank_next_slots(ptype, turns, filled, EMB, top_k=16)
    return {r.slot.key: r.similarity for r in ranked}


def _assert_pivots_to(key: str, ptype: PersonaType, turns: list[str]) -> None:
    sims = _sims_by_key(ptype, turns, {"identity", "home"})
    top2 = sorted(sims, key=sims.get, reverse=True)[:2]
    assert key in top2, f"{key} 가 유사도 상위 2위 밖: {sims}"
    assert sims[key] >= _STUB_FOLLOWUP_SIM
    assert sims[key] > sims["routine_destinations"]   # 템플릿 기본 슬롯보다 강한 신호


def test_pivot_to_preferred_target_on_subway_mention():
    _assert_pivots_to(
        "preferred_target_seeking", PersonaType.intellectual_disability,
        ["아들 19살 자폐예요", "화곡동 살아요", "지하철만 보이면 혼자라도 타러 뛰어가요"],
    )


def test_pivot_to_autobiographical_on_old_home_mention():
    _assert_pivots_to(
        "autobiographical_destination_pull", PersonaType.dementia,
        ["어머니 78세 치매요", "정릉동 살아요", "자꾸 옛날 집에 가야 한다고 나가려 하세요"],
    )


def test_pivot_to_aversive_escape_on_noise_hiding():
    _assert_pivots_to(
        "aversive_context_escape", PersonaType.intellectual_disability,
        ["사이렌 큰 소리 나면 귀 막고 화장실로 숨어버려요"],
    )


def test_type_filter_blocks_other_persona_slots():
    """치매 발화가 발달장애 전용 슬롯으로 새지 않는다 (유형 필터)."""
    ranked, _ = retrieval.rank_next_slots(
        PersonaType.dementia, ["자꾸 옛날 집 얘기를 하세요"], set(), EMB, top_k=16
    )
    keys = {r.slot.key for r in ranked}
    assert "preferred_target_seeking" not in keys
    assert "transition_routine_disruption" not in keys


# ── 5) answer_example — 꼬리질문 모드 전용 ──────────────────────────

def test_answer_example_only_in_followup_prompt():
    slot = slot_by_key("mobility_transport_capacity")
    conv = [{"role": "user", "text": "혼자 잘 걸으세요"}]
    fresh = prompts.build_phrase_input(PersonaType.dementia, slot, False, conv)
    follow = prompts.build_phrase_input(PersonaType.dementia, slot, True, conv)
    assert "답변 눈높이 예시" not in fresh          # 첫 질문: 예시 낭독 금지
    assert "쉬지 않고 약 30분" in follow            # 꼬리질문: 구체성 눈높이 제공
    assert "그대로 낭독 금지" in follow


def test_answer_example_excluded_from_embed_text():
    """예시 속 고유명사가 검색 코퍼스를 오염시키지 않는다."""
    slot = slot_by_key("elopement_pattern_consistency")
    assert "지하철역 방향으로 이동했고" not in slot.embed_text


# ── 6) finalize — 축별 근거(axis_evidence) 조립 ─────────────────────

def test_finalize_groups_notes_by_axis_field():
    s = InterviewSession(
        id="axis1", guardian_name="보호자", persona_type=PersonaType.dementia,
        draft_fields={"name": "김순자", "age": "78세", "home": "성북구 정릉동"},
        draft_behaviors=["쉬지 않고 30분 걸음", "길 잃으면 계속 걸음", "면목동 방앗간 얘기 반복"],
        slot_notes={
            "mobility_transport_capacity": ["쉬지 않고 30분 걸음"],
            "lost_behavior": ["길 잃으면 계속 걸음"],
            "autobiographical_destination_pull": ["면목동 방앗간 얘기 반복"],
            "medication": ["혈압약 복용"],          # axis_field 없음 → 축 근거에서 제외
        },
        awaiting_confirmation=True,
    )
    p = interview.finalize_persona(s, geocoder=GazetteerGeocoder())
    assert p.axis_evidence["mobility_transport_capacity"] == ["쉬지 않고 30분 걸음"]
    assert p.axis_evidence["lost_behavior"] == ["길 잃으면 계속 걸음"]
    assert p.axis_evidence["autobiographical_destination_pull"] == ["면목동 방앗간 얘기 반복"]
    assert "medication" not in p.axis_evidence
    # behavior_notes 는 기존 그대로 (Phase 2 소비자 호환)
    assert "길 잃으면 계속 걸음" in p.behavior_notes


def test_apply_extraction_records_slot_notes():
    s = InterviewSession(id="axis2", guardian_name="보호자",
                         persona_type=PersonaType.intellectual_disability)
    slot = slot_by_key("aversive_context_escape")
    interview._apply_extraction(s, slot, {
        "fields": {}, "attraction_points": [],
        "behavior_notes": ["시끄러우면 화장실로 숨음"], "slot_filled": True,
    })
    assert s.slot_notes["aversive_context_escape"] == ["시끄러우면 화장실로 숨음"]
    assert "aversive_context_escape" in s.filled_keys


# ── 7) 가드레일 — 차단 시 회의록 원문 폴백 ──────────────────────────

def test_guard_falls_back_to_meeting_question():
    slot = slot_by_key("distress_induced_movement_reactivity")
    bad = "복용량을 늘리셔야 할 것 같은데 진단을 받아보셨나요?"   # 층① 블록리스트(의료 조언)
    out, fell_back = safety.guard_question(bad, slot, EMB)
    assert fell_back
    assert out == slot.question   # 폴백 = 회의록 원문


def test_autism_routes_to_developmental_disability():
    """'자폐' 발화는 아동이 아니라 발달장애 세트로 라우팅 (축 고도화 결정)."""
    assert interview._detect_type("아들이 자폐 스펙트럼이에요") == PersonaType.intellectual_disability
    assert interview._detect_type("일곱 살 아이예요") == PersonaType.child
