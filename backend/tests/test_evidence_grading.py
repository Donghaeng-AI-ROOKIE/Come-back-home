"""장소 근거 강도 — 모델이 판정하고, 코드는 원문 대조만 한다 (2026-09-26 재작성).

예전에는 '자주·종종·발견' 같은 표면형을 정규식으로 찾아 근거를 올리고 내렸다. 사용자
결정(보호자 문장을 단어 목록으로 해석하지 않는다)에 따라 판정은 Mi:dm 이 하고, 코드는
모델이 근거로 낸 원문 구절(quote)과 장소 이름이 답에 실제로 있는지만 본다. 아래 테스트는
예전 규칙이 막던 **라이브 실측 실패**를 새 방식으로도 막는지 확인한다.
"""

from app import storage
from app.phase0 import interview
from app.phase0.slots import slot_by_key
from app.schemas.persona import InterviewSession, PersonaType

_PLACE_SLOT = slot_by_key("autobiographical_destination_pull")
_WANDER_SLOT = slot_by_key("dementia_wandering_pattern")


def _session(sid: str, **kw) -> InterviewSession:
    return InterviewSession(id=sid, guardian_name="보호자", persona_type=PersonaType.dementia, **kw)


def _apply(s, slot, points, utterance, question=""):
    if question:
        s.messages.append({"role": "assistant", "text": question})
    s.messages.append({"role": "user", "text": utterance})
    interview._apply_extraction(s, slot, {"answer_kind": "informative", "attraction_points": points},
                                utterance=utterance)


# ── 모델 판정을 그대로 받는다(코드가 단어로 올리거나 내리지 않는다) ─────────

def test_grounded_repeat_evidence_is_kept():
    s = _session("ev-keep")
    _apply(s, _PLACE_SLOT, [{"label": "원마루 공원", "area_text": "", "evidence": "caregiver_report",
                             "quote": "원마루 공원에 자주 가세요"}], "원마루 공원에 자주 가세요")
    assert s.draft_attractions[0]["evidence"] == "caregiver_report"
    assert s.extraction_audit == []


def test_model_grade_is_not_upgraded_by_surface_words():
    """'자주'가 있어도 모델이 mention_only 로 냈으면 그대로 — 코드는 단어로 승급하지 않는다.

    실측(2026-07-21)에서 Mi:dm 은 이런 답을 mention_only 로 떨어뜨렸다. 개인 해석(K)은
    원문을 다시 읽어 판정하므로, 온보딩 태그는 SAR 단독 경로의 초기 가중치에만 쓰인다.
    """
    s = _session("ev-noup")
    _apply(s, _PLACE_SLOT, [{"label": "원마루 공원", "evidence": "mention_only",
                             "quote": "원마루 공원에 자주 가세요"}], "원마루 공원에 자주 가세요")
    assert s.draft_attractions[0]["evidence"] == "mention_only"


# ── 원문 대조로 막는 실측 실패 ────────────────────────────────────────

def test_graded_evidence_without_quote_in_answer_is_downgraded():
    s = _session("ev-quote")
    _apply(s, _PLACE_SLOT, [{"label": "방직공장", "evidence": "caregiver_report",
                             "quote": "방직공장에 매일 가려고 하세요"}], "젊으실 때 방직공장에 다니셨대요")
    assert s.draft_attractions[0]["evidence"] == "mention_only"
    assert s.extraction_audit == [{"event": "evidence_downgraded", "label": "방직공장",
                                   "claimed": "caregiver_report", "reason": "quote_not_in_answer"}]


def test_evidence_not_transferred_to_unmentioned_place():
    """발화에 없는 장소에는 근거를 붙이지 않는다 — 라이브 실측 최악 케이스(2026-07-22).

    "대흥역에서 발견한 적이 있어요"에 Mi:dm 이 이전 턴의 망원시장을 발견지로 냈다.
    """
    s = _session("ev-x", draft_attractions=[{"label": "망원시장", "area_text": "망원시장",
                                            "evidence": "caregiver_report"}])
    _apply(s, _WANDER_SLOT, [{"label": "망원시장", "area_text": "망원시장",
                              "evidence": "previous_missing_found",
                              "quote": "대흥역에서 발견한 적이 한번 있어요"}],
           "대흥역에서 발견한 적이 한번 있어요", question="과거에 길을 잃으셨을 때 어디서 찾으셨나요?")
    found = next(a for a in s.draft_attractions if a["label"] == "망원시장")
    assert found["evidence"] == "caregiver_report"     # 0.9 로 둔갑하지 않는다
    rejected = [e for e in s.extraction_audit if e["event"] == "point_not_in_answer"]
    assert rejected[-1]["label"] == "망원시장"
    # #257: 이전 장소가 아예 없던 경우에도 무관한 발화의 quote만으로 새로 만들지 않는다.
    s.draft_attractions.clear()
    _apply(s, _WANDER_SLOT, [{"label": "망원시장", "quote": "대흥역에서 발견한 적이 한번 있어요"}],
           "대흥역에서 발견한 적이 한번 있어요")
    assert not s.draft_attractions


