"""챗봇 고도화(2026-07-17) 회귀 — 데드엔드·장애 플래그·규칙 폴백·재질문 UX.

어제(07-16) 라이브 실측(엔드포인트 410)에서 확인된 4가지 실패 모드의 회귀 방지:
  ② finalize 실패(집 위치 미확보) 후 done=True 데드엔드 — 세션이 죽어 복구 불가
  ② Mi:dm 호출 실패가 침묵 — "이상한 반복 인터뷰"로만 체감
  ③ name/age/home 추출이 Mi:dm 단일 장애점 — 엔드포인트 다운이면 등록 퍼널 전체 실패
  ④ 재질문이 직전 질문을 토씨까지 재낭독(Q5=Q6) + 폴백 씨앗 질문의 복합 문형
"""

from app import storage
from app.geo.geocode import GazetteerGeocoder
from app.phase0 import interview, retrieval, safety
from app.phase0.slots import slot_by_key, slots_for
from app.schemas.persona import InterviewSession, PersonaType

EMB = retrieval.HashingEmbedder()


# ── ② finalize 데드엔드 → 복구 루프 ──────────────────────────────────

def _confirmed_session(home: str, sid: str = "hard1") -> InterviewSession:
    """모든 슬롯이 끝나 요약 확인 게이트에 도달한 세션."""
    s = InterviewSession(
        id=sid, guardian_name="보호자", persona_type=PersonaType.dementia,
        draft_fields={"name": "김순자", "age": "78세", "home": home},
        filled_keys=[sp.key for sp in slots_for(PersonaType.dementia)],
        awaiting_confirmation=True,
        asked_more_places=True,   # 요약까지 간 세션은 추가 장소 스윕을 이미 지났다
    )
    storage.interviews.save(s.id, s)
    return s


def test_finalize_failure_keeps_session_alive_and_recovers(monkeypatch):
    """지오코딩 실패 → 세션은 살아있고 → 집 재답변으로 등록까지 완주.

    구버전: done=True 로 닫혀 "다시 확인해 달라"는 안내와 달리 이후 입력이
    전부 무시되는 막다른 길이었다.
    """
    monkeypatch.setattr(interview, "_GEO", GazetteerGeocoder())
    s = _confirmed_session(home="지도에없는곳")

    out = interview.answer_interview(s.id, "네 맞아요")
    assert not out.done                        # 구버전: True (데드엔드)
    assert not out.awaiting_confirmation
    assert "home" not in out.draft_fields      # 실패 값 제거 — first-wins 가 새 답을 막지 않게
    assert "home" not in out.filled_keys
    assert out.prev_target_key == "home"       # 다음 답변은 home 으로 추출

    # 집 재답변 (스텁 추출은 빈손 — 규칙 폴백이 채운다) → 요약 확인 재진입
    out = interview.answer_interview(s.id, "성북구 정릉동이에요")
    assert out.draft_fields.get("home") == "성북구 정릉동"
    assert out.awaiting_confirmation

    out = interview.answer_interview(s.id, "네")
    assert out.done and out.persona_id         # 등록 완주


# ── ② LLM 장애 세션 플래그 ──────────────────────────────────────────

def test_llm_failure_sets_degraded_flag(monkeypatch):
    """Mi:dm 호출이 실패하면 폴백으로 진행하되 세션에 장애가 노출된다."""
    from app.llm.midm import MidmClient

    monkeypatch.setattr(MidmClient, "is_stub", property(lambda self: False))

    def _boom(*a, **k):
        raise RuntimeError("HTTP 410 Gone")

    monkeypatch.setattr(interview.midm, "chat", _boom)

    s = interview.start_interview("보호자", PersonaType.dementia)
    out = interview.answer_interview(s.id, "김순자님이고 78세, 치매가 있으세요")

    assert out.llm_degraded
    assert out.llm_call_failures >= 1
    # 장애 중에도 규칙 폴백으로 필수 필드는 확보 (③과 결합)
    assert out.draft_fields.get("name") == "김순자"
    assert out.draft_fields.get("age") == "78세"


def test_stub_mode_is_not_degraded():
    """스텁 모드(키 없음)는 정상 폴백 — 장애 플래그를 올리면 안 된다."""
    s = interview.start_interview("보호자", PersonaType.dementia)
    out = interview.answer_interview(s.id, "김순자님이고 78세, 치매가 있으세요")
    assert not out.llm_degraded and out.llm_call_failures == 0


# ── ③ 규칙 기반 최소 추출 (identity/home) ────────────────────────────

def test_rule_extract_identity():
    f = interview._rule_extract_fields("identity", "저희 어머니 김순자님이고 78세예요")
    assert f == {"name": "김순자", "age": "78세"}
    f = interview._rule_extract_fields("identity", "이름은 박말녀, 여든이 넘으셨어요")
    assert f.get("name") == "박말녀"          # 나이는 숫자 표현이 없으면 못 뽑는다(보수적)
    f = interview._rule_extract_fields("identity", "할머니세요, 82살이요")
    assert f.get("name") is None and f.get("age") == "82세"   # 호칭을 이름으로 오인 금지


