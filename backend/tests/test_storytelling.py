"""수색 안내 문구 — 입력 관문·조립·검증.

핵심 계약: 자유 텍스트는 톤 파라미터로 내려오지 않는다, 진단명이 문장에
나타나지 않는다, 확정 표현을 쓰지 않는다.
실명은 **노출 허용** 항목이다 — 호명이 수색 행동을 바꾸므로 진단명과 다르다.
"""

from dataclasses import fields as dataclass_fields
from datetime import datetime, timedelta

import pytest

from app import storage
from app.phase3 import storytelling
from app.phase3.storytelling import GuidanceRejected, ToneParams
from app.schemas.case import Case, CaseStatus
from app.schemas.common import GeoPoint
from app.schemas.persona import (
    AttractionEvidence,
    AttractionPoint,
    EnvResponse,
    Persona,
    PersonaType,
)
from app.schemas.report import Appearance, MissingReport

LKP = GeoPoint(lat=37.6061, lng=127.0106)
NOW = datetime(2026, 8, 5, 18, 0)


def _case(elapsed_h: float = 2.0, poa_cells: int = 100) -> Case:
    report = MissingReport(
        id="r1", persona_id="p1", missing_type=PersonaType.dementia, lkp=LKP,
        lkp_time=NOW - timedelta(hours=elapsed_h),
        appearance=Appearance(summary="회색 점퍼·검은 바지·지팡이"),
    )
    return Case(
        id="c1", report=report, status=CaseStatus.searching,
        lkp=LKP, lkp_time=report.lkp_time,
        current_poa={f"cell{i}": 1.0 / poa_cells for i in range(poa_cells)},
    )


def _persona(**over) -> Persona:
    base = dict(
        id="p1", type=PersonaType.dementia, name="김순자", age=78, home=LKP,
    )
    base.update(over)
    return Persona(**base)


# ── 입력 관문 ────────────────────────────────────────────────


def test_tone_params_has_no_free_text_fields():
    """설계 계약: 톤 파라미터에 자유 텍스트 필드가 없어야 한다.

    "제약을 프롬프트가 아니라 입력에 건다"가 이 기능의 법적 방어선이다.
    나중에 편의를 위해 behavior_notes 같은 필드를 끼워넣으려는 시도를
    코드리뷰가 아니라 여기서 깨뜨린다.
    """
    names = {f.name for f in dataclass_fields(ToneParams)}
    forbidden = {
        "behavior_notes", "axis_quotes", "axis_evidence", "axis_scores",
        "home", "attraction_points",
    }
    assert not names & forbidden
    # name 은 의도적으로 허용 — 자유 텍스트가 아니라 단일 고정값이고,
    # 호명이 수색 행동을 바꿔 필요성 테스트를 통과한다.
    assert "name" in names


def test_free_text_never_reaches_tone_params():
    """차단 필드가 가득한 페르소나를 넣어도 톤 파라미터에 흔적이 없다."""
    persona = _persona(
        behavior_notes=["해질녘에 옛 직장 방향으로 걷는 습관"],
        axis_quotes={"a": ["엄마는 물만 보면 다가가세요"]},
        axis_evidence={"a": ["보호자 진술 재서술"]},
        attraction_points=[
            AttractionPoint(
                label="단골 목욕탕", location=LKP,
                evidence=AttractionEvidence.caregiver_report,
            )
        ],
    )
    params = storytelling.to_tone_params(_case(), persona, now=NOW)
    blob = repr(params)
    for leaked in ("옛 직장", "물만 보면", "목욕탕"):
        assert leaked not in blob
    # 실명은 통과 항목이라 여기 있는 게 정상이다.
    assert params.name == "김순자"


def test_persona_type_is_input_only():
    """type 은 어조를 고르는 입력일 뿐, 결과 문장에 드러나면 안 된다(민감정보)."""
    persona = _persona(behavior_tendency="stay")
    text = storytelling.guidance_for(_case(), persona, now=NOW)
    assert "치매" not in text
    assert "장애" not in text


def test_no_persona_still_gives_range_hint():
    """사전 미등록이어도 경과시간만으로 방향은 준다."""
    text = storytelling.guidance_for(_case(elapsed_h=1.0), persona=None, now=NOW)
    assert text
    assert "10분" in text  # 짧은 경과 → 좁게 먼저


# ── 조립 ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "tendency,expected",
    [
        ("stay", "한자리에 머물러"),
        ("move", "쉬지 않고 걷고"),
        ("backtrack", "왔던 길을 되짚어"),
        ("hide", "눈에 잘 띄지 않는"),
    ],
)
def test_tendency_changes_copy(tendency, expected):
    text = storytelling.guidance_for(_case(), _persona(behavior_tendency=tendency), now=NOW)
    assert expected in text


def test_env_response_adds_direction():
    persona = _persona(
        behavior_tendency="move",
        env_responses=[EnvResponse(feature="water", direction="접근", strength=0.7)],
    )
    text = storytelling.guidance_for(_case(), persona, now=NOW)
    assert "물가" in text
    assert "하천변" in text


def test_avoidance_is_also_a_direction():
    """회피도 시민이 볼 곳을 바꾸므로 유효한 지시다."""
    persona = _persona(env_responses=[EnvResponse(feature="forest", direction="회피", strength=0.6)])
    text = storytelling.guidance_for(_case(), persona, now=NOW)
    assert "피하셨을" in text


def test_only_first_env_hint_used():
    """지시를 여러 개 주면 시민이 어디로 갈지 못 정한다."""
    persona = _persona(env_responses=[
        EnvResponse(feature="water", direction="접근", strength=0.7),
        EnvResponse(feature="market", direction="접근", strength=0.6),
    ])
    text = storytelling.guidance_for(_case(), persona, now=NOW)
    assert "하천변" in text
    assert "시장" not in text


