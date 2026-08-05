"""확인 게이트 요약 카드 — 전량 표시·슬롯 묶기·빈칸 안내 회귀.

라이브 실측(2026-08-05): 요약이 장소 3곳·행동 2개만 보이고 나머지 17가지를
"…외 17가지 저장"으로 접은 채 "이게 맞나요?"를 물었다. 보호자가 확인할 수 없는
확인 절차 + 같은 슬롯 노트가 라벨 접두를 반복해 중복으로 보이는 문제까지.

여기서 고정하는 계약:
  1) 접지 않는다 — 수집한 장소·행동은 전부 요약에 나온다
  2) 같은 슬롯 노트는 제목 하나 아래로 묶인다 (라벨 접두 반복 금지)
  3) 제목은 내부 라벨이 아니라 보호자용 표현(SlotSpec.display_label)
  4) 못 받은 슬롯은 '아직 안 알려주신 것'으로 보여 보충 기회를 준다
"""

from app.phase0 import interview
from app.phase0.slots import slot_by_key, slots_for
from app.schemas.persona import InterviewSession, PersonaType

_DEM = PersonaType.dementia
_ALL_KEYS = [s.key for s in slots_for(_DEM)]


def _session(**kw) -> InterviewSession:
    base = {
        "id": "sum1", "guardian_name": "보호자", "persona_type": _DEM,
        "draft_fields": {"name": "김순자", "age": "82세", "home": "서울 성북구 정릉동"},
        "filled_keys": list(_ALL_KEYS),   # 기본은 '다 받은' 세션 — 빈칸 안내가 섞이지 않게
    }
    base.update(kw)
    return InterviewSession(**base)


# ── 1) 접지 않는다 ──────────────────────────────────────────────────

def test_summary_shows_every_place_and_note():
    """장소 5곳·행동 6개 전부 노출 — '…외 N' 축약이 없다."""
    s = _session(
        draft_attractions=[{"label": f"장소{i}", "area_text": "정릉동",
                            "origin_slot": "routine_destinations"} for i in range(5)],
        draft_behaviors=[f"길 잃었을 때 행동: 관찰 {i}" for i in range(6)],
    )
    text = interview.build_summary(s)

    assert "…외" not in text and "곳 저장" not in text and "가지 저장" not in text
    for i in range(5):
        assert f"장소{i}" in text
    for i in range(6):
        assert f"관찰 {i}" in text


def test_summary_keeps_confirmation_prompt():
    """확인 요청 문장은 그대로 — 확인 게이트의 응답 규약(_is_affirmative)이 여기 걸려 있다."""
    text = interview.build_summary(_session())
    assert "맞나요?" in text


# ── 2)·3) 슬롯 묶기 + 보호자용 제목 ─────────────────────────────────

def test_same_slot_notes_grouped_under_one_heading():
    """같은 슬롯 노트 2개 → 제목 1줄 + 항목 2줄. 라벨 접두는 사라진다."""
    slot = slot_by_key("routine_destinations")
    s = _session(draft_behaviors=[
        f"{slot.label}: 혼자 정릉시장에 자주 감",
        f"{slot.label}: 늘 같은 골목길로 걸어서 이동",
    ])
    text = interview.build_summary(s)

    assert text.count(slot.display_label) == 1          # 제목은 한 번만
    assert f"{slot.label}:" not in text                 # 내부 라벨 접두 노출 금지
    assert "   - 혼자 정릉시장에 자주 감" in text
    assert "   - 늘 같은 골목길로 걸어서 이동" in text


def test_single_note_rendered_inline():
    """노트가 하나뿐이면 제목+내용 한 줄 — 한 줄짜리 목록으로 늘리지 않는다."""
    slot = slot_by_key("lost_behavior")
    s = _session(draft_behaviors=[f"{slot.label}: 계속 앞으로 걸어감"])
    text = interview.build_summary(s)

    assert f"• {slot.display_label}: 계속 앞으로 걸어감" in text


