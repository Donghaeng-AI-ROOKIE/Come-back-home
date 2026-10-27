"""제보 처리 단계 시간 로그 — 어디서 기다렸는지 워커 로그에 남는가.

10/27 운영 측정 4회차: 목격 제보 분석이 끝나고 재예측의 첫 모델 호출까지 88초가
비었는데, 그 사이 기록이 없어 어느 잠금을 누가 쥐고 있었는지 알 수 없었다.
"""
import re
import threading
import time
from datetime import datetime, timedelta

import pytest
from fastapi import BackgroundTasks

from app import storage
from app.api import phase3
from app.phase3 import alerts, tip_flow, tip_receipts
from app.schemas.case import Case, CaseStatus
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.report import MissingReport
from app.schemas.tip import Tip, TipDecision

POINT = GeoPoint(lat=37.5216, lng=126.9243)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    storage.reset_for_tests()
    monkeypatch.setattr(tip_receipts, "schedule", lambda *a: None)
    yield
    storage.reset_for_tests()


@pytest.fixture()
def fast_thresholds(monkeypatch):
    monkeypatch.setattr(storage, "LOCK_WAIT_LOG_MS", 50)
    monkeypatch.setattr(storage, "LOCK_HOLD_LOG_MS", 50)


def make_case(tips=()):
    now = datetime.now()  # noqa: DTZ005 — Case 시각 필드는 naive(LocalNaiveDT)
    c = Case(id="timing-case", guardian_id="owner",
             report=MissingReport(id="r", missing_type=PersonaType.dementia, lkp=POINT, lkp_time=now - timedelta(hours=1)),
             lkp=POINT, lkp_time=now - timedelta(hours=1), status=CaseStatus.predicted,
             current_poa={"8930e1d80c3ffff": 1.0}, tips=list(tips))
    storage.cases.save(c.id, c)
    return c


def receive(c):
    return phase3.submit_tip(c.id, phase3.TipIn(text="합성 제보 원문", background_analysis=True,
                                                submission_id="timing-one", reporter_user_id="owner"), BackgroundTasks())


def hold_in_thread(lock, seconds):
    entered = threading.Event()

    def run():
        with lock:
            entered.set()
            time.sleep(seconds)

    thread = threading.Thread(target=run)
    thread.start()
    assert entered.wait(1)
    return thread


def stage_ms(line, key):
    return int(re.search(rf"{key}=(\d+)", line).group(1))


def test_long_wait_is_logged_with_who_waited(capsys, fast_thresholds):
    lock = threading.Lock()
    thread = hold_in_thread(lock, 0.2)
    with storage.timed_lock(lock, "tester", "case-1") as held:
        pass
    thread.join(1)
    assert held.wait_ms >= 150
    assert "[lock-wait] by=tester case=case-1 wait_ms=" in capsys.readouterr().out


def test_long_hold_is_logged_after_release(capsys, fast_thresholds):
    lock = threading.Lock()
    with storage.timed_lock(lock, "slow-holder", "case-2"):
        time.sleep(0.1)
    assert not lock.locked()
    assert "[lock-hold] by=slow-holder case=case-2 hold_ms=" in capsys.readouterr().out


def test_short_waits_and_holds_stay_quiet(capsys):
    with storage.timed_lock(threading.Lock(), "quick", "case-3"):
        pass
    assert capsys.readouterr().out == ""


def test_lock_is_released_when_the_body_raises():
    lock = threading.Lock()
    with pytest.raises(ValueError), storage.timed_lock(lock, "boom"):
        raise ValueError("body failed")
    assert not lock.locked()


def test_serialize_case_names_the_holder_and_stays_reentrant(capsys, fast_thresholds):
    @storage.serialize_case
    def outer(case_id):
        return inner(case_id)

    @storage.serialize_case
    def inner(case_id):
        time.sleep(0.1)
        return "ok"

    assert outer("case-4") == "ok"  # nested on the same RLock stripe must not deadlock
    out = capsys.readouterr().out
    assert re.search(r"\[lock-hold\] by=\S*outer case=case-4 hold_ms=\d+", out)


