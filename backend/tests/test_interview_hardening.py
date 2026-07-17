"""챗봇 고도화(2026-07-17) 회귀 — 데드엔드·장애 플래그·규칙 폴백·재질문 UX.

어제(07-16) 라이브 실측(엔드포인트 410)에서 확인된 4가지 실패 모드의 회귀 방지:
  ② finalize 실패(집 위치 미확보) 후 done=True 데드엔드 — 세션이 죽어 복구 불가
  ② Mi:dm 호출 실패가 침묵 — "이상한 반복 인터뷰"로만 체감
  ③ name/age/home 추출이 Mi:dm 단일 장애점 — 엔드포인트 다운이면 등록 퍼널 전체 실패
  ④ 재질문이 직전 질문을 토씨까지 재낭독(Q5=Q6) + 폴백 씨앗 질문의 복합 문형
"""

from app import storage
from app.geo.geocode import GazetteerGeocoder
from app.phase0 import interview, retrieval, safety
from app.phase0.slots import slot_by_key, slots_for
from app.schemas.persona import InterviewSession, PersonaType

EMB = retrieval.HashingEmbedder()


# ── ② finalize 데드엔드 → 복구 루프 ──────────────────────────────────

def _confirmed_session(home: str) -> InterviewSession:
    """모든 슬롯이 끝나 요약 확인 게이트에 도달한 세션."""
    s = InterviewSession(
        id="hard1", guardian_name="보호자", persona_type=PersonaType.dementia,
        draft_fields={"name": "김순자", "age": "78세", "home": home},
        filled_keys=[sp.key for sp in slots_for(PersonaType.dementia)],
        awaiting_confirmation=True,
    )
    storage.interviews.save(s.id, s)
    return s


def test_finalize_failure_keeps_session_alive_and_recovers(monkeypatch):
    """지오코딩 실패 → 세션은 살아있고 → 집 재답변으로 등록까지 완주.

    구버전: done=True 로 닫혀 "다시 확인해 달라"는 안내와 달리 이후 입력이
    전부 무시되는 막다른 길이었다.
    """
    monkeypatch.setattr(interview, "_GEO", GazetteerGeocoder())
    s = _confirmed_session(home="지도에없는곳")

    out = interview.answer_interview(s.id, "네 맞아요")
    assert not out.done                        # 구버전: True (데드엔드)
    assert not out.awaiting_confirmation
    assert "home" not in out.draft_fields      # 실패 값 제거 — first-wins 가 새 답을 막지 않게
    assert "home" not in out.filled_keys
    assert out.prev_target_key == "home"       # 다음 답변은 home 으로 추출

    # 집 재답변 (스텁 추출은 빈손 — 규칙 폴백이 채운다) → 요약 확인 재진입
    out = interview.answer_interview(s.id, "성북구 정릉동이에요")
    assert out.draft_fields.get("home") == "성북구 정릉동"
    assert out.awaiting_confirmation

    out = interview.answer_interview(s.id, "네")
    assert out.done and out.persona_id         # 등록 완주


# ── ② LLM 장애 세션 플래그 ──────────────────────────────────────────

def test_llm_failure_sets_degraded_flag(monkeypatch):
    """Mi:dm 호출이 실패하면 폴백으로 진행하되 세션에 장애가 노출된다."""
    from app.llm.midm import MidmClient

    monkeypatch.setattr(MidmClient, "is_stub", property(lambda self: False))

    def _boom(*a, **k):
        raise RuntimeError("HTTP 410 Gone")

    monkeypatch.setattr(interview.midm, "chat", _boom)

    s = interview.start_interview("보호자", PersonaType.dementia)
    out = interview.answer_interview(s.id, "김순자님이고 78세, 치매가 있으세요")

    assert out.llm_degraded
    assert out.llm_call_failures >= 1
    # 장애 중에도 규칙 폴백으로 필수 필드는 확보 (③과 결합)
    assert out.draft_fields.get("name") == "김순자"
    assert out.draft_fields.get("age") == "78세"


def test_stub_mode_is_not_degraded():
    """스텁 모드(키 없음)는 정상 폴백 — 장애 플래그를 올리면 안 된다."""
    s = interview.start_interview("보호자", PersonaType.dementia)
    out = interview.answer_interview(s.id, "김순자님이고 78세, 치매가 있으세요")
    assert not out.llm_degraded and out.llm_call_failures == 0


# ── ③ 규칙 기반 최소 추출 (identity/home) ────────────────────────────

