"""지오코딩 — 장소 텍스트(동/랜드마크/상호) → 좌표(GeoPoint) + 정밀도.

Phase 0 온보딩 끌림점(area_text: "면목동 방앗간", "성북구 정릉동" 등)을 Phase 2
시뮬레이션 좌표로 바꾼다. draft → Persona.attraction_points 확정의 끊긴 고리.

정밀도(precision)를 함께 반환 — SAR에서 거친 앵커는 반경 넓게, 정밀 POI는 좁게:
  poi(건물·상호) > address(도로명·지번) > dong(동 중심) > approx(근사)

백엔드 교체형(정밀→거침 순 체인):
- KakaoGeocoder:    카카오 Local — 키워드 장소검색(상호까지 건물 좌표) + 주소검색. ★가장 정밀
- NominatimGeocoder: OSM(네트워크, 키 불필요). 카카오 밖 보강.
- GazetteerGeocoder: 오프라인 사전(결정적·키리스). 최후 폴백·테스트용.
config.kakao_rest_key 있으면 카카오 우선.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint


@dataclass
class GeoResult:
    point: GeoPoint
    precision: str          # poi | address | dong | approx
    source: str             # kakao | nominatim | gazetteer
    matched: str | None = None   # 실제 매칭된 장소/주소명


class Geocoder(Protocol):
    def locate(self, query: str) -> GeoResult | None: ...
    def geocode(self, query: str) -> GeoPoint | None: ...


class _BaseGeocoder:
    """geocode() 는 locate() 의 좌표만 뽑아주는 편의 래퍼."""

    def locate(self, query: str) -> GeoResult | None:  # pragma: no cover - 추상
        raise NotImplementedError

    def geocode(self, query: str) -> GeoPoint | None:
        r = self.locate(query)
        return r.point if r else None


# ── 카카오 Local (가장 정밀) ─────────────────────────────────────────
# 행정구역 접미사 — 마지막 토큰이 이걸로 끝나면 '순수 지역명'으로 보고 주소검색 먼저.
_ADMIN_SUFFIX = ("특별시", "광역시", "시", "도", "구", "군", "동", "읍", "면", "리")


def _looks_like_region(query: str) -> bool:
    """'면목동', '성북구 정릉동'처럼 마지막 토큰이 행정구역 접미사로 끝나는가.

    True  → 주소검색 먼저(동 좌표). '면목동'을 키워드로 넣으면 엉뚱한 랜드마크가 걸림.
    False → 키워드검색 먼저(상호/건물 POI). '면목동 방앗간', '서울숲' 등.
    """
    toks = query.split()
    return bool(toks) and toks[-1].endswith(_ADMIN_SUFFIX)


class KakaoGeocoder(_BaseGeocoder):
    """카카오 Local API — 입력 종류에 따라 검색 순서를 바꾼다.

    - 순수 지역명("면목동", "성북구 정릉동") → 주소검색 먼저 → 동/주소 좌표(precision=address).
    - 상호·장소명("면목동 방앗간", "서울숲")   → 키워드검색 먼저 → 건물 POI(precision=poi).
    각각 실패하면 다른 방식으로 폴백. REST 키 필요.
    """

    KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
    ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"

    def __init__(self, rest_key: str, timeout: float = 8.0) -> None:
        self.rest_key = rest_key
        self.timeout = timeout

    def _get(self, url: str, query: str) -> list[dict]:
        import json
        import urllib.parse
        import urllib.request

        full = f"{url}?{urllib.parse.urlencode({'query': query, 'size': 1})}"
        req = urllib.request.Request(full, headers={"Authorization": f"KakaoAK {self.rest_key}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8")).get("documents", [])
        except Exception:  # noqa: BLE001 — 네트워크/인증 실패는 조용히 미탐
            return []

    def _keyword(self, query: str) -> GeoResult | None:
        docs = self._get(self.KEYWORD_URL, query)
        if not docs:
            return None
        d = docs[0]
        return GeoResult(GeoPoint(lat=float(d["y"]), lng=float(d["x"])),
                         precision="poi", source="kakao", matched=d.get("place_name"))

    def _address(self, query: str) -> GeoResult | None:
        docs = self._get(self.ADDRESS_URL, query)
        if not docs:
            return None
        d = docs[0]
        return GeoResult(GeoPoint(lat=float(d["y"]), lng=float(d["x"])),
                         precision="address", source="kakao", matched=d.get("address_name"))

    def locate(self, query: str) -> GeoResult | None:
        if not query:
            return None
        # 순수 지역명이면 주소→키워드, 상호/장소명이면 키워드→주소
        steps = (self._address, self._keyword) if _looks_like_region(query) else (self._keyword, self._address)
        for step in steps:
            res = step(query)
            if res is not None:
                return res
        return None


# ── OSM Nominatim ────────────────────────────────────────────────────
class NominatimGeocoder(_BaseGeocoder):
    URL = "https://nominatim.openstreetmap.org/search"

    def __init__(self, timeout: float = 8.0, country: str = "kr") -> None:
        self.timeout = timeout
        self.country = country

    def locate(self, query: str) -> GeoResult | None:
        import json
        import urllib.parse
        import urllib.request

        if not query:
            return None
        params = urllib.parse.urlencode({
            "q": query, "format": "json", "limit": 1, "countrycodes": self.country,
        })
        req = urllib.request.Request(
            f"{self.URL}?{params}",
            headers={"User-Agent": "come-back-home/0.1 (SAR onboarding)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                rows = json.loads(resp.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None
        if not rows:
            return None
        r = rows[0]
        return GeoResult(
            GeoPoint(lat=float(r["lat"]), lng=float(r["lon"])),
            precision="approx", source="nominatim", matched=r.get("display_name"),
        )


# ── 오프라인 gazetteer (최후 폴백) ──────────────────────────────────
_GAZETTEER: dict[str, GeoPoint] = {
    "정릉동": GeoPoint(lat=37.6076, lng=127.0133),
    "면목동": GeoPoint(lat=37.5872, lng=127.0873),
    "화곡동": GeoPoint(lat=37.5417, lng=126.8407),
    "안양천": GeoPoint(lat=37.5290, lng=126.8760),
    "정릉초등학교": GeoPoint(lat=37.6087, lng=127.0155),
    "성북구": GeoPoint(lat=37.5894, lng=127.0167),
    "중랑구": GeoPoint(lat=37.6063, lng=127.0925),
    "강서구": GeoPoint(lat=37.5509, lng=126.8495),
    "종로구": GeoPoint(lat=37.5730, lng=126.9794),
    "강남구": GeoPoint(lat=37.5172, lng=127.0473),
    "노원구": GeoPoint(lat=37.6542, lng=127.0568),
    "은평구": GeoPoint(lat=37.6027, lng=126.9291),
}


def _normalize(text: str) -> str:
    return re.sub(r"[\s()]+", "", text)


class GazetteerGeocoder(_BaseGeocoder):
    """오프라인 사전 매칭 — 긴 키(동)를 먼저 시도해 구보다 동을 우선."""

    def __init__(self, table: dict[str, GeoPoint] | None = None) -> None:
        self.table = table or _GAZETTEER
        self._keys = sorted(self.table, key=len, reverse=True)

    def locate(self, query: str) -> GeoResult | None:
        if not query:
            return None
        q = _normalize(query)
        for key in self._keys:
            if _normalize(key) in q:
                return GeoResult(self.table[key], precision="dong", source="gazetteer", matched=key)
        return None


# ── 체인 ─────────────────────────────────────────────────────────────
class ChainGeocoder(_BaseGeocoder):
    """여러 백엔드를 순서대로 시도, 첫 성공 반환 (정밀→거침 순 권장)."""

    def __init__(self, *backends: Geocoder) -> None:
        self.backends = backends

    def locate(self, query: str) -> GeoResult | None:
        for b in self.backends:
            hit = b.locate(query)
            if hit is not None:
                return hit
        return None


def get_geocoder(use_nominatim: bool = False) -> Geocoder:
    """설정 기반 체인. kakao_rest_key 있으면 카카오 우선 → (nominatim) → gazetteer."""
    from app.config import settings

    backends: list[Geocoder] = []
    if getattr(settings, "kakao_rest_key", ""):
        backends.append(KakaoGeocoder(settings.kakao_rest_key))
    if use_nominatim:
        backends.append(NominatimGeocoder())
    backends.append(GazetteerGeocoder())
    return backends[0] if len(backends) == 1 else ChainGeocoder(*backends)


# ── draft 끌림점 → AttractionPoint ──────────────────────────────────
def to_attraction_points(
    drafts: list[dict], geocoder: Geocoder | None = None, *, default_weight: float = 1.0
) -> tuple[list[AttractionPoint], list[dict]]:
    """온보딩 초안 [{"label","area_text"}] → (AttractionPoint[], 미해결[]).

    지오코딩되면 좌표·정밀도(precision) 담아 AttractionPoint 생성, 안 되면 미해결.
    """
    geocoder = geocoder or get_geocoder()
    points: list[AttractionPoint] = []
    unresolved: list[dict] = []
    for d in drafts:
        area = d.get("area_text") or d.get("label")
        res = geocoder.locate(area) if area else None
        if res is None:
            unresolved.append(d)
            continue
        points.append(AttractionPoint(
            label=d.get("label") or area,
            location=res.point,
            weight=default_weight,
            precision=res.precision,
        ))
    return points, unresolved