def test_receipt_processing_prints_one_stage_line(capsys, monkeypatch):
    c = make_case()
    receipt = receive(c)
    monkeypatch.setattr(tip_flow.tip_llm, "structure_tip", lambda *a: {"specificity": "중"})
    monkeypatch.setattr(tip_flow, "needs_heavy", lambda *a: False)
    tip_receipts.process(receipt.id)
    lines = [l for l in capsys.readouterr().out.splitlines() if l.startswith("[tip-timing]")]
    assert len(lines) == 1
    line = lines[0]
    assert f"receipt={receipt.id[:8]} case={c.id}" in line and "outcome=processed" in line
    for key in ("queued_ms", "structure_ms", "lock_wait_ms", "analyze_ms", "final_lock_wait_ms", "total_ms"):
        assert f"{key}=" in line
    assert "heavy_ms=" not in line


def test_receipt_line_shows_the_case_lock_wait(capsys, monkeypatch, fast_thresholds):
    c = make_case()
    receipt = receive(c)
    monkeypatch.setattr(tip_flow.tip_llm, "structure_tip", lambda *a: {"specificity": "중"})
    monkeypatch.setattr(tip_flow, "needs_heavy", lambda *a: False)
    thread = hold_in_thread(storage.case_lock(c.id), 0.3)
    tip_receipts.process(receipt.id)
    thread.join(1)
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if l.startswith("[tip-timing]"))
    assert stage_ms(line, "lock_wait_ms") >= 200
    assert f"[lock-wait] by=tip_receipts.process case={c.id}" in out


def test_receipt_line_includes_heavy_time(capsys, monkeypatch):
    c = make_case()
    receipt = receive(c)
    monkeypatch.setattr(tip_flow.tip_llm, "structure_tip", lambda *a: {"specificity": "중"})
    monkeypatch.setattr(tip_flow, "needs_heavy", lambda *a: True)
    monkeypatch.setattr(tip_flow, "finish_tip", lambda *a: time.sleep(0.05) or True)
    tip_receipts.process(receipt.id)
    line = next(l for l in capsys.readouterr().out.splitlines() if l.startswith("[tip-timing]"))
    assert stage_ms(line, "heavy_ms") >= 40


def test_failed_analysis_still_prints_its_stages(capsys, monkeypatch):
    c = make_case()
    receipt = receive(c)
    monkeypatch.setattr(tip_flow.tip_llm, "structure_tip", lambda *a: {"specificity": "중"})

    def broken(*a, **k):
        raise RuntimeError("analysis failed")

    monkeypatch.setattr(tip_flow, "process_tip", broken)
    tip_receipts.process(receipt.id)
    line = next(l for l in capsys.readouterr().out.splitlines() if l.startswith("[tip-timing]"))
    assert "outcome=RuntimeError" in line and "structure_ms=" in line


def test_finish_tip_prints_layer2_prediction_stages(capsys, monkeypatch):
    seen = datetime.now() - timedelta(minutes=10)  # noqa: DTZ005 — Tip.seen_at 은 naive(LocalNaiveDT)
    tip = Tip(id="layer2-tip-1", case_id="timing-case", text="목격", location=POINT, seen_at=seen,
              p=0.97, decision=TipDecision.layer2)
    c = make_case([tip])
    monkeypatch.setattr(tip_flow.pipeline, "run_prediction", lambda case, now=None: time.sleep(0.05))
    monkeypatch.setattr(alerts, "notify_prediction", lambda case: {})
    assert tip_flow.finish_tip(c.id, tip.id) is True
    line = next(l for l in capsys.readouterr().out.splitlines() if l.startswith("[tip-heavy]"))
    assert f"case={c.id} tip=layer2-t" in line and "kind=layer2" in line
    assert stage_ms(line, "predict_ms") >= 40
    for key in ("lock_wait_ms", "notify_ms", "total_ms"):
        assert f"{key}=" in line
