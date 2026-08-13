"""개인정보 파기 라이프사이클 — 종결→TTL→파기, 파생물 동반삭제, 감사로그.

전부 인메모리 storage 직접 조작 (모델 스텁·API 키 불필요).
시간은 close_case/purge_expired 의 now 파라미터로 주입해 sleep 없이 검증.
"""

from datetime import datetime, timedelta

import pytest
from fastapi import BackgroundTasks
from fastapi import HTTPException

from app import storage
from app.api import debug as debug_api
from app.api import phase2 as phase2_api
from app.api import phase3 as phase3_api
from app.config import settings
from app.privacy import lifecycle
from app.schemas.case import Case, CaseStatus, CloseReason
from app.schemas.common import GeoPoint
from app.schemas.persona import InterviewSession, Persona, PersonaType
from app.schemas.privacy import AuditRecord
from app.schemas.report import MissingReport

LKP = GeoPoint(lat=37.5511, lng=126.9410)


@pytest.fixture(autouse=True)
def _isolated_audit_file(tmp_path, monkeypatch):
    """감사로그 파일을 테스트 임시 경로로 격리 — 실제 data/ 오염 방지."""
    monkeypatch.setattr(settings, "privacy_audit_path", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(lifecycle, "_audit_loaded", False)


def _make_case(persona_id: str | None = None, status: CaseStatus = CaseStatus.searching) -> Case:
    report = MissingReport(
        id=storage.new_id(), persona_id=persona_id,
        missing_type=PersonaType.dementia, lkp=LKP,
        lkp_time=datetime.now() - timedelta(hours=2),
    )
    case = Case(id=storage.new_id(), report=report, status=status,
                lkp=report.lkp, lkp_time=report.lkp_time)
    storage.cases.save(case.id, case)
    return case


def _make_persona() -> Persona:
    persona = Persona(id=storage.new_id(), type=PersonaType.dementia,
                      name="김실종", age=78, home=LKP)
    storage.personas.save(persona.id, persona)
    return persona


# ── 종결 ────────────────────────────────────────────────────────────

def test_close_found_sets_status_and_starts_ttl():
    case = _make_case()
    now = datetime(2026, 7, 13, 12, 0)
    lifecycle.close_case(case, CloseReason.found, now=now)
    assert case.status == CaseStatus.found
    assert case.close_reason == CloseReason.found
    assert case.closed_at == now
    assert lifecycle.purge_due_at(case) == now + timedelta(days=settings.privacy_retention_days)


def test_close_withdrawn_maps_to_closed_status():
    case = _make_case()
    lifecycle.close_case(case, CloseReason.withdrawn)
    assert case.status == CaseStatus.closed


def test_close_twice_rejected():
    case = _make_case()
    lifecycle.close_case(case, CloseReason.found)
    with pytest.raises(lifecycle.AlreadyClosed):
        lifecycle.close_case(case, CloseReason.withdrawn)


# ── 파기예정일 조회 ─────────────────────────────────────────────────

def test_retention_before_close_has_no_countdown():
    case = _make_case()
    info = lifecycle.retention_info(case)
    assert info["purge_due_at"] is None
    assert info["expired"] is False


def test_retention_after_close_reports_due_date():
    case = _make_case()
    now = datetime(2026, 7, 13, 12, 0)
    lifecycle.close_case(case, CloseReason.found, now=now)
    info = lifecycle.retention_info(case, now=now + timedelta(days=1))
    assert info["purge_due_at"] == now + timedelta(days=settings.privacy_retention_days)
    assert info["expired"] is False
    late = lifecycle.retention_info(case, now=now + timedelta(days=settings.privacy_retention_days))
    assert late["expired"] is True


# ── TTL 자동 파기 ───────────────────────────────────────────────────

def test_purge_expired_keeps_case_within_ttl():
    case = _make_case()
    now = datetime(2026, 7, 13, 12, 0)
    lifecycle.close_case(case, CloseReason.found, now=now)
    purged = lifecycle.purge_expired(now=now + timedelta(days=settings.privacy_retention_days - 1))
    assert case.id not in purged["cases"]
    assert storage.cases.get(case.id) is not None


def test_purge_expired_deletes_case_and_derivatives_after_ttl():
    case = _make_case()
    storage.debug_traces.save(case.id, {"walker_paths": ["파생물 스텁"]})
    now = datetime(2026, 7, 13, 12, 0)
    lifecycle.close_case(case, CloseReason.found, now=now)
    purged = lifecycle.purge_expired(now=now + timedelta(days=settings.privacy_retention_days))
    assert case.id in purged["cases"]
    assert storage.cases.get(case.id) is None
    assert storage.debug_traces.get(case.id) is None  # 파생물 동반삭제


def test_purge_expired_never_touches_open_cases():
    case = _make_case()  # searching — 종결 안 됨
    purged = lifecycle.purge_expired(now=datetime.now() + timedelta(days=365))
    assert case.id not in purged["cases"]
    assert storage.cases.get(case.id) is not None


def test_purge_expired_sweeps_orphan_sessions():
    """persona_id 없는 방치 세션(고아 draft)은 TTL 파기 — 등록 완료·최근 것은 유지."""
    expired_at = datetime.now() - timedelta(hours=settings.privacy_session_ttl_hours + 1)
    stale = InterviewSession(id=storage.new_id(), guardian_name="보호자",
                             last_active_at=expired_at)
    # 셀프리뷰 회귀: finalize 지오코딩 실패 경로는 done=True 인데 persona_id 가
    # 없는 고아를 남긴다 (interview.py) — done 여부와 무관하게 쓸어내야 한다
    orphan_done = InterviewSession(id=storage.new_id(), guardian_name="보호자",
                                   done=True, last_active_at=expired_at)
    fresh = InterviewSession(id=storage.new_id(), guardian_name="보호자")
    registered = InterviewSession(id=storage.new_id(), guardian_name="보호자",
                                  done=True, persona_id="p-1", last_active_at=expired_at)
    for s in (stale, orphan_done, fresh, registered):
        storage.interviews.save(s.id, s)

    purged = lifecycle.purge_expired()

    assert stale.id in purged["interviews"]
    assert orphan_done.id in purged["interviews"]
    assert storage.interviews.get(fresh.id) is not None       # 아직 TTL 안 지남
    assert storage.interviews.get(registered.id) is not None  # 페르소나 파기 경로 담당


# ── 명시 삭제요청 ───────────────────────────────────────────────────

def test_explicit_delete_refused_while_searching():
    case = _make_case()
    with pytest.raises(lifecycle.NotClosed):
        lifecycle.request_case_deletion(case)
    assert storage.cases.get(case.id) is not None


def test_explicit_delete_after_close_purges_immediately():
    case = _make_case()
    lifecycle.close_case(case, CloseReason.withdrawn)
    lifecycle.request_case_deletion(case)
    assert storage.cases.get(case.id) is None


# ── 페르소나 파기 (동반삭제·가드) ───────────────────────────────────

def test_persona_purge_blocked_by_active_case():
    persona = _make_persona()
    _make_case(persona_id=persona.id, status=CaseStatus.searching)
    with pytest.raises(lifecycle.ActiveCaseLinked):
        lifecycle.purge_persona(persona.id)
    assert storage.personas.get(persona.id) is not None


def test_persona_purge_cascades_interviews_and_closed_cases():
    persona = _make_persona()
    session = InterviewSession(id=storage.new_id(), guardian_name="보호자",
                               persona_id=persona.id)
    storage.interviews.save(session.id, session)
    case = _make_case(persona_id=persona.id)
    lifecycle.close_case(case, CloseReason.found)

    lifecycle.purge_persona(persona.id)

    assert storage.personas.get(persona.id) is None
    assert storage.interviews.get(session.id) is None   # 대화 전문 동반삭제
    assert storage.cases.get(case.id) is None           # 종결 케이스 동반삭제


# ── 종결 후 수색 API 차단 (셀프리뷰 회귀) ──────────────────────────
# 종결해도 알림·제보가 계속 흐르면 라이프사이클이 무효: 발견된 사람의
# 인상착의 알림 발송 + 제보가 status 를 searching 으로 되돌리는 구멍.

def test_closed_case_rejects_alerts_and_tips():
    case = _make_case()
    case.current_poa = {"cell-a": 1.0}
    lifecycle.close_case(case, CloseReason.found)
    with pytest.raises(HTTPException) as exc:
        phase3_api.send_alerts(case.id)
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException) as exc:
        phase3_api.submit_tip(case.id, phase3_api.TipIn(text="정릉시장에서 봤어요"),
                              BackgroundTasks())
    assert exc.value.status_code == 409
    assert case.status == CaseStatus.found  # 제보가 종결을 되돌리지 못함


