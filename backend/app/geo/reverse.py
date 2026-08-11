"""역지오코딩 — 좌표 → 사람이 읽는 장소 이름.

보호자 제보 알림(피그마 2695:15003)은 제보를 **위치 이름**으로 묶어 보여준다
("[서울특별시 성북구] 정릉로"). 좌표를 그대로 띄우면 보호자가 어디인지 알 수 없다.

geocode.py 는 반대 방향(텍스트 → 좌표)이고 여기는 그 역이다. 카카오 키가 있으면
그쪽이 정밀하지만 키 없이도 동작해야 하므로 Nominatim(OSM, 키 불필요)을 쓴다.

## 왜 캐시가 필수인가
Nominatim 이용약관은 **초당 1건**을 넘기지 말 것을 요구한다. 제보가 여러 건이면
같은 골목이 반복 조회되므로, 좌표를 ~11m 격자로 반올림해 캐시하면 실제 호출은
장소당 한 번으로 줄어든다.

## 실패는 숨기지 않는다
네트워크가 없거나 OSM 에 이름이 없으면 좌표 문자열로 떨어진다 — 빈 문자열이나
"알 수 없음"을 주면 화면이 조용히 비어 보인다.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request

from app.config import settings
from app.schemas.common import GeoPoint

URL = "https://nominatim.openstreetmap.org/reverse"
_UA = "come-back-home/0.1 (SAR guardian tip labels)"

# 좌표 반올림 자릿수 — 4자리 ≈ 11m. 같은 건물 앞 제보들은 한 칸으로 묶인다.
_ROUND = 4

_cache: dict[tuple[float, float], str] = {}
# 실패도 기억한다 — 안 그러면 OSM 이 죽어 있을 때 **모든 요청이** 타임아웃을 다시
# 물어 경보 목록 조회가 통째로 느려진다. 단 영구는 아니다(일시 장애면 곧 복구).
_failed_at: dict[tuple[float, float], float] = {}
_FAIL_TTL_SEC = 600.0
_lock = threading.Lock()
_last_call = 0.0


def _fallback(point: GeoPoint) -> str:
    return f"{point.lat:.4f}, {point.lng:.4f}"


def _compose(addr: dict) -> str:
    """OSM address 필드 → "[시 구] 도로명" 한 줄.

    구/동까지만 쓰고 번지·우편번호는 버린다 — 제보 위치는 **구역**을 알리는 것이
    목적이고, 번지까지 붙이면 실제보다 정밀해 보인다(제보 위치는 목격자가 찍은
    대략적인 지점이다).
    """
    city = addr.get("city") or addr.get("province") or addr.get("state") or ""
    borough = addr.get("borough") or addr.get("county") or ""
    spot = (
        addr.get("road")
        or addr.get("suburb")
        or addr.get("quarter")
        or addr.get("neighbourhood")
        or addr.get("village")
        or ""
    )
    head = " ".join(x for x in (city, borough) if x)
    if head and spot:
        return f"[{head}] {spot}"
    return spot or head


def label_for(point: GeoPoint, fallback: str | None = None, timeout: float | None = None) -> str:
    """좌표 하나의 장소 이름.

    @param fallback 조회 실패 시 돌려줄 값. `None` 이면 좌표 문자열.
        빈 문자열을 주면 "이름을 모른다"는 뜻이 되어 화면이 다른 문구로 물러난다 —
        경보의 지역 표시가 이 방식이다(좌표를 지역명 자리에 넣으면 안 된다).
    """
    key = (round(point.lat, _ROUND), round(point.lng, _ROUND))
    fb = _fallback(point) if fallback is None else fallback
    with _lock:
        hit = _cache.get(key)
        if hit is None:
            failed = _failed_at.get(key)
            if failed is not None and time.monotonic() - failed < _FAIL_TTL_SEC:
                return fb
    if hit is not None:
        return hit

    global _last_call
    params = urllib.parse.urlencode({
        "lat": point.lat,
        "lon": point.lng,
        "format": "json",
        # 17 = 도로 단위. 18 이상은 상호(미용실 등)까지 나와서 "제보 위치"로는
        # 지나치게 좁고, 15 이하는 동 단위라 어느 골목인지 알 수 없다.
        "zoom": 17,
        "accept-language": "ko",
    })
    req = urllib.request.Request(f"{URL}?{params}", headers={"User-Agent": _UA})
    try:
        with _lock:
            # 이용약관(초당 1건) 준수 — 잠금 안에서 간격을 벌린다.
            gap = time.monotonic() - _last_call
            if gap < 1.0:
                time.sleep(1.0 - gap)
            _last_call = time.monotonic()
        with urllib.request.urlopen(req, timeout=timeout or settings.geocode_timeout_sec) as resp:
            row = json.loads(resp.read().decode("utf-8"))
        label = _compose(row.get("address") or {})
    except Exception:  # noqa: BLE001 — 이름이 없다고 제보 목록이 죽으면 안 된다
        with _lock:
            _failed_at[key] = time.monotonic()
        return fb
    if not label:
        with _lock:
            _failed_at[key] = time.monotonic()
        return fb

    with _lock:
        _cache[key] = label
        _failed_at.pop(key, None)
    return label


def labels_for(points: list[GeoPoint]) -> list[str]:
    """여러 좌표를 한 번에. 캐시 덕분에 같은 장소는 한 번만 조회된다."""
    return [label_for(p) for p in points]


def cached_label(point: GeoPoint) -> str:
    """**네트워크를 타지 않는** 조회 — 캐시에 있으면 이름, 없으면 빈 문자열.

    경보 목록(`GET /phase3/alerts`)은 시민 앱이 15초마다 부르는 폴링 경로다. 거기서
    외부 호출을 하면 OSM 이 느린 날 경보가 통째로 늦어진다 — 골든타임에 가장 하면
    안 되는 일이다. 그래서 그 경로는 캐시만 읽고, 채우는 일은 신고 접수 때
    `warm()` 이 미리 해 둔다.
    """
    key = (round(point.lat, _ROUND), round(point.lng, _ROUND))
    with _lock:
        return _cache.get(key, "")


def warm(point: GeoPoint) -> None:
    """캐시를 미리 채운다(신고 접수 시 1회). 실패는 조용히 넘긴다 — 이름이 없어도
    경보는 나가야 하고, 앱은 "내 주변"으로 물러난다."""
    try:
        label_for(point, fallback="")
    except Exception:  # noqa: BLE001
        pass
