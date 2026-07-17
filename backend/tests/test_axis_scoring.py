"""축 점수 컴파일(phase0.axis_scoring) — 골드셋 실험으로 확정된 규약의 스펙 테스트.

EXAONE 은 가짜 클라이언트로 대체: 채점 로직(기준표 파싱, 다수결, F 폴백,
quote 검증, 형식 위반 복구)과 인터뷰 배관(원발화 보존 → axis_quotes)을 검증한다.
"""

import threading
import time

from app.geo.geocode import GazetteerGeocoder
from app.phase0 import axis_scoring, interview
from app.phase0.slots import slot_by_key
from app.schemas.common import GeoPoint
from app.schemas.persona import InterviewSession, Persona, PersonaType


# ── 가짜 EXAONE — 응답 목록을 순서대로 돌려준다 ─────────────────────

class FakeExaone:
    is_stub = False

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


def _persona(ptype=PersonaType.dementia, quotes=None, evidence=None):
    return Persona(
        id="p1", type=ptype, name="김순자", age=78,
        home=GeoPoint(lat=37.6, lng=127.0),
        axis_quotes=quotes or {}, axis_evidence=evidence or {},
    )


def _resp(choice, quote="", reason="근거"):
    return f'{{"choice": "{choice}", "quote": "{quote}", "reason": "{reason}"}}'


# ── 1) 기준표 로드·채점 축 집합 ─────────────────────────────────────

def test_rubric_loads_all_axes_with_directions():
    # 2026-07-17 축 구조 개정: route_environment_familiarity 제외로 10축(방향표는
    # 관계변수 제외라 마찬가지로 10) — 공통3+치매3+발달4
    rubrics, directions = axis_scoring.load_rubrics()
    assert len(rubrics) == 10 and len(directions) == 10
    assert "route_environment_familiarity" not in rubrics   # 관계 변수로 분리됨
    for r in rubrics.values():
        assert set(r["anchors"]) == {"0.1", "0.3", "0.5", "0.7", "0.9"}


def test_scored_axes_dementia_six_developmental_seven():
    # 치매: 공통3+특화3(길찾기·자전적기억·정서반응)=6, 발달: 공통3+특화4=7
    rubrics, _ = axis_scoring.load_rubrics()
    dem = axis_scoring.scored_axes(PersonaType.dementia, rubrics)
    dd = axis_scoring.scored_axes(PersonaType.intellectual_disability, rubrics)
    assert len(dem) == 6 and len(dd) == 7
    # 관찰 지표(점수 없음)·경로 관계변수는 기준표에 없어 자동 제외
    assert "lost_behavior" not in dem and "dementia_wandering_pattern" not in dem
    assert "route_environment_familiarity" not in dem
    assert "elopement_pattern_consistency" in dd   # 행동축이지만 채점 대상


# ── 2) 다수결·중앙값·F ──────────────────────────────────────────────

def test_majority_wins():
    assert axis_scoring._majority([0.5, 0.5, 0.7]) == (0.5, "다수결")


def test_no_majority_falls_back_to_median():
    score, how = axis_scoring._majority([0.9, 0.5, 0.7])
    assert score == 0.7 and "중앙값" in how


def test_f_majority_gives_none():
    score, how = axis_scoring._majority([None, None, 0.5])
    assert score is None and "판정 불가" in how


# ── 3) 채점 본체 — 근거 있는 축만 호출, F·근거 없음은 미채점 ─────────

def test_score_axes_for_scores_only_evidenced_axes():
    quote = "쉬지 않고 30분 정도 걸으시고, 버스는 혼자 못 타요"
    p = _persona(quotes={"mobility_transport_capacity": [quote]})
    fake = FakeExaone([_resp("C", quote)] * 3)
    scores, report = axis_scoring.score_axes_for(p, client=fake, runs=3)
    assert scores == {"mobility_transport_capacity": 0.5}
    assert fake.calls == 3                       # 근거 없는 나머지 축은 호출 자체가 없다
    assert len(report["unscored"]) == 5          # 치매 6축 - 근거 있는 1축
    assert all(v == "근거 없음(추출 공백)" for v in report["unscored"].values())


def test_f_axis_is_unscored_not_zero():
    p = _persona(quotes={"hazard_awareness_vulnerability": ["같이 나가본 적이 없어요"]})
    fake = FakeExaone([_resp("F")] * 3)
    scores, report = axis_scoring.score_axes_for(p, client=fake, runs=3)
    assert "hazard_awareness_vulnerability" not in scores
    assert "판정 불가" in report["unscored"]["hazard_awareness_vulnerability"]


