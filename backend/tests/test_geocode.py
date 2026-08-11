"""지오코딩 — gazetteer 매칭 + draft → AttractionPoint 변환 검증.

기본 백엔드 테스트는 오프라인 gazetteer 로 결정적으로. 카카오(네트워크·키)는
KAKAO_REST_KEY 있을 때만 도는 live 테스트로 분리.
"""

import io
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
    # 근거 태그 없는 draft → mention_only 계수 0.3 (evidence 곱셈 병합의 출발값)
    assert all(p.weight == 0.3 for p in points)
    assert all(p.precision == "dong" for p in points)   # gazetteer → 동 단위
    assert len(unresolved) == 1 and unresolved[0]["label"] == "미상 장소"


def test_positional_suffix_falls_back_to_base_name():
    """'대흥역 2번 출구'는 지오코더가 못 찾지만 '대흥역'은 찾는다 (라이브 실측 2026-07-22).

    보호자는 만난 지점을 그대로 말하므로("○○역 2번 출구", "○○아파트 앞"),
    핵심 지명 폴백이 없으면 **과거 발견지가 좌표를 못 얻어 통째로 사라진다.**
    """
    from app.geo.geocode import GeoResult, base_place_name
    from app.schemas.common import GeoPoint

    assert base_place_name("대흥역 2번 출구") == "대흥역"
    assert base_place_name("성산아파트 앞 근처") == "성산아파트"
    assert base_place_name("망원시장") == "망원시장"

    class _ExactGeo:
        def locate(self, q, anchor=None):
            if q == "대흥역":
                return GeoResult(GeoPoint(lat=37.5470, lng=126.9435), "poi", "test")
            return None

    points, unresolved = to_attraction_points(
        [{"label": "대흥역 2번 출구", "area_text": "대흥역 2번 출구"}], geocoder=_ExactGeo())
    assert not unresolved
    assert points[0].label == "대흥역 2번 출구"      # 라벨은 보호자 표현 그대로 보존
    assert points[0].location.lat == 37.5470        # 좌표는 핵심 지명으로 확보


def test_to_attraction_points_passes_through_origin_slot():
    """origin_slot(작업4, unfamiliarity 게이지 폴백 판단용)이 draft → AttractionPoint 로 그대로 전달."""
    drafts = [
        {"label": "정릉시장", "area_text": "정릉동", "origin_slot": "routine_destinations"},
        {"label": "옛 직장", "area_text": "면목동"},   # origin_slot 없는 기존 draft(하위호환)
    ]
    points, unresolved = to_attraction_points(drafts, geocoder=GazetteerGeocoder())
    by_label = {p.label: p for p in points}
    assert by_label["정릉시장"].origin_slot == "routine_destinations"
    assert by_label["옛 직장"].origin_slot == ""


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


# ── home 앵커 (전국 오검색 방어) ─────────────────────────────────────
def test_anchor_filters_far_matches_to_unresolved():
    """앵커(집) 기준 ANCHOR_MAX_KM 밖 매칭은 채택하지 않고 미해결 처리.

    라이브 실측 버그 재현: "은행 앞"→과천 21km, "산책로"→경북 188km —
    백엔드가 앵커를 무시해도(gazetteer 등) 최종 방어선이 걸러야 한다.
    """
    from app.geo.geocode import GeoPoint

    table = {
        "동네가게": GeoPoint(lat=37.6076, lng=127.0133),   # 정릉동 (집 근처)
        "먼가게": GeoPoint(lat=35.1796, lng=129.0756),     # 부산 (~325km)
    }
    home = GeoPoint(lat=37.6061, lng=127.0106)             # 정릉동 집
    drafts = [{"label": "동네가게"}, {"label": "먼가게"}]
    points, unresolved = to_attraction_points(
        drafts, geocoder=GazetteerGeocoder(table), anchor=home)
    assert [p.label for p in points] == ["동네가게"]
    assert len(unresolved) == 1 and unresolved[0]["label"] == "먼가게"
    assert "오검색 의심" in unresolved[0]["reason"]


def test_kakao_keyword_sends_anchor_params(monkeypatch):
    """앵커가 있으면 카카오 키워드검색에 x/y/radius/sort=distance 가 실린다 (오프라인)."""
    from app.geo.geocode import ANCHOR_MAX_KM, GeoPoint

    captured = {}
    g = KakaoGeocoder("fake-key")

    def fake_get(url, query, extra=None):
        captured["url"] = url
        captured["extra"] = extra
        return [{"y": "37.61", "x": "127.01", "place_name": "가게"}]

    monkeypatch.setattr(g, "_get", fake_get)
    home = GeoPoint(lat=37.6061, lng=127.0106)
    res = g.locate("은행 앞", anchor=home)                 # 상호형 → 키워드검색 먼저
    assert res is not None and res.precision == "poi"
    assert captured["extra"] == {
        "x": home.lng, "y": home.lat,
        "radius": int(ANCHOR_MAX_KM * 1000), "sort": "distance",
    }


