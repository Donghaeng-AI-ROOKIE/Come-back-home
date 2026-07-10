"""지오코딩 — 장소 텍스트(동/랜드마크) → 좌표(GeoPoint).

Phase 0 온보딩에서 뽑은 끌림점(area_text: "면목동", "성북구 정릉동" 등)을 Phase 2
시뮬레이션이 쓰는 좌표로 바꾼다. draft → Persona.attraction_points 확정의 끊긴 고리.

백엔드 교체형:
- GazetteerGeocoder: 오프라인 사전(결정적·키리스). 데모 지역 + 서울 자치구 커버.
- NominatimGeocoder: OSM 실지오코더(네트워크, 키 불필요). 사전에 없는 곳 보강.
- ChainGeocoder: 사전 우선 → 실패 시 다음 백엔드.
기본은 gazetteer (오프라인·테스트 안정). config 로 nominatim 체인 활성화.
"""

from __future__ import annotations

import re
from typing import Protocol

from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint


class Geocoder(Protocol):
    def geocode(self, query: str) -> GeoPoint | None: ...


# ── 오프라인 gazetteer ───────────────────────────────────────────────
# 근사 중심좌표(WGS84). 데모(정릉동 김순자·화곡동 아동) + 서울 주요 지역.
_GAZETTEER: dict[str, GeoPoint] = {
    # 동 단위 (데모)
    "정릉동": GeoPoint(lat=37.6076, lng=127.0133),
    "면목동": GeoPoint(lat=37.5872, lng=127.0873),
    "화곡동": GeoPoint(lat=37.5417, lng=126.8407),
    "안양천": GeoPoint(lat=37.5290, lng=126.8760),
    "정릉초등학교": GeoPoint(lat=37.6087, lng=127.0155),
    # 자치구 (동을 못 잡으면 구 수준으로라도)
    "성북구": GeoPoint(lat=37.5894, lng=127.0167),
    "중랑구": GeoPoint(lat=37.6063, lng=127.0925),
    "강서구": GeoPoint(lat=37.5509, lng=126.8495),
    "종로구": GeoPoint(lat=37.5730, lng=126.9794),
    "강남구": GeoPoint(lat=37.5172, lng=127.0473),
    "노원구": GeoPoint(lat=37.6542, lng=127.0568),
    "은평구": GeoPoint(lat=37.6027, lng=126.9291),
}


def _normalize(text: str) -> str:
    # 공백·괄호 제거, 조사/수식 최소 정리
    return re.sub(r"[\s()]+", "", text)


class GazetteerGeocoder:
    """오프라인 사전 매칭 — query 안에 사전 키가 포함되면 그 좌표.

    긴 키(동)를 먼저 시도해 '성북구 정릉동'에서 구가 아니라 동을 잡는다.
    """

    def __init__(self, table: dict[str, GeoPoint] | None = None) -> None:
        self.table = table or _GAZETTEER
        self._keys = sorted(self.table, key=len, reverse=True)

    def geocode(self, query: str) -> GeoPoint | None:
        if not query:
            return None
        q = _normalize(query)
        for key in self._keys:
            if _normalize(key) in q:
                return self.table[key]
        return None


class NominatimGeocoder:
    """OpenStreetMap Nominatim 실지오코더 (네트워크, API 키 불필요).

    사전에 없는 임의 장소 보강용. 예의상 UA 지정, 저속. 실패 시 None.
    """

    URL = "https://nominatim.openstreetmap.org/search"

    def __init__(self, timeout: float = 8.0, country: str = "kr") -> None:
        self.timeout = timeout
        self.country = country

    def geocode(self, query: str) -> GeoPoint | None:
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
        except Exception:  # noqa: BLE001 — 네트워크/파싱 실패는 조용히 미탐
            return None
        if not rows:
            return None
        return GeoPoint(lat=float(rows[0]["lat"]), lng=float(rows[0]["lon"]))


class ChainGeocoder:
    """여러 백엔드를 순서대로 시도, 첫 성공 반환."""

    def __init__(self, *backends: Geocoder) -> None:
        self.backends = backends

    def geocode(self, query: str) -> GeoPoint | None:
        for b in self.backends:
            hit = b.geocode(query)
            if hit is not None:
                return hit
        return None


def get_geocoder(use_nominatim: bool = False) -> Geocoder:
    """기본 gazetteer. use_nominatim 이면 사전 → OSM 체인."""
    gaz = GazetteerGeocoder()
    if use_nominatim:
        return ChainGeocoder(gaz, NominatimGeocoder())
    return gaz


# ── draft 끌림점 → AttractionPoint ──────────────────────────────────

def to_attraction_points(
    drafts: list[dict], geocoder: Geocoder | None = None, *, default_weight: float = 1.0
) -> tuple[list[AttractionPoint], list[dict]]:
    """온보딩 초안 [{"label","area_text"}] → (좌표화된 AttractionPoint, 실패 목록).

    area_text 가 지오코딩되면 AttractionPoint 생성, 안 되면 실패 목록에 남겨
    후속 보완(수동 확인·다른 지오코더)로 넘긴다.
    """
    geocoder = geocoder or get_geocoder()
    points: list[AttractionPoint] = []
    unresolved: list[dict] = []
    for d in drafts:
        area = d.get("area_text") or d.get("label")
        loc = geocoder.geocode(area) if area else None
        if loc is None:
            unresolved.append(d)
            continue
        points.append(
            AttractionPoint(label=d.get("label") or area, location=loc, weight=default_weight)
        )
    return points, unresolved
