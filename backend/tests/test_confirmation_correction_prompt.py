"""확인 게이트에서 '아니요, 수정할게요' — 무엇을 고칠지 되묻는다.

라이브 실측(2026-08-07): 요약 화면의 '아니요, 수정할게요' 칩(프런트 CONFIRM_CHIPS)이
그 문구를 그대로 보내는데, 서버는 일반 정정으로 흘렸다. Mi:dm 은 바꿀 대상을 못
찾고, **똑같은 요약이 다시 떠서** 보호자는 무엇을 해야 할지 모른 채 멈췄다.
"""

from app import storage
from app.phase0 import interview
from app.schemas.persona import InterviewSession, PersonaType

CHIP = "아니요, 수정할게요"          # frontend/src/screens/RegChatScreen.tsx CONFIRM_CHIPS


def _at_gate(**kw) -> InterviewSession:
    base = dict(
        id="cc1", guardian_name="보호자", persona_type=PersonaType.dementia,
        draft_fields={"name": "김순자", "age": "82세", "home": "마포구 백범로 35"},
        draft_attractions=[{"label": "망원시장", "area_text": "망원동",
                            "evidence": "caregiver_report",
                            "origin_slot": "routine_destinations"}],
        draft_behaviors=["길 잃었을 때 행동: 그 자리에 가만히 서 계세요"],
        slot_notes={"lost_behavior": ["그 자리에 가만히 서 계세요"]},
        filled_keys=["identity", "home", "routine_destinations", "lost_behavior"],
        awaiting_confirmation=True,
    )
    return InterviewSession(**{**base, **kw})


# ── 감지 ─────────────────────────────────────────────────────────────

def test_detects_bare_correction_request():
    for t in [CHIP, "수정할게요", "고칠래요", "아니 틀렸어요", "바꿔주세요", "잘못됐어요"]:
        assert interview._is_bare_correction_request(t), t


def test_real_correction_is_not_bare():
    """무엇을 고칠지 말한 발화는 기존 정정 경로로 가야 한다."""
    for t in ["집 주소가 틀렸어요 마포구 신수동이에요",
              "이름이 잘못됐어요 김순희예요",
              "망원시장은 빼주세요",
              "주소를 백범로로 변경해주세요"]:
        assert not interview._is_bare_correction_request(t), t


def test_affirmative_is_not_bare_correction():
    for t in ["네, 맞아요", "이대로 등록해주세요"]:
        assert not interview._is_bare_correction_request(t), t


# ── 흐름 ─────────────────────────────────────────────────────────────

def test_gate_asks_what_to_correct():
    """요약 재낭독이 아니라 '어느 부분을 고칠까요?' 가 나가고, 게이트는 열려 있다."""
    s = _at_gate(id="cc-flow")
    storage.interviews.save(s.id, s)

    out = interview.answer_interview(s.id, CHIP)
    q = out.messages[-1]["text"]
    assert "어느 부분을 고칠까요" in q
    assert "이렇게 등록할게요" not in q          # 같은 요약 재낭독 금지
    assert out.awaiting_confirmation             # 다음 발화가 정정으로 들어오게 유지
    assert not out.done


def test_correction_menu_lists_editable_items():
    """고칠 수 있는 항목을 실제로 보여준다 — 보호자가 지목할 수 있어야 한다."""
    s = _at_gate(id="cc-menu")
    menu = interview._ask_what_to_correct(s)
    assert "성함·나이" in menu
    assert "지내시는 곳" in menu
    assert "가시려 할 만한 곳" in menu           # 등록된 장소가 있으므로
    assert "길을 잃으시면 하시는 행동" in menu    # 수집된 슬롯의 보호자용 라벨


def test_correction_after_menu_still_applies(monkeypatch):
    """되물은 다음 턴의 실제 정정은 종전대로 반영된다."""
    s = _at_gate(id="cc-then")
    storage.interviews.save(s.id, s)
    interview.answer_interview(s.id, CHIP)

    monkeypatch.setattr(interview.midm, "extract_correction",
                        lambda labels, u: {"fields": {},
                                           "place_ops": [{"op": "remove", "target": "망원시장"}]})
    out = interview.answer_interview(s.id, "망원시장은 빼주세요")
    assert all(a.get("label") != "망원시장" for a in out.draft_attractions)
