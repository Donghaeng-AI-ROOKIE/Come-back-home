"""발견 장소가 질문의 틀만으로 답해졌을 때도 끌림점이 된다 — 라이브 실측 2026-08-07.

  🤖 과거에 길을 잃거나 실종된 적이 있다면, 어디에서 발견됐고 …
  🙋 한번 있었고 서강대학교 정문에 앉아계셨어요
  → 노트('과거 실종·배회 행동 패턴')로만 남고 **끌림점으로는 사라졌다.**

보호자는 질문이 세운 틀을 답에서 되풀이하지 않는다. 예전에는 정규식이 질문의 '발견'
틀과 지명 접미어로 장소를 직접 만들었다. 이제는 장소가 비면 모델에게 다시 보게 하고
(재추출), 발견 여부는 직전 질문을 함께 준 좁은 확인 질문으로 모델이 판정한다.
"""

from app import storage
from app.phase0 import interview
from app.schemas.persona import InterviewSession, PersonaType

_FOUND_Q = ("과거에 길을 잃거나 실종된 적이 있다면, 어디에서 발견됐고 "
            "어떤 행동을 하고 있었는지 알려주세요.")
_ANSWER = "한번 있었고 서강대학교 정문에 앉아계셨어요"


def _session(sid: str) -> InterviewSession:
    s = InterviewSession(id=sid, guardian_name="보호자", persona_type=PersonaType.dementia,
                         draft_fields={"name": "김순자", "age": "82세", "home": "마포구 백범로 35"},
                         filled_keys=["identity", "home"], prev_target_key="dementia_wandering_pattern",
                         messages=[{"role": "assistant", "text": _FOUND_Q}])
    storage.interviews.save(s.id, s)
    return s


def test_notes_only_extraction_is_rechecked_and_place_survives(monkeypatch):
    """추출이 노트만 내도 재추출로 끌림점이 남고, 발견 확인에는 직전 질문이 함께 간다."""
    s = _session("ff-e2e")
    checked = []

    def extractor(slot, conv, recheck_places=False):
        out = {"answer_kind": "informative", "fields": {}, "slot_filled": True,
               "behavior_notes": ["서강대학교 정문에 앉아계셨다"], "attraction_points": []}
        if recheck_places:
            out["attraction_points"] = [{"label": "서강대학교", "area_text": "서강대학교",
                                         "place_type": "found_location",
                                         "evidence": "previous_missing_found",
                                         "quote": "서강대학교 정문에 앉아계셨어요"}]
        return out

    monkeypatch.setattr(interview.midm, "extract_answer", extractor)
    monkeypatch.setattr(interview.midm, "verify_found",
                        lambda label, q, a: checked.append((label, q, a)) or True)
    monkeypatch.setattr(interview, "_next_slot", lambda *a, **k: None)
    out = interview.answer_interview(s.id, _ANSWER)
    assert [(a["label"], a["evidence"]) for a in out.draft_attractions] == [
        ("서강대학교", "previous_missing_found")]
    assert checked == [("서강대학교", _FOUND_Q, _ANSWER)]


def test_none_answer_creates_nothing(monkeypatch):
    """'실종까지 가신 적은 없습니다'(모델 판정 none) — 재추출도 장소도 없다."""
    s = _session("ff-neg")
    calls = []

    def extractor(slot, conv, recheck_places=False):
        calls.append(recheck_places)
        return {"answer_kind": "none", "fields": {}, "slot_filled": True,
                "behavior_notes": [], "attraction_points": []}

    monkeypatch.setattr(interview.midm, "extract_answer", extractor)
    monkeypatch.setattr(interview, "_next_slot", lambda *a, **k: None)
    out = interview.answer_interview(s.id, "실종까지 가신 적은 없습니다")
    assert calls == [False]
    assert out.draft_attractions == []
    assert "dementia_wandering_pattern" in out.filled_keys


def test_model_extraction_wins(monkeypatch):
    """첫 추출이 이 답의 장소를 제대로 뽑았으면 재추출하지 않는다(중복 호출·중복 장소 방지)."""
    s = _session("ff-model")
    calls = []

    def extractor(slot, conv, recheck_places=False):
        calls.append(recheck_places)
        return {"answer_kind": "informative", "fields": {}, "slot_filled": True, "behavior_notes": [],
                "attraction_points": [{"label": "서강대학교", "evidence": "mention_only",
                                       "quote": "서강대학교 정문에 앉아계셨어요"}]}

    monkeypatch.setattr(interview.midm, "extract_answer", extractor)
    monkeypatch.setattr(interview, "_next_slot", lambda *a, **k: None)
    out = interview.answer_interview(s.id, _ANSWER)
    assert calls == [False]
    assert [a["label"] for a in out.draft_attractions] == ["서강대학교"]
