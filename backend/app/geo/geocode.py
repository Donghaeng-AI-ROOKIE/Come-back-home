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
from app.schemas.persona import AttractionEvidence, AttractionPoint


@dataclass
class GeoResult:
    point: GeoPoint
    precision: str          # poi | address | dong | approx
    source: str             # kakao | nominatim | gazetteer
    matched: str | None = None   # 실제 매칭된 장소/주소명


class Geocoder(Protocol):
    def locate(self, query: str, anchor: GeoPoint | None = None) -> GeoResult | None: ...
    def geocode(self, query: str) -> GeoPoint | None: ...


# 앵커(집) 기준 끌림점 탐색 반경 상한 (km). 카카오 radius 파라미터 상한(20,000m)과 정합.
# 라이브 인터뷰 실측 버그의 방어선: "은행 앞"→과천 21km, "산책로"→경북 188km 전국 오검색.
ANCHOR_MAX_KM = 20.0


class _BaseGeocoder:
    """geocode() 는 locate() 의 좌표만 뽑아주는 편의 래퍼."""

    def locate(self, query: str, anchor: GeoPoint | None = None) -> GeoResult | None:  # pragma: no cover - 추상
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

    def _get(self, url: str, query: str, extra: dict | None = None) -> list[dict]:
        import json
        import urllib.parse
        import urllib.request

        params = {"query": query, "size": 1, **(extra or {})}
        full = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(full, headers={"Authorization": f"KakaoAK {self.rest_key}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8")).get("documents", [])
        except Exception:  # noqa: BLE001 — 네트워크/인증 실패는 조용히 미탐
            return []

    def _keyword(self, query: str, anchor: GeoPoint | None = None) -> GeoResult | None:
        # 앵커(집)가 있으면 반경 내 근접순 검색 — "은행 앞" 같은 일반명사가
        # 전국 아무 곳에나 걸리는 것을 API 단에서 차단 (radius 상한 20,000m).
        extra = ({"x": anchor.lng, "y": anchor.lat,
                  "radius": int(ANCHOR_MAX_KM * 1000), "sort": "distance"}
                 if anchor else None)
        docs = self._get(self.KEYWORD_URL, query, extra)
        if not docs:
            return None
        d = docs[0]
        return GeoResult(GeoPoint(lat=float(d["y"]), lng=float(d["x"])),
                         precision="poi", source="kakao", matched=d.get("place_name"))

    def _address(self, query: str, anchor: GeoPoint | None = None) -> GeoResult | None:
        # 주소검색 API 는 x/y 파라미터 미지원 — anchor 는 시그니처 통일용
        docs = self._get(self.ADDRESS_URL, query)
        if not docs:
            return None
        d = docs[0]
        return GeoResult(GeoPoint(lat=float(d["y"]), lng=float(d["x"])),
                         precision="address", source="kakao", matched=d.get("address_name"))

    def locate(self, query: str, anchor: GeoPoint | None = None) -> GeoResult | None:
        if not query:
            return None
        # 순수 지역명이면 주소→키워드, 상호/장소명이면 키워드→주소
        steps = (self._address, self._keyword) if _looks_like_region(query) else (self._keyword, self._address)
        for step in steps:
            res = step(query, anchor)
            if res is not None:
                return res
        return None


