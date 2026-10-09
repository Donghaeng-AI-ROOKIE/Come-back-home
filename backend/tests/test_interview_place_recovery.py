"""주소 없는 끌림점 되묻기 + 추출 입력의 '추출 대상' 분리 — 라이브 실측 2026-07-21.

실측 사고 두 건:
① 보호자가 "예전에 살던 집"을 말했지만 동네를 물어본 적이 없어 area_text 가 비었고,
   지오코딩 실패 → finalize 가 미해결을 버려 **끌림점이 통째로 사라짐**.
② "원평중학교 앞에서 발견됐어요"(과거 발견지 = 가장 강한 근거)가 추출되지 않음.
   원인은 추출 프롬프트가 대화를 통짜로 주고 "마지막 발화를 대상으로" 라고만 해서,
   대화가 길어지면 모델이 이전 턴 장소들을 재추출한 것. Mi:dm 실호출 A/B 0/3 → 3/3.
"""

from app.phase0 import interview, prompts
from app.phase0.slots import slot_by_key
from app.schemas.persona import InterviewSession, PersonaType


def _session(**kw) -> InterviewSession:
    base = dict(id="pr1", guardian_name="보호자", persona_type=PersonaType.dementia)
    return InterviewSession(**{**base, **kw})


# ── ① 주소 없는 끌림점 탐지·되묻기·확정 ──────────────────────────────

def test_arealess_attraction_detected():
    # 자리표시("언급 없음")는 추출 단계에서 원문 대조로 이미 비워진다(test_interview_correction)
    s = _session(draft_attractions=[
        {"label": "원마루 공원", "area_text": "분평동"},
        {"label": "예전에 살던 집", "area_text": "  "},
        {"label": "옛 직장", "area_text": ""},
    ])
    assert [a["label"] for a in interview._arealess_attractions(s)] == ["예전에 살던 집", "옛 직장"]


def test_pending_area_answer_fills_area_text(monkeypatch):
    """되묻기 답에서 지역 표현은 모델이 고르고, 코드는 답에 그대로 있는지만 본다."""
    monkeypatch.setattr(interview.midm, "extract_area", lambda label, answer: "청주시 서원구 산남동")
    s = _session(draft_attractions=[{"label": "예전에 살던 집", "area_text": ""}],
                 pending_area_label="예전에 살던 집")
    interview._resolve_pending_area(s, "청주시 서원구 산남동이요")
    # 조사를 뗀 값이 그대로 지오코딩 질의가 된다
    assert s.draft_attractions[0]["area_text"] == "청주시 서원구 산남동"
    assert s.pending_area_label is None


def test_pending_area_ignorance_does_not_loop(monkeypatch):
    """모른다는 답(모델이 지역 없음)이면 값을 만들지 않고 되묻기를 끝낸다 — 같은 질문 반복 금지."""
    monkeypatch.setattr(interview.midm, "extract_area", lambda label, answer: None)
    s = _session(draft_attractions=[{"label": "예전에 살던 집", "area_text": ""}],
                 pending_area_label="예전에 살던 집")
    interview._resolve_pending_area(s, "모르겠어요")
    assert s.draft_attractions[0]["area_text"] == ""
    assert s.pending_area_label is None


def test_pending_area_rejects_area_not_in_answer(monkeypatch):
    """모델이 답에 없는 지역을 내면(지어낸 값) 받지 않고 기록한다."""
    monkeypatch.setattr(interview.midm, "extract_area", lambda label, answer: "청주시 서원구 분평동")
    s = _session(draft_attractions=[{"label": "예전에 살던 집", "area_text": ""}],
                 pending_area_label="예전에 살던 집")
    interview._resolve_pending_area(s, "그냥 아주 옛날에 살던 곳이라 잘 기억이 안 나요")
    assert s.draft_attractions[0]["area_text"] == ""
    assert s.extraction_audit == [{"event": "area_not_in_answer", "label": "예전에 살던 집",
                                   "area": "청주시 서원구 분평동"}]


