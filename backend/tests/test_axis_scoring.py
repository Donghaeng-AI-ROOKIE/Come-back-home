"""축 점수 컴파일(phase0.axis_scoring) — 골드셋 실험으로 확정된 규약의 스펙 테스트.

EXAONE 은 가짜 클라이언트로 대체: 채점 로직(기준표 파싱, 다수결, F 폴백,
quote 검증, 형식 위반 복구)과 인터뷰 배관(원발화 보존 → axis_quotes)을 검증한다.
"""

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
    rubrics, directions = axis_scoring.load_rubrics()
    assert len(rubrics) == 11 and len(directions) == 11
    for r in rubrics.values():
        assert set(r["anchors"]) == {"0.1", "0.3", "0.5", "0.7", "0.9"}


def test_scored_axes_are_seven_per_type_excluding_observation():
    rubrics, _ = axis_scoring.load_rubrics()
    dem = axis_scoring.scored_axes(PersonaType.dementia, rubrics)
    dd = axis_scoring.scored_axes(PersonaType.intellectual_disability, rubrics)
    assert len(dem) == 7 and len(dd) == 7
    # 관찰 지표(점수 없음)는 기준표에 없어 자동 제외
    assert "lost_behavior" not in dem and "dementia_wandering_pattern" not in dem
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
    assert fake.calls == 3                       # 근거 없는 6축은 호출 자체가 없다
    assert len(report["unscored"]) == 6
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


def test_call_failure_drops_run_only():
    quote = "쉬지 않고 30분 정도 걸으시고, 버스는 혼자 못 타요"

    class Flaky(FakeExaone):
        def chat(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("일시 오류")
            return super().chat(messages, **kwargs)

    p = _persona(quotes={"mobility_transport_capacity": [quote]})
    fake = Flaky([_resp("C", quote)] * 2)
    scores, report = axis_scoring.score_axes_for(p, client=fake, runs=3)
    assert scores["mobility_transport_capacity"] == 0.5
    assert report["axes"]["mobility_transport_capacity"]["errors"] == 1


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
