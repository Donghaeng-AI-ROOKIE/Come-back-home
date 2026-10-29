"""등록 첫 질문에서 성별을 함께 받는다(10/29 팀 점검 — 사전등록 인터뷰가 성별을 묻지 않았다).

성별은 이름·나이처럼 모델이 뽑고, 코드는 답에 근거가 있는지만 대조한다(2026-09-26 결정:
보호자 문장을 단어 규칙으로 해석하지 않는다). 답에 없으면 비워 둔 채 등록을 이어 간다.
"""
import pytest

from app.geo.geocode import GazetteerGeocoder
from app.phase0 import interview, prompts
from app.phase0.slots import slot_by_key, slots_for
from app.schemas.common import GeoPoint
from app.schemas.persona import InterviewSession, PersonaType

_DEM = PersonaType.dementia


def _session(**kw) -> InterviewSession:
    base = {
        "id": "sex1", "guardian_name": "보호자", "persona_type": _DEM,
        "draft_fields": {"name": "김순자", "age": "82세", "home": "서울 성북구 정릉동"},
        "filled_keys": [s.key for s in slots_for(_DEM)],
    }
    base.update(kw)
    return InterviewSession(**base)


def test_first_question_asks_name_age_and_sex():
    s = interview.start_interview("보호자")
    assert s.messages[0]["text"] == "등록하실 어르신의 성함과 나이, 성별을 알려주세요."


def test_sex_is_asked_only_on_the_first_question_turn():
    # 공통 추출 지시에 넣었더니 다른 턴의 장소 추출이 흔들렸다(10/29 실호출: '조용한 골목' 1/3 → 3/3).
    # 공통 지시는 #349 이전 그대로 두고, 첫 질문 턴의 입력에만 성별 지시를 붙인다.
    assert "sex" not in prompts.EXTRACT_SYSTEM
    conv = [{"role": "assistant", "text": "질문"}, {"role": "user", "text": "김순자 할머니고 82세예요"}]
    assert "fields.sex" in prompts.build_extract_input(slot_by_key("identity"), conv)
    for key in ("home", "distress_induced_movement_reactivity", "routine_destinations"):
        assert "sex" not in prompts.build_extract_input(slot_by_key(key), conv)


def test_correction_prompt_carries_sex():
    assert "name/age/sex/home" in prompts.CORRECTION_SYSTEM
    parsed = prompts.parse_correction('{"intent":"correct","fields":{"sex":"F"},"place_ops":[]}', [])
    assert parsed["fields"] == {"sex": "F"}


@pytest.mark.parametrize(("value", "answer", "kept"), [
    ("F", "김순자 할머니고 82세예요", "F"),
    ("여성", "김순자, 82세 여자예요", "F"),
    ("M", "박영수 할아버지, 79세입니다", "M"),
    ("M", "김순자, 82세예요", None),            # 답에 성별을 가리키는 말이 없다 — 지어낸 값
    ("F", "박영수 할아버지, 79세입니다", None),  # 답과 반대
    ("모름", "김순자 할머니고 82세예요", None),   # F/M 이 아니다
])
def test_sex_is_kept_only_with_support_in_the_answer(value, answer, kept):
    s = _session(draft_fields={})
    fields = interview._grounded_fields(s, {"sex": value}, answer)
    assert fields.get("sex") == kept
    if kept is None:
        assert {"event": "field_not_in_answer", "field": "sex", "value": value} in s.extraction_audit


def test_summary_lists_sex_after_age():
    text = interview.build_summary(_session(draft_fields={
        "name": "김순자", "age": "82세", "sex": "F", "home": "서울 성북구 정릉동"}))
    assert "• 대상자: 김순자, 82세, 여성, 치매 어르신" in text


def test_summary_without_sex_stays_as_before():
    text = interview.build_summary(_session())
    assert "• 대상자: 김순자, 82세, 치매 어르신" in text


def test_correction_menu_names_sex():
    assert "성함·나이·성별" in interview._ask_what_to_correct(_session())


@pytest.mark.parametrize(("sex", "saved"), [("M", "M"), (None, None)])
def test_finalize_saves_sex(sex, saved):
    fields = {"name": "박영수", "age": "79세", "home": "성북구 정릉동"}
    if sex:
        fields["sex"] = sex
    s = InterviewSession(id=f"sexfin-{sex}", guardian_name="보호자", persona_type=_DEM,
                         draft_fields=fields, awaiting_confirmation=True)
    p = interview.finalize_persona(s, geocoder=GazetteerGeocoder())
    assert p.sex == saved
    assert interview.storage.personas.get(p.id).sex == saved


def test_direct_registration_takes_sex():
    p = interview.register_persona(None, name="김순자", age=82, ptype=_DEM,
                                   home=GeoPoint(lat=37.55, lng=126.94), sex="F")
    assert p.sex == "F"
