"""개인정보 파기 — 감사로그 레코드.

파기 증적에 개인정보를 다시 남기면 모순이므로 ID·행위·사유 코드만 담는다.
detail 에 이름·연락처·위치 등 개인정보를 넣지 않는다 (테스트로 강제).
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AuditRecord(BaseModel):
    id: str
    action: str       # case_closed / case_purged / persona_purged / interview_purged
    target_type: str  # case / persona / interview
    target_id: str
    detail: str = ""  # 사유 코드만 (예: "reason=found", "ttl_expired")
    at: datetime = Field(default_factory=datetime.now)


class PrivacyRun(BaseModel):
    """자동/수동 파기 회차의 영속 상태. 개인정보 원문을 담지 않는다."""
    id: str
    mode: str = "automatic"  # automatic | manual | recovery
    status: str = "running"   # running | completed | failed
    scheduled_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    scanned_count: int = 0
    target_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    skipped_count: int = 0
    error_code: str = ""


class PrivacyJob(BaseModel):
    """건별 파기 작업. target_id는 내부 재시도용이며 감사 응답에는 노출하지 않는다."""
    id: str
    target_type: str  # case | interview | persona
    target_id: str
    policy_version: str = "privacy-v1"
    due_at: datetime
    state: str = "pending"  # pending | running | retry_wait | blocked | failed | completed | cancelled
    stage: str = "pending"
    attempts: int = 0
    next_retry_at: datetime | None = None
    last_error_code: str = ""
    run_id: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None


class PrivacySchedulerState(BaseModel):
    """스케줄러 생존 신호와 다음 실행 시각."""
    id: str = "singleton"
    owner_id: str = ""
    lease_until: datetime | None = None
    heartbeat_at: datetime | None = None
    last_run_id: str = ""
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None


class PrivacyAlert(BaseModel):
    """외부 전송 없이도 관리 API에서 확인할 수 있는 장애 알림 상태."""
    id: str
    code: str
    severity: str = "error"
    state: str = "open"  # open | acknowledged | resolved
    created_at: datetime = Field(default_factory=datetime.now)
    resolved_at: datetime | None = None