def test_rule_extract_home():
    f = interview._rule_extract_fields("home", "서울 성북구 정릉동이에요")
    assert f["home"].endswith("정릉동")
    f = interview._rule_extract_fields("home", "면목로 12에 살아요")
    assert f["home"] == "면목로 12"
    assert interview._rule_extract_fields("home", "잘 모르겠어요") == {}


def test_stub_interview_captures_required_fields_end_to_end():
    """엔드포인트 없이(스텁)도 name/age/home 이 실제로 쌓인다 — 등록 퍼널 방어선."""
    s = interview.start_interview("보호자", PersonaType.dementia)
    out = interview.answer_interview(s.id, "김순자님이고 78세, 치매 어르신이에요")
    out = interview.answer_interview(s.id, "성북구 정릉동 살아요")
    assert out.draft_fields.get("name") == "김순자"
    assert out.draft_fields.get("age") == "78세"
    assert out.draft_fields.get("home") == "성북구 정릉동"
    assert "home" in out.filled_keys


# ── ④ 재질문 UX — 토씨까지 같은 재낭독 금지 + 단일 질문 폴백 ─────────

def test_reask_never_repeats_verbatim(monkeypatch):
    """같은 슬롯을 연속으로 물어도 직전 질문과 문장이 달라야 한다(Q5=Q6 방지)."""
    slot = slot_by_key("routine_destinations")

    class _Hit:
        similarity = 0.9
    _Hit.slot = slot

    monkeypatch.setattr(interview.retrieval, "rank_next_slots",
                        lambda *a, **k: ([_Hit()], []))
    # 뭐라도 건졌지만 미충족 — 같은 슬롯 꼬리질문(재선택 허용) 경로
    monkeypatch.setattr(interview.midm, "extract_answer",
                        lambda slot, conv: {"fields": {}, "attraction_points": [],
                                            "behavior_notes": ["시장 근처를 좋아함"],
                                            "slot_filled": False})
    s = interview.start_interview("보호자", PersonaType.dementia)
    s.draft_fields["home"] = "정릉동"
    s.filled_keys.append("home")            # 2.5 home 게이트 우회
    storage.interviews.save(s.id, s)

    out = interview.answer_interview(s.id, "김순자 78세 치매예요")
    q1 = out.messages[-1]["text"]
    out = interview.answer_interview(s.id, "시장에 자주 가요")
    q2 = out.messages[-1]["text"]
    assert q1 != q2                          # 구버전: 토씨까지 동일
    assert q2.endswith(q1)                   # 변형 = 재질문 티가 나는 프리픽스


def test_empty_extraction_avoids_immediate_same_slot():
    """빈손 답변 뒤에는 방금 물은 슬롯을 곧바로 재선택하지 않는다(스텁 추출 빈손 활용)."""
    s = interview.start_interview("보호자", PersonaType.dementia)
    s.draft_fields.update({"name": "김순자", "age": "78세", "home": "정릉동"})
    s.filled_keys += ["identity", "home"]
    s.prev_target_key = "routine_destinations"
    s.asked_counts["routine_destinations"] = 1
    storage.interviews.save(s.id, s)

    # "글쎄요" — 규칙 폴백 대상도 아니고 스텁 추출은 slot_filled=True 라
    # 빈손 경로를 보려면 실패 추출을 흉내낸다
    import unittest.mock as mock
    with mock.patch.object(interview.midm, "extract_answer",
                           return_value={"fields": {}, "attraction_points": [],
                                         "behavior_notes": [],
                                         "slot_filled": False}):
        out = interview.answer_interview(s.id, "글쎄요")
    assert out.prev_target_key != "routine_destinations"


# ── 확인 게이트 — 정정을 긍정으로 오판 금지 (라이브 실측 2026-07-17) ──

def test_affirmative_rejects_partial_matches():
    """'…주소예요'의 '예'가 긍정으로 오판돼 정정이 그대로 등록되던 버그 회귀."""
    assert not interview._is_affirmative("마포구 신수동 백범로가 정확한 주소예요")
    assert not interview._is_affirmative("주소를 백범로로 변경해주세요")
    assert not interview._is_affirmative("동네 이름이 신수동이에요")
    assert interview._is_affirmative("네 맞아요")
    assert interview._is_affirmative("네!")
    assert interview._is_affirmative("맞습니다")
    assert interview._is_affirmative("이대로 등록해주세요")


