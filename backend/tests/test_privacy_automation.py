"""자동 파기 회차·재시도·관리 API의 결정론적 검증."""

from datetime import datetime, timedelta

import pytest

from fastapi.testclient import TestClient

from app import storage
from app.api.privacy import router
from app.config import settings
from app.main import app
from app.privacy import lifecycle, worker
from app.schemas.case import Case, CaseStatus, CloseReason
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType, InterviewSession
from app.schemas.privacy import PrivacyJob
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


@pytest.mark.parametrize("change", ["registered", "resumed"])
def test_recovered_job_rechecks_interview_eligibility(monkeypatch, tmp_path, change):
    storage.reset_for_tests()
    monkeypatch.setattr(settings, "privacy_audit_path", str(tmp_path / "audit.jsonl"))
    now = datetime.now()
    old = now - timedelta(hours=settings.privacy_session_ttl_hours + 1)
    session = InterviewSession(id="stale-job-session", guardian_name="synthetic", last_active_at=old)
    storage.interviews.save(session.id, session)
    worker.discover_jobs(now)
    job = next(j for j in storage.privacy_jobs.list() if j.target_id == session.id)
    job.state = "running"  # same recovery path as a previously interrupted run
    storage.privacy_jobs.save(job.id, job)
    if change == "registered":
        session.persona_id = "newly-registered-person"
    else:
        session.last_active_at = now
    storage.interviews.save(session.id, session)
    run = worker.run_once(now=now, discover=False)
    assert storage.interviews.get(session.id) is not None
    assert storage.privacy_jobs.get(job.id).stage == "eligibility_changed"
    assert storage.privacy_jobs.get(job.id).state == "cancelled"
    assert run.skipped_count == 1
    assert run.success_count == 0


def test_recovered_job_does_not_delete_active_case(monkeypatch, tmp_path):
    storage.reset_for_tests()
    monkeypatch.setattr(settings, "privacy_audit_path", str(tmp_path / "audit.jsonl"))
    case, _ = _case()
    now = datetime.now()
    job = PrivacyJob(id="stale-case-job", target_type="case", target_id=case.id,
                     due_at=now, state="running")
    storage.privacy_jobs.save(job.id, job)
    case.status = CaseStatus.searching
    storage.cases.save(case.id, case)
    run = worker.run_once(now=now, discover=False)
    assert storage.cases.get(case.id) is not None
    assert storage.privacy_jobs.get(job.id).stage == "eligibility_changed"
    assert storage.privacy_jobs.get(job.id).state == "cancelled"
    # close_case now reserves its own expiry job, also cancelled after eligibility changes.
    assert run.skipped_count == 2
    assert run.success_count == 0


@pytest.mark.parametrize("configured,provided,status", [("", None, 503), ("secret", None, 403), ("secret", "wrong", 403), ("secret", "secret", 200)])
def test_automation_admin_auth_fails_closed(monkeypatch, configured, provided, status):
    monkeypatch.setattr(settings, "privacy_admin_key", configured)
    headers = {"X-Privacy-Admin-Key": provided} if provided is not None else {}
    response = TestClient(app).get("/privacy/automation/jobs", headers=headers)
    assert response.status_code == status
