"""P1-5 스테이지 타이머 — 예측 소요시간 계측 (계측은 결과에 영향 없음)."""

from datetime import datetime, timedelta

from app import storage
from app.llm.exaone import ExaoneClient
from app.phase2 import pipeline
from app.schemas.case import Case, CaseStatus
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.report import MissingReport

LKP = GeoPoint(lat=37.6061, lng=127.0106)


def _case() -> Case:
    report = MissingReport(id=storage.new_id(), persona_id=None,
                           missing_type=PersonaType.dementia,
                           lkp=LKP, lkp_time=datetime.now() - timedelta(hours=1))
    return Case(id=storage.new_id(), report=report, status=CaseStatus.intake,
                lkp=report.lkp, lkp_time=report.lkp_time)


def test_call_log_records_ts_and_elapsed():
    """call_log 항목에 ts(ISO)·elapsed_ms 가 붙는다 — P2-1 이 이 값을 집계."""
    c = ExaoneClient()
    c._log_call("prior", "p", "r", elapsed_ms=12.34)
    entry = c.call_log[-1]
    assert entry["ts"] and entry["elapsed_ms"] == 12.3
    c._log_call("mind", "p", "r")
    assert c.call_log[-1]["elapsed_ms"] is None


def test_run_prediction_records_stage_timings():
    """트레이스 예측이 8개 스테이지 타이밍을 저장하고, 부분합이 total 을 넘지 않는다."""
    case = _case()
    storage.cases.save(case.id, case)
    pipeline.run_prediction(case, seed=1, trace=True)
    debug = storage.debug_traces.get(case.id)
    keys = {"prepare_ms", "prior_ms", "roadnet_ms", "topdown_ms",
            "bottomup_ms", "statistical_ms", "combine_ms", "total_ms"}
    assert keys <= set(debug.timings)
    assert debug.timings["total_ms"] > 0
    parts = sum(v for k, v in debug.timings.items() if k != "total_ms")
    assert parts <= debug.timings["total_ms"] * 1.05
