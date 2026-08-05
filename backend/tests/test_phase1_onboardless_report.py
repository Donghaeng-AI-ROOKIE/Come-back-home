"""온보딩 없는 신고 흐름(2026-08) — 신규 코드 경로 검증.

기존 챗봇 엔진(answer_interview 내부 알고리즘)은 손대지 않았으므로 기존 테스트
(test_interview_*.py)가 그 회귀를 이미 담당한다. 여기서는 이번에 새로 얹은 레이어만
검증한다:
  1. slots_for(tiers=...) 필터
  2. persona_status_for() 상태 판정
  3. 신고 전 Tier1 미니챗 — 확인 게이트 생략 자동 확정(skip_confirmation)
  4. 보완챗(supplement) — 기존 persona 병합(Tier1 보존, id·버전 유지하며 갱신)
  5. persona 갱신 → 진행중 case 재예측 트리거(persona_events), 종결 case는 제외
"""

from datetime import datetime, timedelta

from app import storage
from app.geo.geocode import GazetteerGeocoder
from app.phase0 import interview, persona_events, retrieval
from app.phase0.slots import slots_for
from app.schemas.case import Case, CaseStatus, CloseReason
from app.schemas.common import GeoPoint
from app.schemas.persona import InterviewSession, Persona, PersonaType
from app.schemas.report import MissingReport

EMB = retrieval.HashingEmbedder()
HOME = GeoPoint(lat=37.6060, lng=127.0092)   # 성북구 정릉동 대략 좌표


# ── 1) slots_for tier 필터 ────────────────────────────────────────────

def test_slots_for_tiers_none_is_unchanged():
    """tiers 인자를 안 주면 기존 slots_for(ptype) 과 완전히 동일."""
    assert slots_for(PersonaType.dementia, None) == slots_for(PersonaType.dementia)


def test_slots_for_tier1_is_five_route_slots():
    tier1 = slots_for(PersonaType.dementia, [1])
    all_slots = slots_for(PersonaType.dementia)
    assert len(tier1) == 5
    assert {s.key for s in tier1} == {
        "identity", "home", "routine_destinations",
        "autobiographical_destination_pull", "dementia_wandering_pattern",
    }
    assert all(s.tier.value == 1 for s in tier1)
    # Tier1 + 나머지(Tier2·3) = 전체, 서로 안 겹침
    rest = slots_for(PersonaType.dementia, [2, 3])
    assert len(rest) == 7
    assert not ({s.key for s in tier1} & {s.key for s in rest})
    assert len(tier1) + len(rest) == len(all_slots)


# ── 2) persona_status_for ─────────────────────────────────────────────

def test_persona_status_none_when_no_persona():
    assert interview.persona_status_for(None) == ("none", "create")


def test_persona_status_partial_after_tier1_only():
    p = Persona(id="p_partial", type=PersonaType.dementia, name="김순자", age=78,
                home=HOME, completed_tiers=[1])
    assert interview.persona_status_for(p) == ("partial", "supplement")


def test_persona_status_complete_after_all_tiers():
    p = Persona(id="p_complete", type=PersonaType.dementia, name="김순자", age=78,
                home=HOME, completed_tiers=[1, 2, 3])
    assert interview.persona_status_for(p) == ("complete", "update")


def test_persona_status_legacy_persona_without_tier_tracking_is_complete():
    """register_persona(구조화 직접등록)처럼 이 인터뷰 흐름을 안 거친 persona —
    completed_tiers 가 비어 있어도 이미 필드가 있으니 complete 취급한다."""
    p = Persona(id="p_legacy", type=PersonaType.dementia, name="김순자", age=78, home=HOME)
    assert interview.persona_status_for(p) == ("complete", "update")


# ── 3) 신고 전 Tier1 미니챗 — skip_confirmation 자동 확정 ───────────────

