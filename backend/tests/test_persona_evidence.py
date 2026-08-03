"""evidence 태그·축 점수 컴파일 — chatbot.md 후속 구현 검증.

핵심 계약:
- 근거(evidence)는 추출 단계에서만 분류 가능 — 추출→세션→지오코딩→prior 프롬프트까지
  어느 단계에서도 증발하지 않는다.
- evidence → 초기 weight 계수(0.9/0.5/0.3)로 출발하고, Phase 2 에서 EXAONE
  상/중/하 등급과 곱셈 병합된다 (팀 결정 2026-07-21).

(축 점수 컴파일은 phase0.axis_scoring — PR #33 — 소관. 여기서 다루지 않는다.)
"""

import pytest

from app.geo.geocode import GazetteerGeocoder, coerce_evidence, to_attraction_points
from app.llm.exaone import _build_prior_input
from app.phase0 import interview, prompts
from app.phase0.slots import slot_by_key
from app.schemas.common import GeoPoint
from app.schemas.persona import (
    AttractionEvidence,
    AttractionPoint,
    InterviewSession,
    Persona,
    PersonaType,
)
from app.schemas.report import MissingReport

LKP = GeoPoint(lat=37.6076, lng=127.0133)


# ── 추출 JSON — place_type/evidence ──────────────────────────────────

def test_parse_extract_preserves_evidence_tags():
    raw = """{"fields": {}, "attraction_points": [
        {"label": "옛 직장", "area_text": "면목동",
         "place_type": "workplace", "evidence": "previous_missing_found"}],
      "behavior_notes": [], "slot_filled": true}"""
    data = prompts.parse_extract(raw)
    assert data["attraction_points"][0]["evidence"] == "previous_missing_found"
    assert data["attraction_points"][0]["place_type"] == "workplace"


def test_parse_extract_failure_has_all_keys():
    data = prompts.parse_extract("JSON 아님")
    assert data["attraction_points"] == [] and data["behavior_notes"] == []
    assert data["fields"] == {} and data["slot_filled"] is False


# ── 지오코딩 — 태그 통과, weight 는 evidence 계수로 출발 ─────────────

def test_to_attraction_points_passes_tags_through():
    drafts = [{"label": "옛 직장", "area_text": "면목동",
               "place_type": "workplace", "evidence": "previous_missing_found"}]
    points, unresolved = to_attraction_points(drafts, GazetteerGeocoder())
    assert not unresolved
    ap = points[0]
    assert ap.place_type == "workplace"
    assert ap.evidence == AttractionEvidence.previous_missing_found
    assert ap.weight == pytest.approx(0.9)   # 발견지 계수 (균등 1.0 아님)


def test_to_attraction_points_weights_by_evidence():
    """근거 강도가 초기 weight 로 내려온다 — 곱셈 병합의 evidence 항."""
    drafts = [
        {"label": "옛 직장", "area_text": "면목동", "evidence": "previous_missing_found"},
        {"label": "정릉시장", "area_text": "정릉동", "evidence": "caregiver_report"},
        {"label": "정릉동", "area_text": "정릉동", "evidence": "mention_only"},
    ]
    points, _ = to_attraction_points(drafts, GazetteerGeocoder())
    assert [p.weight for p in points] == pytest.approx([0.9, 0.5, 0.3])


def test_to_attraction_points_coerces_unknown_evidence():
    drafts = [{"label": "정릉시장", "area_text": "정릉동", "evidence": "확실함"}]
    points, _ = to_attraction_points(drafts, GazetteerGeocoder())
    assert points[0].evidence == AttractionEvidence.mention_only


def test_coerce_evidence_none_and_valid():
    assert coerce_evidence(None) == AttractionEvidence.mention_only
    assert coerce_evidence("caregiver_report") == AttractionEvidence.caregiver_report


def test_attraction_point_backward_compatible():
    """구버전 저장 데이터(태그 없음)가 그대로 파싱돼야 한다."""
    ap = AttractionPoint.model_validate({"label": "옛집", "location": {"lat": 37.6, "lng": 127.0}})
    assert ap.evidence == AttractionEvidence.mention_only and ap.place_type == ""


# ── 세션 누적 — 중복 장소의 근거 승격 ────────────────────────────────

def _session(**kw) -> InterviewSession:
    base = dict(id="s1", guardian_name="보호자", persona_type=PersonaType.dementia)
    return InterviewSession(**{**base, **kw})


def test_apply_extraction_upgrades_evidence_on_duplicate():
    s = _session()
    slot = slot_by_key("autobiographical_destination_pull")
    interview._apply_extraction(s, slot, {
        "attraction_points": [{"label": "옛집", "area_text": "면목동", "evidence": "mention_only"}]})
    interview._apply_extraction(s, slot, {
        "attraction_points": [{"label": "옛집", "area_text": "면목동",
                               "evidence": "previous_missing_found"}]})
    assert len(s.draft_attractions) == 1
    assert s.draft_attractions[0]["evidence"] == "previous_missing_found"
    # 반대 방향(강→약)으로는 내려가지 않는다
    interview._apply_extraction(s, slot, {
        "attraction_points": [{"label": "옛집", "area_text": "면목동", "evidence": "mention_only"}]})
    assert s.draft_attractions[0]["evidence"] == "previous_missing_found"


# ── EXAONE prior 입력 — 근거 태그가 프롬프트에 실린다 ────────────────

def _report() -> MissingReport:
    from datetime import datetime

    return MissingReport(id="r1", missing_type=PersonaType.dementia,
                         lkp=LKP, lkp_time=datetime(2026, 7, 16, 18, 0))


def test_prior_input_annotates_evidence_but_keeps_bare_labels():
    persona = Persona(
        id="p1", type=PersonaType.dementia, name="김순자", age=78, home=LKP,
        attraction_points=[
            AttractionPoint(label="옛집", location=LKP,
                            evidence=AttractionEvidence.previous_missing_found),
            AttractionPoint(label="정릉시장", location=LKP),
        ],
    )
    text = _build_prior_input(persona, _report())
    assert "옛집 — 근거: 과거 실종 때 실제 발견된 곳" in text
    assert "정릉시장 — 근거: 지나가듯 언급만" in text


# (축 점수 컴파일 테스트는 tests/test_axis_scoring.py — PR #33 — 에 있다)