def test_pending_area_takes_place_name_from_sentence(monkeypatch):
    """문장으로 답해도 모델이 고른 지명만 쓴다 — 라이브 실측(2026-08-07) '예전 가게' 소실."""
    seen = []
    monkeypatch.setattr(interview.midm, "extract_area",
                        lambda label, answer: seen.append((label, answer)) or "망원시장")
    s = _session(draft_attractions=[{"label": "예전 가게", "area_text": ""}],
                 pending_area_label="예전 가게")
    interview._resolve_pending_area(s, "망원시장에서 생선가게를 하셨어요")
    assert s.draft_attractions[0]["area_text"] == "망원시장"
    assert seen == [("예전 가게", "망원시장에서 생선가게를 하셨어요")]


def test_past_place_rechecked_when_model_misses_it(monkeypatch):
    """'예전에 살던 집'을 Mi:dm 이 장소로 안 뽑으면(실측 0/3) 무엇이 빠졌는지 알려 다시 묻는다.

    노트로만 남으면 예측에 못 들어간다 — 보호자가 말한 목적지 후보가 통째로 증발.
    예전에는 정규식이 발화에서 라벨을 직접 만들었다.
    """
    from app import storage

    s = _session(id="pr-label", draft_fields={"name": "송복남", "age": "82세",
                                              "home": "마포구 백범로 35"},
                 filled_keys=["identity", "home"],
                 prev_target_key="autobiographical_destination_pull")
    storage.interviews.save(s.id, s)

    def extractor(slot, conv, recheck_places=False):
        out = {"answer_kind": "informative", "fields": {}, "attraction_points": [],
               "behavior_notes": ["예전에 살던 집 이야기를 자주 함"], "slot_filled": True}
        if recheck_places:
            out["attraction_points"] = [{"label": "예전에 살던 집", "area_text": "",
                                         "evidence": "caregiver_report",
                                         "quote": "예전에 살던 집 이야길 종종 하십니다"}]
        return out

    monkeypatch.setattr(interview.midm, "extract_answer", extractor)
    out = interview.answer_interview(s.id, "예전에 살던 집 이야길 종종 하십니다")
    assert [a["label"] for a in out.draft_attractions] == ["예전에 살던 집"]
    assert out.draft_attractions[0]["evidence"] == "caregiver_report"   # 모델 판정 유지
    assert "'예전에 살던 집'은 어느 동네인가요" in out.messages[-1]["text"]


def test_no_area_question_when_label_geocodes(monkeypatch):
    """'대흥역 2번 출구'처럼 라벨만으로 좌표가 나오면 동네를 되묻지 않는다."""
    from app import storage

    s = _session(id="pr-geo", draft_fields={"name": "송복남", "age": "82세",
                                            "home": "마포구 백범로 35"},
                 filled_keys=["identity", "home"],
                 prev_target_key="dementia_wandering_pattern")
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "extract_answer",
                        lambda slot, conv: {"fields": {},
                                            "behavior_notes": [], "slot_filled": True,
                                            "attraction_points": [
                                                {"label": "대흥역 2번 출구", "area_text": ""}]})
    monkeypatch.setattr(interview, "_geocodable", lambda label: True)
    monkeypatch.setattr(interview, "_next_slot", lambda *a, **k: None)
    out = interview.answer_interview(s.id, "대흥역 2번 출구에 앉아계시는걸 발견한 적이 있어요")
    assert out.pending_area_label is None
    assert "어느 동네인가요" not in out.messages[-1]["text"]


def test_past_place_area_asked_immediately(monkeypatch):
    """과거 장소를 들은 **그 턴에** 주소를 묻는다 (요약까지 미루지 않는다)."""
    from app import storage

    s = _session(id="pr-now", draft_fields={"name": "송복남", "age": "82세",
                                            "home": "청주시 서원구 분평동"},
                 filled_keys=["identity", "home"],
                 prev_target_key="autobiographical_destination_pull")
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "extract_answer",
                        lambda slot, conv, **_: {"fields": {}, "behavior_notes": [],
                                                 "slot_filled": True,
                                                 "attraction_points": [
                                                     {"label": "예전에 살던 집",
                                                      "area_text": "청주시 서원구 분평동"}]})
    monkeypatch.setattr(interview.midm, "extract_area", lambda label, answer: "청주시 서원구 산남동")
    out = interview.answer_interview(s.id, "예전에 살던 집에 가야한다는 말을 종종 합니다")
    # 발화에 없는 지역(= 현재 집 동네를 복사한 값)은 버리고 되묻는다
    assert "'예전에 살던 집'은 어느 동네인가요" in out.messages[-1]["text"]
    assert out.pending_area_label == "예전에 살던 집"
    assert out.draft_attractions[0]["area_text"] == ""

    out = interview.answer_interview(s.id, "청주시 서원구 산남동이요")
    assert out.draft_attractions[0]["area_text"] == "청주시 서원구 산남동"
    assert [a["label"] for a in out.draft_attractions] == ["예전에 살던 집"]  # 주소가 새 장소가 되지 않는다