def _tier1_ready_session(sid: str, *, guardian_id: str = "g1") -> InterviewSession:
    """Tier1 5개 슬롯이 이미 다 채워지고 확정 직전인 세션(기존 test_interview_hardening.py
    의 _confirmed_session 패턴 재사용 — prev_target_key=None 이면 답변 처리의 추출
    단계를 건너뛰고 곧장 종료 판정으로 간다)."""
    tier1_keys = [s.key for s in slots_for(PersonaType.dementia, [1])]
    s = InterviewSession(
        id=sid, guardian_name="보호자", persona_type=PersonaType.dementia,
        mode="create", target_tiers=[1], skip_confirmation=True, guardian_id=guardian_id,
        draft_fields={"name": "김순자", "age": "78세", "home": "성북구 정릉동"},
        draft_attractions=[{"label": "정릉시장", "area_text": "성북구 정릉동",
                             "place_type": "market", "evidence": "mention_only",
                             "origin_slot": "routine_destinations"}],
        filled_keys=tier1_keys,
        asked_more_places=True,   # 요약 전 추가장소 스윕 게이트 통과 처리
    )
    storage.interviews.save(s.id, s)
    return s


def test_tier1_quickchat_autofinalizes_without_confirmation(monkeypatch):
    monkeypatch.setattr(interview, "_GEO", GazetteerGeocoder())
    s = _tier1_ready_session("qc1")

    out = interview.answer_interview(s.id, "네")

    assert out.done
    assert not out.awaiting_confirmation
    assert out.persona_id

    persona = storage.personas.get(out.persona_id)
    assert persona is not None
    assert persona.completed_tiers == [1]
    assert persona.guardian_id == "g1"
    assert persona.name == "김순자"
    assert len(persona.attraction_points) == 1


def test_tier1_quickchat_finalize_failure_recovers_without_confirmation_loop(monkeypatch):
    """지오코딩 실패해도 skip_confirmation 경로가 죽지 않고 home 재질문으로 복귀."""
    monkeypatch.setattr(interview, "_GEO", GazetteerGeocoder())
    s = _tier1_ready_session("qc2")
    s.draft_fields["home"] = "지도에없는곳"
    storage.interviews.save(s.id, s)

    out = interview.answer_interview(s.id, "네")

    assert not out.done
    assert not out.persona_id
    assert "home" not in out.draft_fields
    assert out.prev_target_key == "home"


# ── 4) 보완챗(supplement) — 기존 persona 병합 ───────────────────────────

def _tier1_only_persona(pid: str = "p_tier1", guardian_id: str = "g2") -> Persona:
    p = Persona(
        id=pid, type=PersonaType.dementia, name="김순자", age=78, home=HOME,
        guardian_id=guardian_id, completed_tiers=[1],
        attraction_points=[],
        behavior_notes=["기존 Tier1 노트"],
    )
    storage.personas.save(p.id, p)
    return p


def test_supplement_merges_into_existing_persona_preserving_tier1(monkeypatch):
    """보완챗 완료 후: 같은 persona id 유지, 버전 증가, 기존 Tier1 데이터(behavior_notes)
    보존, 새 Tier2·3 데이터 추가, completed_tiers 가 [1,2,3] 로 확장."""
    monkeypatch.setattr(interview, "_GEO", GazetteerGeocoder())
    existing = _tier1_only_persona()
    tier23_keys = [s.key for s in slots_for(PersonaType.dementia, [2, 3])]

    s = InterviewSession(
        id="sup1", guardian_name="보호자", persona_type=PersonaType.dementia,
        mode="supplement", target_tiers=[2, 3], guardian_id="g2",
        persona_id=existing.id,   # 세션 생성 시점부터 기존 persona 에 연결
        draft_fields={},          # home 재질문 없음 — 기존 값 재사용 검증 대상
        draft_behaviors=["기존 Tier1 노트", "보완챗에서 나온 새 노트"],
        filled_keys=tier23_keys,
        asked_more_places=True,
    )
    storage.interviews.save(s.id, s)

    persona = interview.finalize_persona(s)

    assert persona.id == existing.id              # 새로 안 만들고 같은 persona
    assert persona.version == 1                    # 0 → 1
    assert persona.completed_tiers == [1, 2, 3]     # Tier1 ∪ Tier2·3
    assert persona.home == HOME                     # 세션에 home 없어 기존 값 재사용
    assert "기존 Tier1 노트" in persona.behavior_notes        # 보존
    assert "보완챗에서 나온 새 노트" in persona.behavior_notes  # 추가


