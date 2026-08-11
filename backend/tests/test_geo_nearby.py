"""산책 루트 조회 — 좌표열·길이·정렬 규칙 (외부 호출 없이 검증)."""
from app.geo import nearby
from app.schemas.common import GeoPoint

CENTER = GeoPoint(lat=37.5585, lng=126.9368)


def _way(name: str, coords: list[tuple[float, float]], **tags) -> dict:
    return {"tags": {"name": name, **tags},
            "geometry": [{"lat": la, "lon": ln} for la, ln in coords]}


def _line(lat: float, lng: float, n: int, step: float) -> list[tuple[float, float]]:
    return [(lat + i * step, lng) for i in range(n)]


def test_returns_geometry_and_real_length(monkeypatch):
    nearby._cache.clear()
    # 0.0001도 ≈ 11m → 60점이면 약 650m
    way = _way("테스트공원", _line(37.5600, 126.9368, 60, 0.0001), leisure="park")
    monkeypatch.setattr(nearby, "_fetch", lambda *a, **k: [way])
    monkeypatch.setattr(nearby, "_disk_get", lambda k: None)
    monkeypatch.setattr(nearby, "_disk_put", lambda k, v: None)

    rows = nearby.nearby_walks(CENTER)
    assert len(rows) == 1
    r = rows[0]
    assert r["name"] == "테스트공원" and r["kind"] == "park"
    assert len(r["path"]) >= 2, "경로 좌표열이 있어야 지도에 선을 그린다"
    assert 0.5 < r["route_km"] < 0.8, r["route_km"]
    # 직선거리와 코스 길이는 다른 값이다
    assert r["distance_km"] != r["route_km"]


def test_short_ways_are_dropped(monkeypatch):
    nearby._cache.clear()
    short = _way("골목", _line(37.5586, 126.9368, 5, 0.0001))   # ≈44m
    monkeypatch.setattr(nearby, "_fetch", lambda *a, **k: [short])
    monkeypatch.setattr(nearby, "_disk_get", lambda k: None)
    monkeypatch.setattr(nearby, "_disk_put", lambda k, v: None)
    assert nearby.nearby_walks(CENTER) == [], "골목 한 토막을 산책 루트라 하지 않는다"


def test_sorted_by_nearest_point_not_centroid(monkeypatch):
    """긴 길은 대표점이 멀어도 옆을 지나가면 가깝다."""
    nearby._cache.clear()
    far_mid = _way("긴산책로", _line(37.5585, 126.9368, 90, 0.0001))   # 바로 옆에서 시작
    near_all = _way("먼공원", _line(37.5700, 126.9368, 60, 0.0001), leisure="park")
    monkeypatch.setattr(nearby, "_fetch", lambda *a, **k: [near_all, far_mid])
    monkeypatch.setattr(nearby, "_disk_get", lambda k: None)
    monkeypatch.setattr(nearby, "_disk_put", lambda k, v: None)
    rows = nearby.nearby_walks(CENTER)
    assert rows[0]["name"] == "긴산책로"


def test_external_failure_returns_empty(monkeypatch):
    nearby._cache.clear()

    def boom(*a, **k):
        raise TimeoutError("overpass down")

    monkeypatch.setattr(nearby, "_fetch", boom)
    monkeypatch.setattr(nearby, "_disk_get", lambda k: None)
    assert nearby.nearby_walks(CENTER) == [], "실패 시 지어낸 길을 그리지 않는다"
