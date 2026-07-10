"""지오코딩 — gazetteer 매칭 + draft → AttractionPoint 변환 검증.

기본 백엔드 테스트는 오프라인 gazetteer 로 결정적으로. 카카오(네트워크·키)는
KAKAO_REST_KEY 있을 때만 도는 live 테스트로 분리.
"""

import os

import pytest

from app.geo.geocode import GazetteerGeocoder, KakaoGeocoder, to_attraction_points


def test_gazetteer_prefers_dong_over_gu():
    g = GazetteerGeocoder()
    # '성북구 정릉동'에서 구가 아니라 더 구체적인 동을 잡아야 한다
    loc = g.geocode("성북구 정릉동 정릉초 근처")
    assert loc is not None
    assert abs(loc.lat - 37.6076) < 1e-3 and abs(loc.lng - 127.0133) < 1e-3


def test_gazetteer_substring_match():
    g = GazetteerGeocoder()
    assert g.geocode("면목동에서 방앗간을 오래 하셨어요") is not None
    assert g.geocode("강서구 화곡동 살아요") is not None


def test_gazetteer_miss_returns_none():
    g = GazetteerGeocoder()
    assert g.geocode("전혀 모르는 시골 어딘가") is None
    assert g.geocode("") is None


def test_to_attraction_points_splits_resolved_and_unresolved():
    drafts = [
        {"label": "옛 직장", "area_text": "면목동"},
        {"label": "집 근처", "area_text": "정릉동"},
        {"label": "미상 장소", "area_text": "이름없는곳"},
    ]
    # 결정적 검증 위해 오프라인 gazetteer 명시
    points, unresolved = to_attraction_points(drafts, geocoder=GazetteerGeocoder())
    assert len(points) == 2
    assert {p.label for p in points} == {"옛 직장", "집 근처"}
    assert all(p.weight == 1.0 for p in points)
    assert all(p.precision == "dong" for p in points)   # gazetteer → 동 단위
    assert len(unresolved) == 1 and unresolved[0]["label"] == "미상 장소"


def test_to_attraction_points_falls_back_to_label_when_no_area():
    drafts = [{"label": "화곡동"}]  # area_text 없음 → label 로 지오코딩 시도
    points, unresolved = to_attraction_points(drafts, geocoder=GazetteerGeocoder())
    assert len(points) == 1 and not unresolved


def test_looks_like_region_heuristic():
    """순수 지역명 판별 — 마지막 토큰이 행정구역 접미사인지 (오프라인)."""
    from app.geo.geocode import _looks_like_region

    assert _looks_like_region("면목동")
    assert _looks_like_region("성북구 정릉동")
    assert _looks_like_region("서울특별시")
    assert not _looks_like_region("면목동 방앗간")   # 상호 포함
    assert not _looks_like_region("서울숲")          # 랜드마크
    assert not _looks_like_region("정릉초등학교")


@pytest.mark.skipif(not os.environ.get("KAKAO_REST_KEY"), reason="카카오 키 없음 (live)")
def test_kakao_keyword_returns_poi_precision():
    """구체 장소명 → 키워드검색 → 실제 상호 건물 좌표(precision=poi). (네트워크)"""
    g = KakaoGeocoder(os.environ["KAKAO_REST_KEY"])
    res = g.locate("정릉동 방앗간")
    assert res is not None
    assert res.precision == "poi" and res.source == "kakao"
    assert 37.0 < res.point.lat < 38.0 and 126.5 < res.point.lng < 127.5


@pytest.mark.skipif(not os.environ.get("KAKAO_REST_KEY"), reason="카카오 키 없음 (live)")
def test_kakao_region_name_uses_address_not_random_poi():
    """순수 지역명 '면목동' → 주소검색(동 좌표), 엉뚱한 랜드마크 금지. (네트워크)"""
    g = KakaoGeocoder(os.environ["KAKAO_REST_KEY"])
    res = g.locate("면목동")
    assert res is not None
    assert res.precision == "address"          # 키워드(poi) 아니라 주소여야
    assert 37.57 < res.point.lat < 37.61       # 중랑구 면목동 근처
