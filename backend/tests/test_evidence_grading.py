"""evidence 근거 강도 판정 — 규칙 백스톱 (라이브 실측 2026-07-21).

Mi:dm 실측 A/B(각 4회): "원마루 공원에 자주 가세요", "예전에 살던 집에 가야 한다는
말을 종종 합니다" 모두 **4/4 mention_only**. 프롬프트 문구를 고쳐도 그대로였다
(모델은 "발견됐다"가 아닌 것을 전부 최약으로 떨어뜨린다). 근거 강도는 한국어
표면형이 뚜렷하므로 코드가 판정하고, LLM 판정은 **승급 방향으로만** 덮는다
— evidence 는 곱셈 병합의 한 축이라(0.9/0.5/0.3) 한 등급 차가 예측 가중치를 바꾼다.
"""

from app.phase0 import interview
from app.phase0.slots import slot_by_key
from app.schemas.persona import InterviewSession, PersonaType

_PLACE_SLOT = slot_by_key("autobiographical_destination_pull")
_WANDER_SLOT = slot_by_key("dementia_wandering_pattern")


def _grade(utterance: str, slot_key: str = "autobiographical_destination_pull"):
    return interview._evidence_from_utterance(utterance, slot_key)


# ── 표면형 판정 ──────────────────────────────────────────────────────

def test_repeated_intent_is_caregiver_report():
    """'가야 한다고 자주 말한다'도 관찰된 지향 — 실측에서 mention_only 로 떨어지던 케이스."""
    assert _grade("예전에 살던 집에 가야한다는 말을 종종 합니다") == "caregiver_report"
    assert _grade("원마루 공원에 자주 가세요") == "caregiver_report"
    assert _grade("매일 그 시장에 가시려고 해요") == "caregiver_report"
    assert _grade("옛 직장을 보러 나가려 하신 적이 있어요") == "caregiver_report"


def test_found_place_is_previous_missing_found():
    assert _grade("한번 있었고 원평중학교 앞에서 발견돼셨어요",
                  "dementia_wandering_pattern") == "previous_missing_found"
    assert _grade("실종됐을 때 옛날 집 근처에서 찾았어요") == "previous_missing_found"


def test_background_mention_not_upgraded():
    """배경 설명은 승급하지 않는다 — LLM 판정(mention_only)이 그대로 남는다."""
    assert _grade("젊으실 때 방직공장에 다니셨대요") is None
    assert _grade("예전에 그 동네에 사셨어요") is None


def test_negated_intent_not_upgraded():
    """'가시려는 건 아니에요' — 반복 표현이 있어도 지향을 부정하면 승급 금지."""
    assert _grade("가끔 옛날 시장 얘기를 하시는데 가시려는 건 아니에요") is None
    assert _grade("자주 가시진 않아요") is None


def test_transitive_discovery_is_not_found_evidence():
    """'~을 발견하다'(타동사)는 피발견이 아니다 — 장소 근거로 올리지 않는다."""
    assert _grade("새로 생긴 공원을 발견하고 좋아하셨어요") is None
    assert _grade("좋아하는 가게를 발견하셨어요") is None
    # 반면 '~에서/~걸 발견됐다'는 피발견 — 슬롯 종류와 무관하게 근거로 인정한다
    assert _grade("대흥역에서 발견한 적이 있어요", "lost_behavior") == "previous_missing_found"
    assert _grade("앉아계시는걸 발견했어요", "lost_behavior") == "previous_missing_found"


# ── 승급만 한다 (내리지 않는다) ──────────────────────────────────────

def test_upgrade_only_never_downgrades():
    ap = {"evidence": "previous_missing_found"}
    interview._upgrade_evidence(ap, "caregiver_report")
    assert ap["evidence"] == "previous_missing_found"      # 약한 규칙이 강한 판정을 못 내린다

    ap = {"evidence": "mention_only"}
    interview._upgrade_evidence(ap, "caregiver_report")
    assert ap["evidence"] == "caregiver_report"

    ap = {"evidence": "caregiver_report"}
    interview._upgrade_evidence(ap, None)                  # 규칙이 못 잡으면 그대로
    assert ap["evidence"] == "caregiver_report"


# ── 추출 경로 통합 ───────────────────────────────────────────────────

