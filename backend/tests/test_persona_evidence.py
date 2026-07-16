"""evidence 태그·preferred_targets 이원화·축 점수 컴파일 — chatbot.md 후속 구현 검증.

핵심 계약:
- 근거(evidence)는 추출 단계에서만 분류 가능 — 추출→세션→지오코딩→prior 프롬프트까지
  어느 단계에서도 증발하지 않는다.
- 카테고리 선호는 지오코딩하지 않고 Persona.preferred_targets 로 분리 저장,
  예측 시점에 LKP 주변 POI 만 매칭한다 (등록된 대상만, 반경·개수 상한).
- evidence → 초기 weight 계수는 팀 회의 미결 — weight 는 아직 1.0 균등이어야 한다.

(축 점수 컴파일은 phase0.axis_scoring — PR #33 — 소관. 여기서 다루지 않는다.)
"""

import pytest

from app.geo import poi
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
    PreferredTarget,
)
from app.schemas.report import MissingReport

LKP = GeoPoint(lat=37.6076, lng=127.0133)


# ── 추출 JSON — place_type/evidence/preferred_targets ────────────────

def test_parse_extract_preserves_evidence_and_preferred_targets():
    raw = """{"fields": {}, "attraction_points": [
        {"label": "옛 직장", "area_text": "면목동",
         "place_type": "workplace", "evidence": "previous_missing_found"}],
      "preferred_targets": [
        {"label": "지하철", "target_type": "transport", "evidence": "caregiver_report"}],
      "behavior_notes": [], "slot_filled": true}"""
    data = prompts.parse_extract(raw)
    assert data["attraction_points"][0]["evidence"] == "previous_missing_found"
    assert data["preferred_targets"][0]["target_type"] == "transport"


def test_parse_extract_failure_has_preferred_targets_key():
    data = prompts.parse_extract("JSON 아님")
    assert data["preferred_targets"] == []


# ── 지오코딩 — 태그 통과, weight 는 아직 균등 ────────────────────────

def test_to_attraction_points_passes_tags_through():
    drafts = [{"label": "옛 직장", "area_text": "면목동",
               "place_type": "workplace", "evidence": "previous_missing_found"}]
    points, unresolved = to_attraction_points(drafts, GazetteerGeocoder())
    assert not unresolved
    ap = points[0]
    assert ap.place_type == "workplace"
    assert ap.evidence == AttractionEvidence.previous_missing_found
    assert ap.weight == 1.0   # evidence→weight 계수는 회의 미결 — 아직 균등이어야 한다


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


def test_apply_extraction_accumulates_preferred_targets():
    s = _session(persona_type=PersonaType.intellectual_disability)
    slot = slot_by_key("preferred_target_seeking")
    interview._apply_extraction(s, slot, {
        "preferred_targets": [{"label": "지하철", "target_type": "transport",
                               "evidence": "mention_only"}]})
    interview._apply_extraction(s, slot, {
        "preferred_targets": [{"label": "지하철", "evidence": "previous_missing_found"},
                              {"label": "자동문", "target_type": "facility"}]})
    assert len(s.draft_preferred) == 2
    assert s.draft_preferred[0]["evidence"] == "previous_missing_found"


# ── finalize — preferred_targets 확정 (지오코딩 없이) ────────────────

def test_finalize_stores_preferred_targets_without_geocoding():
    s = _session(
        persona_type=PersonaType.intellectual_disability,
        draft_fields={"name": "박민수", "age": "24세", "home": "정릉동"},
        draft_preferred=[
            {"label": "지하철", "target_type": "transport", "evidence": "previous_missing_found"},
            {"label": "자동문", "evidence": "이상한값"},   # evidence 무효 → mention_only
            {"target_type": "transport"},                  # label 없음 → 버림
        ],
        awaiting_confirmation=True,
    )
    p = interview.finalize_persona(s, geocoder=GazetteerGeocoder())
    assert [t.label for t in p.preferred_targets] == ["지하철", "자동문"]
    assert p.preferred_targets[0].evidence == AttractionEvidence.previous_missing_found
    assert p.preferred_targets[1].evidence == AttractionEvidence.mention_only


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


# ── POI 매칭 — 등록된 대상만, 반경·개수 상한 ─────────────────────────