def test_format_violation_recovered_and_counted():
    quote = "신호를 잘 안 지키세요"
    p = _persona(quotes={"hazard_awareness_vulnerability": [quote]})
    # run2 는 실측된 위반 형태(닫는 중괄호 중복) — 복구되고 위반으로 집계
    fake = FakeExaone([_resp("C", quote), _resp("C", quote) + "}", _resp("C", quote)])
    scores, report = axis_scoring.score_axes_for(p, client=fake, runs=3)
    assert scores["hazard_awareness_vulnerability"] == 0.5
    assert report["axes"]["hazard_awareness_vulnerability"]["format_violations"] == 1


def test_quote_hallucination_is_flagged():
    p = _persona(quotes={"hazard_awareness_vulnerability": ["신호를 잘 안 지키세요"]})
    fake = FakeExaone([_resp("C", "물가에 자주 가려고 하세요")] * 3)   # 입력에 없는 인용
    _, report = axis_scoring.score_axes_for(p, client=fake, runs=3)
    assert report["axes"]["hazard_awareness_vulnerability"]["quote_fails"] == 3


def test_stub_mode_skips_scoring():
    class Stub:
        is_stub = True
    scores, report = axis_scoring.score_axes_for(_persona(), client=Stub())
    assert scores == {} and "skipped" in report


def test_transient_failure_is_retried(monkeypatch):
    # 일시 장애 1회는 재시도로 복구 — run 유실 없음 (비동기 유실 방지 fix)
    monkeypatch.setattr(axis_scoring, "RETRY_WAIT_S", 0)
    quote = "쉬지 않고 30분 정도 걸으시고, 버스는 혼자 못 타요"

    class FlakyOnce(FakeExaone):
        def chat(self, messages, **kwargs):
            if self.calls + 1 == 2:      # run2 의 1차 시도만 실패
                self.calls += 1
                raise RuntimeError("일시 오류")
            return super().chat(messages, **kwargs)

    p = _persona(quotes={"mobility_transport_capacity": [quote]})
    fake = FlakyOnce([_resp("C", quote)] * 3)
    scores, report = axis_scoring.score_axes_for(p, client=fake, runs=3)
    meta = report["axes"]["mobility_transport_capacity"]
    assert scores["mobility_transport_capacity"] == 0.5
    assert meta["retries"] == 1 and meta["errors"] == 0
    assert len(meta["choices"]) == 3      # 세 run 모두 살아남음


def test_repeated_failure_drops_run_only(monkeypatch):
    monkeypatch.setattr(axis_scoring, "RETRY_WAIT_S", 0)
    quote = "쉬지 않고 30분 정도 걸으시고, 버스는 혼자 못 타요"

    class FlakyTwice(FakeExaone):
        def chat(self, messages, **kwargs):
            if self.calls + 1 in (2, 3):  # run2 는 재시도까지 실패 → run 폐기
                self.calls += 1
                raise RuntimeError("일시 오류")
            return super().chat(messages, **kwargs)

    p = _persona(quotes={"mobility_transport_capacity": [quote]})
    fake = FlakyTwice([_resp("C", quote)] * 2)
    scores, report = axis_scoring.score_axes_for(p, client=fake, runs=3)
    assert scores["mobility_transport_capacity"] == 0.5
    assert report["axes"]["mobility_transport_capacity"]["errors"] == 1


# ── 6) 백필 — 미채점 persona 의 마지막 채점 기회 (신고 접수 시) ──────

def _saved_unscored(pid: str):
    p = _persona()
    p.id = pid
    p.axis_quotes = {"mobility_transport_capacity": ["쉬지 않고 30분 걸으세요"]}
    interview.storage.personas.save(pid, p)
    return p


def test_backfill_scores_unscored_persona(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "axis_scoring_enabled", True)
    # 백필은 골든타임 경로라 항상 강제 비동기(force_async=True) — 결정론적 검증을
    # 위해 _start_scoring 을 동기 호출로 대체(실 스레드 타이밍에 의존하지 않음).
    monkeypatch.setattr(interview, "_start_scoring",
                        lambda pid, **kw: interview._score_and_save(pid))
    monkeypatch.setattr(axis_scoring, "score_axes_for",
                        lambda persona, **kw: ({"mobility_transport_capacity": 0.5}, {"runs": 3}))
    _saved_unscored("bf1")
    interview.ensure_axis_scores("bf1")
    assert interview.storage.personas.get("bf1").axis_scores == {
        "mobility_transport_capacity": 0.5}


