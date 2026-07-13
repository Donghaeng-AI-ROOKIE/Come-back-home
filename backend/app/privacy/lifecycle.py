"""개인정보 파기 라이프사이클.

법적 근거: 개인정보 보호법 제21조 "목적 달성 시 지체 없이 파기" —
표준 개인정보 보호지침은 이를 "정당한 사유가 없는 한 5일 이내"로 구체화.
기본 TTL(settings.privacy_retention_days=5)은 이 상한에 맞춘 값이다.

라이프사이클:
    등록(Phase0) → 활성화(신고, Phase1) → 종결(발견/철회) → TTL → 자동 파기

설계 결정:
- 파생물 동반삭제 — 케이스 파기 시 debug_traces(워커 궤적·LLM 트레이스)까지
  지운다. tips·report 는 Case 에 내장이라 본체와 함께 사라진다.
- 감사로그는 ID·행위·사유 코드만 — 파기 증적에 개인정보를 남기면 모순.
- 얼굴 임베딩은 애초에 생성하지 않는다 (기존 결정 = 최소수집 원칙).
- 수색 중(활성) 케이스는 명시 삭제 불가 — 철회(withdrawn) 종결이 먼저다.
  오종결·오삭제로 골든타임 수색 데이터가 소실되는 것을 막는 가드레일.
- 인메모리 백본이라 "파기 = dict 에서 제거". DB 전환 시 이 모듈이
  물리삭제/익명화 정책의 단일 진입점이 된다.
"""

from datetime import datetime, timedelta

from app import storage
from app.config import settings
from app.schemas.case import Case, CaseStatus, CloseReason
from app.schemas.privacy import AuditRecord

# 수색이 살아있는 상태 — 이 상태의 케이스·연결 페르소나는 파기를 거부한다
ACTIVE_STATUSES = {CaseStatus.intake, CaseStatus.predicted, CaseStatus.searching}


class LifecycleError(Exception):
    """라이프사이클 규칙 위반 — API 층에서 409 로 매핑."""


class AlreadyClosed(LifecycleError):
    pass


class NotClosed(LifecycleError):
    pass


class ActiveCaseLinked(LifecycleError):
    pass


def _audit(action: str, target_type: str, target_id: str, detail: str = "") -> AuditRecord:
    rec = AuditRecord(
        id=storage.new_id(),
        action=action, target_type=target_type, target_id=target_id, detail=detail,
    )
    storage.audit_logs.save(rec.id, rec)
    return rec


def close_case(case: Case, reason: CloseReason, now: datetime | None = None) -> Case:
    """종결 처리 — 이 순간부터 TTL 카운트다운이 시작된다."""
    if case.status in (CaseStatus.found, CaseStatus.closed):
        raise AlreadyClosed(f"이미 종결된 케이스: {case.id} ({case.status.value})")
    case.status = CaseStatus.found if reason == CloseReason.found else CaseStatus.closed
    case.close_reason = reason
    case.closed_at = now or datetime.now()
    storage.cases.save(case.id, case)
    _audit("case_closed", "case", case.id, f"reason={reason.value}")
    return case


def purge_due_at(case: Case) -> datetime | None:
    """파기 예정 시각. 종결 전에는 카운트다운이 없다 (None)."""
    if case.closed_at is None:
        return None
    return case.closed_at + timedelta(days=settings.privacy_retention_days)


def retention_info(case: Case, now: datetime | None = None) -> dict:
    """파기 예정일 조회 — 보호자·운영 대시보드용."""
    now = now or datetime.now()
    due = purge_due_at(case)
    return {
        "case_id": case.id,
        "status": case.status,
        "closed_at": case.closed_at,
        "retention_days": settings.privacy_retention_days,
        "purge_due_at": due,
        "expired": due is not None and now >= due,
    }


def purge_case(case: Case, *, cause: str) -> None:
    """케이스 파기 — 본체(report·tips 내장) + 파생물(debug_traces) 동반삭제."""
    storage.debug_traces.delete(case.id)
    storage.cases.delete(case.id)
    _audit("case_purged", "case", case.id, cause)


def request_case_deletion(case: Case) -> None:
    """명시 삭제요청 — 즉시 파기. 단 수색 중이면 철회 종결이 먼저다."""
    if case.status in ACTIVE_STATUSES:
        raise NotClosed(
            f"수색 중 케이스는 삭제 불가: {case.id} — "
            "먼저 철회(withdrawn)로 종결한 뒤 삭제하세요"
        )
    purge_case(case, cause="explicit_request")


def purge_persona(persona_id: str, *, cause: str = "explicit_request") -> None:
    """페르소나 파기 — 인터뷰 세션·종결된 연결 케이스까지 동반삭제.

    활성 케이스가 연결돼 있으면 거부한다: 실종자 수색이 진행 중인데
    보호자 요청으로 데이터를 지우면 수색 자체가 무너지기 때문.
    """
    linked = [c for c in storage.cases.list() if c.report.persona_id == persona_id]
    active = [c for c in linked if c.status in ACTIVE_STATUSES]
    if active:
        raise ActiveCaseLinked(
            f"수색 중 케이스 {len(active)}건이 연결됨 — 종결 후 삭제 가능"
        )
    for c in linked:
        purge_case(c, cause=f"persona_purge:{persona_id}")
    for s in storage.interviews.list():
        if s.persona_id == persona_id:
            storage.interviews.delete(s.id)
            _audit("interview_purged", "interview", s.id, f"persona_purge:{persona_id}")
    storage.personas.delete(persona_id)
    _audit("persona_purged", "persona", persona_id, cause)


def purge_expired(now: datetime | None = None) -> list[str]:
    """TTL 만료분 일괄 파기 — 스케줄러(또는 수동 트리거)가 주기 호출."""
    now = now or datetime.now()
    purged: list[str] = []
    for case in storage.cases.list():
        due = purge_due_at(case)
        if due is not None and now >= due:
            purge_case(case, cause="ttl_expired")
            purged.append(case.id)
    return purged
