"""내 주변 산책 **루트** — 실제 산책로의 좌표열을 가져온다.

## 왜 좌표열까지 가져오나
"산책 루트 추천"이라면서 장소 이름과 지도 한 장만 보여주면, 어디를 어떻게 걷는
길인지는 여전히 알 수 없다. 여기서 돌려주는 것은 **그 길의 실제 모양**이다 —
공원이면 둘레길, 산책로면 그 길 자체. 앱은 이 좌표열을 지도에 그린다.

## 왜 Overpass 인가
이름 검색(Nominatim)은 대표 좌표 한 점만 준다. Overpass 는 OSM 원본 way 의
좌표열(`out geom`)을 그대로 주므로 길의 모양과 **실제 길이**를 함께 얻는다.
직선거리를 "걸어서 N km"라고 적으면 그건 잰 적 없는 숫자다.

## 비용
한 번에 15초쯤 걸린다. 그래서 동네 단위(≈110m 격자)로 캐시하고, 앱은 세션 내내
다시 묻지 않는다(useNearbyWalks 의 staleTime: Infinity). 실패하면 빈 목록이다 —
지어낸 길을 그리지 않는다.
"""

from __future__ import annotations

import json
import math
import threading
import urllib.parse
import urllib.request

from app.schemas.common import GeoPoint

# 공개 Overpass 는 자주 504(과부하)를 낸다 — 실측 08-11. 미러를 순서대로 시도한다.
# 시연·현장에서 "가끔 안 나오는 기능"은 없는 기능과 같다.
URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
)
URL = URLS[0]   # 하위호환 — 테스트가 참조한다
_UA = "come-back-home/0.1 (SAR nearby walks)"

# 검색 반경(m). 걸어서 갈 만한 거리 — 이보다 멀면 "내 주변"이 아니다.
RADIUS_M = 2000
# 이보다 짧은 길은 "산책 루트"라고 부르지 않는다(m). 골목 한 토막·놀이터 울타리
# 같은 것들이 이름만 갖고 잔뜩 잡힌다.
MIN_ROUTE_M = 400
# 좌표열 상한 — 썸네일에 그릴 용도라 이보다 촘촘할 필요가 없다.
MAX_POINTS = 120

# leisure=park 는 공원 경계(둘레), highway=footway/path/pedestrian 은 길 자체.
# 둘 다 "걸을 수 있는 선"이라는 점에서 같고, 화면에는 종류를 구분해 적는다.
_QUERY = """[out:json][timeout:25];
(
  way(around:{r},{lat},{lng})["leisure"~"park|garden"]["name"];
  way(around:{r},{lat},{lng})["highway"~"footway|path|pedestrian"]["name"];
);
out geom tags;"""

_ROUND = 3  # ≈110m — 같은 동네면 같은 결과를 재사용
_cache: dict[tuple[float, float], list[dict]] = {}
_lock = threading.Lock()


def _disk_key(key: tuple[float, float]) -> str:
    return f"{key[0]:.3f},{key[1]:.3f}"


def _disk_get(key: tuple[float, float]) -> list[dict] | None:
    """디스크 캐시 — 한 번 받아 두면 Overpass 가 죽어도 그 동네는 계속 나온다.

    지연 임포트: storage 가 이 모듈을 간접 참조할 수 있어 순환을 피한다.
    """
    from app import storage
    return storage.nearby_walks_cache.get(_disk_key(key))


def _disk_put(key: tuple[float, float], rows: list[dict]) -> None:
    from app import storage
    storage.nearby_walks_cache.save(_disk_key(key), rows)


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _length_m(pts: list[tuple[float, float]]) -> float:
    return sum(_haversine_m(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def _thin(pts: list[tuple[float, float]], limit: int = MAX_POINTS) -> list[tuple[float, float]]:
    """균등 간격으로 솎아낸다. 처음과 끝은 반드시 남긴다(길의 양 끝이 잘리면 안 된다)."""
    if len(pts) <= limit:
        return pts
    step = len(pts) / limit
    out = [pts[int(i * step)] for i in range(limit)]
    if out[-1] != pts[-1]:
        out[-1] = pts[-1]
    return out


def _kind_of(tags: dict) -> str:
    if tags.get("leisure") in ("park", "garden"):
        return "park"
    return "path"


def _fetch(center: GeoPoint, timeout: float) -> list[dict]:
    """미러를 차례로 시도한다. 전부 실패하면 마지막 예외를 올린다.

    미러당 timeout 을 짧게 잡는다 — 길게 잡으면 (미러 수 × timeout) 만큼 앱이
    로딩 상태로 멈춰 있는다. 실측: 40초×3 = 최대 120초 동안 화면에 스피너만 돌았다.
    """
    query = _QUERY.format(r=RADIUS_M, lat=center.lat, lng=center.lng)
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    last: Exception | None = None
    for url in URLS:
        try:
            req = urllib.request.Request(url, data=body, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8")).get("elements", [])
        except Exception as e:  # noqa: BLE001 — 다음 미러로 넘어간다
            last = e
            print(f"[nearby] {url} 실패({type(e).__name__}) — 다음 미러 시도")
    raise last if last else RuntimeError("Overpass 미러 없음")


def nearby_walks(center: GeoPoint, limit: int = 4, timeout: float = 12.0) -> list[dict]:
    """가까운 순으로 산책 루트. 실패하거나 없으면 빈 목록.

    각 항목: name / lat·lng(대표점) / distance_km(내 위치→길 시작점 직선)
    / route_km(길의 실제 길이) / kind / path(좌표열)
    """
    key = (round(center.lat, _ROUND), round(center.lng, _ROUND))
    with _lock:
        hit = _cache.get(key)
    if hit is None:
        hit = _disk_get(key)
        if hit is not None:
            with _lock:
                _cache[key] = hit
    if hit is not None:
        return hit[:limit]

    try:
        elements = _fetch(center, timeout)
    except Exception as e:  # noqa: BLE001 — 외부 서비스 실패는 기능 없음으로 처리
        print(f"[nearby] Overpass 실패({type(e).__name__}) — 빈 목록으로 응답")
        return []

    me = (center.lat, center.lng)
    best: dict[str, dict] = {}   # 이름당 하나 — 같은 공원이 여러 way 로 쪼개져 온다
    for el in elements:
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        geom = el.get("geometry") or []
        if not name or len(geom) < 2:
            continue
        pts = [(g["lat"], g["lon"]) for g in geom]
        route_m = _length_m(pts)
        if route_m < MIN_ROUTE_M:
            continue
        # 내 위치에서 그 길의 **가장 가까운 지점**까지. 대표점 하나로 재면 긴
        # 길일수록 실제보다 멀어 보인다(경의선숲길처럼 옆을 지나가는 길이 그렇다).
        near_m = min(_haversine_m(me, p) for p in pts)
        prev = best.get(name)
        if prev is not None and prev["_near_m"] <= near_m:
            continue
        mid = pts[len(pts) // 2]
        best[name] = {
            "name": name,
            "lat": mid[0],
            "lng": mid[1],
            "distance_km": round(near_m / 1000, 2),
            "route_km": round(route_m / 1000, 2),
            "kind": _kind_of(tags),
            "path": [{"lat": la, "lng": ln} for la, ln in _thin(pts)],
            "_near_m": near_m,
        }

    rows = sorted(best.values(), key=lambda r: r["_near_m"])
    for r in rows:
        r.pop("_near_m", None)
    with _lock:
        _cache[key] = rows
    if rows:
        _disk_put(key, rows)   # 빈 결과는 남기지 않는다 — 다음에 다시 시도한다
    return rows[:limit]
