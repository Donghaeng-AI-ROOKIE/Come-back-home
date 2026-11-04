"""지오 API — 좌표를 사람이 읽는 장소 이름으로 바꾼다.

보호자 제보 알림이 제보를 위치별로 묶어 보여주는데, 묶음 제목이 좌표면 보호자가
어디인지 알 수 없다. 묶음은 앱이 만들고(같은 골목 제보를 한 카드로), 이름만
서버가 붙인다 — 외부 지오코딩 키·이용약관(초당 1건)·캐시를 앱마다 다루게 하는
것보다 서버 한 곳이 낫다.
"""

import threading
import urllib.request

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from app.geo import geocode, nearby, reverse
from app.schemas.common import GeoPoint

router = APIRouter(prefix="/geo", tags=["지오 — 좌표 ↔ 장소명"])


class LabelsIn(BaseModel):
    points: list[GeoPoint]


class LabelsOut(BaseModel):
    labels: list[str]


class PlaceOut(BaseModel):
    """장소 검색 1건 — 신고 화면의 '마지막 목격 장소'가 쓴다."""
    lat: float
    lng: float
    label: str
    precision: str
    source: str
    # 이 좌표가 무엇을 가리키는가 — point(건물·역 같은 한 지점) | road(도로) | area(동·구).
    # 신고 화면은 road·area 일 때 위치를 확인해 달라고 안내한다(_granularity 참고).
    granularity: str = "point"


# Nominatim 의 place 분류 가운데 한 지점(번지)을 가리키는 것. 나머지(suburb·quarter·
# city …)는 동네·도시 대표점이다.
_PLACE_POINT_TYPES = {"house"}


def _granularity(res: geocode.GeoResult) -> str:
    """좌표가 한 지점인가, 도로·지역의 대표점인가.

    `precision` 만으로는 가릴 수 없다. Nominatim 결과는 무엇에 걸렸든 모두 "approx" 다
    (geocode.NominatimGeocoder). 10/27 실측: 시연 검색어 "킨텍스"는 역(railway
    station)을 정확히 찾았고, "경기 고양시 일산서구 킨텍스로 217-60"은 도로
    (highway) 중심을 줘 실제 위치에서 약 2.5km 떨어졌다 — 둘 다 "approx" 였다.
    그래서 출처가 주는 분류를 본다. 분류를 모르면 지점으로 둔다(근거 없이 경고하지 않는다).
    """
    detail = res.detail or {}
    if res.source == "gazetteer" or res.precision == "dong":
        return "area"
    if res.source == "nominatim":
        cls = detail.get("class")
        if cls == "highway":
            return "road"
        if cls == "boundary" or (cls == "place" and detail.get("type") not in _PLACE_POINT_TYPES):
            return "area"
        return "point"
    if res.source == "kakao" and res.precision == "address":
        # 카카오 주소검색 address_type: REGION(지명)·ROAD(도로명)·REGION_ADDR·ROAD_ADDR(번지까지).
        kind = detail.get("address_type")
        if kind == "ROAD":
            return "road"
        if kind == "REGION":
            return "area"
    return "point"


@router.get("/search", response_model=PlaceOut)
def search(q: str) -> PlaceOut:
    """장소·주소 문자열 → 좌표. **앱의 주소 검색이 이걸 쓴다.**

    앱은 원래 `expo-location` 의 `geocodeAsync` 를 불렀는데 그 함수는 **웹에서
    동작하지 않는다.** 배포본이 웹이라 주소 검색이 늘 실패했고, 좌표가 없으니
    지도는 시안 목업 이미지(미국 지도)에 머물고 신고 버튼도 막혔다 —
    "장소를 입력해도 지도가 안 바뀐다"의 정체(현장 제보 08-12).

    서버가 하는 편이 낫기도 하다. 카카오 키·이용약관·캐시를 앱마다 다루지 않고
    한 곳에서 처리하며, 이미 온보딩 끌림점이 쓰는 것과 **같은 지오코더 체인**
    (카카오 → Nominatim → 내장 지명사전)을 타므로 두 경로가 같은 좌표를 준다.
    """
    query = (q or "").strip()
    if not query:
        raise HTTPException(400, "검색어가 비어 있습니다")
    geocoder = geocode.get_geocoder(use_nominatim=True)
    # "킨텍스 정문", "대화역 2번 출구"처럼 만난 지점 표현이 붙으면 지오코더가 못 찾는다.
    # 제보 장소(phase3.tip_flow._geocode_tip_location, #320)와 같이 원문을 먼저 찾고,
    # 못 찾았을 때만 꼬리말을 뗀 이름으로 한 번 더 찾는다. 원문이 찾히면 결과는 그대로다.
    result = None
    for candidate in dict.fromkeys((query, geocode.base_place_name(query))):
        result = geocoder.locate(candidate)
        if result is not None:
            break
    if result is None:
        raise HTTPException(404, "장소를 찾지 못했습니다")
    return PlaceOut(
        lat=result.point.lat, lng=result.point.lng,
        # 검색어보다 **매칭된 정식 명칭**을 우선한다 — "하남시청역"으로 찾아도
        # 화면에는 "하남시청역 5호선" 처럼 무엇에 걸렸는지 보이는 편이 낫다.
        label=result.matched or query,
        precision=result.precision, source=result.source,
        granularity=_granularity(result),
    )


