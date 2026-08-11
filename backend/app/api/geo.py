"""지오 API — 좌표를 사람이 읽는 장소 이름으로 바꾼다.

보호자 제보 알림이 제보를 위치별로 묶어 보여주는데, 묶음 제목이 좌표면 보호자가
어디인지 알 수 없다. 묶음은 앱이 만들고(같은 골목 제보를 한 카드로), 이름만
서버가 붙인다 — 외부 지오코딩 키·이용약관(초당 1건)·캐시를 앱마다 다루게 하는
것보다 서버 한 곳이 낫다.
"""

import threading
import urllib.request

from fastapi import APIRouter, HTTPException, Response
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
    result = geocode.get_geocoder(use_nominatim=True).locate(query)
    if result is None:
        raise HTTPException(404, "장소를 찾지 못했습니다")
    return PlaceOut(
        lat=result.point.lat, lng=result.point.lng,
        # 검색어보다 **매칭된 정식 명칭**을 우선한다 — "하남시청역"으로 찾아도
        # 화면에는 "하남시청역 5호선" 처럼 무엇에 걸렸는지 보이는 편이 낫다.
        label=result.matched or query,
        precision=result.precision, source=result.source,
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
def nearby_walks(lat: float, lng: float, limit: int = 4) -> list[NearbyWalk]:
    """내 주변 산책 **루트** — 실제 OSM 산책로의 좌표열까지.

    이름과 지도 한 장만 주면 어디를 어떻게 걷는 길인지 알 수 없다. 길의 실제
    모양(path)과 실제 길이(route_km)를 함께 준다 — 직선거리를 "걸어서 N km"로
    적으면 잰 적 없는 숫자가 된다. 못 찾으면 빈 목록이고 앱이 그 사실을 말한다.
    """
    rows = nearby.nearby_walks(GeoPoint(lat=lat, lng=lng), limit=limit)
    return [NearbyWalk(**r) for r in rows]


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
