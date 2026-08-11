"""내 주변 산책 장소 — 실제 공원·산책로를 좌표 기준으로 찾는다.

시민 홈의 "내 주변 산책 루트 추천"이 앱에 박힌 고정 목록("경의선 숲길 1.2km" 등)
이었다. 어디서 앱을 켜도 같은 이름이 뜨므로 **내 주변이 아니다** — 거리 숫자까지
붙어 있어 실제로 잰 값처럼 보인다.

OSM 에서 실제 장소를 찾고 거리는 좌표로 계산한다(reverse.py 와 같은 Nominatim,
같은 캐시·초당 1건 정책). 못 찾으면 빈 목록이고 화면이 그 사실을 말한다 —
지어낸 목록을 채워 넣지 않는다.
"""

from __future__ import annotations

import json
import math
import threading
import time
import urllib.parse
import urllib.request

from app.config import settings
from app.schemas.common import GeoPoint

URL = "https://nominatim.openstreetmap.org/search"
_UA = "come-back-home/0.1 (SAR nearby walks)"

# 검색 반경(km). 걸어서 갈 만한 거리 — 이보다 멀면 "내 주변"이 아니다.
RADIUS_KM = 2.0
# 찾을 종류. OSM **이름** 검색이라 한국어 그대로 넣는다. 한 종류당 1초씩
# 걸리므로(초당 1건 정책) 무한정 늘리지 않는다 — 도심 산책로의 대부분이
# 이 네 낱말 중 하나를 이름에 갖는다.
QUERIES = ("공원", "산책로", "숲길", "둘레길")

_ROUND = 3  # ≈110m — 같은 동네면 같은 결과를 재사용
_cache: dict[tuple[float, float], list[dict]] = {}
_lock = threading.Lock()
_last_call = 0.0


def _haversine_km(a: GeoPoint, b: GeoPoint) -> float:
    r = 6371.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp = p2 - p1
    dl = math.radians(b.lng - a.lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _search(query: str, center: GeoPoint, timeout: float) -> list[dict]:
    dlat = RADIUS_KM / 111.32
    dlng = RADIUS_KM / (111.32 * math.cos(math.radians(center.lat)) or 1)
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "limit": 10,
        "accept-language": "ko",
        "viewbox": f"{center.lng - dlng},{center.lat + dlat},{center.lng + dlng},{center.lat - dlat}",
        "bounded": 1,
    })
    req = urllib.request.Request(f"{URL}?{params}", headers={"User-Agent": _UA})
    global _last_call
    with _lock:
        gap = time.monotonic() - _last_call
        if gap < 1.0:
            time.sleep(1.0 - gap)
        _last_call = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def nearby_walks(center: GeoPoint, limit: int = 4) -> list[dict]:
    """가까운 순으로 산책 장소. 실패하거나 없으면 빈 목록."""
    key = (round(center.lat, _ROUND), round(center.lng, _ROUND))
    with _lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit[:limit]

    found: dict[str, dict] = {}
    for q in QUERIES:
        try:
            rows = _search(q, center, settings.geocode_timeout_sec)
        except Exception:  # noqa: BLE001 — 산책 추천이 없다고 홈이 죽으면 안 된다
            continue
        for r in rows:
            name = (r.get("name") or "").strip()
            if not name:
                continue
            try:
                point = GeoPoint(lat=float(r["lat"]), lng=float(r["lon"]))
            except Exception:  # noqa: BLE001
                continue
            dist = _haversine_km(center, point)
            if dist > RADIUS_KM:
                continue
            # 같은 이름이 여러 번 잡히면 가까운 쪽만 남긴다.
            prev = found.get(name)
            if prev is None or dist < prev["distance_km"]:
                found[name] = {
                    "name": name,
                    "lat": point.lat,
                    "lng": point.lng,
                    "distance_km": round(dist, 1),
                    "kind": r.get("type") or "",
                }

    out = sorted(found.values(), key=lambda x: x["distance_km"])
    with _lock:
        _cache[key] = out
    return out[:limit]