def test_closed_case_rejects_phase2_and_debug_predict():
    """예측 API 는 status 를 predicted 로 덮어써 종결을 '부활'시킬 수 있다 —
    phase2·debug 예측 진입점 모두 종결 케이스를 거부해야 한다."""
    case = _make_case()
    lifecycle.close_case(case, CloseReason.found)
    with pytest.raises(HTTPException) as exc:
        phase2_api.predict(case.id)
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException) as exc:
        debug_api.predict_traced(case.id)
    assert exc.value.status_code == 409
    assert case.status == CaseStatus.found  # 부활 안 함


def test_closed_case_rerun_check_says_no():
    case = _make_case()
    lifecycle.close_case(case, CloseReason.withdrawn)
    res = phase3_api.rerun_check(case.id)
    assert res["should_rerun"] is False
    assert "종결" in res["reason"]


# ── 감사로그 ────────────────────────────────────────────────────────

def test_audit_trail_written_and_survives_purge():
    case = _make_case()
    lifecycle.close_case(case, CloseReason.found)
    lifecycle.request_case_deletion(case)
    actions = [(r.action, r.target_id) for r in storage.audit_logs.list()]
    assert ("case_closed", case.id) in actions
    assert ("case_purged", case.id) in actions


def test_audit_log_survives_restart(monkeypatch):
    """인메모리가 날아가도 JSONL 파일에서 증적이 복원된다."""
    case = _make_case()
    lifecycle.close_case(case, CloseReason.found)
    # 재시작 시뮬레이션: 메모리 로그를 새 저장소로 갈아끼우고 로드 플래그 리셋
    monkeypatch.setattr(storage, "audit_logs", storage.Repository())
    monkeypatch.setattr(lifecycle, "_audit_loaded", False)
    records = lifecycle.get_audit_log()
    assert any(r.action == "case_closed" and r.target_id == case.id for r in records)


def test_audit_load_skips_corrupt_lines(monkeypatch, tmp_path):
    """파일 일부가 손상돼도 나머지 증적은 살린다."""
    good = AuditRecord(id="rec-good", action="case_purged",
                       target_type="case", target_id="case-x")
    path = tmp_path / "corrupt.jsonl"
    path.write_text("깨진 줄{{{\n" + good.model_dump_json() + "\n", encoding="utf-8")
    monkeypatch.setattr(settings, "privacy_audit_path", str(path))
    monkeypatch.setattr(lifecycle, "_audit_loaded", False)
    monkeypatch.setattr(storage, "audit_logs", storage.Repository())
    assert [r.id for r in lifecycle.get_audit_log()] == ["rec-good"]


def test_audit_log_contains_no_personal_data():
    """파기 증적에 이름·좌표 등 개인정보가 새면 파기가 모순이 된다."""
    persona = _make_persona()
    case = _make_case(persona_id=persona.id)
    lifecycle.close_case(case, CloseReason.found)
    lifecycle.purge_persona(persona.id)
    dump = " ".join(r.model_dump_json() for r in storage.audit_logs.list())
    assert "김실종" not in dump
    assert str(LKP.lat) not in dump