def test_apply_extraction_upgrades_llm_grade():
    """Mi:dm 이 mention_only 로 내려도 발화 근거가 있으면 올라간다."""
    s = InterviewSession(id="ev1", guardian_name="보호자", persona_type=PersonaType.dementia)
    interview._apply_extraction(s, _PLACE_SLOT, {"attraction_points": [
        {"label": "예전에 살던 집", "area_text": "산남동", "evidence": "mention_only"}]},
        utterance="예전에 살던 집에 가야한다는 말을 종종 합니다")
    assert s.draft_attractions[0]["evidence"] == "caregiver_report"


def test_apply_extraction_keeps_grade_without_evidence_cue():
    s = InterviewSession(id="ev2", guardian_name="보호자", persona_type=PersonaType.dementia)
    interview._apply_extraction(s, _PLACE_SLOT, {"attraction_points": [
        {"label": "방직공장", "area_text": "면목동", "evidence": "mention_only"}]},
        utterance="젊으실 때 방직공장에 다니셨대요")
    assert s.draft_attractions[0]["evidence"] == "mention_only"


def test_evidence_not_transferred_to_unmentioned_place():
    """발화에 없는 장소에는 근거를 붙이지 않는다 — 라이브 실측 최악 케이스.

    "대흥역에서 발견한 적이 있어요"에 Mi:dm 이 (이전 턴의) 망원시장을 반환했고,
    승급 규칙이 그 '발견' 근거를 망원시장에 붙여 **엉뚱한 곳이 0.9** 를 받았다.
    """
    s = InterviewSession(id="ev-x", guardian_name="보호자", persona_type=PersonaType.dementia)
    interview._apply_extraction(s, _WANDER_SLOT, {"attraction_points": [
        {"label": "망원시장", "area_text": "망원시장", "evidence": "caregiver_report"}]},
        utterance="대흥역에서 발견한 적이 한번 있어요")
    found = next(a for a in s.draft_attractions if a["label"] == "망원시장")
    assert found["evidence"] == "caregiver_report"     # 0.9 로 둔갑하지 않는다


def test_llm_found_grade_rejected_without_cue():
    """발화에 '발견' 근거가 없으면 모델의 최상위 등급을 인정하지 않는다.

    실측: "과거에 망원시장에서 가게를 하신 적이 있어서 거기에 가야 한다고 종종
    말씀하시곤 해요" → Mi:dm previous_missing_found. 평소 다니는 시장이 0.9 가 됐다.
    """
    s = InterviewSession(id="ev-vf", guardian_name="보호자", persona_type=PersonaType.dementia)
    interview._apply_extraction(s, _PLACE_SLOT, {"attraction_points": [
        {"label": "망원시장", "area_text": "망원시장",
         "evidence": "previous_missing_found"}]},
        utterance="과거에 망원시장에서 가게를 하신 적이 있어서 거기에 가야 한다고 종종 말씀하시곤 해요")
    # '종종 ... 가야 한다' = 반복 지향이므로 caregiver_report 까지만
    assert s.draft_attractions[0]["evidence"] == "caregiver_report"


def test_llm_found_grade_kept_with_cue():
    """발견 근거가 실제로 있으면 최상위 등급을 유지한다."""
    s = InterviewSession(id="ev-vk", guardian_name="보호자", persona_type=PersonaType.dementia)
    interview._apply_extraction(s, _WANDER_SLOT, {"attraction_points": [
        {"label": "대흥역", "area_text": "대흥역", "evidence": "previous_missing_found"}]},
        utterance="대흥역에서 발견한 적이 한번 있어요")
    assert s.draft_attractions[0]["evidence"] == "previous_missing_found"


def test_found_place_recovered_from_utterance():
    """모델이 발견지를 놓치면 발화의 지명을 직접 끌림점으로 만든다."""
    s = InterviewSession(id="ev-rec", guardian_name="보호자", persona_type=PersonaType.dementia,
                         draft_attractions=[{"label": "망원시장", "area_text": "망원시장",
                                             "evidence": "caregiver_report"}])
    ext = {"attraction_points": [{"label": "망원시장", "area_text": "망원시장",
                                  "evidence": "caregiver_report"}]}
    interview._ensure_found_place(s, _WANDER_SLOT, ext, "대흥역에서 발견한 적이 한번 있어요")
    labels = [a["label"] for a in s.draft_attractions]
    assert "대흥역" in labels
    ap = next(a for a in s.draft_attractions if a["label"] == "대흥역")
    assert ap["evidence"] == "previous_missing_found"