def test_backfill_marks_in_progress_and_triggers(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "axis_scoring_enabled", True)
    called = []
    monkeypatch.setattr(interview, "_start_scoring", lambda pid, **kw: called.append(pid))
    _saved_unscored("bf2")
    interview.ensure_axis_scores("bf2")
    assert called == ["bf2"]
    # 진행 중 표시 저장 → 연속 신고에도 이중 채점(이중 쿼터) 방지
    assert (interview.storage.personas.get("bf2").axis_scoring_report["status"]
            == interview._SCORING_IN_PROGRESS)
    interview.ensure_axis_scores("bf2")
    assert called == ["bf2"]


def test_backfill_skips_scored_in_progress_and_no_evidence(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "axis_scoring_enabled", True)
    called = []
    monkeypatch.setattr(interview, "_start_scoring", lambda pid, **kw: called.append(pid))
    p1 = _saved_unscored("bf3")
    p1.axis_scores = {"mobility_transport_capacity": 0.5}   # 이미 채점됨
    interview.storage.personas.save("bf3", p1)
    p2 = _persona()
    p2.id = "bf4"                                           # 근거 없음(직접 등록)
    interview.storage.personas.save("bf4", p2)
    interview.ensure_axis_scores("bf3")
    interview.ensure_axis_scores("bf4")
    interview.ensure_axis_scores(None)                      # persona 미연결 신고
    interview.ensure_axis_scores("없는아이디")
    assert called == []


# ── 6-보강) 셀프리뷰 발견 수정 검증 (2026-07-17) ─────────────────────

def test_scoring_does_not_resurrect_deleted_persona(monkeypatch):
    # 파기 경합: 채점 도중(score_axes_for 실행 중) 보호자가 삭제를 요청하면,
    # 채점 완료 후의 저장이 삭제된 persona 를 되살리면 안 된다.
    pid = "del1"
    p = _persona()
    p.id = pid
    interview.storage.personas.save(pid, p)

    def fake_score_then_delete(persona, **kw):
        interview.storage.personas.delete(pid)   # 채점 도중 삭제 요청 도착 가정
        return ({"mobility_transport_capacity": 0.5}, {"runs": 3})

    monkeypatch.setattr(axis_scoring, "score_axes_for", fake_score_then_delete)
    interview._score_and_save(pid)
    assert interview.storage.personas.get(pid) is None


