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
from app.phase0 import interview, prompts
from app.phase0.slots import SLOTS, slot_by_key
from app.schemas.persona import InterviewSession, PersonaType

_MED = slot_by_key("medication")


def test_probe_stays_on_for_slots_that_need_it():
    """파고들기는 켜져 있어야 한다 — 씨앗 질문이 잘려 못 묻는 하위 항목의 유일한 통로.

    복약이 대표 사례: clean_question 이 "복용 중인 약이 있나요?" 에서 잘라
    '거르면 어떤 증상'을 못 묻는다(PR #64가 파고들기를 넣은 이유).
    """
    assert interview.GUARDS["probe"] is True
    assert _MED.probe_followup is True


def test_lost_behavior_opts_out_of_followup():
    """길 잃었을 때 행동만 꼬리질문을 뺀다 (2026-08-07 사용자 결정).

    답 한 마디에 우세 경향이 그대로 드러나서("그 자리에 가만히 서계세요" = 머무름)
    남은 각도가 '구체적 목격 사례'뿐이고, 그 꼬리질문이 방금 한 말을 되묻는 꼴이었다.
    """
    slot = slot_by_key("lost_behavior")
    assert slot.probe_followup is False
    assert slot.probes                      # probes 자체는 남긴다(embed_text·문장화용)
    s = InterviewSession(id="lb-off", guardian_name="보호자",
                         persona_type=PersonaType.dementia)
    assert not interview._needs_probe(s, slot, "그 자리에 가만히 서계세요")


def test_only_lost_behavior_opts_out():
    """옵트아웃은 이 슬롯 하나뿐 — 나머지는 종전대로 파고든다."""
    off = [s.key for s in SLOTS if not s.probe_followup]
    assert off == ["lost_behavior"]


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
                                            "behavior_notes": ["혈압약을 저녁에 복용"],
                                            "slot_filled": True})
    monkeypatch.setattr(interview.midm, "probe_gap",
                        lambda ptype, slot, evidence: ["거르면 나타나는 증상"])
    monkeypatch.setattr(interview.midm, "probe_question",
                        lambda *a, **k: "약을 거르시면 어떤 증상이 나타나시나요?")
    # 이 테스트는 꼬리질문 흐름을 검증하는 것이지 grounding 판정이 아니다 —
    # 임베더 교체로 이 특정 문구의 절대 유사도가 임계를 살짝 밑돌 수 있어(관련
    # 슬롯 중엔 압도적으로 가장 가깝지만) 가드는 통과시킨다.
    monkeypatch.setattr(interview.safety, "guard_question",
                        lambda q, slot, emb, bank=None: (q, False))
    out = interview.answer_interview(s.id, "혈압약을 저녁에만 드세요")
    assert "거르" in out.messages[-1]["text"]
    assert out.prev_target_key == "medication"      # 같은 슬롯을 이어서 판다
    assert out.probed_keys == ["medication"]


def test_parse_probe_gap_requires_quote_for_answered():
    """근거 인용 없는 '답함' 은 인정하지 않는다 — 모델이 목록만 베끼는 것을 막는다."""
    slot = slot_by_key("lost_behavior")            # probes 2개
    labels = prompts._probe_labels(slot)
    quoted = ('{"items":[{"i":1,"answered":true,"quote":"그 자리에 서서 가만히 계세요"},'
              '{"i":2,"answered":false,"quote":""}]}')
    assert prompts.parse_probe_gap(quoted, slot) == [labels[1]]
    # 인용이 비었으면 '답함' 을 되돌린다
    bare = '{"items":[{"i":1,"answered":true,"quote":""},{"i":2,"answered":true,"quote":""}]}'
    assert prompts.parse_probe_gap(bare, slot) == labels


def test_parse_probe_gap_failure_is_silence():
    """파싱 실패는 '남은 게 없음' — 판정 불능일 때 아무 각도나 묻지 않는다."""
    slot = slot_by_key("lost_behavior")
    assert prompts.parse_probe_gap("", slot) == []
    assert prompts.parse_probe_gap("설명만 돌려줌", slot) == []
    assert prompts.parse_probe_gap('{"items":[{"i":99,"answered":true,"quote":"x"}]}',
                                   slot) == prompts._probe_labels(slot)


def test_probe_sees_raw_utterance_not_only_notes(monkeypatch):
    """각도 판정 근거에 **원발화**가 들어가야 한다.

    라이브 실측(2026-08-07): "네 신호도 잘 지키시고 위험 감지 능력은 좋아요"에
    Mi:dm 이 노트를 '위험 감지 능력은 좋아요'로만 남겨(신호 부분 소실), 파고들기가
    방금 답한 신호를 또 물었다. 노트만 보면 보호자가 한 말을 놓친다.
    """
    slot = slot_by_key("hazard_awareness_vulnerability")
    s = _session(slot_notes={slot.key: ["위험 감지 능력은 좋아요"]},
                 slot_quotes={slot.key: ["네 신호도 잘 지키시고 위험 감지 능력은 좋아요"]})
    evidence = interview._slot_evidence(s, slot)
    assert "위험 감지 능력은 좋아요" in evidence
    assert any("신호" in e for e in evidence)       # 원발화가 근거에 포함


