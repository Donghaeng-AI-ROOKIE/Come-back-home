"""환경 레이어 — 도로망 노드에 "주변이 무엇인가"를 입힌다.

소스 2개 (상호 보완):
1. OSM 태그 (osmnx.features_from_point) — 물·숲·공원·시장 지오메트리를 받아
   노드별 최단거리(m)를 계산. 구체적 장소(POI)에 강함.
2. 환경부 EGIS 토지피복지도 (WMS, 인증키 불필요) — 노드 좌표의 피복 분류
   (대분류 l1 / 중분류 l2 / 세분류 l3). 전 국토 빈틈없는 커버리지.
   - 케이스 영역 래스터(GetMap) 1회 + 색→클래스 보정(GetFeatureInfo) 소수 호출.
   - 색상표를 하드코딩하지 않는다: 래스터에 실제로 나온 색마다 대표 지점 하나를
     GetFeatureInfo 로 물어 (색, 클래스) 표를 그 자리에서 만든다.

결과는 net.node_env[node] 에 저장하고 JSON 으로 디스크 캐시.
시뮬레이션·게이지·트리거·EXAONE 프롬프트는 env(node) dict 만 읽는다:

    {"landcover_l1": "시가화건조지역", "landcover_l3": "도로", "landcover_code": "154",
     "water_m": 37.2, "forest_m": 411.0, "park_m": None, "market_m": 88.5}
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

from app.config import settings
from app.geo.roadnet import OSMnxNetwork
from app.schemas.common import GeoPoint

# OSM 태그 → env 카테고리 (거리 필드명은 "<카테고리>_m")
_OSM_CATEGORIES: dict[str, callable] = {
    "water": lambda row: row.get("natural") == "water" or _notna(row.get("waterway")),
    "forest": lambda row: row.get("natural") == "wood" or row.get("landuse") == "forest",
    "park": lambda row: row.get("leisure") == "park",
    "market": lambda row: row.get("amenity") == "marketplace",
}
_OSM_TAGS = {
    "natural": ["water", "wood"],
    "waterway": True,
    "landuse": ["forest"],
    "leisure": ["park"],
    "amenity": ["marketplace"],
}


def _notna(v) -> bool:
    return v is not None and v == v  # NaN 은 자기 자신과 다르다


# ── 진입점 ──────────────────────────────────────────────────────────
def attach(net: OSMnxNetwork, center: GeoPoint, radius_m: int | None = None) -> dict:
    """net.node_env 를 채운다. 디스크 캐시가 있으면 API 호출 없이 로드.

    반환: 요약 통계 (테스트·로그용).
    """
    r = radius_m or settings.roadnet_radius_m
    cache = Path(settings.roadnet_cache_dir) / f"env_{center.lat:.4f}_{center.lng:.4f}_{r}.json"
    if cache.exists():
        loaded = json.loads(cache.read_text(encoding="utf-8"))
        net.node_env = {int(k): v for k, v in loaded.items()}
        return {"nodes": len(net.node_env), "source": "cache"}

    env: dict[int, dict] = {n: {} for n in net.graph.nodes}
    _attach_osm_distances(net, env, center, r)
    stats = _attach_landcover(net, env)

    net.node_env = env
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(env, ensure_ascii=False), encoding="utf-8")
    return {"nodes": len(env), "source": "api", **stats}


# ── 소스 1: OSM 태그 → 카테고리별 최단거리 ──────────────────────────
def _attach_osm_distances(net: OSMnxNetwork, env: dict[int, dict], center: GeoPoint, radius_m: int) -> None:
    import osmnx as ox
    from pyproj import Transformer
    from shapely.geometry import Point
    from shapely.ops import transform as shp_transform

    try:
        gdf = ox.features_from_point((center.lat, center.lng), tags=_OSM_TAGS, dist=radius_m)
    except Exception:  # noqa: BLE001 — 해당 태그가 하나도 없는 지역
        gdf = None

    # 미터 단위 거리용 투영 (위경도 → 한국 평면좌표 EPSG:5179)
    to_m = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True).transform

    node_pts = {n: shp_transform(to_m, Point(loc.lng, loc.lat))
                for n in net.graph.nodes for loc in [net.node_location(n)]}

    for cat, match in _OSM_CATEGORIES.items():
        geoms = []
        if gdf is not None:
            for _, row in gdf.iterrows():
                if match(row) and row.geometry is not None:
                    geoms.append(shp_transform(to_m, row.geometry))
        field = f"{cat}_m"
        if not geoms:
            for n in env:
                env[n][field] = None
            continue
        from shapely.strtree import STRtree

        tree = STRtree(geoms)
        for n, pt in node_pts.items():
            nearest = tree.nearest(pt)
            env[n][field] = round(pt.distance(geoms[nearest]), 1)


# ── 소스 2: EGIS 토지피복 — 래스터 1회 + 색 보정 조회 ────────────────
def _attach_landcover(net: OSMnxNetwork, env: dict[int, dict]) -> dict:
    import io as _io

    from PIL import Image

    locs = {n: net.node_location(n) for n in net.graph.nodes}
    lats = [p.lat for p in locs.values()]
    lngs = [p.lng for p in locs.values()]
    pad = 0.001
    bbox = (min(lngs) - pad, min(lats) - pad, max(lngs) + pad, max(lats) + pad)

    # 해상도 ≈ 5m/픽셀 (위도 1도 ≈ 111km), 최대 2048px
    w = min(2048, max(256, int((bbox[2] - bbox[0]) * 111_000 * 0.8 / 5)))
    h = min(2048, max(256, int((bbox[3] - bbox[1]) * 111_000 / 5)))

    png = _wms_get(
        request="GetMap", layers=settings.egis_landcover_layer,
        bbox=",".join(f"{v:.6f}" for v in bbox), width=w, height=h, format="image/png",
    )
    img = Image.open(_io.BytesIO(png)).convert("RGB")

    def to_px(p: GeoPoint) -> tuple[int, int]:
        x = int((p.lng - bbox[0]) / (bbox[2] - bbox[0]) * (w - 1))
        y = int((bbox[3] - p.lat) / (bbox[3] - bbox[1]) * (h - 1))
        return x, y

    # 색 양자화(채널당 /8): 경계 안티앨리어싱으로 생기는 미세 변형색을 묶는다
    def q(rgb: tuple) -> tuple:
        return tuple(c // 8 * 8 for c in rgb)

    node_color = {n: q(img.getpixel(to_px(p))) for n, p in locs.items()}

    # 색 → 클래스 보정표: 노드 수 많은 색부터 대표 노드 1곳씩 GetFeatureInfo 조회.
    # 호출 상한(60)을 넘는 희귀색(경계 잔여물)은 최근접 색으로 처리.
    from collections import Counter

    freq = Counter(node_color.values())
    palette: dict[tuple, dict] = {}
    calls = 0
    for color, _cnt in freq.most_common():
        if calls >= 60:
            break
        n = next(m for m, c in node_color.items() if c == color)
        info = _feature_info(locs[n])
        calls += 1
        if info:
            palette[color] = info

    for n, color in node_color.items():
        info = palette.get(color) or _nearest_color(palette, color)
        env[n].update(info or {"landcover_l1": None, "landcover_l3": None, "landcover_code": None})
    return {"landcover_colors": len(palette), "feature_info_calls": calls}


def _nearest_color(palette: dict[tuple, dict], color: tuple) -> dict | None:
    """보정표에 없는 색(경계 안티앨리어싱 등) → 가장 가까운 색의 클래스."""
    if not palette:
        return None
    best = min(palette, key=lambda c: sum((a - b) ** 2 for a, b in zip(c, color)))
    if sum((a - b) ** 2 for a, b in zip(best, color)) > 3 * 60**2:
        return None  # 너무 다른 색이면 미상 처리
    return palette[best]


def _feature_info(p: GeoPoint) -> dict | None:
    """좌표 1곳의 피복 분류 조회 (GetFeatureInfo)."""
    d = 0.0005
    raw = _wms_get(
        request="GetFeatureInfo",
        layers=settings.egis_landcover_layer, query_layers=settings.egis_landcover_layer,
        bbox=f"{p.lng - d:.6f},{p.lat - d:.6f},{p.lng + d:.6f},{p.lat + d:.6f}",
        width=101, height=101, x=50, y=50, info_format="application/json",
    )
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
        props = data["features"][0]["properties"]
        return {
            "landcover_l1": props.get("l1_name"),
            "landcover_l3": props.get("l3_name"),
            "landcover_code": props.get("l3_code"),
        }
    except (json.JSONDecodeError, KeyError, IndexError):
        return None


def _wms_get(**params) -> bytes:
    base = {"service": "WMS", "version": "1.1.1", "srs": "EPSG:4326"}
    url = settings.egis_wms_url + "?" + urllib.parse.urlencode({**base, **params})
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read()