def test_spread_changes_closing():
    """범위는 별도 문장이 아니라 맺음말로만 반영한다 — 수색 탭에 지도와 누적
    확률이 이미 있어 문장으로 또 말하면 중복이다."""
    persona = _persona(behavior_tendency="stay")
    narrow = storytelling.guidance_for(_case(poa_cells=100), persona, now=NOW)
    wide = storytelling.guidance_for(_case(poa_cells=500), persona, now=NOW)
    assert "먼저 살펴봐" in narrow
    assert "넓게 살펴봐" in wide


def test_places_are_capped():
    """넷 이상 나열하면 어디부터 갈지 못 정한다."""
    persona = _persona(
        behavior_tendency="hide",  # 장소 3개
        env_responses=[EnvResponse(feature="water", direction="접근", strength=0.7)],  # +2개
    )
    text = storytelling.guidance_for(_case(), persona, now=NOW)
    places_part = text.split(". ")[-1]
    assert places_part.count(",") <= storytelling.MAX_PLACES - 1


def test_states_are_separated_by_periods():
    """상태 문장이 둘이면 마침표로 이어야 한다 — 공백으로만 이으면
    "있어요 물가 쪽으로…"처럼 한 문장으로 읽힌다(회귀)."""
    persona = _persona(
        behavior_tendency="move",
        env_responses=[EnvResponse(feature="water", direction="접근", strength=0.7)],
    )
    text = storytelling.guidance_for(_case(), persona, now=NOW)
    assert "있어요 물가" not in text
    assert "있어요. 물가" in text


def test_particle_matches_final_consonant():
    """'골목를' 같은 어색한 조사가 나오지 않는다."""
    text = storytelling.guidance_for(_case(), _persona(behavior_tendency="stay"), now=NOW)
    assert "그늘을" in text  # 받침 있음 → 을
    assert "그늘를" not in text


def test_unknown_tendency_is_ignored():
    """컴파일러가 새 값을 내놓아도 문장이 깨지지 않는다(닫힌 어휘 가드)."""
    text = storytelling.guidance_for(_case(), _persona(behavior_tendency="teleport"), now=NOW)
    assert text  # 경과시간 안내로 폴백


# ── 출력 검증 ────────────────────────────────────────────────


def test_validate_rejects_certainty():
    with pytest.raises(GuidanceRejected):
        storytelling.validate("실종자는 정릉천에 있습니다")


def test_validate_rejects_condition_disclosure():
    with pytest.raises(GuidanceRejected):
        storytelling.validate("치매가 있으셔서 길을 잃으셨어요")


def test_real_name_is_allowed():
    """실명은 노출 허용 항목이다 — 경찰 실종경보가 이미 공개하고, 무엇보다
    호명하면 반응할 수 있어 수색 행동을 바꾼다. 진단명과 성격이 다르다."""
    storytelling.validate("김순자 님을 찾고 있어요", _persona())


def test_name_appears_as_subject():
    text = storytelling.guidance_for(_case(), _persona(behavior_tendency="stay"), now=NOW)
    assert text.startswith("김순자 님은")


def test_no_name_when_persona_absent():
    """사전 미등록이면 이름이 없다 — 없는 걸 지어내지 않는다."""
    text = storytelling.guidance_for(_case(), persona=None, now=NOW)
    assert "님은" not in text


def test_validate_rejects_blocked_field_words():
    """차단 필드 어절이 새어나오면 관문이 뚫린 것 — 심층 방어."""
    persona = _persona(behavior_notes=["해질녘에 옛 직장 방향으로 걷는 습관"])
    with pytest.raises(GuidanceRejected):
        storytelling.validate("해질녘에 자주 다니시던 길을 봐주세요", persona)


def test_validate_rejects_too_long():
    with pytest.raises(GuidanceRejected):
        storytelling.validate("가" * 500)


def test_guidance_for_returns_empty_on_rejection(monkeypatch):
    """검증 실패가 수색 화면을 깨뜨리지 않는다."""
    monkeypatch.setattr(storytelling, "build_guidance", lambda p: "실종자는 여기에 있습니다")
    assert storytelling.guidance_for(_case(), _persona(), now=NOW) == ""


def test_all_templates_pass_own_validator():
    """모든 조합이 자기 검증기를 통과해야 한다 — 템플릿에 금칙어가 섞이면
    운영 중에 안내가 조용히 사라진다."""
    persona_base = _persona()
    for tendency in list(storytelling._TENDENCY_HINT) + [None]:
        for feature, direction in storytelling._ENV_HINT:
            persona = _persona(
                behavior_tendency=tendency,
                env_responses=[EnvResponse(feature=feature, direction=direction, strength=0.5)],
            )
            for cells in (100, 500):
                text = storytelling.guidance_for(_case(poa_cells=cells), persona, now=NOW)
                assert text, f"빈 문구: {tendency}/{feature}/{direction}/{cells}"
    storytelling.validate(storytelling.guidance_for(_case(), persona_base, now=NOW), persona_base)


# ── API ─────────────────────────────────────────────────────


def test_guidance_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    case = _case()
    persona = _persona(behavior_tendency="stay")
    storage.cases.save(case.id, case)
    storage.personas.save(persona.id, persona)
    try:
        r = TestClient(app).get(f"/phase3/cases/{case.id}/guidance")
        assert r.status_code == 200
        body = r.json()
        assert body["personalized"] is True
        assert "한자리에 머물러" in body["guidance"]
    finally:
        storage.cases.delete(case.id)
        storage.personas.delete(persona.id)
