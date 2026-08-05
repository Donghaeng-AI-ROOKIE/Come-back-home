"""presence 엔드포인트 — 라우팅·검증·종결 처리 계약.

모듈 로직 자체는 test_presence.py. 여기서는 HTTP 경계만 본다.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import storage
from app.main import app
from app.phase3 import presence
from app.privacy import lifecycle
from app.config import settings
from app.schemas.case import Case, CaseStatus, CloseReason
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.report import MissingReport

LKP = GeoPoint(lat=37.6061, lng=127.0106)
TOKEN = "tok-abcdefgh"


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "privacy_audit_path", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(lifecycle, "_audit_loaded", False)
    presence.reset()
    yield
    presence.reset()


@pytest.fixture
def client():
    return TestClient(app)


def _make_case(status: CaseStatus = CaseStatus.searching) -> Case:
    report = MissingReport(
        id=storage.new_id(), missing_type=PersonaType.dementia, lkp=LKP,
        lkp_time=datetime.now() - timedelta(hours=1),
    )
    case = Case(id=storage.new_id(), report=report, status=status,
                lkp=report.lkp, lkp_time=report.lkp_time)
    storage.cases.save(case.id, case)
    return case


def test_heartbeat_returns_count(client):
    case = _make_case()
    r = client.post(f"/phase3/cases/{case.id}/presence", json={"token": TOKEN})
    assert r.status_code == 200
    assert r.json() == {"case_id": case.id, "watching": 1}


def test_get_does_not_count_observer(client):
    """GET 은 하트비트가 아니다 — 운영 대시보드가 열어둔다고 시민 수가 늘면 거짓 집계."""
    case = _make_case()
    for _ in range(3):
        assert client.get(f"/phase3/cases/{case.id}/presence").json()["watching"] == 0


def test_unknown_case_404(client):
    assert client.post("/phase3/cases/없는사건/presence", json={"token": TOKEN}).status_code == 404
    assert client.get("/phase3/cases/없는사건/presence").status_code == 404


def test_short_token_rejected(client):
    """토큰 길이 하한 — 한 글자 토큰이 통과하면 서로 다른 사용자가 충돌해 과소집계된다."""
    case = _make_case()
    r = client.post(f"/phase3/cases/{case.id}/presence", json={"token": "a"})
    assert r.status_code == 422


def test_closed_case_rejects_heartbeat_but_allows_read(client):
    """종결 케이스: 쓰기(하트비트)는 409, 조회는 허용 — 이 파일의 기존 규칙과 동일."""
    case = _make_case()
    client.post(f"/phase3/cases/{case.id}/presence", json={"token": TOKEN})
    lifecycle.close_case(case, CloseReason.found)

    assert client.post(f"/phase3/cases/{case.id}/presence", json={"token": TOKEN}).status_code == 409
    r = client.get(f"/phase3/cases/{case.id}/presence")
    assert r.status_code == 200
    # 종결 시점에 즉시 0 — TTL 만료를 기다리며 유령 카운트가 남지 않는다.
    assert r.json()["watching"] == 0


def test_purge_clears_presence(client):
    """종결을 거치지 않고 바로 파기되는 경로에서도 참여자 기록이 남지 않는다."""
    case = _make_case(status=CaseStatus.closed)
    presence.heartbeat(case.id, TOKEN)
    lifecycle.purge_case(case, cause="test")
    assert presence.count(case.id) == 0