def test_confirmation_address_correction_overwrites_home(monkeypatch):
    """확인 게이트에서 주소 정정 → 등록되지 않고, 주소가 실제로 바뀌어 재요약된다."""
    monkeypatch.setattr(interview, "_GEO", GazetteerGeocoder())
    s = _confirmed_session(home="마포구 신수동", sid="hard-corr")

    class _Hit:
        slot = slot_by_key("home")
        similarity = 0.9

    monkeypatch.setattr(interview.retrieval, "rank_next_slots",
                        lambda *a, **k: ([_Hit()], []))
    out = interview.answer_interview(s.id, "정릉동이 정확한 주소예요")
    assert not out.done                              # 구버전: 긍정 오판 → 그대로 등록
    assert out.awaiting_confirmation                 # 재요약 후 다시 확인 대기
    assert out.draft_fields["home"] == "정릉동"      # 규칙 백스톱 + overwrite 반영
    assert "정릉동" in out.messages[-1]["text"]      # 재요약에 정정 주소 노출

    out = interview.answer_interview(s.id, "네 맞아요")
    assert out.done and out.persona_id


# ── 노트 품질 — 무지·환각 차단 + '질문 요약: 답변 요약' 형식 ─────────

_LOST = slot_by_key("lost_behavior")


def test_note_filter_drops_ignorance_and_hallucination():
    """'잘 모르겠어요' 복사와 발화에 없는 프롬프트 예시 문구(환각)를 모두 차단."""
    s = InterviewSession(id="hard-note1", guardian_name="보호자",
                         persona_type=PersonaType.dementia)
    interview._apply_extraction(s, _LOST, {
        "fields": {}, "attraction_points": [],
        "behavior_notes": ["잘 모르겠어요", "길 잃으면 계속 걷는 편"],
        "slot_filled": False,
    }, utterance="잘 모르겠어요")
    assert s.draft_behaviors == [] and s.slot_notes == {}


def test_note_saved_with_question_summary_prefix():
    """노트는 '슬롯 라벨(질문 요약): 답변 요약' 형식으로 저장, 채점용 원노트는 유지."""
    s = InterviewSession(id="hard-note2", guardian_name="보호자",
                         persona_type=PersonaType.dementia)
    interview._apply_extraction(s, _LOST, {
        "fields": {}, "attraction_points": [],
        "behavior_notes": ["큰길 쪽으로 나가는 편"], "slot_filled": True,
    }, utterance="보통 큰길쪽으로 나가세요")
    assert s.draft_behaviors == ["길 잃었을 때 행동: 큰길 쪽으로 나가는 편"]
    assert s.slot_notes["lost_behavior"] == ["큰길 쪽으로 나가는 편"]   # 축 채점 입력은 원노트


def test_guard_fallback_emits_single_question():
    """폴백 씨앗 질문이 복합 문형(물음표 3개)이어도 한 질문만 내보낸다."""
    slot = slot_by_key("medication")
    assert slot.question.count("?") == 3     # 회의록 원문은 복합 문형(참고용으로 유지)
    out, fell_back = safety.guard_question("복용량을 늘리셔야 해요", slot, EMB)  # 층① 차단
    assert fell_back
    assert out.count("?") == 1
    assert out == "복용 중인 약이 있나요?"


# ── 첫 두 질문 고정 — identity·home 은 문장 변형 금지 ────────────────

def test_first_two_questions_are_fixed(monkeypatch):
    """identity·home 질문은 Mi:dm 이 살아 있어도 씨앗 원문 그대로 나간다."""
    monkeypatch.setattr(interview.midm, "phrase_question",
                        lambda *a, **k: "임의로 바꾼 거주지 질문인가요?")
    s = interview.start_interview("보호자")
    assert s.messages[0]["text"] == slot_by_key("identity").question   # Q1 고정
    out = interview.answer_interview(s.id, "김순자님이고 82세, 치매 어르신이에요")
    assert out.messages[-1]["text"] == slot_by_key("home").question    # Q2 고정
    assert "임의로 바꾼" not in out.messages[-1]["text"]


# ── 갭 기반 꼬리질문 — 충족 기준·확보 사실이 프롬프트에 실린다 ──────

def test_phrase_input_carries_gap_information():
    from app.phase0 import prompts
    slot = slot_by_key("mobility_transport_capacity")
    conv = [{"role": "user", "text": "쉬지 않고 30분은 걸으세요"}]
    out = prompts.build_phrase_input(
        PersonaType.dementia, slot, True, conv,
        collected=["쉬지 않고 30분 걸을 수 있음"])
    assert "충족 기준:" in out and slot.filled_when in out
    assert "이 슬롯에서 이미 확보한 사실: 쉬지 않고 30분 걸을 수 있음" in out
    assert "비어 있는 부분 하나만" in out
    # 확보 사실이 없으면 '(아직 없음)' 표기
    out2 = prompts.build_phrase_input(PersonaType.dementia, slot, False, conv)
    assert "(아직 없음)" in out2


