"""자동 개인정보 파기 워커.

스케줄러와 수동 API가 공유하는 건별 작업 경로다. 오류 메시지 원문은 저장하지
않고 예외 종류를 제한된 코드로만 기록한다.
"""

from datetime import datetime, timedelta
import threading
import uuid

from app import storage
from app.config import settings
from app.privacy import lifecycle
from app.schemas.privacy import PrivacyAlert, PrivacyJob, PrivacyRun, PrivacySchedulerState

_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now()


def _error_code(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return "timeout"
    if "lock" in name or "operational" in name:
        return "storage_unavailable"
    if isinstance(exc, lifecycle.LifecycleError):
        return "policy_blocked"
    return "purge_failed"


def _open_alert(code: str) -> None:
    if any(a.code == code and a.state == "open" for a in storage.privacy_alerts.list()):
        return
    alert = PrivacyAlert(id=uuid.uuid4().hex[:12], code=code)
    storage.privacy_alerts.save(alert.id, alert)


def _due_jobs(now: datetime) -> list[PrivacyJob]:
    jobs = []
    for job in storage.privacy_jobs.list():
        if job.state in {"pending", "running"}:
            jobs.append(job)
        elif job.state == "retry_wait" and job.next_retry_at and now >= job.next_retry_at:
            jobs.append(job)
    return sorted(jobs, key=lambda j: j.due_at)


def discover_jobs(now: datetime | None = None) -> tuple[int, int]:
    """만료 대상을 작업으로 등록한다. 반환값은 (검사 수, 신규 작업 수)다."""
    now = now or _now()
    scanned = 0
    created = 0
    existing = {(j.target_type, j.target_id) for j in storage.privacy_jobs.list()
                if j.state != "completed"}
    for case in storage.cases.list():
        scanned += 1
        due = lifecycle.purge_due_at(case)
        if due and now >= due and ("case", case.id) not in existing:
            job = PrivacyJob(id=uuid.uuid4().hex[:12], target_type="case",
                             target_id=case.id, due_at=due)
            storage.privacy_jobs.save(job.id, job)
            created += 1
    session_ttl = timedelta(hours=settings.privacy_session_ttl_hours)
    for session in storage.interviews.list():
        scanned += 1
        due = session.last_active_at + session_ttl
        if session.persona_id is None and now >= due and ("interview", session.id) not in existing:
            job = PrivacyJob(id=uuid.uuid4().hex[:12], target_type="interview",
                             target_id=session.id, due_at=due)
            storage.privacy_jobs.save(job.id, job)
            created += 1
    return scanned, created


def _execute(job: PrivacyJob, run_id: str, now: datetime) -> bool:
    job.state = "running"
    job.stage = "deleting"
    job.attempts += 1
    job.run_id = run_id
    storage.privacy_jobs.save(job.id, job)
    try:
        if job.target_type == "case":
            target = storage.cases.get(job.target_id)
            if target is not None:
                lifecycle.purge_case(target, cause="ttl_expired")
        elif job.target_type == "interview":
            if storage.interviews.get(job.target_id) is not None:
                storage.interviews.delete(job.target_id)
                lifecycle._audit("interview_purged", "interview", job.target_id, "abandoned_ttl")
        else:
            raise ValueError("unsupported_target")
        job.state = "completed"
        job.stage = "verified"
        job.completed_at = now
        job.next_retry_at = None
        job.last_error_code = ""
        storage.privacy_jobs.save(job.id, job)
        return True
    except Exception as exc:  # noqa: BLE001 — 건별 격리
        code = _error_code(exc)
        job.last_error_code = code
        if job.attempts >= settings.privacy_retry_max_attempts:
            job.state = "failed"
            job.stage = "failed"
            _open_alert("purge_retry_exhausted")
        else:
            delay = settings.privacy_retry_base_seconds * (2 ** (job.attempts - 1))
            job.state = "retry_wait"
            job.stage = "retry_scheduled"
            job.next_retry_at = now + timedelta(seconds=delay)
        storage.privacy_jobs.save(job.id, job)
        return False


def run_once(mode: str = "automatic", now: datetime | None = None,
             *, discover: bool = True) -> PrivacyRun:
    """한 회차 실행. 동시 호출은 프로세스 안에서 직렬화한다."""
    now = now or _now()
    with _lock:
        run = PrivacyRun(id=uuid.uuid4().hex[:12], mode=mode,
                         scheduled_at=now, started_at=now)
        storage.privacy_runs.save(run.id, run)
        try:
            scanned, created = discover_jobs(now) if discover else (0, 0)
            jobs = _due_jobs(now)
            run.scanned_count = scanned
            run.target_count = len(jobs)
            for job in jobs:
                if _execute(job, run.id, now):
                    run.success_count += 1
                else:
                    run.failure_count += 1
            cleanup_control_records(now)
            storage.vacuum()
            run.status = "completed"
        except Exception as exc:  # noqa: BLE001 — 회차 상태도 남긴다
            run.status = "failed"
            run.error_code = _error_code(exc)
            _open_alert("purge_scheduler_failed")
        run.finished_at = _now()
        storage.privacy_runs.save(run.id, run)
        state = storage.privacy_scheduler.get("singleton") or PrivacySchedulerState()
        state.heartbeat_at = run.finished_at
        state.last_run_id = run.id
        state.last_run_at = run.finished_at
        interval = (settings.privacy_scheduler_interval_seconds
                    if discover else settings.privacy_retry_poll_seconds)
        state.next_run_at = run.finished_at + timedelta(seconds=interval)
        storage.privacy_scheduler.save("singleton", state)
        return run


def retry_job(job_id: str) -> PrivacyJob | None:
    job = storage.privacy_jobs.get(job_id)
    if job is None:
        return None
    if job.state not in {"failed", "blocked", "retry_wait"}:
        return job
    job.state = "pending"
    job.next_retry_at = None
    job.last_error_code = ""
    storage.privacy_jobs.save(job.id, job)
    return job


def cleanup_control_records(now: datetime | None = None) -> None:
    """해결된 제어 기록만 정책 기간 후 정리한다. 미해결 작업·알림은 보존한다."""
    now = now or _now()
    cutoff = now - timedelta(days=settings.privacy_control_retention_days)
    for job in storage.privacy_jobs.list():
        if job.state == "completed" and job.completed_at and job.completed_at < cutoff:
            storage.privacy_jobs.delete(job.id)
    for run in storage.privacy_runs.list():
        if run.status == "completed" and run.finished_at and run.finished_at < cutoff:
            storage.privacy_runs.delete(run.id)
    for alert in storage.privacy_alerts.list():
        if alert.state == "resolved" and alert.resolved_at and alert.resolved_at < cutoff:
            storage.privacy_alerts.delete(alert.id)