def test_headings_use_guardian_wording_not_slot_label():
    """모든 슬롯이 보호자용 표현을 갖고, 요약 제목으로 그 표현이 쓰인다."""
    for slot in slots_for(_DEM):
        assert slot.guardian_label, f"{slot.key} 에 보호자용 표현이 없다"
        assert slot.display_label == slot.guardian_label

    slot = slot_by_key("routine_destinations")
    text = interview.build_summary(_session(draft_behaviors=[f"{slot.label}: 정릉시장"]))
    assert "혼자 다니시는 곳" in text and "혼자 자주 가는 곳·경로" not in text


def test_untagged_legacy_note_is_not_dropped():
    """라벨 접두가 없는 구버전·시드 노트도 유실 없이 나온다."""
    s = _session(draft_behaviors=["해질녘 옛집 방향으로 걷는 습관"])
    text = interview.build_summary(s)
    assert "해질녘 옛집 방향으로 걷는 습관" in text


def test_note_body_with_colon_survives():
    """본문에 ': ' 가 들어가도 접두만 떼고 본문은 온전히 남는다."""
    slot = slot_by_key("medication")
    s = _session(draft_behaviors=[f"{slot.label}: 아침: 혈압약, 저녁: 치매약"])
    text = interview.build_summary(s)
    assert "아침: 혈압약, 저녁: 치매약" in text


# ── 4) 빈칸 안내 ────────────────────────────────────────────────────

def test_unfilled_slots_listed_as_missing():
    """못 받은 슬롯은 '아직 안 알려주신 것'에 보호자용 표현으로 나온다."""
    filled = [k for k in _ALL_KEYS if k != "medication"]
    s = _session(filled_keys=filled)
    text = interview.build_summary(s)

    assert "아직 안 알려주신 것" in text
    assert slot_by_key("medication").display_label in text


def test_slot_with_notes_not_listed_as_missing():
    """충족 판정이 없어도 노트가 남았으면 빈칸이 아니다 — 위아래 동시 노출 금지."""
    slot = slot_by_key("medication")
    filled = [k for k in _ALL_KEYS if k != slot.key]
    s = _session(filled_keys=filled,
                 draft_behaviors=[f"{slot.label}: 혈압약을 아침저녁으로 드심"])
    text = interview.build_summary(s)

    missing = text.split("아직 안 알려주신 것")[1] if "아직 안 알려주신 것" in text else ""
    assert slot.display_label not in missing
    assert "혈압약을 아침저녁으로 드심" in text


def test_slot_with_place_not_listed_as_missing():
    """장소만 나온 슬롯도 빈칸이 아니다 — 장소 목록에 이미 보인다."""
    slot = slot_by_key("autobiographical_destination_pull")
    filled = [k for k in _ALL_KEYS if k != slot.key]
    s = _session(filled_keys=filled, draft_attractions=[
        {"label": "옛집", "area_text": "미아리", "origin_slot": slot.key}])
    text = interview.build_summary(s)

    assert "아직 안 알려주신 것" not in text
    assert "옛집 (미아리)" in text


def test_missing_name_flagged_even_when_slot_marked_filled():
    """필드 슬롯은 채움 판정이 아니라 값으로 본다.

    실측(스텁·장애 모드): Mi:dm 이 identity 를 slot_filled 로 내면서 이름은 못 뽑아,
    요약이 "대상자: 82세, 치매 어르신"으로 이름 없이 확인을 받아갔다.
    """
    s = _session(draft_fields={"age": "82세", "home": "성북구 정릉동"})
    text = interview.build_summary(s)

    assert "아직 안 알려주신 것" in text
    assert slot_by_key("identity").display_label in text


def test_no_missing_section_when_everything_collected():
    """다 받았으면 빈칸 안내를 붙이지 않는다 — 없는 걱정을 만들지 않게."""
    text = interview.build_summary(_session())
    assert "아직 안 알려주신 것" not in text