def test_past_place_area_not_asked_when_guardian_said_it(monkeypatch):
    """보호자가 직접 동네를 말했으면 되묻지 않는다 — 불필요한 질문 금지."""
    from app import storage

    s = _session(id="pr-said", draft_fields={"name": "송복남", "age": "82세",
                                             "home": "청주시 서원구 분평동"},
                 filled_keys=["identity", "home"],
                 prev_target_key="autobiographical_destination_pull")
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "extract_answer",
                        lambda slot, conv: {"fields": {}, "behavior_notes": [],
                                            "slot_filled": True,
                                            "attraction_points": [
                                                {"label": "예전에 살던 집",
                                                 "area_text": "산남동",
                                                 "quote": "산남동에 있는 예전 집"}]})
    monkeypatch.setattr(interview, "_next_slot", lambda *a, **k: None)
    out = interview.answer_interview(s.id, "산남동에 있는 예전 집에 가야한다고 하세요")
    assert out.pending_area_label is None
    assert out.draft_attractions[0]["area_text"] == "산남동"


def test_area_grounding_check():
    assert interview._area_grounded("산남동", "산남동에 있는 예전 집이요")
    assert interview._area_grounded("청주시 서원구 산남동", "산남동이요")
    assert not interview._area_grounded("청주시 서원구 분평동", "예전에 살던 집에 가야한대요")
    assert not interview._area_grounded("", "아무 말")


def test_summary_gate_asks_for_missing_area(monkeypatch):
    """요약 직전, 지역 표기 없는 끌림점이 있으면 반드시 한 번 묻고 넘어간다.

    되묻기 → 답변 → area_text 확정 → 그 다음 턴에 요약, 순서까지 확인한다.
    """
    from app import storage

    s = _session(id="pr-gate", draft_fields={"name": "송복남", "age": "82세",
                                             "home": "청주시 서원구 분평동"},
                 filled_keys=["identity", "home"],
                 draft_attractions=[{"label": "예전에 살던 집", "area_text": "",
                                     "origin_slot": "autobiographical_destination_pull"}],
                 asked_more_places=True,          # 장소 스윕은 이미 끝난 상태
                 prev_target_key="routine_destinations")
    storage.interviews.save(s.id, s)

    # LLM 없이 결정론적으로 — 추출은 빈손, 다음 슬롯 없음(= 종료 판정 진입)
    monkeypatch.setattr(interview.midm, "extract_answer",
                        lambda slot, conv, **_: {"fields": {}, "attraction_points": [],
                                                 "behavior_notes": [],
                                                 "slot_filled": True})
    monkeypatch.setattr(interview, "_next_slot", lambda *a, **k: None)
    monkeypatch.setattr(interview.midm, "extract_area", lambda label, answer: "청주시 서원구 산남동")

    out = interview.answer_interview(s.id, "딱히 없어요")
    assert "'예전에 살던 집'은 어느 동네인가요" in out.messages[-1]["text"]
    assert out.pending_area_label == "예전에 살던 집"
    assert not out.awaiting_confirmation          # 아직 요약 아님

    out = interview.answer_interview(s.id, "청주시 서원구 산남동이요")
    assert out.draft_attractions[0]["area_text"] == "청주시 서원구 산남동"
    assert out.awaiting_confirmation              # 이제 요약으로 진행
    assert "산남동" in out.messages[-1]["text"]

    out2 = interview.answer_interview(s.id, "네")           # 같은 장소를 두 번 묻지 않는다
    assert out2.asked_area_labels == ["예전에 살던 집"]


