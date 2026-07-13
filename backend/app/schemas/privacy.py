"""개인정보 파기 — 감사로그 레코드.

파기 증적에 개인정보를 다시 남기면 모순이므로 ID·행위·사유 코드만 담는다.
detail 에 이름·연락처·위치 등 개인정보를 넣지 않는다 (테스트로 강제).
"""

from datetime import datetime

from pydantic import BaseModel, Field


class AuditRecord(BaseModel):
    id: str
    action: str       # case_closed / case_purged / persona_purged / interview_purged
    target_type: str  # case / persona / interview
    target_id: str
    detail: str = ""  # 사유 코드만 (예: "reason=found", "ttl_expired")
    at: datetime = Field(default_factory=datetime.now)