# ── OSM Nominatim ────────────────────────────────────────────────────
class NominatimGeocoder(_BaseGeocoder):
    URL = "https://nominatim.openstreetmap.org/search"

    def __init__(self, timeout: float = 8.0, country: str = "kr") -> None:
        self.timeout = timeout
        self.country = country

    def locate(self, query: str, anchor: GeoPoint | None = None) -> GeoResult | None:
        import json
        import math
        import urllib.parse
        import urllib.request

        if not query:
            return None
        q: dict = {"q": query, "format": "json", "limit": 1, "countrycodes": self.country}
        if anchor is not None:
            # 앵커 기준 ~ANCHOR_MAX_KM 박스로 제한 (viewbox=left,top,right,bottom + bounded)
            dlat = ANCHOR_MAX_KM / 111.32
            dlng = ANCHOR_MAX_KM / (111.32 * math.cos(math.radians(anchor.lat)))
            q["viewbox"] = f"{anchor.lng - dlng},{anchor.lat + dlat},{anchor.lng + dlng},{anchor.lat - dlat}"
            q["bounded"] = 1
        params = urllib.parse.urlencode(q)
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

    def locate(self, query: str, anchor: GeoPoint | None = None) -> GeoResult | None:
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

    def locate(self, query: str, anchor: GeoPoint | None = None) -> GeoResult | None:
        for b in self.backends:
            hit = b.locate(query, anchor)
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
    drafts: list[dict],
    geocoder: Geocoder | None = None,
    *,
    default_weight: float = 1.0,
    anchor: GeoPoint | None = None,
) -> tuple[list[AttractionPoint], list[dict]]:
    """온보딩 초안 [{"label","area_text"}] → (AttractionPoint[], 미해결[]).

    지오코딩되면 좌표·정밀도(precision) 담아 AttractionPoint 생성, 안 되면 미해결.
    anchor(집 좌표)가 있으면: (1) 백엔드에 근접 검색 힌트로 전달하고,
    (2) 결과가 anchor 에서 ANCHOR_MAX_KM 를 벗어나면 채택하지 않고 미해결 처리 —
    백엔드가 앵커를 무시하는 경우(nominatim 미탐 폴백 등)까지 막는 최종 방어선.
    실측 버그: "은행 앞"→과천 21km, "산책로"→경북 188km (전국 키워드 오검색).

    place_type/evidence 태그는 좌표화 과정에서 증발하지 않게 그대로 통과시킨다
    (근거 분류는 추출 단계에서만 가능 — 여기서 소실되면 복원 불가). evidence →
    초기 weight 매핑은 팀 회의 미결이라 weight 는 아직 default_weight 균등.
    """
    from app.geo import h3grid

    geocoder = geocoder or get_geocoder()
    points: list[AttractionPoint] = []
    unresolved: list[dict] = []
    for d in drafts:
        label = str(d.get("label") or "").strip()
        area = str(d.get("area_text") or "").strip()
        # 후보 쿼리는 구체 장소(라벨) 우선. area_text 를 먼저 쓰던 구버전은 라벨
        # "대흥역"이 area "대흥동"의 동 중심 좌표로 찍히는 라벨-좌표 불일치를 냈다
        # (라이브 실측 2026-07-17). "지역+라벨" 결합 → 라벨 → 지역 순으로 시도하고,
        # 앵커 반경 밖 매칭은 다음 후보로 넘어간다.
        candidates: list[str] = []
        if label and area and label not in area and area not in label:
            candidates.append(f"{area} {label}")
        candidates += [label, area]
        # 공백 제거 변형도 시도 — Mi:dm 이 "망원 시장"처럼 띄어 추출하면 nominatim
        # 이 못 찾아 조용히 탈락하던 실측(2026-07-17 8차). 카카오는 양쪽 다 잘 찾지만
        # 폴백 백엔드는 표기에 민감하다.
        candidates += [re.sub(r"\s+", "", q) for q in candidates]
        candidates = list(dict.fromkeys(q for q in candidates if q))

        res = None
        rejected_far = False
        for q in candidates:
            r = geocoder.locate(q, anchor)
            if r is None:
                continue
            if anchor is not None and h3grid.haversine_km(anchor, r.point) > ANCHOR_MAX_KM:
                rejected_far = True
                continue
            res = r
            break
        if res is None:
            extra = ({"reason": f"집 기준 {ANCHOR_MAX_KM:.0f}km 밖 매칭 — 오검색 의심"}
                     if rejected_far else {})
            unresolved.append({**d, **extra})
            continue
        points.append(AttractionPoint(
            label=d.get("label") or area,
            location=res.point,
            weight=default_weight,
            precision=res.precision,
            place_type=str(d.get("place_type") or ""),
            evidence=coerce_evidence(d.get("evidence")),
        ))
    return points, unresolved


def coerce_evidence(raw) -> AttractionEvidence:
    """LLM 추출값 → enum. 모르는 값·누락은 최약 근거(mention_only)로 — 과대평가 방지."""
    try:
        return AttractionEvidence(raw)
    except ValueError:
        return AttractionEvidence.mention_only
