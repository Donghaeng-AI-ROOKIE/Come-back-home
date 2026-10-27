"""사건의 지역명(경보·종결 카드의 "[고양시 일산서구] 킨텍스로")이 워커 재시작에도 남는가.

10/27 운영: 경보 상세가 "내 주변 인근", 종결 카드가 "[] 어르신"으로 보였다(#324 로
화면은 막음). 경보·종결 응답은 워커 메모리 캐시(reverse.cached_label)만 읽는데,
그 캐시는 재시작하면 비고 신고 접수 때 한 번만 채워진다. 그래서 접수 때 얻은
이름을 사건에 저장하고 응답이 그 값을 먼저 쓰게 한다.
"""
import time
from datetime import UTC, datetime, timedelta

import pytest

from app import storage
from app.config import settings
from app.geo import reverse
from app.phase1 import intake
from app.phase3 import alerts
from app.privacy import lifecycle
from app.schemas.case import CloseReason
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType

KINTEX = GeoPoint(lat=37.6652142, lng=126.7483258)
KINTEX_STATION_EXIT = GeoPoint(lat=37.66499, lng=126.74752)   # 층2 제보 지점(약 75m)
OSM_ROW = {"address": {"road": "킨텍스로", "borough": "일산서구", "city": "고양시"}}
LABEL = "[고양시 일산서구] 킨텍스로"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """디스크 영속을 켠 격리 DB. 접수의 다른 부수 작업(1차 알림·도로망)은 끈다."""
    monkeypatch.setattr(settings, "persist_storage", True)
    monkeypatch.setattr(settings, "storage_db_path", str(tmp_path / "storage.db"))
    monkeypatch.setattr(settings, "reflex_alert_on_intake", False)
    monkeypatch.setattr(settings, "roadnet_preload", False)
    monkeypatch.setattr(settings, "reverse_geocode_on_intake", True)
    monkeypatch.setattr(reverse.time, "sleep", lambda *_: None)
    reverse._cache.clear()
    reverse._failed_at.clear()
    storage.reset_for_tests()
    yield tmp_path / "storage.db"
    storage.reset_for_tests()
    reverse._cache.clear()
    reverse._failed_at.clear()


def _fake_osm(monkeypatch, rows):
    """urlopen 을 가짜 응답으로. rows 의 원소가 예외면 그 호출은 실패한다."""
    import json

    class _Resp:
        def __init__(self, row):
            self.row = row

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(self.row).encode("utf-8")

    seq = list(rows)

    def _urlopen(*a, **k):
        row = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(row, Exception):
            raise row
        return _Resp(row)

    monkeypatch.setattr(reverse.urllib.request, "urlopen", _urlopen)


def _no_network(monkeypatch):
    def _fail(*a, **k):
        raise AssertionError("외부 조회가 일어났다")
    monkeypatch.setattr(reverse.urllib.request, "urlopen", _fail)


def _report():
    return intake.create_report(missing_type=PersonaType.dementia, lkp=KINTEX,
                                lkp_time=datetime.now(UTC) - timedelta(minutes=30))


def _report_without_label(monkeypatch):
    """이 변경 전에 접수된 사건처럼, 지역명을 저장하지 않은 사건."""
    monkeypatch.setattr(settings, "reverse_geocode_on_intake", False)
    case = _report()
    assert case.area_label == ""
    return case


