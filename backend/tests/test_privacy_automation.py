"""자동 파기 회차·재시도·관리 API의 결정론적 검증."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app import storage
from app.api.privacy import router
from app.config import settings
from app.main import app
from app.privacy import lifecycle, worker
from app.schemas.case import Case, CaseStatus, CloseReason
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.report import MissingReport


def _case():
    now = datetime(2026, 1, 1, 12)
    report = MissingReport(id=storage.new_id(), persona_id=None,
                           missing_type=PersonaType.dementia,
                           lkp=GeoPoint(lat=37.5, lng=126.9), lkp_time=now)
    case = Case(id=storage.new_id(), report=report, status=CaseStatus.searching,
                lkp=report.lkp, lkp_time=report.lkp_time)
    storage.cases.save(case.id, case)
    lifecycle.close_case(case, CloseReason.found, now=now)
    return case, now


def test_run_once_creates_job_and_removes_expired_case(monkeypatch):
    case, closed_at = _case()
    run = worker.run_once(now=closed_at + timedelta(days=settings.privacy_retention_days))
    assert run.status == "completed"
    assert run.success_count == 1
    assert storage.cases.get(case.id) is None
    job = next(j for j in storage.privacy_jobs.list() if j.target_id == case.id)
    assert job.state == "completed"
    assert storage.privacy_scheduler.get("singleton").last_run_id == run.id


def test_automation_api_hides_target_id_and_paginates(monkeypatch):
    monkeypatch.setattr(settings, "privacy_admin_key", "test-admin")
    worker.run_once(mode="manual", now=datetime(2026, 1, 1))
    client = TestClient(app)
    response = client.get("/privacy/automation/jobs?page=1&size=1",
                          headers={"X-Privacy-Admin-Key": "test-admin"})
    assert response.status_code == 200
    assert response.json()["page"] == 1
    for item in response.json()["items"]:
        assert "target_id" not in item
