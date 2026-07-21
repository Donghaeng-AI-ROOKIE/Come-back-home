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


# ── 장소 지역 표기(area_text) 정정 — 라이브 실측 2026-07-21 ──────────

_PLACE_SLOT = slot_by_key("autobiographical_destination_pull")


def test_placeholder_area_normalized_to_empty():
    """Mi:dm 이 area_text 를 '언급 없음' 문자열로 채우던 실측 — 빈 값으로 정규화."""
    s = _session()
    interview._apply_extraction(s, _PLACE_SLOT, {"attraction_points": [
        {"label": "예전에 살던 집", "area_text": "언급 없음"}]})
    assert s.draft_attractions[0]["area_text"] == ""


def test_correction_overwrites_existing_area_text():
    """'그 집 주소는 산남동이에요' → 이미 area_text 가 있어도 정정이 반영된다.

    구버전은 `if not kept.get("area_text")` 조건에 막혀(플레이스홀더도 truthy)
    정정이 통째로 무시되고 요약이 글자 하나 안 바뀐 채 반복됐다.
    """
    s = _session()
    s.draft_attractions = [{"label": "예전에 살던 집", "area_text": "분평동"}]
    interview._apply_extraction(s, _PLACE_SLOT, {"attraction_points": [
        {"label": "예전에 살던 집", "area_text": "청주시 서원구 산남동"}]}, overwrite=True)
    assert s.draft_attractions[0]["area_text"] == "청주시 서원구 산남동"


# ── 장소 변경 지시(place_ops) — 이름·위치 정정과 삭제 (라이브 실측 2026-07-21) ──
# 구버전은 확인 게이트에서 슬롯 하나를 골라 재추출할 뿐이라 "A가 아니라 B",
# "X는 빼주세요" 를 표현할 수단 자체가 없었다(무반응). 더 나쁜 것은 장소 정정이
# home 슬롯으로 랭킹돼 **수색 원점이 조용히 바뀌던 것**이다.

def _place_session() -> InterviewSession:
    s = _session(name="송복남", age="82세", home="청주시 서원구 분평동")
    s.draft_attractions = [
        {"label": "원마루 공원", "area_text": "청주시 서원구 분평동"},
        {"label": "원평중학교", "area_text": "원평중학교"},
    ]
    return s


def _fake_correction(result: dict):
    return lambda labels, utterance: {"fields": {}, "place_ops": [], **result}


def test_correction_renames_place(monkeypatch):
    s = _place_session()
    monkeypatch.setattr(interview.midm, "extract_correction", _fake_correction(
        {"place_ops": [{"op": "rename", "target": "원평중학교", "value": "원평초등학교"}]}))
    assert interview._apply_correction(s, "원평중학교가 아니라 원평초등학교예요")
    assert [a["label"] for a in s.draft_attractions] == ["원마루 공원", "원평초등학교"]


def test_rename_carries_stale_area_text(monkeypatch):
    """area_text 가 옛 이름을 담고 있으면 함께 바뀐다 — 안 그러면 옛 장소로 좌표가 잡힌다."""
    s = _place_session()
    s.draft_attractions[1]["area_text"] = "원평중학교 앞"   # 실측 형태(라벨+부가어)
    monkeypatch.setattr(interview.midm, "extract_correction", _fake_correction(
        {"place_ops": [{"op": "rename", "target": "원평중학교", "value": "원평초등학교"}]}))
    interview._apply_correction(s, "원평중학교가 아니라 원평초등학교예요")
    assert s.draft_attractions[1] == {"label": "원평초등학교", "area_text": "원평초등학교"}


def test_correction_removes_place(monkeypatch):
    s = _place_session()
    monkeypatch.setattr(interview.midm, "extract_correction", _fake_correction(
        {"place_ops": [{"op": "remove", "target": "원마루 공원"}]}))
    assert interview._apply_correction(s, "원마루 공원은 이제 안 가세요. 빼주세요")
    assert [a["label"] for a in s.draft_attractions] == ["원평중학교"]


def test_correction_sets_area_without_touching_home(monkeypatch):
    """장소 위치 정정이 자택을 덮지 않는다 — 실측 최악 케이스의 회귀 테스트."""
    s = _place_session()
    monkeypatch.setattr(interview.midm, "extract_correction", _fake_correction(
        {"fields": {"home": "청주시 서원구 수곡동"},          # 모델이 home 으로 오해해도
         "place_ops": [{"op": "set_area", "target": "원마루 공원", "value": "수곡동이요"}]}))
    assert interview._apply_correction(s, "원마루 공원은 분평동이 아니라 수곡동이에요")
    assert s.draft_attractions[0]["area_text"] == "수곡동"     # 조사 제거해서 반영
    assert s.draft_fields["home"] == "청주시 서원구 분평동"     # 수색 원점 불변