def test_more_places_sweep_before_summary():
    """모든 슬롯이 끝나면 요약 전에 '다른 곳 또 있나요' 스윕이 정확히 1회 나온다.

    (2026-07-21) 직전 슬롯이 얕게 채워졌으면 하위 항목 꼬리질문이 한 번 먼저 나간다
    — probed_keys 를 미리 채워 그 경로를 비활성화하고 스윕 자체를 검증한다.
    """
    s = InterviewSession(
        id="hard-sweep", guardian_name="보호자", persona_type=PersonaType.dementia,
        draft_fields={"name": "김순자", "age": "78세", "home": "신수동"},
        filled_keys=[sp.key for sp in slots_for(PersonaType.dementia)],
        probed_keys=[sp.key for sp in slots_for(PersonaType.dementia)],
        draft_attractions=[{"label": "망원시장", "area_text": "망원동",
                            "evidence": "caregiver_report"}],
        prev_target_key="communication_approach_vulnerability",
    )
    storage.interviews.save(s.id, s)

    out = interview.answer_interview(s.id, "경계하는 편이에요")
    q = out.messages[-1]["text"]
    assert "망원시장" in q and "또 있을까요" in q     # 스윕 — 아는 장소를 나열하며 묻는다
    assert not out.awaiting_confirmation
    assert out.prev_target_key == "routine_destinations"   # 답은 자주 가는 곳으로 추출

    out = interview.answer_interview(s.id, "없어요")
    assert out.awaiting_confirmation                # 스윕은 1회 — 바로 요약으로


def test_geocode_tries_space_collapsed_variant():
    """'망원 시장'(띄어쓰기)도 공백 제거 변형으로 좌표를 찾는다 (8차 실측)."""
    from app.geo.geocode import GeoResult, to_attraction_points
    from app.schemas.common import GeoPoint

    class _ExactGeo:   # 표기 그대로만 매칭하는 백엔드 (nominatim 흉내)
        def locate(self, q, anchor=None):
            if q == "망원시장":
                return GeoResult(GeoPoint(lat=37.556, lng=126.906),
                                 precision="poi", source="x", matched=q)
            return None

    points, unresolved = to_attraction_points(
        [{"label": "망원 시장", "area_text": "망원 시장"}], geocoder=_ExactGeo())
    assert not unresolved
    assert points[0].label == "망원 시장"


def test_home_never_becomes_attraction():
    """거주지 답변에서 추출된 거주 동네는 끌림점으로 저장되지 않는다 (7차 실측)."""
    s = InterviewSession(id="hard-homeattr", guardian_name="보호자",
                         persona_type=PersonaType.dementia)
    interview._apply_extraction(s, slot_by_key("home"), {
        "fields": {"home": "마포구 신수동"},
        "attraction_points": [
            {"label": "신수동", "area_text": "신수동", "evidence": "mention_only"},
            {"label": "대흥동", "area_text": "대흥동", "evidence": "caregiver_report"}],
        "behavior_notes": [], "slot_filled": True,
    }, utterance="마포구 신수동에 거주하시고 대흥동에 자주 가세요")
    labels = [a["label"] for a in s.draft_attractions]
    assert "신수동" not in labels          # 거주지 = 끌림점 금지
    assert "대흥동" in labels              # 진짜 끌림점은 유지


def test_attraction_slots_share_collected_places():
    """장소 수집 슬롯들은 세션 전체 장소를 확보 사실로 공유 — 중복 질문 방지."""
    s = InterviewSession(id="hard-share", guardian_name="보호자",
                         persona_type=PersonaType.dementia)
    # 자전적 기억 턴에서 망원시장이 나옴
    interview._apply_extraction(s, slot_by_key("autobiographical_destination_pull"), {
        "fields": {}, "attraction_points": [
            {"label": "망원시장", "area_text": "망원동", "evidence": "caregiver_report"}],
        "behavior_notes": [], "slot_filled": True,
    }, utterance="망원동 망원시장도 자주 가세요")
    # routine 슬롯의 확보 사실에도 망원시장이 보인다
    got = interview._slot_collected(s, slot_by_key("routine_destinations"))
    assert "장소: 망원시장" in got


# ── origin_slot 태깅 (작업4, unfamiliarity 게이지 폴백 판단용) ────────
def test_attraction_tagged_with_origin_slot():
    s = InterviewSession(id="hard-origin", guardian_name="보호자",
                         persona_type=PersonaType.dementia)
    interview._apply_extraction(s, slot_by_key("routine_destinations"), {
        "fields": {}, "attraction_points": [
            {"label": "정릉시장", "area_text": "정릉동", "evidence": "caregiver_report"}],
        "behavior_notes": [], "slot_filled": True,
    }, utterance="정릉시장에 자주 가세요")
    assert s.draft_attractions[0]["origin_slot"] == "routine_destinations"


