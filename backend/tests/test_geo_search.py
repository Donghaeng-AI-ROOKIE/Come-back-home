"""신고 화면의 '마지막 목격 장소' 검색(/geo/search).

10/27 운영에서 본 두 가지를 고정한다.
- 꼬리말: "킨텍스 정문"처럼 만난 지점 표현이 붙으면 지오코더가 못 찾는다. 제보
  쪽(#320, tip_flow._geocode_tip_location)처럼 꼬리말을 뗀 이름으로 한 번 더 찾는다.
- 정밀도: "경기 고양시 일산서구 킨텍스로 217-60"은 Nominatim 이 도로(highway)
  중심을 줬다(실제 위치에서 약 2.5km). precision 은 Nominatim 이면 늘 "approx"라
  역("킨텍스")과 도로를 가리지 못한다. 그래서 무엇에 걸렸는지를 따로 알려 준다.
"""
import pytest
from fastapi import HTTPException

from app.api import geo
from app.geo import geocode
from app.geo.geocode import GeoResult, KakaoGeocoder
from app.schemas.common import GeoPoint

KINTEX = GeoPoint(lat=37.6652142, lng=126.7483258)
ROAD_CENTER = GeoPoint(lat=37.6848002, lng=126.7617743)
SEOGU = GeoPoint(lat=37.6779933, lng=126.7453605)
EXIT2 = GeoPoint(lat=37.6655, lng=126.7470)


class _FakeGeo:
    """질의 → 결과 표. 어떤 순서로 무엇을 물었는지 기록한다."""

    def __init__(self, table: dict[str, GeoResult]):
        self.table = table
        self.calls: list[str] = []

    def locate(self, query, anchor=None):
        self.calls.append(query)
        return self.table.get(query)


def _nominatim(point, cls, typ, name):
    return GeoResult(point, precision="approx", source="nominatim", matched=name,
                     detail={"class": cls, "type": typ})


@pytest.fixture
def fake(monkeypatch):
    def install(table):
        g = _FakeGeo(table)
        monkeypatch.setattr(geocode, "get_geocoder", lambda use_nominatim=False: g)
        return g
    return install


def test_suffix_is_stripped_when_the_exact_query_finds_nothing(fake):
    g = fake({"킨텍스": _nominatim(KINTEX, "railway", "station", "킨텍스, 킨텍스로, 일산서구")})
    out = geo.search("킨텍스 정문")
    assert (out.lat, out.lng) == (KINTEX.lat, KINTEX.lng)
    assert g.calls == ["킨텍스 정문", "킨텍스"]


def test_exact_hit_is_unchanged_and_not_retried(fake):
    g = fake({
        "킨텍스역 2번 출구": GeoResult(EXIT2, precision="poi", source="kakao", matched="킨텍스역 2번 출구"),
        "킨텍스역": _nominatim(KINTEX, "railway", "station", "킨텍스역"),
    })
    out = geo.search("킨텍스역 2번 출구")
    assert (out.lat, out.lng, out.label, out.precision, out.source) == (
        EXIT2.lat, EXIT2.lng, "킨텍스역 2번 출구", "poi", "kakao")
    assert g.calls == ["킨텍스역 2번 출구"]


def test_nothing_found_is_still_404_and_a_bare_name_is_asked_once(fake):
    g = fake({})
    with pytest.raises(HTTPException) as e:
        geo.search("이름 없는 골목")
    assert e.value.status_code == 404
    assert g.calls == ["이름 없는 골목"]


def test_a_road_match_is_reported_as_road(fake):
    fake({"경기 고양시 일산서구 킨텍스로 217-60": _nominatim(ROAD_CENTER, "highway", "secondary", "킨텍스로, 대화동")})
    assert geo.search("경기 고양시 일산서구 킨텍스로 217-60").granularity == "road"


def test_a_station_from_nominatim_is_a_point(fake):
    # 시연 검색어. Nominatim 이라 precision 은 approx 지만 역 하나를 정확히 가리킨다.
    fake({"킨텍스": _nominatim(KINTEX, "railway", "station", "킨텍스, 킨텍스로")})
    out = geo.search("킨텍스")
    assert out.precision == "approx"
    assert out.granularity == "point"


@pytest.mark.parametrize(("result", "expected"), [
    (_nominatim(SEOGU, "boundary", "administrative", "일산서구"), "area"),
    (_nominatim(SEOGU, "place", "suburb", "대화동"), "area"),
    (_nominatim(KINTEX, "place", "house", "킨텍스로 217-60"), "point"),
    (GeoResult(SEOGU, precision="dong", source="gazetteer", matched="성북구"), "area"),
    (GeoResult(KINTEX, precision="poi", source="kakao", matched="킨텍스"), "point"),
    (GeoResult(KINTEX, precision="address", source="kakao", detail={"address_type": "ROAD_ADDR"}), "point"),
    (GeoResult(KINTEX, precision="address", source="kakao", detail={"address_type": "REGION_ADDR"}), "point"),
    (GeoResult(ROAD_CENTER, precision="address", source="kakao", detail={"address_type": "ROAD"}), "road"),
    (GeoResult(SEOGU, precision="address", source="kakao", detail={"address_type": "REGION"}), "area"),
    # 분류를 모르면 지점으로 둔다 — 근거 없이 경고를 띄우지 않는다.
    (GeoResult(KINTEX, precision="approx", source="nominatim"), "point"),
])
def test_granularity_by_source(fake, result, expected):
    fake({"검색어": result})
    assert geo.search("검색어").granularity == expected


def test_kakao_address_search_keeps_the_address_type(monkeypatch):
    k = KakaoGeocoder("test-key")
    monkeypatch.setattr(k, "_get", lambda url, query, extra=None: [
        {"x": "126.76", "y": "37.68", "address_name": "경기 고양시 일산서구 킨텍스로", "address_type": "ROAD"}])
    res = k._address("킨텍스로")
    assert res.precision == "address"
    assert res.detail == {"address_type": "ROAD"}