def test_place_named_in_question_can_take_evidence(monkeypatch):
    """'거기서 발견됐어요' — 장소 이름이 직전 질문에 있으면 근거를 받을 수 있다."""
    monkeypatch.setattr(interview.midm, "verify_found", lambda label, q, a: True)
    s = _session("ev-q")
    _apply(s, _WANDER_SLOT, [{"label": "망원시장", "evidence": "previous_missing_found",
                              "quote": "네 거기서 발견됐어요"}],
           "네 거기서 발견됐어요", question="망원시장에서 발견되신 적이 있나요?")
    assert s.draft_attractions[0]["evidence"] == "previous_missing_found"


def test_found_grade_needs_confirmation(monkeypatch):
    """발견지는 좁은 질문으로 한 번 더 확인한다 — 아니라면 인정하지 않는다.

    실측(2026-07-22): "과거에 망원시장에서 가게를 하신 적이 있어서 거기에 가야 한다고
    종종 말씀하시곤 해요" → Mi:dm previous_missing_found. 평소 다니는 시장이 0.9 가 됐다.
    """
    asked = []
    monkeypatch.setattr(interview.midm, "verify_found",
                        lambda label, q, a: asked.append((label, a)) or False)
    s = _session("ev-vf")
    utterance = "과거에 망원시장에서 가게를 하신 적이 있어서 거기에 가야 한다고 종종 말씀하시곤 해요"
    _apply(s, _PLACE_SLOT, [{"label": "망원시장", "area_text": "망원시장",
                             "evidence": "previous_missing_found", "quote": utterance}], utterance)
    assert asked == [("망원시장", utterance)]
    assert s.draft_attractions[0]["evidence"] == "mention_only"
    assert s.extraction_audit[-1]["reason"] == "found_not_confirmed"


def test_found_grade_kept_when_confirmed(monkeypatch):
    monkeypatch.setattr(interview.midm, "verify_found", lambda label, q, a: True)
    s = _session("ev-vk")
    _apply(s, _WANDER_SLOT, [{"label": "대흥역", "area_text": "대흥역", "evidence": "previous_missing_found",
                              "quote": "대흥역에서 발견한 적이 한번 있어요"}],
           "대흥역에서 발견한 적이 한번 있어요")
    assert s.draft_attractions[0]["evidence"] == "previous_missing_found"


def test_found_grade_not_accepted_when_check_unavailable(monkeypatch):
    """확인 호출이 실패하면(판정 없음) 최상위 근거를 인정하지 않는다."""
    monkeypatch.setattr(interview.midm, "verify_found", lambda label, q, a: None)
    s = _session("ev-vn")
    _apply(s, _WANDER_SLOT, [{"label": "대흥역", "evidence": "previous_missing_found",
                              "quote": "대흥역에서 발견됐어요"}], "대흥역에서 발견됐어요")
    assert s.draft_attractions[0]["evidence"] == "mention_only"
    assert s.extraction_audit[-1]["reason"] == "found_check_unavailable"


def test_place_absent_from_answer_is_not_created():
    """이름도 원문 구절도 답에 없는 장소는 받지 않는다 — 재출력·지어낸 값."""
    s = _session("ev-drop")
    _apply(s, _PLACE_SLOT, [{"label": "옛 직장", "area_text": "면목동", "evidence": "caregiver_report",
                             "quote": "옛 직장에 가려고 하세요"}], "요즘은 집에만 계세요")
    assert s.draft_attractions == []
    assert s.extraction_audit[0]["event"] == "point_not_in_answer"


def test_paraphrased_label_kept_when_quote_is_in_answer():
    """모델이 이름을 조금 바꿔 적어도(옛날→예전) 원문 구절이 답에 있으면 받는다."""
    s = _session("ev-para")
    utterance = "옛날에 살던 집에 가야 한다고 종종 말씀하세요"
    _apply(s, _PLACE_SLOT, [{"label": "예전에 살던 집", "area_text": "", "evidence": "caregiver_report",
                             "quote": "옛날에 살던 집에 가야 한다고 종종 말씀하세요"}], utterance)
    assert s.draft_attractions[0]["label"] == "예전에 살던 집"
    # 이름이 답·질문에 없어 근거 강도는 내린다(이름을 바꿔 적은 곳에 근거를 붙이지 않는다)
    assert s.draft_attractions[0]["evidence"] == "mention_only"


def test_merge_only_upgrades():
    s = _session("ev-merge", draft_attractions=[{"label": "대흥역", "evidence": "previous_missing_found"}])
    _apply(s, _PLACE_SLOT, [{"label": "대흥역", "evidence": "mention_only", "quote": "대흥역 근처요"}],
           "대흥역 근처요")
    assert s.draft_attractions[0]["evidence"] == "previous_missing_found"


