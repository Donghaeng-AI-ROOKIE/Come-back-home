"""카테고리 POI 매칭 — 발달장애 preferred_targets 의 Phase 2 소비 경로.

"지하철", "편의점" 같은 카테고리 선호는 온보딩에서 좌표화할 수 없다(전국 어디에나
있다). 대신 예측 시점에 LKP 주변의 해당 카테고리 POI 만 찾아 그 예측 스코프의
끌림점으로 합류시킨다. 회의록 원칙: **모든 지하철역 일괄 가중치 금지, 등록된
대상만 반영** — 반경·개수 상한이 그 구현이다.

데이터원 결정(2026-07-16): 카카오 로컬 — 기존 지오코딩 체인과 같은 REST 키·백엔드로
일관되고, 국내 상업 POI(편의점·자동문 시설류) 커버리지가 OSM 태그보다 낫다.
카테고리 그룹 코드가 있는 대상은 카테고리 검색, 없는 대상(자동문·분수 등)은
키워드 검색으로 폴백. 키가 없으면 빈 결과(스텁) — 예측은 기존 끌림점만으로 계속.
"""

from __future__ import annotations

from typing import Protocol

from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, PreferredTarget

# LKP 주변 매칭 반경 — 도보권. roadnet_radius_m(3km, LKP 반경 그래프)와 정합.
MATCH_RADIUS_KM = 3.0
# 대상 하나당 근접 POI 상한 — 카테고리 전체가 아니라 "가장 가까운 몇 곳"만.
MAX_POI_PER_TARGET = 3

# 카카오 카테고리 그룹 코드 — 라벨에 이 키워드가 있으면 카테고리 검색.
# (키워드 검색보다 재현율·정밀도가 좋다: "지하철"을 키워드로 넣으면 상호에
# '지하철'이 든 가게가 걸린다.)
_CATEGORY_CODES: list[tuple[tuple[str, ...], str]] = [
    (("지하철", "전철", "역"), "SW8"),
    (("편의점",), "CS2"),
    (("마트", "슈퍼"), "MT1"),
    (("학교",), "SC4"),
    (("병원",), "HP8"),
    (("약국",), "PM9"),
    (("은행",), "BK9"),
    (("카페",), "CE7"),
    (("문화", "영화"), "CT1"),
]


def _category_code(label: str) -> str | None:
    for hints, code in _CATEGORY_CODES:
        if any(h in label for h in hints):
            return code
    return None


class POISearcher(Protocol):
    """(대상, 앵커) → [(장소명, 좌표)] 근접순. 테스트는 가짜 구현을 주입한다."""

    def search(self, target: PreferredTarget, anchor: GeoPoint,
               radius_m: int, size: int) -> list[tuple[str, GeoPoint]]: ...


class KakaoPOISearcher:
    """카카오 로컬 카테고리/키워드 검색 — 반경 내 근접순."""

    CATEGORY_URL = "https://dapi.kakao.com/v2/local/search/category.json"
    KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"

    def __init__(self, rest_key: str, timeout: float = 8.0) -> None:
        self.rest_key = rest_key
        self.timeout = timeout

    def _get(self, url: str, params: dict) -> list[dict]:
        import json
        import urllib.parse
        import urllib.request

        full = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(full, headers={"Authorization": f"KakaoAK {self.rest_key}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8")).get("documents", [])
        except Exception:  # noqa: BLE001 — 네트워크/인증 실패는 조용히 미탐 (geocode 와 동일)
            return []

    def search(self, target: PreferredTarget, anchor: GeoPoint,
               radius_m: int, size: int) -> list[tuple[str, GeoPoint]]:
        base = {"x": anchor.lng, "y": anchor.lat, "radius": radius_m,
                "sort": "distance", "size": size}
        code = _category_code(target.label)
        if code:
            docs = self._get(self.CATEGORY_URL, {**base, "category_group_code": code})
        else:
            docs = self._get(self.KEYWORD_URL, {**base, "query": target.label})
        return [(d.get("place_name", target.label),
                 GeoPoint(lat=float(d["y"]), lng=float(d["x"]))) for d in docs]


class NullPOISearcher:
    """키 없는 환경 스텁 — 항상 미탐. 예측은 기존 끌림점만으로 계속된다."""

    def search(self, target: PreferredTarget, anchor: GeoPoint,
               radius_m: int, size: int) -> list[tuple[str, GeoPoint]]:
        return []


def get_searcher() -> POISearcher:
    from app.config import settings

    key = getattr(settings, "kakao_rest_key", "")
    return KakaoPOISearcher(key) if key else NullPOISearcher()


def match_preferred_targets(
    targets: list[PreferredTarget],
    lkp: GeoPoint,
    searcher: POISearcher | None = None,
) -> list[AttractionPoint]:
    """등록된 카테고리 선호 → LKP 주변 POI → 이번 예측용 끌림점.

    반환된 AttractionPoint 는 Persona 에 저장하지 않는다 — LKP 가 바뀌면 매칭도
    바뀌는 예측 스코프 산출물이다 (pipeline 이 예측 직전에 합류시킨다).
    """
    searcher = searcher or get_searcher()
    points: list[AttractionPoint] = []
    for t in targets:
        hits = searcher.search(t, lkp, int(MATCH_RADIUS_KM * 1000), MAX_POI_PER_TARGET)
        for name, loc in hits[:MAX_POI_PER_TARGET]:
            points.append(AttractionPoint(
                label=f"{t.label}({name})" if name != t.label else t.label,
                location=loc,
                precision="poi",
                place_type=t.target_type or "category",
                evidence=t.evidence,
                origin_slot="preferred_target_seeking",  # PreferredTarget 은 이 슬롯에서만 생성됨
            ))
    return points
