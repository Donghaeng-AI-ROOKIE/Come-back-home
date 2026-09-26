"""보호자 답은 판정과 무관하게 질문과 함께 보존되고, K 는 그 원문을 읽는다.

라이브 흐름에서 '못 알아'·'기억이 안'이 들어간 답이나 Mi:dm 이 빈손으로 낸 답은
slot_quotes 에 남지 않아 K 가 한 번도 보지 못했다(2026-09-26 코드 대조).
"""

from app import storage
from app.llm import initial_behavior
from app.phase0 import interview
from app.phase0.slots import slot_by_key
from app.schemas.common import GeoPoint
from app.schemas.persona import InterviewSession, Persona, PersonaType

_LOST = slot_by_key("lost_behavior")
_EMPTY = {"fields": {}, "attraction_points": [], "behavior_notes": [], "slot_filled": False}


def _session(**kw) -> InterviewSession:
    base = {"id": "turns", "guardian_name": "보호자", "persona_type": PersonaType.dementia,
            "draft_fields": {"name": "김순자", "age": "82세", "home": "마포구 백범로 35"},
            "filled_keys": ["identity", "home"],
            "messages": [{"role": "assistant", "text": "길을 잃으시면 어떻게 하세요?"}]}
    return InterviewSession(**{**base, **kw})


def test_every_answer_is_kept_with_its_question(monkeypatch):
    s = _session(id="turns-lost", prev_target_key=_LOST.key)
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "extract_answer", lambda slot, conv: dict(_EMPTY))
    answer = "집을 못 알아보세요. 기억이 안 나시는지 주소도 못 말씀하세요."
    out = interview.answer_interview(s.id, answer)
    assert out.slot_turns == [{"slot": _LOST.key, "question": "길을 잃으시면 어떻게 하세요?", "answer": answer}]


def test_profile_answers_are_not_behavior_turns(monkeypatch):
    s = _session(id="turns-home", prev_target_key="home", filled_keys=["identity"],
                 draft_fields={"name": "김순자", "age": "82세"},
                 messages=[{"role": "assistant", "text": "지금 어디에 사세요?"}])
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "extract_answer", lambda slot, conv: dict(_EMPTY))
    out = interview.answer_interview(s.id, "마포구 백범로 35예요")
    assert out.slot_turns == []


def test_k_reads_question_answer_pairs_instead_of_bare_quotes():
    p = Persona(id="turn-person", type="dementia", name="비공개", age=80, home=GeoPoint(lat=37.6, lng=127.0),
                onboarding_quotes={"lost_behavior": ["네"]},
                onboarding_turns=[{"slot": "lost_behavior", "question": "길을 잃으시면 그 자리에서 기다리시나요?",
                                   "answer": "네"}])
    notes = initial_behavior.evidence_notes(initial_behavior.build_payload(p, None, [], None))
    assert [n["text"] for n in notes] == ["질문: 길을 잃으시면 그 자리에서 기다리시나요?\n답변: 네"]
    assert notes[0]["provenance"] == "guardian_original"
