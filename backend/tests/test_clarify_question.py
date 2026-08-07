"""질문을 못 알아들었을 때 쉬운 말로 풀어 다시 묻기 — 라이브 실측 2026-08-07.

  🤖 구체적 목격 사례에 대해서도 알려주세요.        ← probes 원문(모델용 내부 메모)
  🙋 구체적 목격 사례가 무슨 의민지 모르겠어요
  🤖 어르신이 불안하거나 초조해지거나 …             ← 설명 없이 다음 슬롯으로

보호자의 물음이 통째로 무시됐다. '답을 모른다'(_is_pure_ignorance, 슬롯 소진)와
'질문을 못 알아들었다'는 다른 사건이다 — 후자는 질문이 잘못 나간 것이라 풀어서
한 번 더 물어야 한다.
"""

from app import storage
from app.phase0 import interview, prompts
from app.phase0.slots import slot_by_key
from app.schemas.persona import InterviewSession, PersonaType

_LOST = slot_by_key("lost_behavior")


def _session(**kw) -> InterviewSession:
    base = dict(id="cl1", guardian_name="보호자", persona_type=PersonaType.dementia,
                draft_fields={"name": "김순자", "age": "82세", "home": "마포구 백범로 35"},
                filled_keys=["identity", "home"])
    return InterviewSession(**{**base, **kw})


# ── 감지: '못 알아들음' vs '답을 모름' ────────────────────────────────

def test_detects_unclear_question():
    for t in ["구체적 목격 사례가 무슨 의민지 모르겠어요",
              "그게 무슨 말이에요?",
              "질문이 어려워요",
              "이해가 안 돼요",
              "뭘 물어보시는 건가요"]:
        assert interview._is_question_unclear(t), t


def test_plain_ignorance_is_not_unclear():
    """'답을 모른다'는 소진 경로 그대로 — 여기로 새면 무한 되묻기가 된다."""
    for t in ["잘 모르겠어요", "모르겠어요", "몰라요"]:
        assert not interview._is_question_unclear(t), t
        assert interview._is_pure_ignorance(t), t


def test_negative_answer_is_not_unclear():
    for t in ["딱히 없어요", "아니요", "없어요"]:
        assert not interview._is_question_unclear(t), t


# ── 흐름: 되묻되 같은 질문을 되풀이하지 않는다 ────────────────────────

def _asked(out) -> str:
    return out.messages[-1]["text"]


def test_clarify_rephrases_instead_of_moving_on(monkeypatch):
    """못 알아들었다고 하면 다음 슬롯으로 넘어가지 않고 풀어서 다시 묻는다."""
    confusing = "구체적 목격 사례에 대해서도 알려주세요."
    s = _session(id="cl-flow", prev_target_key="lost_behavior",
                 filled_keys=["identity", "home", "lost_behavior"],
                 probed_keys=["lost_behavior"],
                 messages=[{"role": "assistant", "text": confusing}])
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(
        interview.midm, "clarify_question",
        lambda ptype, slot, q, u: "실제로 길을 잃으셨던 때가 궁금해요. 그때 어디 계셨는지 기억나시나요?")

    out = interview.answer_interview(s.id, "구체적 목격 사례가 무슨 의민지 모르겠어요")
    assert out.prev_target_key == "lost_behavior"      # 같은 슬롯에 머문다
    assert out.clarified_keys == ["lost_behavior"]
    assert _asked(out) != confusing                    # 재낭독 금지
    assert "기억나시나요" in _asked(out)


def test_clarify_does_not_spend_reask_budget(monkeypatch):
    """되묻기는 재질문 예산과 별개 — 답을 못 받은 게 아니라 질문이 잘못 나갔다."""
    s = _session(id="cl-budget", prev_target_key="lost_behavior",
                 asked_counts={"lost_behavior": 1},
                 messages=[{"role": "assistant", "text": "구체적 목격 사례에 대해서도 알려주세요."}])
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "clarify_question",
                        lambda *a, **k: "그때 어디 계셨는지 기억나시나요?")

    out = interview.answer_interview(s.id, "그게 무슨 말이에요?")
    assert out.asked_counts.get("lost_behavior") == 1   # 안 깎인다
    assert "lost_behavior" not in interview._exhausted_keys(out)


