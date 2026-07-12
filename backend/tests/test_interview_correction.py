"""확인 게이트 '정정' 처리 — first-wins 를 넘어 덮어써야 한다.

라이브 실측 버그 (2026-07-11 인터뷰 테스트 ③): 요약 확인 단계에서
보호자가 나이를 정정("78세가 아니라 81세예요")했는데, _apply_extraction 의
first-wins(setdefault) 정책에 막혀 정정이 무시되고 틀린 나이로 등록됨.
first-wins 는 인터뷰 중간(과거 거주지가 현재 집을 덮는 것 방지)에는 옳지만,
정정 발화는 보호자의 명시적 수정 의사이므로 덮어써야 한다.
"""

from app.phase0 import interview
from app.phase0.slots import slot_by_key
from app.schemas.persona import InterviewSession, PersonaType


def _session(**fields) -> InterviewSession:
    return InterviewSession(
        id="corr1", guardian_name="보호자", persona_type=PersonaType.dementia,
        draft_fields=dict(fields), awaiting_confirmation=True,
    )


_SLOT = slot_by_key("identity")   # 성함·나이·유형 슬롯 (fields sink)


def test_apply_extraction_first_wins_by_default():
    """인터뷰 중간 추출은 기존 값을 못 덮는다 (기존 동작 보존)."""
    s = _session(age="78세")
    interview._apply_extraction(s, _SLOT, {"fields": {"age": "81세"}})
    assert s.draft_fields["age"] == "78세"


def test_apply_extraction_overwrite_for_correction():
    """overwrite=True(정정 경로)면 기존 값을 덮는다."""
    s = _session(age="78세")
    interview._apply_extraction(s, _SLOT, {"fields": {"age": "81세"}}, overwrite=True)
    assert s.draft_fields["age"] == "81세"


def test_confirmation_correction_overwrites_field(monkeypatch):
    """확인 게이트에서 '아니요, 81세예요' → 나이가 실제로 정정되고 재요약된다."""
    s = _session(name="김순자", age="78세", home="정릉동")

    class _Hit:
        slot = _SLOT

    monkeypatch.setattr(interview.retrieval, "rank_next_slots",
                        lambda *a, **k: ([_Hit()], []))
    monkeypatch.setattr(interview.midm, "extract_answer",
                        lambda slot, conv: {"fields": {"age": "81세"},
                                            "attraction_points": [],
                                            "behavior_notes": [],
                                            "slot_filled": True})
    out = interview._handle_confirmation(s, "아니요, 나이가 81세예요")
    assert out.draft_fields["age"] == "81세"          # 정정 반영 (구버전: 78세 유지)
    assert out.awaiting_confirmation                   # 재요약 후 다시 확인 대기
    assert "81" in out.messages[-1]["text"]            # 요약에 정정값 노출
