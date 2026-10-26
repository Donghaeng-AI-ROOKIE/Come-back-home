"""연구용 JSON API 요청의 사용량 원장. 표준 라이브러리만 사용.

네트워크 요청 전에 시작 이벤트를 디스크에 기록한다. 키/본문은 기록하지 않는다.
요청당 하나의 attempt_id, 재시도 전체를 묶는 logical_request_id를 사용한다.
이 모듈을 통과한 요청만 자동 기록된다. 운영 서버 전체 계측은 별도 연결 필요.
"""
from __future__ import annotations

import json
import os
import threading

try:
    import fcntl
except ImportError:  # Windows — fcntl 은 POSIX 전용이라 모듈 import 자체가 앱을 죽인다
    fcntl = None
    import msvcrt
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

DEFAULT_LEDGER = Path(__file__).with_name("usage_events.jsonl")


def _now():
    return datetime.now(timezone.utc).isoformat()


class CallBudgetExceeded(RuntimeError):
    pass


def append_event(event, ledger_path=DEFAULT_LEDGER, *, max_started=None):
    path = Path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"schema_version": 1, "event_id": str(uuid.uuid4()),
              "recorded_at": _now(), **event}
    payload = (json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n").encode()
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        index = _started_index(path) if max_started is not None else None
        if index is not None:
            # 지난 기록은 파일 잠금 밖에서 센다. 잠금을 쥔 채 큰 원장을 읽으면 같은
            # 원장에 쓰는 다른 스레드(워커 이벤트 루프 포함)가 그동안 모두 멈춘다.
            with index.lock:
                index.advance(fd, complete=False)
        _lock(fd)
        if index is not None:
            # 같은 파일 잠금 안에서 남은 꼬리만 마저 세고 예약해 동시 호출도 상한을 지킨다.
            with index.lock:
                index.advance(fd, complete=True)
                count = index.counts.get(record.get("run_id"), 0)
            if count >= max_started:
                raise CallBudgetExceeded("approved call budget exhausted")
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("ledger write failed")
            view = view[written:]
        os.fsync(fd)
    finally:
        _unlock(fd)
        os.close(fd)
    return record


class _StartedIndex:
    """이 프로세스가 이미 센 원장 앞부분의 run_id별 시작 이벤트 수.

    원장은 덧붙이기만 하므로 센 바이트는 다시 읽지 않는다. 파일이 교체·축소되거나
    앞부분이 바뀌면 처음부터 다시 센다. 메모리는 한 줄과 run_id별 숫자만 쓴다.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.identity = None
        self.head = b""
        self.offset = 0
        self.counts = {}

    def advance(self, fd, *, complete):
        """complete=False(잠금 밖)는 다른 쓰기가 끝내지 않은 마지막 줄을 남겨 둔다.
        complete=True(잠금 안)는 끝까지 읽는다. 깨진 기록은 어느 쪽이든 예외로 실패한다."""
        stat = os.fstat(fd)
        identity = (stat.st_dev, stat.st_ino)
        with os.fdopen(os.dup(fd), "rb") as reader:
            same_head = True
            if self.head:
                reader.seek(0)
                same_head = reader.read(len(self.head)) == self.head
            if identity != self.identity or stat.st_size < self.offset or not same_head:
                self.identity, self.head, self.offset, self.counts = identity, b"", 0, {}
            reader.seek(self.offset)
            for line in reader:
                if not complete and not line.endswith(b"\n"):
                    break
                if line.strip():
                    row = json.loads(line)
                    if row.get("event_type") == "api_attempt_started":
                        run_id = row.get("run_id")
                        self.counts[run_id] = self.counts.get(run_id, 0) + 1
                self.offset += len(line)
            if not self.head and self.offset:
                reader.seek(0)
                self.head = reader.read(min(self.offset, 256))


_INDEXES = {}
_INDEXES_LOCK = threading.Lock()


def _started_index(path):
    with _INDEXES_LOCK:
        return _INDEXES.setdefault(os.path.abspath(path), _StartedIndex())


def warm_started_index(ledger_path=DEFAULT_LEDGER):
    """기존 원장을 파일 잠금 없이 미리 세어 둔다. 첫 상한 검사가 원장 전체를 기다리지 않게 한다."""
    try:
        fd = os.open(ledger_path, os.O_RDONLY)
    except FileNotFoundError:
        return
    try:
        index = _started_index(ledger_path)
        with index.lock:
            index.advance(fd, complete=False)
    finally:
        os.close(fd)


def _lock(fd) -> None:
    """파일 배타 잠금 — POSIX 는 flock, Windows 는 0번 바이트 잠금(O_APPEND 라 쓰기는 끝에 간다)."""
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_EX)
        return
    os.lseek(fd, 0, os.SEEK_SET)
    msvcrt.locking(fd, msvcrt.LK_LOCK, 1)


def _unlock(fd) -> None:
    if fcntl is not None:
        return                                  # flock 은 close 로 풀린다
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    except OSError:
        pass                                    # 잠금을 못 얻었던 경우 — 풀 것도 없다


def _usage(value):
    """알려진 사용량 필드만 저장하며 본문·추론 텍스트는 포함하지 않는다."""
    if not isinstance(value, dict):
        return None
    fields = {"prompt_tokens", "completion_tokens", "total_tokens", "input_tokens",
              "output_tokens", "cached_tokens", "cache_read_input_tokens",
              "cache_creation_input_tokens", "reasoning_tokens"}
    details = {"prompt_tokens_details", "completion_tokens_details",
               "input_tokens_details", "output_tokens_details"}
    out = {k: v for k, v in value.items()
           if k in fields and isinstance(v, int) and not isinstance(v, bool)}
    for name in details:
        child = _usage(value.get(name))
        if child:
            out[name] = child
    return out or None


def logged_json_request(url, payload, *, headers, provider, model, role, run_id,
                        support_round=None, logical_request_id=None, attempt=1,
                        billing_basis="unconfirmed", timeout=60,
                        ledger_path=DEFAULT_LEDGER, max_started=None):
    """POST 후 원래 JSON을 반환. 실패는 기록한 뒤 다시 발생시킨다.

    자동 재시도 없음. 호출자가 재시도하면 logical_request_id는 유지하고 attempt 증가.
    비용은 usage와 다르며 제공자 정산 자료로 확정한다. 미확인 비용은 None.
    """
    request = Request(url, data=json.dumps(payload, ensure_ascii=False).encode(),
                      headers=headers, method="POST")
    attempt_id = str(uuid.uuid4())
    logical_request_id = logical_request_id or str(uuid.uuid4())
    common = {"attempt_id": attempt_id, "logical_request_id": logical_request_id,
              "attempt": attempt, "provider": provider, "model_requested": model,
              "role": role, "run_id": run_id, "support_round": support_round,
              "endpoint_host": urlsplit(url).hostname, "billing_basis": billing_basis}
    append_event({**common, "event_type": "api_attempt_started", "started_at": _now()}, ledger_path, max_started=max_started)
    started = time.monotonic()
    result = {**common, "event_type": "api_attempt_finished", "http_status": None,
              "usage": None, "usage_status": "unavailable", "actual_cost": None,
              "estimated_cost": None, "currency": None, "pricing_source": None,
              "cost_status": "unconfirmed", "provider_request_id": None}
    try:
        with urlopen(request, timeout=timeout) as response:
            result["http_status"] = response.status
            result["provider_request_id"] = (response.headers.get("x-request-id")
                                              or response.headers.get("request-id"))
            data = json.loads(response.read())
        result["usage"] = _usage(data.get("usage"))
        result["usage_status"] = "reported" if result["usage"] is not None else "unavailable"
        result["model_returned"] = data.get("model")
        result["provider_response_id"] = data.get("id")
        choices = data.get("choices")
        if choices:
            result["finish_reason"] = choices[0].get("finish_reason")
            result["content_present"] = bool(choices[0].get("message", {}).get("content"))
        result["outcome"] = "response_received"
        return data
    except HTTPError as exc:
        result.update(http_status=exc.code, outcome="http_error", error_type="HTTPError")
        result["provider_request_id"] = exc.headers.get("x-request-id") if exc.headers else None
        try:
            error_data = json.loads(exc.read())
            result["usage"] = _usage(error_data.get("usage"))
            if result["usage"] is not None:
                result["usage_status"] = "reported"
        except (ValueError, AttributeError):
            pass
        raise
    except Exception as exc:
        result.update(outcome="request_or_decode_error", error_type=type(exc).__name__)
        raise
    finally:
        result.update(finished_at=_now(), duration_ms=round((time.monotonic()-started)*1000, 2))
        append_event(result, ledger_path)
