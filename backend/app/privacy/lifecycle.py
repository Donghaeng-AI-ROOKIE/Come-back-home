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
from pathlib import Path

from app import storage
from app.config import settings
from app.phase3 import presence
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


# ── 감사로그 영속화 (JSONL append-only) ─────────────────────────────
# 인메모리 storage 는 재시작 시 증발한다 — "파기했다는 증거"가 사라지면
# 증적으로서 무가치하므로 감사로그만은 파일에 남긴다. 개인정보가 없는
# 데이터라 파일 보존이 파기 원칙과 모순되지 않는다.

_audit_loaded = False   # 프로세스당 1회 파일 → 메모리 로드


def _ensure_audit_loaded() -> None:
    global _audit_loaded
    if _audit_loaded:
        return
    _audit_loaded = True   # 실패해도 재시도 폭주 방지 — 이번 프로세스는 메모리로만 동작
    path = Path(settings.privacy_audit_path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = AuditRecord.model_validate_json(line)
            storage.audit_logs.save(rec.id, rec)
        except Exception as e:  # noqa: BLE001 — 손상 라인은 건너뛰고 나머지는 살린다
            print(f"[privacy] 감사로그 손상 라인 무시: {e}")


def _append_audit_file(rec: AuditRecord) -> None:
    # 파일 기록 실패가 파기 자체를 막으면 안 된다 — 메모리 기록은 이미 됐고,
    # 영속 증적만 이번 건이 빠진다 (경고로 노출)
    try:
        path = Path(settings.privacy_audit_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(rec.model_dump_json() + "\n")
    except OSError as e:
        print(f"[privacy] 감사로그 파일 기록 실패 (메모리 기록은 유지): {e}")


def _audit(action: str, target_type: str, target_id: str, detail: str = "") -> AuditRecord:
    _ensure_audit_loaded()
    rec = AuditRecord(
        id=storage.new_id(),
        action=action, target_type=target_type, target_id=target_id, detail=detail,
    )
    storage.audit_logs.save(rec.id, rec)
    _append_audit_file(rec)
    return rec


def get_audit_log() -> list[AuditRecord]:
    """전체 감사로그 (시간순) — 재시작 후에도 파일에서 복원된다."""
    _ensure_audit_loaded()
    return sorted(storage.audit_logs.list(), key=lambda r: r.at)


def ensure_not_closed(case: Case) -> None:
    """종결 케이스에 수색 작업(예측·알림·제보)이 흐르는 것을 차단하는 정책 게이트.

    특히 Phase 2 예측은 status 를 predicted 로 덮어써 종결을 '부활'시키므로
    (pipeline.run_prediction), 모든 수색 진입점이 이 게이트를 먼저 통과해야 한다.
    """
    if case.status in (CaseStatus.found, CaseStatus.closed):
        raise AlreadyClosed(
            f"종결된 케이스 ({case.status.value}) — 예측·알림·제보 불가"
        )


def close_case(case: Case, reason: CloseReason, now: datetime | None = None) -> Case:
    """종결 처리 — 이 순간부터 TTL 카운트다운이 시작된다."""
    if case.status in (CaseStatus.found, CaseStatus.closed):
        raise AlreadyClosed(f"이미 종결된 케이스: {case.id} ({case.status.value})")
    case.status = CaseStatus.found if reason == CloseReason.found else CaseStatus.closed
    case.close_reason = reason
    case.closed_at = now or datetime.now()
    storage.cases.save(case.id, case)
    # 종결과 동시에 익명 참여자 카운트를 턴다. 안 그러면 TTL(90s)이 다 지날 때까지
    # 끝난 사건에 "N명이 함께 보고 있어요"가 남는다.
    presence.clear(case.id)
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
    presence.clear(case.id)  # 종결을 거치지 않고 바로 파기되는 경로(테스트·일괄파기)도 있다
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


def purge_expired(now: datetime | None = None) -> dict[str, list[str]]:
    """TTL 만료분 일괄 파기 — 스케줄러(또는 수동 트리거)가 주기 호출.

    두 종류를 쓸어낸다:
    - 종결 후 retention_days 지난 케이스
    - 미완료인 채 session_ttl_hours 방치된 인터뷰 세션 (draft 에 이름·주소
      초안이 남는데 persona_id 가 없어 보호자 삭제요청으로 못 지우는 것들)
    """
    now = now or datetime.now()
    purged: dict[str, list[str]] = {"cases": [], "interviews": []}
    for case in storage.cases.list():
        due = purge_due_at(case)
        if due is not None and now >= due:
            purge_case(case, cause="ttl_expired")
            purged["cases"].append(case.id)
    session_ttl = timedelta(hours=settings.privacy_session_ttl_hours)
    for s in storage.interviews.list():
        # persona_id 가 있으면 페르소나 파기 경로가 책임진다. 없으면 고아 draft —
        # 진행 중 방치든, 완료했지만 등록 실패(예: finalize 지오코딩 오류로
        # done=True + persona_id=None)든 TTL 로 쓸어낸다.
        if s.persona_id is None and now >= s.last_active_at + session_ttl:
            storage.interviews.delete(s.id)
            _audit("interview_purged", "interview", s.id, "abandoned_ttl")
            purged["interviews"].append(s.id)
    return purged