def test_confirmation_added_place_triggers_area_question(monkeypatch):
    """확인 단계에서 추가된 장소도 주소가 없으면 요약 대신 되묻는다.

    안 물으면 지오코딩 실패 → finalize 에서 탈락 → 보호자가 방금 추가한 곳이
    조용히 사라진다(요약 전 게이트와 같은 사고).
    """
    s = _session(id="pr-add", draft_fields={"name": "송복남", "age": "82세",
                                            "home": "청주시 서원구 분평동"},
                 awaiting_confirmation=True)
    monkeypatch.setattr(interview.midm, "extract_correction",
                        lambda labels, utterance: {"intent": "correct", "fields": {}, "place_ops": [
                            {"op": "add", "value": "청주 중앙시장", "area": ""}]})
    out = interview._handle_confirmation(s, "청주 중앙시장도 자주 가세요")
    assert "'청주 중앙시장'은 어느 동네인가요" in out.messages[-1]["text"]
    assert out.pending_area_label == "청주 중앙시장"
    assert not out.awaiting_confirmation      # 요약이 아니라 질문으로 빠졌다


# ── ② 추출 입력 — 마지막 발화 분리 ───────────────────────────────────

def test_extract_input_separates_target_utterance():
    slot = slot_by_key("dementia_wandering_pattern")
    conv = [{"role": "assistant", "text": "과거에 실종된 적이 있나요?"},
            {"role": "user", "text": "원마루 공원에 자주 가세요"},
            {"role": "assistant", "text": "어디서 발견되셨나요?"},
            {"role": "user", "text": "원평중학교 앞에서 발견돼셨어요"}]
    text = prompts.build_extract_input(slot, conv)
    assert "[추출 대상 — 이 발화에서만 뽑는다]" in text
    assert text.index("원마루 공원") < text.index("[추출 대상")   # 옛 발화는 맥락 구역에만
    assert text.rstrip().endswith("위 JSON 하나만 출력.")
    assert "이전 대화에서 이미 나온 장소는 다시 넣지 마라" in text


def test_extract_input_falls_back_when_last_is_assistant():
    slot = slot_by_key("identity")
    text = prompts.build_extract_input(slot, [{"role": "assistant", "text": "성함이?"}])
    assert "[대화]" in text and "[추출 대상" not in text


def test_question_examples_stripped_for_extraction():
    """질문에 붙는 '(예: …)'는 추출 입력에서만 제거 — 보호자에게 보인 기록은 불변."""
    msgs = [{"role": "assistant",
             "text": "어디에서 발견됐는지 알려주세요. (예: 시장 근처에서 발견됐고, 계속 걷고 있었습니다)"},
            {"role": "user", "text": "원평중학교 앞에서요"}]
    out = interview._strip_question_examples(msgs)
    assert out[0]["text"] == "어디에서 발견됐는지 알려주세요."
    assert out[1]["text"] == "원평중학교 앞에서요"
    assert "(예:" in msgs[0]["text"]        # 원본 불변


def test_generic_place_area_is_asked_even_if_label_geocodes(monkeypatch):
    """이름 없이 부른 곳('교회')은 라벨로 좌표가 나와도 동네를 묻는다 — 집 옆 아무 교회가 걸린다."""
    from app import storage

    s = _session(id="pr-generic", draft_fields={"name": "이순례", "age": "77세",
                                                "home": "고양시 일산서구 대화동"},
                 filled_keys=["identity", "home"],
                 prev_target_key="autobiographical_destination_pull")
    storage.interviews.save(s.id, s)
    monkeypatch.setattr(interview.midm, "extract_answer",
                        lambda slot, conv, **_: {"answer_kind": "informative", "fields": {},
                                                 "behavior_notes": [], "slot_filled": True,
                                                 "attraction_points": [
                                                     {"label": "교회", "area_text": "", "name_kind": "generic",
                                                      "evidence": "caregiver_report",
                                                      "quote": "일요일 아침마다 교회에 가야 한다고 하세요"}]})
    monkeypatch.setattr(interview, "_geocodable", lambda label: True)
    out = interview.answer_interview(s.id, "요즘 일요일 아침마다 교회에 가야 한다고 하세요.")
    assert out.pending_area_label == "교회"
    assert "'교회'은 어느 동네인가요" in out.messages[-1]["text"]
    assert out.draft_attractions[0]["name_kind"] == "generic"