def test_rule_extract_identity():
    f = interview._rule_extract_fields("identity", "저희 어머니 김순자님이고 78세예요")
    assert f == {"name": "김순자", "age": "78세"}
    f = interview._rule_extract_fields("identity", "이름은 박말녀, 여든이 넘으셨어요")
    assert f.get("name") == "박말녀"          # 나이는 숫자 표현이 없으면 못 뽑는다(보수적)
    f = interview._rule_extract_fields("identity", "할머니세요, 82살이요")
    assert f.get("name") is None and f.get("age") == "82세"   # 호칭을 이름으로 오인 금지


def test_rule_extract_home():
    f = interview._rule_extract_fields("home", "서울 성북구 정릉동이에요")
    assert f["home"].endswith("정릉동")
    f = interview._rule_extract_fields("home", "면목로 12에 살아요")
    assert f["home"] == "면목로 12"
    assert interview._rule_extract_fields("home", "잘 모르겠어요") == {}


def test_stub_interview_captures_required_fields_end_to_end():
    """엔드포인트 없이(스텁)도 name/age/home 이 실제로 쌓인다 — 등록 퍼널 방어선."""
    s = interview.start_interview("보호자", PersonaType.dementia)
    out = interview.answer_interview(s.id, "김순자님이고 78세, 치매 어르신이에요")
    out = interview.answer_interview(s.id, "성북구 정릉동 살아요")
    assert out.draft_fields.get("name") == "김순자"
    assert out.draft_fields.get("age") == "78세"
    assert out.draft_fields.get("home") == "성북구 정릉동"
    assert "home" in out.filled_keys


# ── ④ 재질문 UX — 토씨까지 같은 재낭독 금지 + 단일 질문 폴백 ─────────

def test_reask_never_repeats_verbatim(monkeypatch):
    """같은 슬롯을 연속으로 물어도 직전 질문과 문장이 달라야 한다(Q5=Q6 방지)."""
    slot = slot_by_key("routine_destinations")

    class _Hit:
        similarity = 0.9
    _Hit.slot = slot

    monkeypatch.setattr(interview.retrieval, "rank_next_slots",
                        lambda *a, **k: ([_Hit()], []))
    # 뭐라도 건졌지만 미충족 — 같은 슬롯 꼬리질문(재선택 허용) 경로
    monkeypatch.setattr(interview.midm, "extract_answer",
                        lambda slot, conv: {"fields": {}, "attraction_points": [],
                                            "preferred_targets": [],
                                            "behavior_notes": ["시장 근처를 좋아함"],
                                            "slot_filled": False})
    s = interview.start_interview("보호자", PersonaType.dementia)
    s.draft_fields["home"] = "정릉동"
    s.filled_keys.append("home")            # 2.5 home 게이트 우회
    storage.interviews.save(s.id, s)

    out = interview.answer_interview(s.id, "김순자 78세 치매예요")
    q1 = out.messages[-1]["text"]
    out = interview.answer_interview(s.id, "시장에 자주 가요")
    q2 = out.messages[-1]["text"]
    assert q1 != q2                          # 구버전: 토씨까지 동일
    assert q2.endswith(q1)                   # 변형 = 재질문 티가 나는 프리픽스


def test_empty_extraction_avoids_immediate_same_slot():
    """빈손 답변 뒤에는 방금 물은 슬롯을 곧바로 재선택하지 않는다(스텁 추출 빈손 활용)."""
    s = interview.start_interview("보호자", PersonaType.dementia)
    s.draft_fields.update({"name": "김순자", "age": "78세", "home": "정릉동"})
    s.filled_keys += ["identity", "home"]
    s.prev_target_key = "routine_destinations"
    s.asked_counts["routine_destinations"] = 1
    storage.interviews.save(s.id, s)

    # "글쎄요" — 규칙 폴백 대상도 아니고 스텁 추출은 slot_filled=True 라
    # 빈손 경로를 보려면 실패 추출을 흉내낸다
    import unittest.mock as mock
    with mock.patch.object(interview.midm, "extract_answer",
                           return_value={"fields": {}, "attraction_points": [],
                                         "preferred_targets": [], "behavior_notes": [],
                                         "slot_filled": False}):
        out = interview.answer_interview(s.id, "글쎄요")
    assert out.prev_target_key != "routine_destinations"


def test_guard_fallback_emits_single_question():
    """폴백 씨앗 질문이 복합 문형(물음표 3개)이어도 한 질문만 내보낸다."""
    slot = slot_by_key("medication")
    assert slot.question.count("?") == 3     # 회의록 원문은 복합 문형(참고용으로 유지)
    out, fell_back = safety.guard_question("복용량을 늘리셔야 해요", slot, EMB)  # 층① 차단
    assert fell_back
    assert out.count("?") == 1
    assert out == "복용 중인 약이 있나요?"
