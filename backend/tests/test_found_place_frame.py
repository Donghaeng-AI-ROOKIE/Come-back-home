"""발견 장소가 질문의 틀만으로 답해졌을 때도 끌림점이 된다 — 라이브 실측 2026-08-07.

  🤖 과거에 길을 잃거나 실종된 적이 있다면, 어디에서 발견됐고 …
  🙋 한번 있었고 서강대학교 정문에 앉아계셨어요
  → 노트('과거 실종·배회 행동 패턴')로만 남고 **끌림점으로는 사라졌다.**

보호자는 질문이 세운 틀을 답에서 되풀이하지 않는다. 발화에 '발견'이 없다고
발견지가 아닌 게 아니다.
"""

from app import storage
from app.phase0 import interview
from app.phase0.slots import slot_by_key
from app.schemas.persona import InterviewSession, PersonaType

_WANDER = slot_by_key("dementia_wandering_pattern")
_FOUND_Q = ("과거에 길을 잃거나 실종된 적이 있다면, 어디에서 발견됐고 "
            "어떤 행동을 하고 있었는지 알려주세요.")


def _session(**kw) -> InterviewSession:
    base = dict(id="ff1", guardian_name="보호자", persona_type=PersonaType.dementia,
                draft_fields={"name": "김순자", "age": "82세", "home": "마포구 백범로 35"},
                messages=[{"role": "assistant", "text": _FOUND_Q}])
    return InterviewSession(**{**base, **kw})


def _run(session, utterance, extracted=None):
    interview._ensure_found_place(
        session, _WANDER,
        extracted if extracted is not None else {"attraction_points": []},
        utterance)
    return session.draft_attractions


# ── 틀 판정 ──────────────────────────────────────────────────────────

def test_found_frame_from_question():
    s = _session()
    assert interview._found_frame(s, "한번 있었고 서강대학교 정문에 앉아계셨어요")


def test_found_frame_rejects_negation():
    """부정이 섞이면 쓰지 않는다 — 이 틀은 최상위 등급(0.9)으로 이어진다."""
    s = _session()
    assert not interview._found_frame(s, "길 잃으신 적은 없어요")
    assert not interview._found_frame(s, "실종까지 가신 적은 없습니다")
    assert not interview._found_frame(s, "잘 모르겠어요")


def test_found_frame_needs_the_question():
    """다른 질문 뒤라면 틀이 없다 — 아무 장소나 발견지로 승격되면 안 된다."""
    s = _session(messages=[{"role": "assistant", "text": "혼자 나가실 때 주로 어디에 가시나요?"}])
    assert not interview._found_frame(s, "마포아트센터에 자주 가세요")


# ── 흐름 ─────────────────────────────────────────────────────────────

def test_place_saved_without_the_word_found():
    """'발견'이라는 낱말이 없어도 지명을 끌림점으로 만든다."""
    s = _session(id="ff-save")
    out = _run(s, "한번 있었고 서강대학교 정문에 앉아계셨어요")
    assert [a["label"] for a in out] == ["서강대학교"]
    assert out[0]["evidence"] == "previous_missing_found"
    assert out[0]["place_type"] == "found_location"


def test_negative_answer_creates_nothing():
    s = _session(id="ff-neg")
    assert _run(s, "실종까지 가신 적은 없습니다") == []


def test_model_extraction_wins():
    """모델이 이 발화의 장소를 제대로 뽑았으면 백스톱은 안 돈다(중복 방지)."""
    s = _session(id="ff-model")
    out = _run(s, "한번 있었고 서강대학교 정문에 앉아계셨어요",
               extracted={"attraction_points": [{"label": "서강대학교"}]})
    assert out == []


def test_end_to_end_place_survives(monkeypatch):
    """추출이 노트만 내도 요약에 쓰일 끌림점이 남는다."""
    s = _session(id="ff-e2e", prev_target_key="dementia_wandering_pattern",
                 filled_keys=["identity", "home"])
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(
        interview.midm, "extract_answer",
        lambda slot, conv: {"fields": {}, "attraction_points": [],
                            "behavior_notes": ["서강대학교 정문에 앉아계셨다"],
                            "slot_filled": True})
    out = interview.answer_interview(s.id, "한번 있었고 서강대학교 정문에 앉아계셨어요")
    assert any(a["label"] == "서강대학교" for a in out.draft_attractions)
