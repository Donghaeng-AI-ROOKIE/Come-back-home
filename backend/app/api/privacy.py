"""개인정보 API — 종결·파기예정일·명시 삭제요청·만료 일괄 파기·감사로그."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import storage
from app.privacy import lifecycle
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


@router.post("/cases/{case_id}/close", response_model=Case)
def close_case(case_id: str, body: CloseCaseIn):
    """케이스 종결(발견/철회) — 이 시점부터 파기 TTL 카운트다운 시작."""
    case = _get_case(case_id)
    try:
        return lifecycle.close_case(case, body.reason)
    except lifecycle.AlreadyClosed as e:
        raise HTTPException(409, str(e))


@router.get("/cases/{case_id}/retention")
def retention(case_id: str):
    """파기 예정일 조회 — 종결 전이면 purge_due_at=null (카운트다운 미시작)."""
    return lifecycle.retention_info(_get_case(case_id))


@router.delete("/cases/{case_id}")
def delete_case(case_id: str):
    """명시 삭제요청 — 즉시 파기. 수색 중이면 409 (철회 종결이 먼저)."""
    case = _get_case(case_id)
    try:
        lifecycle.request_case_deletion(case)
    except lifecycle.NotClosed as e:
        raise HTTPException(409, str(e))
    return {"purged": True, "case_id": case_id}


@router.delete("/personas/{persona_id}")
def delete_persona(persona_id: str):
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
def purge_expired():
    """TTL 만료분 일괄 파기 — 운영 스케줄러가 주기 호출 (백본은 수동 트리거)."""
    purged = lifecycle.purge_expired()
    return {"purged_case_ids": purged, "count": len(purged)}


@router.get("/audit", response_model=list[AuditRecord])
def audit_log():
    """파기 증적 조회 — 개인정보 미포함(ID·행위·사유 코드만)."""
    return sorted(storage.audit_logs.list(), key=lambda r: r.at)