@router.post("/labels", response_model=LabelsOut)
def labels(body: LabelsIn) -> LabelsOut:
    """좌표 목록 → 장소명 목록 (입력과 같은 순서).

    이름을 못 찾으면 그 자리는 좌표 문자열이 된다 — 목록이 통째로 실패하지
    않게 하려는 것이다(제보를 못 보는 것이 이름을 못 보는 것보다 나쁘다).
    """
    return LabelsOut(labels=reverse.labels_for(body.points))


class NearbyWalk(BaseModel):
    name: str
    lat: float                    # 대표점(경로 중간) — 썸네일 중심
    lng: float
    distance_km: float            # 내 위치 → 그 길의 가장 가까운 지점(직선)
    route_km: float = 0.0         # 길 자체의 길이 — 화면에 적는 "코스 N km"
    kind: str = ""                # 'park'(둘레길) | 'path'(산책로)
    path: list[GeoPoint] = []     # 실제 좌표열 — 앱이 지도에 그린다


@router.get("/nearby-walks", response_model=list[NearbyWalk])
def nearby_walks(lat: float = Query(ge=-90, le=90), lng: float = Query(ge=-180, le=180),
                 limit: int = Query(default=4, ge=1, le=12)) -> list[NearbyWalk]:
    """Disabled recommendations: older clients receive an immediate empty list."""
    return nearby.nearby_walks(GeoPoint(lat=lat, lng=lng), limit=limit)


# ── 지도 타일 중계 ────────────────────────────────────────────
# 폰에서 tile.openstreetmap.org 가 안 열리는 사례가 나왔다(학교 WiFi·이동통신
# 양쪽에서 지도가 회색으로만 떴다 — 실측 08-11). 원인이 망 정책인지 OSM 쪽
# 제한인지 단정할 수 없고, 시연·실험 중에 지도가 안 뜨는 건 치명적이다.
# **앱이 이미 붙어 있는 우리 서버가 대신 받아 준다** — 앱은 외부 호스트를
# 직접 부르지 않는다. 받아 둔 타일은 메모리에 캐시해 같은 칸을 다시 안 받는다.
_TILE_UA = "come-back-home/0.1 (SAR demo; contact: jodaeheum800@gmail.com)"
_tile_cache: dict[str, bytes] = {}
_tile_lock = threading.Lock()
_TILE_CACHE_MAX = 3000   # 256px png 약 15KB × 3000 ≈ 45MB


@router.get("/tiles/{z}/{x}/{y}.png")
def map_tile(z: int, x: int, y: int) -> Response:
    """OSM 래스터 타일 중계. 실패하면 404 — 앱은 회색 배경으로 물러난다."""
    if not (0 <= z <= 19):
        raise HTTPException(400, "허용되지 않는 확대 수준입니다.")
    key = f"{z}/{x}/{y}"
    with _tile_lock:
        hit = _tile_cache.get(key)
    if hit is not None:
        return Response(content=hit, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=604800"})

    url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _TILE_UA})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read()
    except Exception as e:  # noqa: BLE001 — 타일 하나가 전체를 막지 않는다
        raise HTTPException(404, f"타일을 가져오지 못했습니다: {type(e).__name__}") from e

    with _tile_lock:
        if len(_tile_cache) >= _TILE_CACHE_MAX:
            _tile_cache.clear()   # 단순 비우기 — LRU 를 둘 만큼 크지 않다
        _tile_cache[key] = data
    return Response(content=data, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=604800"})