def test_ensure_axis_scores_lock_prevents_double_trigger(monkeypatch):
    # 락 없이는 근접 시각의 중복 호출(같은 사람 신고 2건)이 둘 다 체크를 통과해
    # 이중 채점(이중 EXAONE 쿼터)을 걸 수 있었다 — 락으로 원자화.
    from app.config import settings
    monkeypatch.setattr(settings, "axis_scoring_enabled", True)
    called = []
    monkeypatch.setattr(interview, "_start_scoring", lambda pid, **kw: called.append(pid))
    _saved_unscored("race1")

    barrier = threading.Barrier(2)

    def trigger():
        barrier.wait()
        interview.ensure_axis_scores("race1")

    threads = [threading.Thread(target=trigger) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert called == ["race1"]


def test_backfill_forces_async_regardless_of_setting(monkeypatch):
    # 골든타임(신고 접수) 경로는 AXIS_SCORING_ASYNC 설정이 off 여도 블로킹되면 안 됨.
    from app.config import settings
    monkeypatch.setattr(settings, "axis_scoring_enabled", True)
    monkeypatch.setattr(settings, "axis_scoring_async", False)
    started = threading.Event()
    finished = threading.Event()

    def slow_score(persona, **kw):
        started.set()
        finished.wait(timeout=2)
        return ({"mobility_transport_capacity": 0.5}, {"runs": 3})

    monkeypatch.setattr(axis_scoring, "score_axes_for", slow_score)
    _saved_unscored("golden1")

    t0 = time.time()
    interview.ensure_axis_scores("golden1")
    elapsed = time.time() - t0
    assert elapsed < 1.0        # 즉시 반환 — 채점은 백그라운드에서 진행 중이어야 함
    assert started.wait(timeout=1)
    finished.set()


# ── 4) 인터뷰 배관 — 원발화 보존 → finalize 에서 axis_quotes ─────────

def test_apply_extraction_keeps_utterance_only_when_evidence():
    s = InterviewSession(id="q1", guardian_name="보호자", persona_type=PersonaType.dementia)
    slot = slot_by_key("mobility_transport_capacity")
    interview._apply_extraction(
        s, slot, {"behavior_notes": ["30분 걸음"]}, utterance="쉬지 않고 30분 걸으세요")
    interview._apply_extraction(s, slot, {}, utterance="글쎄요")   # 근거 없음 → 미보존
    assert s.slot_quotes["mobility_transport_capacity"] == ["쉬지 않고 30분 걸으세요"]


def test_attraction_only_answer_is_preserved():
    # 장소 추출물만 나온 답변도 원발화 보존 — 자전적기억 축 근거 공백 완화
    s = InterviewSession(id="q2", guardian_name="보호자", persona_type=PersonaType.dementia)
    slot = slot_by_key("autobiographical_destination_pull")
    interview._apply_extraction(
        s, slot, {"attraction_points": [{"label": "옛집", "area_text": "면목동"}]},
        utterance="예전 살던 면목동 집에 가야 한다고 하세요")
    assert s.slot_quotes["autobiographical_destination_pull"] == ["예전 살던 면목동 집에 가야 한다고 하세요"]


def test_finalize_maps_quotes_to_axis_and_flag_off_by_default():
    s = InterviewSession(
        id="q3", guardian_name="보호자", persona_type=PersonaType.dementia,
        draft_fields={"name": "김순자", "age": "78세", "home": "성북구 정릉동"},
        slot_quotes={"mobility_transport_capacity": ["쉬지 않고 30분 걸으세요"],
                     "medication": ["혈압약 드세요"]},        # axis_field 없음 → 제외
        awaiting_confirmation=True,
    )
    p = interview.finalize_persona(s, geocoder=GazetteerGeocoder())
    assert p.axis_quotes["mobility_transport_capacity"] == ["쉬지 않고 30분 걸으세요"]
    assert "medication" not in p.axis_quotes
    assert p.axis_scores == {}          # 기능 플래그 기본 off — 회의 채택 전 무동작


# ── 5) 채점 실행 경로 — 확정 후 채점, 비동기 기본 ────────────────────

def _confirmed_session(sid: str) -> InterviewSession:
    return InterviewSession(
        id=sid, guardian_name="보호자", persona_type=PersonaType.dementia,
        draft_fields={"name": "김순자", "age": "78세", "home": "성북구 정릉동"},
        slot_quotes={"mobility_transport_capacity": ["쉬지 않고 30분 걸으세요"]},
        awaiting_confirmation=True,
    )


def test_finalize_scores_after_confirm_when_sync(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "axis_scoring_enabled", True)
    monkeypatch.setattr(settings, "axis_scoring_async", False)
    monkeypatch.setattr(
        axis_scoring, "score_axes_for",
        lambda persona, **kw: ({"mobility_transport_capacity": 0.5}, {"runs": 3}))
    p = interview.finalize_persona(_confirmed_session("sync1"), geocoder=GazetteerGeocoder())
    saved = interview.storage.personas.get(p.id)
    assert saved.axis_scores == {"mobility_transport_capacity": 0.5}
    assert saved.axis_scoring_report == {"runs": 3}


def test_finalize_async_returns_before_scores_arrive(monkeypatch):
    # 비동기 기본값: finalize 반환 시점의 저장본에는 "채점 진행 중" 상태만 있고,
    # 점수는 백그라운드 완료 후 채워진다 (스레드 시작을 가로채 시점만 검증).
    from app.config import settings
    monkeypatch.setattr(settings, "axis_scoring_enabled", True)
    monkeypatch.setattr(settings, "axis_scoring_async", True)
    import threading
    started = {}
    monkeypatch.setattr(threading.Thread, "start", lambda self: started.setdefault("y", True))
    p = interview.finalize_persona(_confirmed_session("async1"), geocoder=GazetteerGeocoder())
    saved = interview.storage.personas.get(p.id)
    assert saved.axis_scores == {}                     # 응답 시점엔 점수 없음(지연 제거)
    assert saved.axis_scoring_report["status"].startswith("채점 진행 중")
    assert started.get("y")                            # 백그라운드 채점이 예약됨


def test_score_and_save_failure_keeps_registration(monkeypatch):
    p = _persona()
    interview.storage.personas.save(p.id, p)

    def boom(persona, **kw):
        raise RuntimeError("EXAONE 다운")
    monkeypatch.setattr(axis_scoring, "score_axes_for", boom)
    interview._score_and_save(p.id)
    saved = interview.storage.personas.get(p.id)
    assert saved is not None and saved.axis_scores == {}
    assert "RuntimeError" in saved.axis_scoring_report["error"]
