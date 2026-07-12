"""건물 높이 레이어 테스트 — fixture JSON 사용, 외부 API 안 침.

fixture: 정릉동 반경 800m 건물 276개 (도로망·환경 레이어 fixture 와 동일 중심점).
재생성: python scripts/make_building_fixture.py
"""

import json
from pathlib import Path

import pytest

from app.geo.envlayer import _parse_height_m, _parse_levels

FIXTURE = Path(__file__).parent / "fixtures" / "jeongneung_buildings_800m.json"


@pytest.fixture(scope="module")
def buildings() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_buildings_found(buildings):
    assert len(buildings) > 50


def test_every_building_has_polygon(buildings):
    for b in buildings:
        assert set(b) >= {"geometry", "height_m", "levels", "name"}
        assert len(b["geometry"]) >= 3  # 폴리곤 최소 꼭짓점
        for pt in b["geometry"]:
            assert len(pt) == 2  # [lng, lat]


def test_height_nonnegative_when_present(buildings):
    for b in buildings:
        if b["height_m"] is not None:
            assert b["height_m"] > 0
        if b["levels"] is not None:
            assert b["levels"] > 0


def test_some_buildings_have_height(buildings):
    # 정릉동 fixture 영역엔 building:levels 태그가 붙은 건물이 다수 존재해야 함
    with_height = sum(1 for b in buildings if b["height_m"] is not None)
    assert with_height > len(buildings) * 0.3


def test_parse_height_m_prefers_height_tag():
    assert _parse_height_m({"height": "12.5"}) == 12.5
    assert _parse_height_m({"height": "9 m"}) == 9.0


def test_parse_height_m_falls_back_to_levels():
    # height 태그 없음, levels=4 → 4 * settings.building_level_height_m(기본 3.0)
    assert _parse_height_m({"building:levels": "4"}) == 12.0


def test_parse_height_m_none_when_untagged():
    assert _parse_height_m({}) is None
    assert _parse_height_m({"height": "not-a-number", "building:levels": "also-bad"}) is None


def test_parse_levels_handles_float_strings():
    assert _parse_levels({"building:levels": "3"}) == 3
    assert _parse_levels({}) is None
    assert _parse_levels({"building:levels": "garbage"}) is None
