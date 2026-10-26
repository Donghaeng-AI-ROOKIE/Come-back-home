"""Persist a citizen's tip before any model, geocoder or prediction work.

The durable receipt table avoids taking the case's long prediction lock during
intake. Two workers drain a bounded queue; startup recovery resumes saved work.
"""
import hashlib
import json
import logging
import queue
import threading

from fastapi import HTTPException

from app import storage
from app.privacy.lifecycle import AlreadyClosed, ensure_not_closed
from app.schemas.tip import Tip, TipReceipt

log = logging.getLogger(__name__)
_guard = threading.RLock()
_queue = queue.Queue(maxsize=128)
_pending = set()
_started = False


def _active(case_id):
    case = storage.cases.get(case_id)
    if case is None:
        raise HTTPException(404, '사건을 찾을 수 없습니다.')
    ensure_not_closed(case)
    return case


def public_tip(receipt):
    return Tip(id=receipt.id, case_id=receipt.case_id, text=receipt.text,
               location=receipt.location, seen_at=receipt.seen_at,
               created_at=receipt.created_at, processing_status=receipt.state)


def receive(case_id, text, location, seen_at, submission_id, force=False):
    text = text.strip()
    if not text:
        raise HTTPException(422, '제보 내용을 입력해 주세요.')
    body = [case_id, text, location.model_dump() if location else None,
            seen_at.isoformat() if seen_at else None, force]
    fingerprint = hashlib.sha256(json.dumps(body, ensure_ascii=False).encode()).hexdigest()
    with _guard:
        case = _active(case_id)
        existing = storage.tip_receipts.get(submission_id)
        if existing is not None:
            if existing.fingerprint != fingerprint or existing.case_id != case_id:
                raise HTTPException(409, '같은 접수 번호에 다른 내용을 보낼 수 없습니다.')
            return next((t for t in case.tips if t.id == submission_id), public_tip(existing)), False
        receipt = TipReceipt(id=submission_id, case_id=case_id, fingerprint=fingerprint,
                             text=text, location=location, seen_at=seen_at)
        storage.tip_receipts.save(receipt.id, receipt)
        try:
            _active(case_id)
        except (AlreadyClosed, HTTPException):
            cancel_case(case_id)
            raise
        return public_tip(receipt), True


def with_pending(case):
    """Read-only guardian view; never replace the cached live Case object."""
    tips = list(case.tips)
    known = {t.id for t in tips}
    pending = [public_tip(r) for r in storage.tip_receipts.list()
               if r.case_id == case.id and r.id not in known
               and r.state not in ('processed', 'cancelled')]
    return case.model_copy(update={'tips': [*tips, *pending]}) if pending else case


def cancel_case(case_id):
    with _guard:
        for r in storage.tip_receipts.list():
            if r.case_id == case_id and r.state not in ('processed', 'cancelled'):
                r.state = 'cancelled'; r.text = ''; r.location = None; r.seen_at = None
                storage.tip_receipts.save(r.id, r)


def purge_case(case_id):
    with _guard:
        for r in storage.tip_receipts.list():
            if r.case_id == case_id:
                storage.tip_receipts.delete(r.id)


def process(receipt_id):
    from app.llm import tip_llm
    from app.phase3 import tip_flow
    with _guard:
        r = storage.tip_receipts.get(receipt_id)
        if r is None or r.state in ('processed', 'cancelled') or r.attempts >= 2:
            return
        try:
            case = _active(r.case_id)
        except (AlreadyClosed, HTTPException):
            cancel_case(r.case_id); return
        r.state = 'running'; r.attempts += 1
        storage.tip_receipts.save(r.id, r)
        existing = next((t for t in case.tips if t.id == r.id), None)
        # The input snapshot is private to this attempt. No case lock spans the LLM.
        text, location, seen_at, created_at = r.text, r.location, r.seen_at, r.created_at
    try:
        structured = tip_llm.structure_tip(text) if existing is None else None
        with storage.case_lock(r.case_id):
            with _guard:
                current = storage.tip_receipts.get(r.id)
                if current is None or current.state == 'cancelled':
                    return
            case = _active(r.case_id)
            result = next((t for t in case.tips if t.id == r.id), None)
            if result is None:
                # Incomplete natural-language reports remain saved for the guardian;
                # never substitute the citizen's present GPS for a past sighting.
                result = tip_flow.process_tip(case, text=text, location=location,
                    seen_at=seen_at, force=True, now=created_at, defer_heavy=True,
                    tip_id=r.id, prestructured=structured)
                result.created_at = created_at
            result.processing_status = 'running'
            storage.cases.save(case.id, case)
        heavy_ok = True
        if tip_flow.needs_heavy(case, result):
            heavy_ok = tip_flow.finish_tip(case.id, result.id) is not False
        with storage.case_lock(r.case_id):
            case = _active(r.case_id)
            result = next(t for t in case.tips if t.id == r.id)
            result.processing_status = 'processed' if heavy_ok else 'failed'
            storage.cases.save(case.id, case)
        with _guard:
            current = storage.tip_receipts.get(r.id)
            if current is not None and current.state != 'cancelled':
                current.state = 'processed' if heavy_ok else 'failed'
                current.error_code = '' if heavy_ok else 'map_update_failed'
                # Once transferred to Case.tips, avoid retaining a second raw copy.
                current.text = ''; current.location = None; current.seen_at = None
                storage.tip_receipts.save(current.id, current)
    except (AlreadyClosed, HTTPException):
        cancel_case(r.case_id)
    except Exception as exc:  # noqa: BLE001 — 분석이 실패해도 원문은 남기고 재시도 대상으로 둔다
        with _guard:
            current = storage.tip_receipts.get(r.id)
            if current is not None and current.state != 'cancelled':
                current.state = 'failed'; current.error_code = type(exc).__name__
                storage.tip_receipts.save(current.id, current)
        log.warning('Saved tip analysis failed: %s', type(exc).__name__)


def _enqueue(receipt_id):
    with _guard:
        if receipt_id in _pending:
            return
        try:
            _queue.put_nowait(receipt_id)
        except queue.Full:
            return  # It is durably saved; the next recovery scan will enqueue it.
        _pending.add(receipt_id)


def recover():
    for r in storage.tip_receipts.list():
        if r.state in ('queued', 'running', 'failed') and r.attempts < 2:
            _enqueue(r.id)


def _worker():
    while True:
        receipt_id = _queue.get()
        try:
            process(receipt_id)
        except Exception as exc:  # noqa: BLE001 — 한 건의 실패가 분석 작업자를 멈추면 안 된다
            log.warning('Tip worker retained queued work: %s', type(exc).__name__)
        finally:
            with _guard:
                _pending.discard(receipt_id)
            _queue.task_done()


def _recovery_loop():
    import time
    while True:
        try:
            recover()
        except Exception as exc:  # noqa: BLE001 — 복구 검사가 실패해도 다음 주기에 다시 본다
            log.warning('Tip recovery failed: %s', type(exc).__name__)
        time.sleep(10)


def start():
    global _started
    with _guard:
        if _started:
            return
        _started = True
        for i in range(2):
            threading.Thread(target=_worker, name=f'tip-analysis-{i}', daemon=True).start()
        threading.Thread(target=_recovery_loop, name='tip-recovery', daemon=True).start()


def schedule(case_id, receipt_id):
    start()
    _enqueue(receipt_id)