def test_attraction_geocode_prefers_label_over_area():
    """라벨(구체 장소)이 area_text(지역)보다 우선 지오코딩된다.

    라이브 실측(2026-07-17): 라벨 "대흥역" + area "대흥동"에서 구버전이
    area 를 먼저 검색해 마커가 동 중심에 찍힘 — 라벨-좌표 불일치.
    """
    from app.geo.geocode import GeoPoint

    station = GeoPoint(lat=37.5476, lng=126.9422)   # 대흥역
    dong = GeoPoint(lat=37.5510, lng=126.9419)      # 대흥동 중심
    g = GazetteerGeocoder({"대흥역": station, "대흥동": dong})
    points, unresolved = to_attraction_points(
        [{"label": "대흥역", "area_text": "대흥동"}], geocoder=g)
    assert not unresolved
    assert abs(points[0].location.lat - station.lat) < 1e-6   # 역 좌표 채택
    assert points[0].label == "대흥역"


# ── 집 주소 후보 사다리 ────────────────────────────────────────────
def test_home_candidates_drops_building_name_before_admin():
    """정밀 → 거침 순서. 도로명까지 살린 후보가 시 이름보다 먼저 나와야 한다."""
    from app.geo.geocode import home_candidates

    cands = home_candidates("하남시 하남대로 856 하남더샵센트럴뷰")
    assert cands[0] == "하남시 하남대로 856 하남더샵센트럴뷰"      # 원문 먼저
    assert "하남시 하남대로 856" in cands                          # 건물명만 뗀 것
    assert cands.index("하남시 하남대로 856") < cands.index("하남시")


def test_locate_home_recovers_when_building_name_blocks_match():
    """아파트 이름이 붙어 통째로 실패하던 정상 주소가 등록된다.

    라이브 실측(2026-08-12): '하남시 하남대로 856 하남더샵센트럴뷰' → None 이라
    finalize 가 ValueError 를 냈고, 보호자가 몇 번을 다시 입력해도 같은 화면이었다.
    """
    from app.geo.geocode import GeoPoint, GeoResult, locate_home

    target = GeoPoint(lat=37.5440, lng=127.2033)

    class ExactGeocoder:
        """실제 지오코더처럼 **정확히 아는 문자열만** 찾는다.

        gazetteer 는 substring 매칭이라 이 상황을 재현하지 못한다 — 건물명이
        붙어도 그냥 걸려 버려서, 사다리가 없어도 통과하는 가짜 초록불이 된다.
        """

        def locate(self, query, anchor=None):
            if query != "하남시 하남대로 856":
                return None
            return GeoResult(target, precision="approx", source="fake", matched=query)

    g = ExactGeocoder()
    assert g.locate("하남시 하남대로 856 하남더샵센트럴뷰") is None   # 사다리 없으면 실패
    res = locate_home(g, "하남시 하남대로 856 하남더샵센트럴뷰")
    assert res is not None
    assert abs(res.point.lat - target.lat) < 1e-6


def test_locate_home_still_none_when_nothing_matches():
    """못 찾은 걸 찾은 척하지 않는다 — 호출부의 ValueError 가 살아 있어야 한다."""
    from app.geo.geocode import locate_home

    assert locate_home(GazetteerGeocoder({}), "전혀 모르는 시골 어딘가") is None


# ── 카카오 인증 실패는 조용하지 않아야 한다 ────────────────────────
def test_kakao_denial_is_logged_once_and_falls_back(capsys, monkeypatch):
    """403(서비스 미활성)이 조용히 미탐 처리되면 키를 넣은 사람이 원인을 못 찾는다.

    실측(2026-08-12): 카카오맵 서비스가 꺼진 채 403 이 나고 있었는데 로그가 없어
    nominatim 폴백으로 계속 돌았고, 좌표 품질만 나쁜 채로 며칠이 지났다.
    다만 끌림점마다 찍히면 안 되므로 상태코드당 한 번만 남긴다.
    """
    import urllib.error
    import urllib.request

    from app.geo import geocode

    monkeypatch.setattr(geocode, "_KAKAO_DENIED_WARNED", set())

    def deny(*_a, **_kw):
        raise urllib.error.HTTPError(
            "https://dapi.kakao.com", 403, "Forbidden", {},
            io.BytesIO(b'{"errorType":"NotAuthorizedError",'
                       b'"message":"App disabled OPEN_MAP_AND_LOCAL service."}'))

    monkeypatch.setattr(urllib.request, "urlopen", deny)

    g = KakaoGeocoder("dummy-key")
    assert g.locate("하남시 하남대로 856") is None      # 미탐으로 물러나 폴백에 넘긴다
    assert g.locate("성수동 철물점") is None

    out = capsys.readouterr().out
    assert out.count("카카오 지오코딩 거부") == 1       # 호출마다가 아니라 한 번만
    assert "403" in out and "OPEN_MAP_AND_LOCAL" in out  # 원인이 그대로 보인다
    assert "dummy-key" not in out                        # 키는 절대 로그로 새지 않는다