def test_attraction_origin_slot_first_wins_on_merge():
    """같은 장소가 다른 슬롯 턴에서 다시 언급돼도 origin_slot 은 처음 슬롯을 유지."""
    s = InterviewSession(id="hard-origin-merge", guardian_name="보호자",
                         persona_type=PersonaType.dementia)
    interview._apply_extraction(s, slot_by_key("routine_destinations"), {
        "fields": {}, "attraction_points": [
            {"label": "망원시장", "area_text": "망원동", "evidence": "mention_only"}],
        "behavior_notes": [], "slot_filled": True,
    }, utterance="망원시장에 자주 가세요")
    interview._apply_extraction(s, slot_by_key("autobiographical_destination_pull"), {
        "fields": {}, "attraction_points": [
            {"label": "망원시장", "area_text": "망원동", "evidence": "previous_missing_found"}],
        "behavior_notes": [], "slot_filled": True,
    }, utterance="예전에 망원시장에서 발견된 적도 있어요")
    assert len(s.draft_attractions) == 1
    assert s.draft_attractions[0]["origin_slot"] == "routine_destinations"   # 처음 슬롯 유지
    assert s.draft_attractions[0]["evidence"] == "previous_missing_found"    # 근거는 승격(기존 동작)


def test_slot_collected_gathers_notes_and_place_labels():
    s = InterviewSession(id="hard-gap", guardian_name="보호자",
                         persona_type=PersonaType.dementia)
    slot = slot_by_key("routine_destinations")
    interview._apply_extraction(s, slot, {
        "fields": {}, "attraction_points": [
            {"label": "망원시장", "area_text": "망원동", "evidence": "caregiver_report"}],
        "behavior_notes": ["망원시장에 자주 감"], "slot_filled": False,
    }, utterance="망원시장에 자주 가세요")
    got = interview._slot_collected(s, slot)
    assert "망원시장에 자주 감" in got
    assert "장소: 망원시장" in got


# ── '여부 먼저' — 존재 전제 세부 질문 가드 (라이브 실측 6차) ─────────

def test_conditional_detail_requires_base_fact(monkeypatch):
    """복용 여부 확인 전에 '약을 드시지 않으면…'이 나오면 씨앗(여부 질문)으로 교체."""
    assert interview._NEG_CONDITIONAL_RE.search("약을 드시지 않으면 밖에 나가려고 하시나요?")
    assert interview._NEG_CONDITIONAL_RE.search("약을 거르시면 더 자주 외출하시나요?")
    assert not interview._NEG_CONDITIONAL_RE.search("길을 잃으시면 보통 어떻게 하시나요?")  # 긍정 조건은 허용

    s = interview.start_interview("보호자", PersonaType.dementia)
    s.draft_fields.update({"name": "김순자", "age": "82세", "home": "신수동"})
    s.filled_keys += ["identity", "home"]
    storage.interviews.save(s.id, s)
    med = slot_by_key("medication")

    class _Hit:
        slot = med
        similarity = 0.1

    monkeypatch.setattr(interview.retrieval, "rank_next_slots",
                        lambda *a, **k: ([_Hit()], []))
    monkeypatch.setattr(interview.midm, "extract_answer",
                        lambda *a, **k: {"fields": {}, "attraction_points": [],
                                         "behavior_notes": [],
                                         "slot_filled": False})
    monkeypatch.setattr(interview.midm, "phrase_question",
                        lambda *a, **k: "약을 드시지 않으면 밖에 나가려고 하시나요?")
    monkeypatch.setattr(interview.safety, "guard_question",
                        lambda q, slot, emb, bank=None: (q, False))   # 가드 통과 가정
    out = interview.answer_interview(s.id, "네 그래요")
    q = out.messages[-1]["text"]
    assert q.startswith("복용 중인 약이 있나요?")   # 여부 확인이 먼저


# ── 라이브 실측 2차(2026-07-17) 회귀 5종 ────────────────────────────

def test_relative_grounding_blocks_topic_drift():
    """다른 슬롯 화제로 흘러간 생성 질문(배회 슬롯 겨냥인데 신호등 질문)은 폴백."""
    target = slot_by_key("dementia_wandering_pattern")
    bank = list(slots_for(PersonaType.dementia))
    drifted = "어르신이 망원시장에 가실 때 횡단보도에서 신호를 지키시나요?"
    out, fell_back = safety.guard_question(drifted, target, EMB, bank=bank)
    assert fell_back                          # 위험인지 슬롯과 더 유사 → 화제 이탈 판정
    assert out == safety.single_question(target.question)


def test_session_wide_question_dedupe():
    """같은 질문 문장은 몇 턴이 지나도 다시 나가지 않는다(4회 반복 회귀)."""
    s = InterviewSession(id="hard-dup", guardian_name="보호자",
                         persona_type=PersonaType.dementia)
    q = "어르신이 횡단보도에서 신호를 지키시나요?"
    s.messages = [{"role": "assistant", "text": q},
                  {"role": "user", "text": "몰라요"},
                  {"role": "assistant", "text": "다른 질문"},
                  {"role": "user", "text": "네"}]
    slot = slot_by_key("hazard_awareness_vulnerability")
    out = interview._dedupe_question(s, slot, q)          # 재등장 → 씨앗 질문으로 교체
    assert interview._norm_q(out) != interview._norm_q(q)
    s.messages.append({"role": "assistant", "text": out})  # 씨앗도 나간 상태에서 또 반복
    out2 = interview._dedupe_question(s, slot, q)
    assert interview._norm_q(out2) not in {interview._norm_q(q), interview._norm_q(out)}