def _wait_until_named(case_id: str, timeout: float = 5.0) -> None:
    """접수 스레드가 이름을 얻을 때까지. 저장 필드가 있는 코드면 저장까지 기다린다."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        case = storage.cases.get(case_id)
        if reverse.cached_label(case.lkp) and getattr(case, "area_label", None) != "":
            return
        time.sleep(0.01)
    raise AssertionError("접수 뒤 지역명을 얻지 못했다")


def _restart():
    """워커 재시작: 메모리 캐시는 비고 사건은 디스크에서 다시 읽는다."""
    reverse._cache.clear()
    reverse._failed_at.clear()
    storage.reset_for_tests()


def test_alert_keeps_the_intake_area_after_a_restart(monkeypatch):
    _fake_osm(monkeypatch, [OSM_ROW])
    case = _report()
    _wait_until_named(case.id)
    assert alerts.describe_alert(storage.cases.get(case.id))["area"] == LABEL

    _restart()
    _no_network(monkeypatch)
    assert alerts.describe_alert(storage.cases.get(case.id))["area"] == LABEL


def test_closed_case_card_keeps_the_area_after_a_restart(monkeypatch):
    _fake_osm(monkeypatch, [OSM_ROW])
    case = _report()
    _wait_until_named(case.id)
    lifecycle.close_case(storage.cases.get(case.id), CloseReason.found)

    _restart()
    _no_network(monkeypatch)
    assert alerts.describe_resolved(storage.cases.get(case.id))["area"] == LABEL


def test_area_lookup_on_the_polling_path_never_goes_to_the_network(monkeypatch):
    from app.phase3 import case_area

    _fake_osm(monkeypatch, [OSM_ROW])
    case = _report()
    _wait_until_named(case.id)
    _restart()
    monkeypatch.setattr(reverse, "label_for", lambda *a, **k: pytest.fail("폴링 경로가 외부 조회를 했다"))
    assert case_area.area_of(storage.cases.get(case.id)) == LABEL


def test_cases_from_before_this_change_fall_back_to_the_cache(monkeypatch):
    from app.phase3 import case_area

    case = _report_without_label(monkeypatch)
    assert case_area.area_of(case) == ""
    reverse._cache[(round(KINTEX.lat, 4), round(KINTEX.lng, 4))] = LABEL
    assert case_area.area_of(case) == LABEL


def test_after_a_layer2_move_the_new_point_name_wins_and_the_old_one_is_the_last_resort(monkeypatch):
    from app.phase3 import case_area

    case = _report_without_label(monkeypatch)
    case.area_label, case.area_label_point = LABEL, KINTEX
    case.lkp = KINTEX_STATION_EXIT                 # 층2 제보가 LKP 를 옮겼다
    assert case_area.area_of(case) == LABEL         # 새 지점 이름을 모르면 접수 때 이름
    reverse._cache[(round(KINTEX_STATION_EXIT.lat, 4), round(KINTEX_STATION_EXIT.lng, 4))] = "[고양시 일산서구] 한류월드로"
    assert case_area.area_of(case) == "[고양시 일산서구] 한류월드로"


def test_a_failed_lookup_at_intake_is_retried(monkeypatch):
    from app.phase3 import case_area

    case = _report_without_label(monkeypatch)
    _fake_osm(monkeypatch, [OSError("timeout"), OSM_ROW])
    waits = []
    case_area.remember(case.id, sleep=lambda s: (waits.append(s), reverse._failed_at.clear()))
    assert storage.cases.get(case.id).area_label == LABEL
    assert storage.cases.get(case.id).area_label_point == KINTEX
    assert len(waits) == 1


def test_retries_are_bounded(monkeypatch):
    from app.phase3 import case_area

    case = _report_without_label(monkeypatch)
    _fake_osm(monkeypatch, [OSError("down")])
    waits = []
    case_area.remember(case.id, sleep=lambda s: (waits.append(s), reverse._failed_at.clear()))
    assert storage.cases.get(case.id).area_label == ""
    assert len(waits) == case_area.ATTEMPTS - 1


def test_a_purged_case_is_not_brought_back(monkeypatch):
    from app.phase3 import case_area

    case = _report_without_label(monkeypatch)
    lifecycle.close_case(case, CloseReason.withdrawn)
    lifecycle.purge_case(storage.cases.get(case.id), cause="test")
    _fake_osm(monkeypatch, [OSM_ROW])
    case_area.remember(case.id, sleep=lambda s: None)
    assert storage.cases.get(case.id) is None


def test_purge_erases_the_area_name_from_disk(_isolated, monkeypatch):
    secret = "[파기검증시 확인구] 지역명파기검증로"
    case = _report_without_label(monkeypatch)
    case.area_label, case.area_label_point = secret, KINTEX
    storage.cases.save(case.id, case)
    lifecycle.close_case(case, CloseReason.withdrawn)
    assert secret.encode() in _isolated.read_bytes()

    lifecycle.purge_case(storage.cases.get(case.id), cause="test")
    assert secret.encode() not in _isolated.read_bytes(), "파기 후에도 지역명이 파일에 남아 있다"
