"""Phase 0 finalize — 인터뷰 초안 → 지오코딩 → 확정 Persona 검증 (오프라인 gazetteer)."""

import pytest

from app.geo.geocode import GazetteerGeocoder
from app.phase0 import interview
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
        id="fin2", guardian_name="보호자", persona_type=PersonaType.child,
        draft_fields={"name": "아이", "age": "만 7세", "home": "화곡동"},
    )
    p = interview.finalize_persona(s, geocoder=GazetteerGeocoder())
    assert p.age == 7


def test_finalize_raises_without_geocodable_home():
    s = InterviewSession(
        id="fin3", guardian_name="보호자", persona_type=PersonaType.child,
        draft_fields={"name": "아이", "age": 7, "home": "지도에없는곳"},
    )
    with pytest.raises(ValueError):
        interview.finalize_persona(s, geocoder=GazetteerGeocoder())