def test_supplement_without_new_home_does_not_require_home_answer(monkeypatch):
    """보완챗은 애초에 home 을 다시 안 물으므로 draft_fields 에 home 이 없어도
    finalize 가 ValueError 없이 성공해야 한다(기존 persona.home 폴백)."""
    monkeypatch.setattr(interview, "_GEO", GazetteerGeocoder())
    existing = _tier1_only_persona(pid="p_tier1b", guardian_id="g3")
    s = InterviewSession(
        id="sup2", guardian_name="보호자", persona_type=PersonaType.dementia,
        mode="supplement", target_tiers=[2, 3], guardian_id="g3",
        persona_id=existing.id, draft_fields={},
    )
    storage.interviews.save(s.id, s)

    persona = interview.finalize_persona(s)   # ValueError 안 남
    assert persona.home == HOME


# ── 5) persona 갱신 → 진행중 case 재예측 트리거 ─────────────────────────

def _case_for_persona(case_id: str, persona_id: str, status: CaseStatus,
                       *, close_reason: CloseReason | None = None) -> Case:
    report = MissingReport(
        id=f"report-{case_id}", persona_id=persona_id,
        missing_type=PersonaType.dementia, lkp=HOME, lkp_time=datetime.now() - timedelta(hours=1),
    )
    case = Case(id=case_id, report=report, status=status, lkp=HOME,
                lkp_time=report.lkp_time, close_reason=close_reason)
    storage.cases.save(case.id, case)
    return case


def test_active_cases_for_excludes_found_and_closed():
    persona_id = "p_active_test"
    searching = _case_for_persona("case_searching", persona_id, CaseStatus.searching)
    _case_for_persona("case_found", persona_id, CaseStatus.found)
    _case_for_persona("case_closed", persona_id, CaseStatus.closed, close_reason=CloseReason.found)
    _case_for_persona("case_other_persona", "다른persona", CaseStatus.searching)

    active = persona_events._active_cases_for(persona_id)

    assert {c.id for c in active} == {searching.id}


def test_rerun_case_updates_poa_and_preserves_reapplied_tips(monkeypatch):
    """_rerun_case 가 실제로 run_prediction 을 돌리고 실패 없이 case 를 저장하는지 —
    스레드 래퍼(notify_persona_updated)는 타이밍이 비결정적이라 내부 함수를 직접 호출해
    결정론적으로 검증한다."""
    from app.phase0 import interview as interview_mod  # noqa: F401  (import 순환 확인용)

    persona = Persona(id="p_rerun", type=PersonaType.dementia, name="김순자", age=78,
                       home=HOME, completed_tiers=[1, 2, 3])
    storage.personas.save(persona.id, persona)
    case = _case_for_persona("case_rerun", persona.id, CaseStatus.searching)

    persona_events._rerun_case(case.id, persona.version)

    updated = storage.cases.get(case.id)
    assert updated is not None
    assert updated.current_poa is not None
    assert sum(updated.current_poa.values()) > 0.99   # 정규화된 분포


def test_rerun_case_failure_does_not_raise(monkeypatch):
    """재예측이 실패해도 예외가 밖으로 새지 않는다 — persona 저장을 되돌리면 안 됨."""
    def _boom(*a, **k):
        raise RuntimeError("예측 엔진 장애")

    from app.phase2 import pipeline
    monkeypatch.setattr(pipeline, "run_prediction", _boom)

    persona = Persona(id="p_rerun_fail", type=PersonaType.dementia, name="김순자", age=78, home=HOME)
    storage.personas.save(persona.id, persona)
    case = _case_for_persona("case_rerun_fail", persona.id, CaseStatus.searching)

    persona_events._rerun_case(case.id, persona.version)   # 예외 없이 조용히 실패

    assert storage.cases.get(case.id) is not None   # case 자체는 그대로 남아있음