class _FakeSearcher:
    """호출 파라미터를 기록하고 고정 POI 를 돌려주는 가짜 카카오."""

    def __init__(self, hits_per_target: int = 5) -> None:
        self.calls: list[tuple[str, int, int]] = []
        self.n = hits_per_target

    def search(self, target, anchor, radius_m, size):
        self.calls.append((target.label, radius_m, size))
        return [(f"{target.label}POI{i}", GeoPoint(lat=37.6 + i * 1e-3, lng=127.01))
                for i in range(self.n)]


def test_match_preferred_targets_caps_and_tags():
    targets = [PreferredTarget(label="지하철", target_type="transport",
                               evidence=AttractionEvidence.previous_missing_found)]
    fake = _FakeSearcher(hits_per_target=5)
    points = poi.match_preferred_targets(targets, LKP, searcher=fake)
    assert len(points) == poi.MAX_POI_PER_TARGET   # 카테고리 일괄 가중 금지 — 상한
    assert fake.calls[0][1] == int(poi.MATCH_RADIUS_KM * 1000)
    assert all(p.precision == "poi" for p in points)
    assert all(p.evidence == AttractionEvidence.previous_missing_found for p in points)
    assert points[0].label == "지하철(지하철POI0)"


def test_match_preferred_targets_stub_without_key():
    points = poi.match_preferred_targets(
        [PreferredTarget(label="지하철")], LKP, searcher=poi.NullPOISearcher())
    assert points == []


def test_kakao_category_code_mapping():
    assert poi._category_code("지하철") == "SW8"
    assert poi._category_code("편의점") == "CS2"
    assert poi._category_code("자동문") is None   # 코드 없음 → 키워드 검색 폴백


# ── pipeline 합류 — 사본에만, 저장 페르소나 불변 ─────────────────────

def test_merge_preferred_pois_returns_copy(monkeypatch):
    from datetime import datetime

    from app.phase2 import pipeline
    from app.schemas.case import Case

    persona = Persona(
        id="p2", type=PersonaType.intellectual_disability, name="박민수", age=24, home=LKP,
        attraction_points=[AttractionPoint(label="단골 역", location=LKP)],
        preferred_targets=[PreferredTarget(label="지하철")],
    )
    case = Case(id="c1", report=MissingReport(
        id="r2", missing_type=PersonaType.intellectual_disability,
        lkp=LKP, lkp_time=datetime(2026, 7, 16, 18, 0)), lkp=LKP,
        lkp_time=datetime(2026, 7, 16, 18, 0))

    matched = [AttractionPoint(label="지하철(성신여대입구역)", location=LKP, precision="poi")]
    monkeypatch.setattr(poi, "match_preferred_targets", lambda targets, lkp, searcher=None: matched)

    merged = pipeline._merge_preferred_pois(persona, case)
    assert [ap.label for ap in merged.attraction_points] == ["단골 역", "지하철(성신여대입구역)"]
    assert [ap.label for ap in persona.attraction_points] == ["단골 역"]   # 원본 불변


def test_merge_preferred_pois_isolates_failure(monkeypatch):
    from datetime import datetime

    from app.phase2 import pipeline
    from app.schemas.case import Case

    persona = Persona(
        id="p3", type=PersonaType.intellectual_disability, name="박민수", age=24, home=LKP,
        preferred_targets=[PreferredTarget(label="지하철")],
    )
    case = Case(id="c2", report=MissingReport(
        id="r3", missing_type=PersonaType.intellectual_disability,
        lkp=LKP, lkp_time=datetime(2026, 7, 16, 18, 0)), lkp=LKP,
        lkp_time=datetime(2026, 7, 16, 18, 0))

    def boom(*a, **kw):
        raise RuntimeError("kakao down")

    monkeypatch.setattr(poi, "match_preferred_targets", boom)
    assert pipeline._merge_preferred_pois(persona, case) is persona   # 매칭 실패 ≠ 예측 실패


def test_merge_preferred_pois_none_persona():
    from app.phase2 import pipeline

    assert pipeline._merge_preferred_pois(None, None) is None


# (축 점수 컴파일 테스트는 tests/test_axis_scoring.py — PR #33 — 에 있다)