def test_clarify_only_once_per_slot(monkeypatch):
    """두 번째로 못 알아들으면 기존 예산 경로로 넘긴다(무한 되묻기 방지)."""
    s = _session(id="cl-once", prev_target_key="lost_behavior",
                 clarified_keys=["lost_behavior"],
                 messages=[{"role": "assistant", "text": "구체적 목격 사례에 대해서도 알려주세요."}])
    storage.interviews.save(s.id, s)
    called: list = []
    monkeypatch.setattr(interview.midm, "clarify_question",
                        lambda *a, **k: called.append(1) or "다시 묻기")

    out = interview.answer_interview(s.id, "그게 무슨 말이에요?")
    assert called == []                                 # 되묻기 재사용 금지
    assert out.clarified_keys == ["lost_behavior"]


def test_clarify_falls_back_without_llm(monkeypatch):
    """LLM 이 빈손이어도 **같은 질문 되풀이는 안 나간다** — 예시 기반 결정론 폴백."""
    confusing = "구체적 목격 사례에 대해서도 알려주세요."
    s = _session(id="cl-fb", prev_target_key="lost_behavior",
                 messages=[{"role": "assistant", "text": confusing}])
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "clarify_question", lambda *a, **k: "")

    out = interview.answer_interview(s.id, "그게 무슨 말이에요?")
    q = _asked(out)
    assert q != confusing
    assert _LOST.guardian_label in q                     # 무엇을 묻는지 보호자 말로
    assert _LOST.answer_example.split(".")[0] in q       # 구체적인 예시 제시


def test_clean_clarify_keeps_quoted_question_marks():
    """예시 안 인용 물음표에서 잘리면 안 된다 — 실 Mi:dm 실측 2회 중 1회.

    clean_question(첫 물음표에서 절단)을 쓰면 "…차를 세워두고 '어디 가세요?" 로
    중동무이가 됐다. 되묻기는 마지막 물음표까지 살린다.
    """
    raw = ("낯선 사람이 집까지 태워준다고 하면 따라가실지 궁금해요. "
           "예를 들어 모르는 사람이 '어디 가세요?'라고 물으면 어떻게 하시나요?")
    assert prompts.clean_clarify(raw) == raw
    assert prompts.clean_question(raw) != raw     # 기존 정리기는 자른다


def test_clean_clarify_accepts_request_without_question_mark():
    """물음표 없이 끝나는 요청형도 받는다 — 실 Mi:dm 출력 6건 중 3건이 이 형태."""
    raw = ("길을 잃어버렸을 때 어떻게 행동하시는지 알고 싶어서요. "
           "예를 들어 그 자리에 가만히 계셨는지, 계속 걸어다니셨는지 궁금해요.")
    assert prompts.clean_clarify(raw) == raw


def test_clean_clarify_rejects_non_question():
    assert prompts.clean_clarify("설명만 하고 끝냅니다.") == ""
    assert prompts.clean_clarify("   ") == ""


def test_clarify_refuses_to_echo_the_same_question(monkeypatch):
    """LLM 이 같은 질문을 그대로 돌려주면 폴백으로 돌린다."""
    confusing = "구체적 목격 사례에 대해서도 알려주세요."
    s = _session(id="cl-echo", prev_target_key="lost_behavior",
                 messages=[{"role": "assistant", "text": confusing}])
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "clarify_question", lambda *a, **k: confusing)

    out = interview.answer_interview(s.id, "그게 무슨 말이에요?")
    assert _asked(out) != confusing
