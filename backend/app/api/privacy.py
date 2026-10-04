"""개인정보 API — 종결·파기예정일·명시 삭제요청·만료 일괄 파기·감사로그."""

import hmac
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from app import storage
from app.config import settings
from app.privacy import lifecycle
from app.privacy import worker
from app.schemas.case import Case, CloseReason
from app.schemas.privacy import AuditRecord

router = APIRouter(prefix="/privacy", tags=["개인정보 — 파기 라이프사이클"])


class CloseCaseIn(BaseModel):
    reason: CloseReason   # found(발견) | withdrawn(신고 철회)


def _get_case(case_id: str) -> Case:
    case = storage.cases.get(case_id)
    if case is None:
        raise HTTPException(404, "케이스 없음")
    return case


def _require_admin(key: str | None) -> None:
    """관리 키가 없으면 fail-closed(기능을 잠그는 방식)로 동작한다."""
    if not settings.privacy_admin_key:
        raise HTTPException(503, "관리자 인증이 설정되지 않음")
    if not hmac.compare_digest(key or "", settings.privacy_admin_key):
        raise HTTPException(403, "관리자 권한 필요")


@router.post("/cases/{case_id}/close", response_model=Case, response_model_exclude={"continuous_state", "prior_context_key"})
def close_case(case_id: str, body: CloseCaseIn, x_privacy_admin_key: str | None = Header(default=None)):
    _require_admin(x_privacy_admin_key)
    """케이스 종결(발견/철회) — 이 시점부터 파기 TTL 카운트다운 시작."""
    case = _get_case(case_id)
    try:
        return lifecycle.close_case(case, body.reason)
    except lifecycle.AlreadyClosed as e:
        raise HTTPException(409, str(e))


@router.get("/cases/{case_id}/retention")
def retention(case_id: str, x_privacy_admin_key: str | None = Header(default=None)):
    _require_admin(x_privacy_admin_key)
    """파기 예정일 조회 — 종결 전이면 purge_due_at=null (카운트다운 미시작)."""
    return lifecycle.retention_info(_get_case(case_id))


@router.delete("/cases/{case_id}")
def delete_case(case_id: str, x_privacy_admin_key: str | None = Header(default=None)):
    _require_admin(x_privacy_admin_key)
    """명시 삭제요청 — 즉시 파기. 수색 중이면 409 (철회 종결이 먼저)."""
    case = _get_case(case_id)
    try:
        lifecycle.request_case_deletion(case)
    except lifecycle.NotClosed as e:
        raise HTTPException(409, str(e))
    return {"purged": True, "case_id": case_id}


@router.delete("/personas/{persona_id}")
def delete_persona(persona_id: str, x_privacy_admin_key: str | None = Header(default=None)):
    _require_admin(x_privacy_admin_key)
    """보호자 삭제요청 — 페르소나·인터뷰·종결된 연결 케이스 동반 파기.

    수색 중 케이스가 연결돼 있으면 409 (수색을 무너뜨리는 삭제 차단).
    """
    if storage.personas.get(persona_id) is None:
        raise HTTPException(404, "페르소나 없음")
    try:
        lifecycle.purge_persona(persona_id)
    except lifecycle.ActiveCaseLinked as e:
        raise HTTPException(409, str(e))
    return {"purged": True, "persona_id": persona_id}


@router.post("/purge-expired")
def purge_expired(x_privacy_admin_key: str | None = Header(default=None)):
    _require_admin(x_privacy_admin_key)
    """TTL 만료분 일괄 파기 — 운영 스케줄러가 주기 호출 (백본은 수동 트리거).

    케이스(종결 후 retention_days)와 방치된 미완료 인터뷰 세션
    (session_ttl_hours)을 함께 쓸어낸다.
    """
    purged = lifecycle.purge_expired()
    return {
        "purged_case_ids": purged["cases"],
        "purged_interview_ids": purged["interviews"],
        "count": len(purged["cases"]) + len(purged["interviews"]),
    }


@router.get("/audit", response_model=list[AuditRecord])
def audit_log(x_privacy_admin_key: str | None = Header(default=None)):
    _require_admin(x_privacy_admin_key)
    """파기 증적 조회 — 개인정보 미포함(ID·행위·사유 코드만), 재시작 후에도 유지."""
    return lifecycle.get_audit_log()


@router.get("/automation/status")
def automation_status(x_privacy_admin_key: str | None = Header(default=None)):
    _require_admin(x_privacy_admin_key)
    now = __import__("datetime").datetime.now()
    jobs = storage.privacy_jobs.list()
    overdue = [j for j in jobs if j.state not in {"completed", "cancelled"} and j.due_at <= now]
    retry_wait = [j for j in jobs if j.state == "retry_wait"]
    failed = [j for j in jobs if j.state == "failed"]
    state = storage.privacy_scheduler.get("singleton")
    last = max(storage.privacy_runs.list(), key=lambda r: r.started_at or r.scheduled_at, default=None)
    return {
        "last_run": last,
        "next_run_at": state.next_run_at if state else None,
        "heartbeat_at": state.heartbeat_at if state else None,
        "overdue_count": len(overdue),
        "retry_wait_count": len(retry_wait),
        "failed_count": len(failed),
        "oldest_overdue_seconds": max(
            (now - j.due_at).total_seconds() for j in overdue
        ) if overdue else 0,
        "open_alert_count": sum(a.state == "open" for a in storage.privacy_alerts.list()),
    }


@router.get("/automation/runs")
def automation_runs(
    page: int = Query(default=1, ge=1), size: int = Query(default=50, ge=1, le=100),
    x_privacy_admin_key: str | None = Header(default=None),
):
    _require_admin(x_privacy_admin_key)
    rows = sorted(storage.privacy_runs.list(), key=lambda r: r.scheduled_at, reverse=True)
    start = (page - 1) * size
    return {"page": page, "size": size, "total": len(rows), "items": rows[start:start + size]}


@router.get("/automation/jobs")
def automation_jobs(
    page: int = Query(default=1, ge=1), size: int = Query(default=50, ge=1, le=100),
    x_privacy_admin_key: str | None = Header(default=None),
):
    _require_admin(x_privacy_admin_key)
    rows = sorted(storage.privacy_jobs.list(), key=lambda j: j.due_at)
    start = (page - 1) * size
    # 대상 ID는 응답에서 제외해 운영 화면이 개인정보를 재노출하지 않게 한다.
    items = [j.model_dump(exclude={"target_id"}) for j in rows[start:start + size]]
    return {"page": page, "size": size, "total": len(rows), "items": items}


@router.post("/automation/jobs/{job_id}/retry")
def retry_automation_job(job_id: str, x_privacy_admin_key: str | None = Header(default=None)):
    _require_admin(x_privacy_admin_key)
    job = worker.retry_job(job_id)
    if job is None:
        raise HTTPException(404, "작업 없음")
    return {"job_id": job.id, "state": job.state}