def test_found_place_not_recovered_when_model_got_it():
    """모델이 제대로 뽑았으면 백스톱은 개입하지 않는다."""
    s = InterviewSession(id="ev-ok", guardian_name="보호자", persona_type=PersonaType.dementia)
    ext = {"attraction_points": [{"label": "대흥역 2번 출구", "area_text": ""}]}
    interview._ensure_found_place(s, _WANDER_SLOT, ext,
                                  "대흥역 2번 출구에서 발견한 적이 있어요")
    assert s.draft_attractions == []      # 중복 생성 없음


def test_found_place_not_recovered_on_negation():
    """'발견된 적 없어요'는 발견지가 아니다."""
    s = InterviewSession(id="ev-neg", guardian_name="보호자", persona_type=PersonaType.dementia)
    interview._ensure_found_place(s, _WANDER_SLOT, {"attraction_points": []},
                                  "대흥역 근처에서 발견된 적은 없어요")
    assert s.draft_attractions == []
    assert _grade("대흥역 근처에서 발견된 적은 없어요", "dementia_wandering_pattern") is None


def test_empty_extraction_on_past_place_slot_is_retried(monkeypatch):
    """장소가 담긴 답인데 Mi:dm 이 빈손이면 1회 재시도한다 (실측: 재시도로 회복)."""
    from app import storage

    s = InterviewSession(id="ev-retry", guardian_name="보호자",
                         persona_type=PersonaType.dementia,
                         draft_fields={"name": "송복남", "age": "82세", "home": "분평동"},
                         filled_keys=["identity", "home"],
                         prev_target_key="dementia_wandering_pattern")
    storage.interviews.save(s.id, s)
    calls = {"n": 0}

    def flaky(slot, conv):
        calls["n"] += 1
        base = {"fields": {}, "behavior_notes": [],
                "slot_filled": True, "attraction_points": []}
        if calls["n"] == 1:
            return base                                     # 첫 호출은 빈손
        return {**base, "attraction_points": [{"label": "원평중학교", "area_text": "원평중학교"}]}

    monkeypatch.setattr(interview.midm, "extract_answer", flaky)
    monkeypatch.setattr(interview, "_next_slot", lambda *a, **k: None)
    out = interview.answer_interview(s.id, "한번 있었고 원평중학교 앞에서 발견돼셨어요")
    assert calls["n"] == 2                                   # 재시도 발생
    assert [a["label"] for a in out.draft_attractions] == ["원평중학교"]
    assert out.draft_attractions[0]["evidence"] == "previous_missing_found"


def test_no_retry_when_answer_has_no_place_cue(monkeypatch):
    """근거 표현이 없는 답변("잘 모르겠어요")은 재시도하지 않는다 — 호출 낭비 금지."""
    from app import storage

    s = InterviewSession(id="ev-noretry", guardian_name="보호자",
                         persona_type=PersonaType.dementia,
                         draft_fields={"name": "송복남", "age": "82세", "home": "분평동"},
                         filled_keys=["identity", "home"],
                         prev_target_key="dementia_wandering_pattern")
    storage.interviews.save(s.id, s)
    calls = {"n": 0}

    def counter(slot, conv):
        calls["n"] += 1
        return {"fields": {}, "behavior_notes": [],
                "slot_filled": True, "attraction_points": []}

    monkeypatch.setattr(interview.midm, "extract_answer", counter)
    monkeypatch.setattr(interview, "_next_slot", lambda *a, **k: None)
    interview.answer_interview(s.id, "잘 모르겠어요")
    assert calls["n"] == 1


def test_wandering_slot_upgrade_to_strongest():
    s = InterviewSession(id="ev3", guardian_name="보호자", persona_type=PersonaType.dementia)
    interview._apply_extraction(s, _WANDER_SLOT, {"attraction_points": [
        {"label": "원평중학교", "area_text": "원평중학교", "evidence": "mention_only"}]},
        utterance="한번 있었고 원평중학교 앞에서 발견돼셨어요")
    assert s.draft_attractions[0]["evidence"] == "previous_missing_found"