def test_pure_ignorance_exhausts_slot():
    """'모르겠다니까요'는 그 슬롯을 즉시 소진 — 정보 섞인 답은 소진하지 않는다."""
    assert interview._is_pure_ignorance("모르겠다니까요")
    assert interview._is_pure_ignorance("잘 모르겠어요")
    assert not interview._is_pure_ignorance("잘 모르겠는데 사고가 난 적은 없으세요")

    s = interview.start_interview("보호자", PersonaType.dementia)
    s.draft_fields.update({"name": "김순자", "age": "82세"})
    s.filled_keys += ["identity", "home"]
    s.prev_target_key = "hazard_awareness_vulnerability"
    s.asked_counts["hazard_awareness_vulnerability"] = 1
    storage.interviews.save(s.id, s)
    import unittest.mock as mock
    with mock.patch.object(interview.midm, "extract_answer",
                           return_value={"fields": {}, "attraction_points": [],
                                         "behavior_notes": [],
                                         "slot_filled": False}):
        out = interview.answer_interview(s.id, "모르겠다니까요")
    assert out.asked_counts["hazard_awareness_vulnerability"] >= interview.MAX_ASKS_PER_SLOT


def test_sentence_like_home_rejected():
    """문장형 답("집에 주로 계세요")은 home 으로 수용하지 않는다 — 장소 표현만."""
    assert not interview._valid_home_text("집에 주로 계세요")
    assert not interview._valid_home_text("잘 모르겠어요")
    assert interview._valid_home_text("마포구 신수동")
    assert interview._valid_home_text("서울역 근처")

    s = interview.start_interview("보호자", PersonaType.dementia)
    s.persona_type = PersonaType.dementia
    s.draft_fields.update({"name": "김순자", "age": "82세"})
    s.filled_keys.append("identity")
    s.prev_target_key = "home"
    s.asked_counts["home"] = 1
    storage.interviews.save(s.id, s)
    import unittest.mock as mock
    with mock.patch.object(interview.midm, "extract_answer",
                           return_value={"fields": {"home": "집에 주로 계세요"},
                                         "attraction_points": [],
                                         "behavior_notes": [], "slot_filled": True}):
        out = interview.answer_interview(s.id, "집에 주로 계세요")
    assert "home" not in out.draft_fields      # 문장형 home 거부
    assert "home" not in out.filled_keys       # 충족 처리도 취소


def test_near_duplicate_notes_blocked():
    """어미만 다른 같은 사실('~편이 아님' vs '~편이 아니에요')은 자카드로 차단."""
    s = InterviewSession(id="hard-jdup", guardian_name="보호자",
                         persona_type=PersonaType.dementia)
    utt = "길을 잘못 들면 스스로 못 알아차리세요"
    interview._apply_extraction(
        s, slot_by_key("wayfinding_error_recovery_deficit"),
        {"fields": {}, "attraction_points": [],
         "behavior_notes": ["길을 잘못 들었을 때 스스로 알아차리시는 편이 아님"],
         "slot_filled": True}, utterance=utt)
    interview._apply_extraction(
        s, slot_by_key("dementia_wandering_pattern"),
        {"fields": {}, "attraction_points": [],
         "behavior_notes": ["길을 잘못 들었을 때 스스로 알아차리시는 편이 아니에요"],
         "slot_filled": True}, utterance=utt)
    assert len(s.draft_behaviors) == 1


def test_profile_slots_reject_behavior_notes():
    """identity/home 은 필드 수집 전용 — '현재 거주지: 길 잃었을 때…' 오귀속 방지."""
    s = InterviewSession(id="hard-prof", guardian_name="보호자",
                         persona_type=PersonaType.dementia)
    interview._apply_extraction(
        s, slot_by_key("home"),
        {"fields": {"home": "정릉동"}, "attraction_points": [],
         "behavior_notes": ["길 잃었을 때 그 자리에 계속 있으세요"], "slot_filled": True},
        utterance="정릉동이요, 길 잃으면 그 자리에 계속 있으세요")
    assert s.draft_behaviors == []                  # 행동 노트는 받지 않는다
    assert s.draft_fields["home"] == "정릉동"       # 필드 수집은 정상


