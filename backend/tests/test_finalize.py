"""Phase 0 finalize — 인터뷰 초안 → 지오코딩 → 확정 Persona 검증 (오프라인 gazetteer)."""

import pytest

from app.geo.geocode import GazetteerGeocoder, GeoResult
from app.phase0 import interview
from app.schemas.common import GeoPoint
from app.schemas.persona import InterviewSession, PersonaType


def test_finalize_builds_persona_with_geocoded_home_and_dedup():
    s = InterviewSession(
        id="fin1", guardian_name="보호자", persona_type=PersonaType.dementia,
        draft_fields={"name": "김순자", "age": "78세", "home": "성북구 정릉동"},
        draft_attractions=[
            {"label": "옛 직장", "area_text": "면목동"},
            {"label": "집 근처", "area_text": "정릉동"},
            {"label": "옛 직장", "area_text": "면목동"},   # 중복
        ],
        draft_behaviors=["길 잃으면 계속 걸음"], awaiting_confirmation=True,
    )
    p = interview.finalize_persona(s, geocoder=GazetteerGeocoder())

    assert p.name == "김순자" and p.age == 78 and p.type == PersonaType.dementia
    assert abs(p.home.lat - 37.6076) < 1e-3 and abs(p.home.lng - 127.0133) < 1e-3  # 정릉동
    labels = [ap.label for ap in p.attraction_points]
    assert labels.count("옛 직장") == 1        # 중복 제거
    assert set(labels) == {"옛 직장", "집 근처"}
    assert all(ap.precision == "dong" for ap in p.attraction_points)
    assert p.behavior_notes == ["길 잃으면 계속 걸음"]
    assert s.persona_id == p.id and s.done and not s.awaiting_confirmation


def test_finalize_age_parsed_from_text():
    s = InterviewSession(
        id="fin2", guardian_name="보호자", persona_type=PersonaType.dementia,
        draft_fields={"name": "김순자", "age": "만 78세", "home": "화곡동"},
    )
    p = interview.finalize_persona(s, geocoder=GazetteerGeocoder())
    assert p.age == 78


def test_finalize_prefers_precise_home_after_removing_nearby_suffix():
    class _SuffixSensitiveGeocoder:
        def locate(self, query, anchor=None):
            if query.endswith("근처"):
                return GeoResult(
                    GeoPoint(lat=37.5894, lng=127.0167),
                    precision="dong", source="gazetteer", matched="성북구",
                )
            if query.endswith("주민센터"):
                return GeoResult(
                    GeoPoint(lat=37.6047214, lng=127.0106113),
                    precision="poi", source="kakao", matched="정릉2동주민센터",
                )
            return None

    session = InterviewSession(
        id="fin-suffix", guardian_name="보호자", persona_type=PersonaType.dementia,
        draft_fields={
            "name": "김순자", "age": 78,
            "home": "서울 성북구 정릉2동 주민센터 근처",
        },
    )
    persona = interview.finalize_persona(session, geocoder=_SuffixSensitiveGeocoder())
    assert persona.home == GeoPoint(lat=37.6047214, lng=127.0106113)


def test_finalize_raises_without_geocodable_home():
    s = InterviewSession(
        id="fin3", guardian_name="보호자", persona_type=PersonaType.dementia,
        draft_fields={"name": "김순자", "age": 78, "home": "지도에없는곳"},
    )
    with pytest.raises(ValueError):
        interview.finalize_persona(s, geocoder=GazetteerGeocoder())


def test_finalize_no_silent_fallback_to_attraction_point():
    """home 미확보 시 끌림점 폴백 금지 — ValueError 로 재질문 유도.

    라이브 실측 버그 재현: Mi:dm 이 home 을 끌림점으로 오추출 →
    draft_fields.home 부재 → (구버전) 첫 끌림점(과거 거주지 면목동!)이
    무경고로 수색 원점이 됨 = 원점 오염. 이제는 반드시 예외.
    """
    s = InterviewSession(
        id="fin4", guardian_name="보호자", persona_type=PersonaType.dementia,
        draft_fields={"name": "김순자", "age": 78},          # home 없음
        draft_attractions=[{"label": "옛집", "area_text": "면목동"}],  # 과거 거주지
        awaiting_confirmation=True,
    )
    with pytest.raises(ValueError, match="집 위치"):
        interview.finalize_persona(s, geocoder=GazetteerGeocoder())