def test_probe_skipped_when_nothing_left(monkeypatch):
    """모델이 '남은 각도 없음'으로 판정하면 파고들지 않고 넘어간다.

    라이브 실측(2026-08-07): "네 신호도 잘 지키시고…"로 이미 답했는데 파고들기가
    같은 각도를 또 물었다. 어휘가 안 겹치면 코드의 토큰 비교로는 영영 못 잡는다 —
    판정은 모델이 한다(probe_gap).
    """
    # always_probe_first 가 아닌 슬롯이어야 판정 경로를 탄다(복약은 판정을 건너뛴다).
    slot = slot_by_key("hazard_awareness_vulnerability")
    assert not slot.always_probe_first
    s = _session(id="pb-none", prev_target_key=slot.key)
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "extract_answer",
                        lambda slot, conv: {"fields": {}, "attraction_points": [],
                                            "behavior_notes": ["신호를 잘 지킴"],
                                            "slot_filled": True})
    # 모델 판정: 확인 목록이 전부 답해졌다
    monkeypatch.setattr(interview.midm, "probe_gap", lambda *a, **k: [])
    called: list = []
    monkeypatch.setattr(interview.midm, "probe_question",
                        lambda *a, **k: called.append(1) or "물어보면 안 되는 질문")

    out = interview.answer_interview(s.id, "네 신호도 잘 지키시고 위험 감지 능력도 있으세요")
    assert called == []                              # 문장화까지 가지 않는다
    assert out.prev_target_key != slot.key           # 다음 슬롯으로 넘어간다
    assert out.probed_keys == [slot.key]             # 재호출 방지로 소진 표시는 남긴다


def test_medication_always_asks_the_symptom_angle(monkeypatch):
    """복약은 '거르면 나타나는 증상'을 판정 없이 반드시 한 번 묻는다.

    실측(2026-08-07, 3/3): 판정기가 "치매약을 아침저녁으로 드시는데 가끔 거르고
    나가십니다"를 증상까지 답한 것으로 넘겨, 꼬리질문이 야간·추위로 건너뛰었다.
    그 둘은 이 슬롯에 묶여 있을 뿐 약과 무관해 보여 "복약 꼬리질문이 없다"로 읽힌다.
    """
    assert _MED.always_probe_first is True
    s = _session(id="pb-med-first", prev_target_key="medication")
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "extract_answer",
                        lambda slot, conv: {"fields": {}, "attraction_points": [],
                                            "behavior_notes": ["치매약 아침저녁 복용"],
                                            "slot_filled": True})
    # 판정기가 '전부 답했다'고 해도 무시해야 한다
    gap_calls: list = []
    monkeypatch.setattr(interview.midm, "probe_gap",
                        lambda *a, **k: gap_calls.append(1) or [])
    seen: list = []

    def _phrase(ptype, slot, angle, evidence):
        seen.append(angle)
        return "약을 거르시면 평소와 다른 모습을 보이시나요?"

    monkeypatch.setattr(interview.midm, "probe_question", _phrase)

    out = interview.answer_interview(s.id, "치매약을 아침저녁으로 드시는데 가끔 거르고 나가십니다")
    assert seen == ["거르면 나타나는 증상"]           # 첫 각도를 그대로 물었다
    assert gap_calls == []                            # 판정 호출 자체를 안 한다
    assert "거르시면" in out.messages[-1]["text"]
    assert out.prev_target_key == "medication"


def test_only_medication_skips_the_gap_judge():
    """판정 우회는 복약 하나뿐 — 나머지는 종전대로 모델이 각도를 고른다."""
    assert [s.key for s in SLOTS if s.always_probe_first] == ["medication"]


def test_probes_are_never_emitted_verbatim(monkeypatch):
    """probes 원문은 모델용 내부 메모 — 어떤 폴백 경로로도 보호자에게 안 나간다."""
    s = _session(id="pb-jargon", prev_target_key="medication")
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "extract_answer",
                        lambda slot, conv: {"fields": {}, "attraction_points": [],
                                            "behavior_notes": ["치매약 아침저녁 복용"],
                                            "slot_filled": True})
    # 각도는 남았는데 문장화가 빈손 — 예전엔 여기서 probes 원문으로 때웠다.
    monkeypatch.setattr(interview.midm, "probe_gap",
                        lambda *a, **k: ["거르면 나타나는 증상"])
    monkeypatch.setattr(interview.midm, "probe_question", lambda *a, **k: "")

    out = interview.answer_interview(s.id, "치매약을 아침저녁으로 드세요")
    said = " ".join(m["text"] for m in out.messages if m["role"] == "assistant")
    for slot in (slot_by_key("lost_behavior"), _MED):
        for angle in slot.probes:
            assert angle not in said, angle


