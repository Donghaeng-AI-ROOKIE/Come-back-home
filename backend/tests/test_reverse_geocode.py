"""역지오코딩(좌표 → 지역명) — geo/reverse.py.

네트워크는 타지 않는다. 외부 응답은 가짜로 주입하고, **정책**만 검증한다:
캐시가 진짜로 재사용되는지, 실패가 화면을 죽이지 않는지, 폴링 경로가 외부
호출을 하지 않는지.
"""

import pytest

from app.geo import reverse
from app.schemas.common import GeoPoint

SEOUL = GeoPoint(lat=37.6029, lng=127.0157)
OSM_ROW = {
    "address": {
        "road": "정릉로",
        "suburb": "정릉1동",
        "borough": "성북구",
        "city": "서울특별시",
        "house_number": "284",
        "postcode": "02815",
    }
}


@pytest.fixture(autouse=True)
def _clear_cache():
    """모듈 전역 캐시가 테스트 사이에 새지 않게."""
    reverse._cache.clear()
    reverse._failed_at.clear()
    yield
    reverse._cache.clear()
    reverse._failed_at.clear()


def _fake_fetch(monkeypatch, row, calls):
    """urlopen 을 가짜 응답으로 대체하고 호출 횟수를 센다."""
    import json

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(row).encode("utf-8")

    def _urlopen(*a, **k):
        calls.append(1)
        return _Resp()

    monkeypatch.setattr(reverse.urllib.request, "urlopen", _urlopen)
    # 이용약관 준수용 1초 대기는 테스트에서 의미가 없다.
    monkeypatch.setattr(reverse.time, "sleep", lambda *_: None)


def test_label_is_region_and_road_not_house_number(monkeypatch):
    """번지·우편번호는 버린다 — 제보 위치는 목격자가 찍은 대략적 지점이라
    번지까지 붙이면 실제보다 정밀해 보인다."""
    _fake_fetch(monkeypatch, OSM_ROW, [])
    label = reverse.label_for(SEOUL)
    assert label == "[서울특별시 성북구] 정릉로"
    assert "284" not in label and "02815" not in label


def test_same_place_is_fetched_once(monkeypatch):
    """같은 골목의 제보가 여러 건이어도 외부 조회는 한 번 (OSM 초당 1건 제한)."""
    calls: list[int] = []
    _fake_fetch(monkeypatch, OSM_ROW, calls)
    near = GeoPoint(lat=SEOUL.lat + 0.00001, lng=SEOUL.lng)  # ~1m — 같은 칸
    reverse.labels_for([SEOUL, SEOUL, near])
    assert len(calls) == 1


def test_failure_falls_back_to_coordinates(monkeypatch):
    """조회가 실패해도 목록은 떠야 한다 — 이름 대신 좌표."""
    def _boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr(reverse.urllib.request, "urlopen", _boom)
    monkeypatch.setattr(reverse.time, "sleep", lambda *_: None)
    assert reverse.label_for(SEOUL) == "37.6029, 127.0157"


def test_failure_is_remembered_so_outage_does_not_slow_every_call(monkeypatch):
    """OSM 이 죽어 있을 때 매 요청이 타임아웃을 다시 물면 경보 조회가 통째로 느려진다."""
    calls: list[int] = []

    def _boom(*a, **k):
        calls.append(1)
        raise OSError("network down")

    monkeypatch.setattr(reverse.urllib.request, "urlopen", _boom)
    monkeypatch.setattr(reverse.time, "sleep", lambda *_: None)
    reverse.label_for(SEOUL)
    reverse.label_for(SEOUL)
    reverse.label_for(SEOUL)
    assert len(calls) == 1


def test_blank_fallback_means_unknown(monkeypatch):
    """경보의 지역명은 실패 시 빈 문자열이어야 한다 — 좌표를 지역명 자리에 넣지 않는다."""
    def _boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr(reverse.urllib.request, "urlopen", _boom)
    monkeypatch.setattr(reverse.time, "sleep", lambda *_: None)
    assert reverse.label_for(SEOUL, fallback="") == ""


def test_cached_label_never_calls_network(monkeypatch):
    """폴링 경로(경보 목록)가 쓰는 함수 — 캐시에 없으면 빈 문자열이고 조회하지 않는다."""
    def _fail(*a, **k):
        raise AssertionError("cached_label 이 외부 호출을 했다")

    monkeypatch.setattr(reverse.urllib.request, "urlopen", _fail)
    assert reverse.cached_label(SEOUL) == ""


def test_warm_then_cached_label_returns_name(monkeypatch):
    """예열해 두면 폴링 경로가 네트워크 없이 이름을 읽는다."""
    _fake_fetch(monkeypatch, OSM_ROW, [])
    reverse.warm(SEOUL)
    monkeypatch.setattr(
        reverse.urllib.request, "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("캐시가 안 쓰였다")),
    )
    assert reverse.cached_label(SEOUL) == "[서울특별시 성북구] 정릉로"
