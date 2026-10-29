"""집 답변에서 집 그 자체("대화동 아파트")를 가볼 만한 장소로 저장하지 않는다.

15회차(10/29): "고양시 일산서구 대화동 아파트에서 저와 함께 지내십니다"를 Mi:dm 이 집
"…대화동"과 장소 "대화동 아파트"로 쪼개, 집이 목적지 후보로 한 번 더 들어갔다. 같은 대본의
14회차는 쪼개지 않았다(온도 0 에서도 출력이 흔들림). 장소 이름이 집 문자열보다 길어 포함
검사를, 뒤에 "근처"가 없어 #257 기준점 규칙을 둘 다 빠져나갔다.
"""
import pytest

from app.phase0 import interview
from app.phase0.slots import slot_by_key
from app.schemas.persona import InterviewSession, PersonaType

HOME_ANSWER = "고양시 일산서구 대화동 아파트에서 저와 함께 지내십니다."


def _session() -> InterviewSession:
    return InterviewSession(id="dw1", guardian_name="보호자", persona_type=PersonaType.dementia)


def _ap(label: str, evidence: str = "mention_only") -> dict:
    return {"label": label, "area_text": "", "place_type": "기타", "name_kind": "generic",
            "evidence": evidence, "quote": label, "same_as": ""}


def test_home_split_into_home_and_place_keeps_only_the_home():
    s = _session()
    interview._apply_extraction(
        s, slot_by_key("home"),
        {"fields": {"home": "고양시 일산서구 대화동"}, "attraction_points": [_ap("대화동 아파트")]},
        utterance=HOME_ANSWER)
    assert s.draft_attractions == []
    assert s.draft_fields["home"] == "고양시 일산서구 대화동"
    assert {"event": "home_dwelling_not_place", "label": "대화동 아파트"} in s.extraction_audit


@pytest.mark.parametrize(("label", "utterance"), [
    ("주간보호센터", "대화동에 사시고 주중 낮에는 주간보호센터에 계십니다."),
    ("딸네 아파트", "대화동에 사시는데 주말에는 딸네 아파트에 가 계세요."),
    ("국밥집", "대화동에 사시고 동네 국밥집에 자주 가세요."),
])
def test_other_places_named_on_the_home_turn_are_kept(label, utterance):
    s = _session()
    interview._apply_extraction(
        s, slot_by_key("home"),
        {"fields": {"home": "고양시 일산서구 대화동"}, "attraction_points": [_ap(label)]},
        utterance=utterance)
    assert [a["label"] for a in s.draft_attractions] == [label]


def test_the_same_name_on_another_turn_is_still_a_place():
    # 집 턴이 아니면 걸지 않는다 — "예전에 살던 대화동 아파트"는 자전적 목적지다.
    s = _session()
    s.draft_fields["home"] = "고양시 일산서구 대화동"
    interview._apply_extraction(
        s, slot_by_key("autobiographical_destination_pull"),
        {"attraction_points": [_ap("대화동 아파트", evidence="caregiver_report")]},
        utterance="예전에 살던 대화동 아파트에 자꾸 가야 한다고 하세요.")
    assert [a["label"] for a in s.draft_attractions] == ["대화동 아파트"]


@pytest.mark.parametrize(("label", "home", "utterance", "expected"), [
    ("대화동 아파트", "고양시 일산서구 대화동", HOME_ANSWER, True),
    ("대화동 아파트", "", HOME_ANSWER, True),            # 집 주소를 아직 못 받았으면 집 답으로 본다
    ("저희 집", "", "저희 집은 대화동이에요.", True),
    ("대화마을 빌라", "일산서구 대화마을", "대화마을 빌라에 사세요.", True),
    ("딸네 아파트", "고양시 일산서구 대화동", "주말에는 딸네 아파트에 가 계세요.", False),
    ("국밥집", "고양시 일산서구 대화동", "동네 국밥집에 자주 가세요.", False),
    ("주간보호센터", "고양시 일산서구 대화동", "주간보호센터에 계십니다.", False),
])
def test_is_home_dwelling(label, home, utterance, expected):
    assert interview._is_home_dwelling(label, home, utterance) is expected