def test_probe_gives_up_when_llm_repeats_question(monkeypatch):
    """LLM 이 원 질문을 되풀이하면 파고들기를 **접는다**(재탕 방지).

    라이브 실측(2026-07-22): "낯선 사람이 다가와 말을 걸면 어떻게 반응하시나요?" 직후
    "낯선 시민이 다가와 말을 걸면 어떤 행동을 보이시나요?" — 정확 일치가 아니라
    _dedupe_question 을 그대로 통과했다. 예전에는 probes 원문을 직접 물어 때웠는데,
    그게 내부 용어 유출의 원인이었다(2026-08-07). 이제는 그냥 넘어간다.

    이력은 **라이브와 같은 모양**이어야 한다 — 씨앗이 맨몸으로 나가는 일은 없고
    (_seed_with_example 이 "(예: …)" 를 붙인다) 재질문에는 프리픽스가 붙는다.
    맨 씨앗으로 픽스처를 두면 자카드가 부풀려지지 않아 구멍이 안 보인다.
    """
    s = _session(id="pb-dup", prev_target_key="medication",
                 messages=[{"role": "assistant",
                            "text": interview._seed_with_example(_MED)}])
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "extract_answer",
                        lambda slot, conv: {"fields": {}, "attraction_points": [],
                                            "behavior_notes": ["혈압약 저녁 복용"],
                                            "slot_filled": True})
    monkeypatch.setattr(interview.midm, "probe_gap",
                        lambda *a, **k: ["거르면 나타나는 증상"])
    monkeypatch.setattr(interview.midm, "probe_question",
                        lambda *a, **k: "복용 중인 약이 있으신가요?")   # 사실상 같은 질문
    monkeypatch.setattr(interview.safety, "guard_question",
                        lambda q, slot, emb, bank=None: (q, False))
    out = interview.answer_interview(s.id, "혈압약을 저녁에만 드세요")
    q = out.messages[-1]["text"]
    assert "복용 중인 약이 있" not in q
    assert "거르면 나타나는 증상" not in q          # probes 원문도 안 나간다


def test_probe_after_reask_is_not_the_seed_again(monkeypatch):
    """재질문을 거친 뒤의 파고들기가 '프리픽스 + 씨앗'이 되면 안 된다.

    라이브 실측(2026-08-07, 팀원 캡쳐본): 복약 질문이 세 번 나갔다.
      ① "복용 중인 약이 있나요? (예: …)"          — 씨앗+예시
      ② "확인이 필요해서 다시 여쭤봅니다. …"        — 재질문(추출 빈손)
      ③ "죄송해요, 한 번만 더 여쭐게요. …"          — **파고들기가 씨앗 재탕**
    ③에서 자카드가 ①·② 대비 0.400·0.333 으로 임계(0.5) 밑이라 각도 폴백이 안 걸렸고
    (껍데기가 분모를 부풀림), _dedupe_question 은 프리픽스만 갈아 끼웠다.

    LLM 이 씨앗을 되뱉는 상황이라 파고들 각도를 못 얻는다 → 파고들기를 접고
    다음 슬롯으로 넘어간다. probes 원문으로 때우던 예전 동작은 폐기(내부 용어 유출).
    """
    seed = "복용 중인 약이 있나요?"
    s = _session(id="pb-reask", prev_target_key="medication",
                 asked_counts={"medication": 2},
                 messages=[
                     {"role": "assistant", "text": interview._seed_with_example(_MED)},
                     {"role": "user", "text": "치매약을 아침저녁으로 드시는데 가끔 거르고 나가십니다"},
                     {"role": "assistant", "text": interview._REASK_PREFIXES[1] + seed},
                 ])
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "extract_answer",
                        lambda slot, conv: {"fields": {}, "attraction_points": [],
                                            "behavior_notes": ["치매약 아침저녁 복용"],
                                            "slot_filled": True})
    # 모델이 씨앗을 그대로 되뱉는 상황(실제 경로 재현)
    monkeypatch.setattr(interview.midm, "probe_gap",
                        lambda *a, **k: ["거르면 나타나는 증상"])
    monkeypatch.setattr(interview.midm, "probe_question", lambda *a, **k: seed)
    monkeypatch.setattr(interview.safety, "guard_question",
                        lambda q, slot, emb, bank=None: (q, False))
    out = interview.answer_interview(s.id, "치매약을 복용해요.")
    q = out.messages[-1]["text"]
    assert "복용 중인 약이 있" not in q
    assert not any(q.startswith(p) for p in interview._REASK_PREFIXES)
    assert "거르면 나타나는 증상" not in q          # probes 원문도 안 나간다


def test_bare_question_strips_wrappers():
    """비교용 알맹이 추출 — 예시·재질문 프리픽스를 벗긴다."""
    seed = "복용 중인 약이 있나요?"
    assert interview._bare_question(interview._seed_with_example(_MED)) == seed
    assert interview._bare_question(interview._REASK_PREFIXES[0] + seed) == seed
    assert interview._bare_question(interview._REASK_PREFIXES[1] + seed) == seed
    assert interview._bare_question(seed) == seed


def test_empty_answer_is_not_probed(monkeypatch):
    """빈손 답변은 파고들지 않는다 — 재질문 예산(asked_counts)이 담당한다."""
    s = _session(id="pb-empty", prev_target_key="medication")
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "extract_answer",
                        lambda slot, conv: {"fields": {}, "attraction_points": [],
                                            "behavior_notes": [],
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
