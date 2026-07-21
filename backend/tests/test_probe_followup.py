"""하위 항목(probes) 꼬리질문 보장 + 노트 유실 폴백 — 라이브 실측 2026-07-22.

사용자 인터뷰에서 드러난 두 증상:
① "복용하는 약 있다"고 답했는데 **거르면 어떤 증상인지**를 안 물었다. 씨앗 질문은
   clean_question 이 첫 물음표에서 자르므로("복용 중인 약이 있나요?") 하위 항목은
   꼬리질문이 유일한 통로인데, Mi:dm 이 얕은 답에도 slot_filled=true 를 내고
   충족된 슬롯은 _blocked_keys 로 후보에서 빠져 **probes 가 한 번도 안 쓰였다.**
② 같은 답변("혈압약을 저녁에만 드세요")에서 Mi:dm 이 behavior_notes 를 빈 배열로
   반환(실측 3/3) → 보호자가 말한 사실이 axis_evidence 에서 통째로 사라졌다.
"""

from app import storage
from app.phase0 import interview
from app.phase0.slots import slot_by_key
from app.schemas.persona import InterviewSession, PersonaType

_MED = slot_by_key("medication")


def _session(**kw) -> InterviewSession:
    base = dict(id="pb1", guardian_name="보호자", persona_type=PersonaType.dementia,
                draft_fields={"name": "송복남", "age": "82세", "home": "마포구 백범로 35"},
                filled_keys=["identity", "home"])
    return InterviewSession(**{**base, **kw})


# ── ① 얕은 충족이면 하위 항목을 파고든다 ────────────────────────────

def test_needs_probe_when_thin():
    s = _session()
    assert interview._needs_probe(s, _MED, "혈압약을 저녁에만 드세요")


def test_no_probe_twice_for_same_slot():
    s = _session(probed_keys=["medication"])
    assert not interview._needs_probe(s, _MED, "혈압약을 저녁에만 드세요")


def test_no_probe_when_enough_collected():
    s = _session(slot_notes={"medication": ["혈압약 저녁 복용", "거르면 어지러워함"]})
    assert not interview._needs_probe(s, _MED, "혈압약을 저녁에만 드세요")


def test_no_probe_for_ignorance_or_negative():
    s = _session()
    assert not interview._needs_probe(s, _MED, "잘 모르겠어요")
    assert not interview._needs_probe(s, _MED, "아니요")


def test_probe_question_actually_asked(monkeypatch):
    """얕게 충족된 턴 다음 질문이 같은 슬롯의 꼬리질문이어야 한다."""
    s = _session(id="pb-flow", prev_target_key="medication")
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "extract_answer",
                        lambda slot, conv: {"fields": {}, "attraction_points": [],
                                            "preferred_targets": [],
                                            "behavior_notes": ["혈압약을 저녁에 복용"],
                                            "slot_filled": True})
    monkeypatch.setattr(interview.midm, "phrase_question",
                        lambda *a, **k: "약을 거르시면 어떤 증상이 나타나시나요?")
    out = interview.answer_interview(s.id, "혈압약을 저녁에만 드세요")
    assert "거르" in out.messages[-1]["text"]
    assert out.prev_target_key == "medication"      # 같은 슬롯을 이어서 판다
    assert out.probed_keys == ["medication"]


def test_probe_falls_back_when_llm_repeats_question(monkeypatch):
    """LLM 이 원 질문을 되풀이하면 하위 항목을 직접 묻는다 (재탕 방지).

    라이브 실측(2026-07-22): "낯선 사람이 다가와 말을 걸면 어떻게 반응하시나요?" 직후
    "낯선 시민이 다가와 말을 걸면 어떤 행동을 보이시나요?" — 정확 일치가 아니라
    _dedupe_question 을 그대로 통과했다.
    """
    s = _session(id="pb-dup", prev_target_key="medication",
                 messages=[{"role": "assistant", "text": "복용 중인 약이 있나요?"}])
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "extract_answer",
                        lambda slot, conv: {"fields": {}, "attraction_points": [],
                                            "preferred_targets": [],
                                            "behavior_notes": ["혈압약 저녁 복용"],
                                            "slot_filled": True})
    monkeypatch.setattr(interview.midm, "phrase_question",
                        lambda *a, **k: "복용 중인 약이 있으신가요?")   # 사실상 같은 질문
    out = interview.answer_interview(s.id, "혈압약을 저녁에만 드세요")
    q = out.messages[-1]["text"]
    assert "복용 중인 약이 있" not in q
    assert "거르면 나타나는 증상" in q      # probes 각도를 직접 묻는다


def test_empty_answer_is_not_probed(monkeypatch):
    """빈손 답변은 파고들지 않는다 — 재질문 예산(asked_counts)이 담당한다."""
    s = _session(id="pb-empty", prev_target_key="medication")
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "extract_answer",
                        lambda slot, conv: {"fields": {}, "attraction_points": [],
                                            "preferred_targets": [], "behavior_notes": [],
                                            "slot_filled": False})
    monkeypatch.setattr(interview, "_next_slot", lambda *a, **k: None)
    out = interview.answer_interview(s.id, "글쎄요 뭐라고 해야 하나")
    assert out.probed_keys == []


# ── ② 노트 유실 폴백 ─────────────────────────────────────────────────

def test_utterance_saved_when_model_returns_no_notes():
    """Mi:dm 이 노트를 안 내면 원발화를 근거로 남긴다 — 대화했는데 저장 안 되는 상태 방지."""
    s = _session()
    interview._apply_extraction(s, _MED, {"attraction_points": [], "behavior_notes": [],
                                          "slot_filled": True},
                                utterance="혈압약을 저녁에만 드세요")
    assert s.slot_notes["medication"] == ["혈압약을 저녁에만 드세요"]
    assert s.draft_behaviors == ["복약·건강 상태: 혈압약을 저녁에만 드세요"]


def test_no_fallback_when_model_gave_notes():
    """모델이 낸 노트가 중복 필터에 걸린 경우는 폴백하지 않는다(이중 저장 방지)."""
    s = _session(slot_notes={"lost_behavior": ["가만히 앉아 있는 편"]},
                 draft_behaviors=["길 잃었을 때 행동: 가만히 앉아 있는 편"])
    interview._apply_extraction(s, _MED, {"attraction_points": [],
                                          "behavior_notes": ["가만히 앉아 있는 편"],
                                          "slot_filled": True},
                                utterance="가만히 앉아계세요")
    assert "medication" not in s.slot_notes


def test_no_fallback_for_ignorance():
    s = _session()
    interview._apply_extraction(s, _MED, {"attraction_points": [], "behavior_notes": [],
                                          "slot_filled": True},
                                utterance="잘 모르겠어요")
    assert "medication" not in s.slot_notes