def test_correction_allows_explicit_home_change(monkeypatch):
    """'지금 사시는 집'을 명시하면 자택 정정은 정상 동작해야 한다."""
    s = _place_session()
    monkeypatch.setattr(interview.midm, "extract_correction", _fake_correction(
        {"fields": {"home": "청주시 서원구 수곡동"}}))
    assert interview._apply_correction(s, "지금 사시는 집은 수곡동이에요")
    assert s.draft_fields["home"] == "청주시 서원구 수곡동"


def test_correction_adds_place(monkeypatch):
    s = _place_session()
    monkeypatch.setattr(interview.midm, "extract_correction", _fake_correction(
        {"place_ops": [{"op": "add", "value": "청주 중앙시장", "area": "청주시 상당구"}]}))
    assert interview._apply_correction(s, "청주 중앙시장도 자주 가세요")
    assert s.draft_attractions[-1]["label"] == "청주 중앙시장"


def test_rename_misclassified_as_remove_is_rejected(monkeypatch):
    """'A가 아니라 B'에 모델이 remove 를 내도 장소를 지우지 않는다.

    실측(2026-07-21): 이름 정정 한 마디에 등록된 장소가 통째로 사라졌다.
    삭제는 되돌릴 수 없으므로 보호자 발화에 뺄 의사가 있을 때만 인정한다.
    """
    s = _place_session()
    monkeypatch.setattr(interview.midm, "extract_correction", _fake_correction(
        {"place_ops": [{"op": "remove", "target": "원평중학교"}]}))
    assert not interview._apply_correction(s, "원평중학교가 아니라 원평초등학교예요")
    assert [a["label"] for a in s.draft_attractions] == ["원마루 공원", "원평중학교"]


def test_home_misclassification_salvaged_as_place_area(monkeypatch):
    """장소의 동네 정정을 모델이 home 으로 보내면, 그 장소의 지역 정정으로 되살린다."""
    s = _place_session()
    monkeypatch.setattr(interview.midm, "extract_correction", _fake_correction(
        {"fields": {"home": "수곡동"}}))          # place_ops 없음 = 실측 그대로
    assert interview._apply_correction(s, "원마루 공원은 분평동이 아니라 수곡동이에요")
    assert s.draft_attractions[0]["area_text"] == "수곡동"    # 장소에 반영
    assert s.draft_fields["home"] == "청주시 서원구 분평동"    # 자택은 불변


def test_correction_ignores_unknown_target(monkeypatch):
    """등록에 없는 장소를 target 으로 지어내면 버린다 (실존 라벨만 인정)."""
    s = _place_session()
    monkeypatch.setattr(interview.midm, "extract_correction", _fake_correction(
        {"place_ops": [{"op": "remove", "target": "있지도 않은 공원"}]}))
    assert not interview._apply_correction(s, "있지도 않은 공원 빼주세요")
    assert len(s.draft_attractions) == 2


def test_correction_falls_back_when_llm_returns_nothing(monkeypatch):
    """스텁·호출 실패(빈 결과)면 기존 슬롯 재추출 경로로 폴백해 나이 정정이 살아난다."""
    s = _place_session()
    s.awaiting_confirmation = True

    class _Hit:
        slot = _SLOT

    monkeypatch.setattr(interview.midm, "extract_correction", _fake_correction({}))
    monkeypatch.setattr(interview.retrieval, "rank_next_slots",
                        lambda *a, **k: ([_Hit()], []))
    monkeypatch.setattr(interview.midm, "extract_answer",
                        lambda slot, conv: {"fields": {"age": "83세"},
                                            "attraction_points": [], "behavior_notes": [],
                                            "slot_filled": True})
    out = interview._handle_confirmation(s, "아니요 83세예요")
    assert out.draft_fields["age"] == "83세"


def test_normal_turn_keeps_first_area_text():
    """정정이 아닌 일반 턴은 기존 지역 표기를 지키는 기존 동작 유지."""
    s = _session()
    s.draft_attractions = [{"label": "예전에 살던 집", "area_text": "분평동"}]
    interview._apply_extraction(s, _PLACE_SLOT, {"attraction_points": [
        {"label": "예전에 살던 집", "area_text": "엉뚱한동"}]})
    assert s.draft_attractions[0]["area_text"] == "분평동"