# ── 과거 장소 슬롯의 재추출 ─────────────────────────────────────────

def _ready(sid: str, **kw) -> InterviewSession:
    s = _session(sid, draft_fields={"name": "송복남", "age": "82세", "home": "분평동"},
                 filled_keys=["identity", "home"], prev_target_key="dementia_wandering_pattern",
                 messages=[{"role": "assistant", "text": "과거에 길을 잃으셨을 때 어디서 찾으셨나요?"}], **kw)
    storage.interviews.save(s.id, s)
    return s


def test_empty_extraction_on_past_place_slot_is_rechecked(monkeypatch):
    """사실이 담긴 답인데 장소가 비면 무엇이 빠졌는지 알려 1회 재추출한다(실측: 재시도로 회복)."""
    s = _ready("ev-retry")
    calls = []

    def flaky(slot, conv, recheck_places=False):
        calls.append(recheck_places)
        base = {"answer_kind": "informative", "fields": {}, "behavior_notes": [],
                "slot_filled": True, "attraction_points": []}
        if not recheck_places:
            return base
        return {**base, "attraction_points": [{"label": "원평중학교", "area_text": "원평중학교",
                                               "evidence": "previous_missing_found",
                                               "quote": "원평중학교 앞에서 발견돼셨어요"}]}

    monkeypatch.setattr(interview.midm, "extract_answer", flaky)
    monkeypatch.setattr(interview.midm, "verify_found", lambda label, q, a: True)
    monkeypatch.setattr(interview, "_next_slot", lambda *a, **k: None)
    out = interview.answer_interview(s.id, "한번 있었고 원평중학교 앞에서 발견돼셨어요")
    assert calls == [False, True]
    assert [a["label"] for a in out.draft_attractions] == ["원평중학교"]
    assert out.draft_attractions[0]["evidence"] == "previous_missing_found"


def test_reemitted_old_place_triggers_recheck(monkeypatch):
    """이전 턴 장소만 되뱉으면(대흥역 답에 망원시장) 새 장소가 없는 것으로 보고 재추출한다."""
    s = _ready("ev-reemit", draft_attractions=[{"label": "망원시장", "area_text": "망원시장",
                                               "evidence": "caregiver_report"}])
    calls = []

    def extractor(slot, conv, recheck_places=False, **_):
        calls.append(recheck_places)
        point = ({"label": "대흥역", "evidence": "previous_missing_found",
                  "quote": "대흥역에서 발견한 적이 있어요"} if recheck_places else
                 {"label": "망원시장", "evidence": "previous_missing_found",
                  "quote": "대흥역에서 발견한 적이 있어요"})
        return {"answer_kind": "informative", "fields": {}, "behavior_notes": [],
                "slot_filled": True, "attraction_points": [point]}

    monkeypatch.setattr(interview.midm, "extract_answer", extractor)
    monkeypatch.setattr(interview.midm, "verify_found", lambda label, q, a: True)
    monkeypatch.setattr(interview, "_next_slot", lambda *a, **k: None)
    out = interview.answer_interview(s.id, "대흥역에서 발견한 적이 있어요")
    assert calls == [False, True]
    by_label = {a["label"]: a["evidence"] for a in out.draft_attractions}
    assert by_label == {"망원시장": "caregiver_report", "대흥역": "previous_missing_found"}


def test_no_recheck_when_model_says_unknown(monkeypatch):
    """모른다는 답(모델 판정 unknown)은 재추출하지 않는다 — 호출 낭비 금지."""
    s = _ready("ev-noretry")
    calls = []

    def counter(slot, conv, recheck_places=False):
        calls.append(recheck_places)
        return {"answer_kind": "unknown", "fields": {}, "behavior_notes": [],
                "slot_filled": False, "attraction_points": []}

    monkeypatch.setattr(interview.midm, "extract_answer", counter)
    monkeypatch.setattr(interview, "_next_slot", lambda *a, **k: None)
    interview.answer_interview(s.id, "잘 모르겠어요")
    assert calls == [False]


def test_no_recheck_when_new_place_found(monkeypatch):
    s = _ready("ev-hit")
    calls = []

    def once(slot, conv, recheck_places=False):
        calls.append(recheck_places)
        return {"answer_kind": "informative", "fields": {}, "behavior_notes": [], "slot_filled": True,
                "attraction_points": [{"label": "대흥역 2번 출구", "evidence": "mention_only",
                                       "quote": "대흥역 2번 출구에서"}]}

    monkeypatch.setattr(interview.midm, "extract_answer", once)
    monkeypatch.setattr(interview, "_next_slot", lambda *a, **k: None)
    interview.answer_interview(s.id, "대흥역 2번 출구에서 발견한 적이 있어요")
    assert calls == [False]