def test_slots_catalog_endpoint():
    """대시보드 축 렌더링용 슬롯 카탈로그 API — 치매 = 공통 8 + 특화 4."""
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    r = client.get("/phase0/slots", params={"persona_type": "dementia"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 12
    assert {s["axis"] for s in data} == {"기본필드", "몸축", "마음축", "행동축"}
    assert all(s["key"] and s["label"] for s in data)


def test_negative_answer_resolves_slot():
    """'딱히 없어요'는 유효한 답 — 슬롯 충족 처리, 재질문 금지 (4차 실측 회귀)."""
    assert interview._is_negative_answer("딱히 없어요")
    assert interview._is_negative_answer("아니요")
    assert interview._is_negative_answer("먹는 약 없다고요")
    assert not interview._is_negative_answer("망원동까진 걸어가세요")
    assert not interview._is_negative_answer("잘 모르겠는데 사고가 난 적은 없으세요")  # 정보 섞임(길이)

    s = interview.start_interview("보호자", PersonaType.dementia)
    s.draft_fields.update({"name": "김순자", "age": "82세", "home": "신수동"})
    s.filled_keys += ["identity", "home"]
    s.prev_target_key = "medication"
    s.asked_counts["medication"] = 1
    storage.interviews.save(s.id, s)
    import unittest.mock as mock
    with mock.patch.object(interview.midm, "extract_answer",
                           return_value={"fields": {}, "attraction_points": [],
                                         "behavior_notes": [],
                                         "slot_filled": False}):
        out = interview.answer_interview(s.id, "아니요")
    assert "medication" in out.filled_keys      # '해당 없음'으로 충족 — 약 후속질문 금지


def test_seed_question_personalized_by_type():
    """폴백 씨앗 질문의 '대상자' 문체를 유형 호칭으로 바꾼다."""
    q = "대상자가 반복해서 찾거나 가려고 하는 과거의 장소가 있나요?"
    assert interview._personalize(q, PersonaType.dementia).startswith("어르신이")
    assert interview._personalize(q, None) == q


def test_attraction_dedup_by_label():
    """같은 장소가 지역 표기만 달리 재언급돼도 한 번만 저장 + 근거 승격."""
    s = InterviewSession(id="hard-attr", guardian_name="보호자",
                         persona_type=PersonaType.dementia)
    interview._apply_extraction(s, _LOST, {
        "fields": {}, "attraction_points": [
            {"label": "망원시장", "area_text": "망원시장", "evidence": "mention_only"}],
        "behavior_notes": [], "slot_filled": False}, utterance="망원시장이요")
    interview._apply_extraction(s, _LOST, {
        "fields": {}, "attraction_points": [
            {"label": "망원시장", "area_text": "망원동", "evidence": "previous_missing_found"}],
        "behavior_notes": [], "slot_filled": False}, utterance="망원시장에서 발견됐어요")
    assert len(s.draft_attractions) == 1
    assert s.draft_attractions[0]["evidence"] == "previous_missing_found"   # 근거 승격


def test_seed_fallback_includes_answer_example():
    """씨앗 질문이 그대로 나갈 때 '(예: …)'를 붙인다 — 단문 절단으로 모호해진
    질문("길을 잃으시면 보통 어떻게 하시나요?")에 축 눈높이 예시 제공."""
    q = interview._seed_with_example(slot_by_key("lost_behavior"))
    assert q.startswith("길을 잃으시면 보통 어떻게 하시나요?")
    assert "(예: " in q and q.count("?") == 1
    # 예시 유무만 다른 같은 질문은 중복으로 인식돼야 한다 (재질문 가드 연동)
    assert interview._norm_q(q) == interview._norm_q("길을 잃으시면 보통 어떻게 하시나요?")


def test_attraction_containment_merge():
    """포함 관계 라벨("대흥역" vs "대흥역 2번 출구")은 한 장소로 병합 + 근거 승격."""
    s = InterviewSession(id="hard-contain", guardian_name="보호자",
                         persona_type=PersonaType.dementia)
    interview._apply_extraction(s, _LOST, {
        "fields": {}, "attraction_points": [
            {"label": "대흥역", "area_text": "대흥동", "evidence": "caregiver_report"}],
        "behavior_notes": [], "slot_filled": False}, utterance="대흥역 쪽을 자주 가세요")
    interview._apply_extraction(s, _LOST, {
        "fields": {}, "attraction_points": [
            {"label": "대흥역 2번 출구", "area_text": "대흥역", "evidence": "previous_missing_found"}],
        "behavior_notes": [], "slot_filled": False}, utterance="대흥역 2번 출구에서 발견됐어요")
    assert len(s.draft_attractions) == 1
    assert s.draft_attractions[0]["label"] == "대흥역"
    assert s.draft_attractions[0]["evidence"] == "previous_missing_found"


def test_ungrounded_presupposition_falls_back():
    """'~한다고 말씀하실 때'는 보호자가 실제로 그렇게 말한 뒤에만 허용."""
    s = InterviewSession(id="hard-presup", guardian_name="보호자",
                         persona_type=PersonaType.dementia,
                         messages=[{"role": "user", "text": "집에 주로 계세요"}])
    bad = "예전에 살던 집에 가야 한다고 말씀하실 때, 어느 지역을 말씀하시나요?"
    assert not interview._presupposition_grounded(s, bad)   # 그런 말 한 적 없음

    s.messages.append({"role": "user", "text": "회사에 가야 한다고 자꾸 말씀하세요"})
    ok = "회사에 가야 한다고 말씀하실 때 어느 회사를 뜻하시는 걸까요?"
    assert interview._presupposition_grounded(s, ok)        # 실제 발화 기반 — 통과

    plain = "혼자 나가실 때 주로 어디에 가시나요?"
    assert interview._presupposition_grounded(s, plain)     # 전제 없음 — 통과


def test_same_fact_not_duplicated_across_slots():
    """같은 원노트는 겨냥 슬롯이 달라도 한 번만 저장된다."""
    s = InterviewSession(id="hard-xdup", guardian_name="보호자",
                         persona_type=PersonaType.dementia)
    ext = {"fields": {}, "attraction_points": [],
           "behavior_notes": ["많이 배회하는 편"], "slot_filled": True}
    interview._apply_extraction(
        s, slot_by_key("wayfinding_error_recovery_deficit"), dict(ext),
        utterance="네 많이 배회하세요")
    interview._apply_extraction(
        s, slot_by_key("dementia_wandering_pattern"), dict(ext),
        utterance="네 많이 배회하세요")
    assert len(s.draft_behaviors) == 1


# ── 옛집 변종 라벨 재추출 → 한 장소로 병합 (2026-07-23 D2 실측) ──────────

def test_past_home_variant_labels_merge_not_fragment():
    """Mi:dm 이 옛집을 변종 라벨로 반복 재추출해도 한 장소로 병합한다.

    라이브 실측(2026-07-23 D2): '예전에 살던 집'(마포구 신수동)이 이후 턴에
    '예전 집'·'마포구 신수동 옛날 집'·되묻기 주소 '마포구 신수동'으로 재추출돼
    같은 집이 3~4조각으로 쌓였다(비연속 부분열이라 라벨 포함매칭이 못 잡음).
    """
    s = InterviewSession(
        id="merge-pasthome", guardian_name="보호자", persona_type=PersonaType.dementia,
        draft_attractions=[{"label": "예전에 살던 집", "area_text": "마포구 신수동",
                            "evidence": "caregiver_report",
                            "origin_slot": "autobiographical_destination_pull"}],
    )
    slot = slot_by_key("autobiographical_destination_pull")
    for label in ("예전 집", "마포구 신수동 옛날 집", "마포구 신수동"):
        interview._apply_extraction(s, slot, {
            "attraction_points": [{"label": label, "area_text": "마포구 신수동",
                                   "evidence": "mention_only"}],
            "slot_filled": True,
        }, utterance="늘 옛날 집 얘기만 하세요")
    labels = [a["label"] for a in s.draft_attractions]
    assert len(s.draft_attractions) == 1, f"옛집이 조각남: {labels}"
    assert labels[0] == "예전에 살던 집"


def test_distinct_places_not_over_merged():
    """서로 다른 장소는 병합하지 않는다 — 옛집 병합이 과병합으로 번지지 않게."""
    s = InterviewSession(
        id="merge-distinct", guardian_name="보호자", persona_type=PersonaType.dementia,
        draft_attractions=[{"label": "정릉시장", "area_text": "성북구 정릉동",
                            "evidence": "caregiver_report"}],
    )
    interview._apply_extraction(s, slot_by_key("routine_destinations"), {
        "attraction_points": [{"label": "대흥역", "area_text": "마포구",
                               "evidence": "previous_missing_found"}],
        "slot_filled": True,
    }, utterance="대흥역에서 발견됐어요")
    labels = sorted(a["label"] for a in s.draft_attractions)
    assert labels == ["대흥역", "정릉시장"], labels


# ── 고유어 나이 파싱 (2026-07-23 골드셋 실측: Mi:dm 이 "여든둘" 그대로 저장) ──

def test_korean_native_age_parsing():
    """고유어 나이 수사를 정수로 변환한다 — Mi:dm 이 '여든둘'을 그대로 넣는 실측.

    골드셋에서 이름 100% 인데 나이 대부분 0% 였던 원인: 나이 칸에 '여든둘'·
    '일흔여덟' 같은 한글 수사가 그대로 저장돼 숫자 파싱이 실패했다.
    """
    assert interview._parse_age("일흔여덟") == 78
    assert interview._parse_age("여든둘") == 82
    assert interview._parse_age("스물다섯") == 25
    assert interview._parse_age("여든") == 80
    assert interview._parse_age("열아홉") == 19
    assert interview._parse_age("여든둘이세요") == 82   # 조사 '세요'가 셋(3)으로 오염 안 됨
    assert interview._parse_age("78세") == 78           # 아라비아 숫자 경로 유지
    assert interview._parse_age("") == 0
