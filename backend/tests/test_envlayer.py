"""환경 레이어 테스트 — fixture JSON 사용, 외부 API 안 침.

fixture: 정릉동 도로망 fixture 668노드의 env dict (OSM 거리 + EGIS 피복).
재생성: python scripts/make_env_fixture.py
"""

import json
from pathlib import Path

import pytest

from app.geo.envlayer import _nearest_color

FIXTURE = Path(__file__).parent / "fixtures" / "jeongneung_env_800m.json"


@pytest.fixture(scope="module")
def env() -> dict[int, dict]:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw.items()}


def test_all_nodes_have_env(env):
    assert len(env) > 100
    for e in env.values():
        assert set(e) >= {"water_m", "forest_m", "park_m", "market_m",
                          "landcover_l1", "landcover_l3", "landcover_code"}


def test_landcover_mostly_road(env):
    # 도로망 노드는 대부분 피복 세분류 '도로' 위에 있어야 한다 — 분류 정합성 검증
    road = sum(1 for e in env.values() if e["landcover_l3"] == "도로")
    assert road / len(env) > 0.7


def test_jeongneung_stream_detected(env):
    # 정릉동 fixture 영역에는 정릉천이 흐른다 — 물가 100m 이내 노드가 존재해야 함
    near_water = [e for e in env.values() if e["water_m"] is not None and e["water_m"] < 100]
    assert len(near_water) >= 5


def test_distances_nonnegative(env):
    for e in env.values():
        for k in ("water_m", "forest_m", "park_m", "market_m"):
            if e[k] is not None:
                assert e[k] >= 0


def test_nearest_color_matches_close_shade():
    palette = {(247, 64, 40): {"landcover_l3": "도로"}, (48, 160, 40): {"landcover_l3": "활엽수림"}}
    assert _nearest_color(palette, (240, 70, 45))["landcover_l3"] == "도로"
    assert _nearest_color(palette, (56, 152, 48))["landcover_l3"] == "활엽수림"


def test_nearest_color_rejects_far_color():
    palette = {(247, 64, 40): {"landcover_l3": "도로"}}
    assert _nearest_color(palette, (10, 10, 255)) is None  # 전혀 다른 색 → 미상
    assert _nearest_color({}, (1, 2, 3)) is None
