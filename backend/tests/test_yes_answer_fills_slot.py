"""여부를 묻는 질문에 "네"라고 답하면 그것도 답이다 — 라이브 실측 2026-08-07.

  🤖 어르신은 차도, 횡단보도, 물가, 계단처럼 위험한 장소를 …피할 수 있나요?
  🙋 네
  🤖 (8턴 뒤) 확인이 필요해서 다시 여쭤봅니다. …피할 수 있나요?
  🙋 답변 했잖아
  🤖 어르신께서 길을 건너실 때 신호를 잘 지키시는지 궁금합니다.

부정("아니요")은 '해당 없음'으로 슬롯을 닫는데 긍정은 아무것도 안 하던 비대칭.
그 결과 같은 슬롯이 세 번 나갔고, 항의 발화가 사실로 저장돼 요약에
"위험한 곳을 피하실 수 있는지: 답변 완료"가 찍혔다.

답변 유형(긍정만·이미 답함)은 Mi:dm 이 answer_kind 로 판정한다(예전: 단어 목록).
"""

from app import storage
from app.phase0 import interview
from app.phase0.slots import slot_by_key
from app.schemas.persona import InterviewSession, PersonaType

_HAZARD = slot_by_key("hazard_awareness_vulnerability")


def _session(**kw) -> InterviewSession:
    base = dict(id="ya1", guardian_name="보호자", persona_type=PersonaType.dementia,
                draft_fields={"name": "김순자", "age": "82세", "home": "마포구 백범로 35"},
                filled_keys=["identity", "home"])
    return InterviewSession(**{**base, **kw})


def _judged(kind):
    return lambda slot, conv: {"answer_kind": kind, "fields": {}, "attraction_points": [],
                               "behavior_notes": [], "slot_filled": False}


# ── 긍정도 답이다 ────────────────────────────────────────────────────

def test_bare_yes_fills_the_slot(monkeypatch):
    s = _session(id="ya-yes", prev_target_key=_HAZARD.key,
                 asked_counts={_HAZARD.key: 1})
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "extract_answer", _judged("yes_only"))
    out = interview.answer_interview(s.id, "네")
    assert _HAZARD.key in out.filled_keys
    assert _HAZARD.key not in out.asked_counts        # 반복 페널티 해제


def test_yes_is_not_stored_as_a_fact(monkeypatch):
    """충족은 시키되 "네" 한 글자를 사실로 남기지는 않는다 — 원문은 질문과 함께 slot_turns 에."""
    s = _session(id="ya-note", prev_target_key=_HAZARD.key,
                 messages=[{"role": "assistant", "text": "위험한 곳을 피하실 수 있나요?"}])
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "extract_answer", _judged("yes_only"))
    out = interview.answer_interview(s.id, "네")
    assert _HAZARD.key not in out.slot_notes
    assert out.draft_behaviors == []
    assert [{k: v for k, v in t.items() if k != "recorded_at"} for t in out.slot_turns] == [{"slot": _HAZARD.key, "question": "위험한 곳을 피하실 수 있나요?",
                               "answer": "네"}]


def test_profile_slots_are_not_filled_by_yes(monkeypatch):
    """이름·집은 "네"로 채울 수 없다 — 부정 처리와 같은 예외."""
    home = slot_by_key("home")
    s = _session(id="ya-home", prev_target_key="home", filled_keys=["identity"],
                 draft_fields={"name": "김순자", "age": "82세"})
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "extract_answer", _judged("yes_only"))
    out = interview.answer_interview(s.id, "네")
    assert home.key not in out.filled_keys


# ── 항의는 사실이 아니다 ─────────────────────────────────────────────

def test_protest_is_not_saved_and_stops_asking(monkeypatch):
    s = _session(id="ya-protest", prev_target_key=_HAZARD.key,
                 asked_counts={_HAZARD.key: 1})
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "extract_answer", _judged("already_answered"))
    out = interview.answer_interview(s.id, "답변 했잖아")
    assert _HAZARD.key not in out.slot_notes          # 사실로 저장 금지
    assert out.draft_behaviors == []
    assert _HAZARD.key in interview._exhausted_keys(out)   # 더 묻지 않는다


# ── 판정이 없으면 코드가 대신 분류하지 않는다 ─────────────────────────

def test_unjudged_answer_is_asked_again_not_classified(monkeypatch):
    """추출 호출이 실패해 answer_kind 가 없으면 채우지도 소진시키지도 않는다 — 같은 슬롯을
    한 번 더 묻고(재질문 예산), 원문은 질문과 함께 보존된다."""
    s = _session(id="ya-none", prev_target_key=_HAZARD.key, asked_counts={_HAZARD.key: 1})
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "extract_answer", _judged(None))
    out = interview.answer_interview(s.id, "네")
    assert _HAZARD.key not in out.filled_keys
    assert _HAZARD.key not in interview._exhausted_keys(out)
    assert out.draft_behaviors == []
    assert out.slot_turns[-1]["answer"] == "네"
