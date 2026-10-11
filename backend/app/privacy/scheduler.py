"""앱 수명주기에 연결되는 자동 파기 반복 실행기."""

import logging
import threading
import time
import uuid

from datetime import datetime, timedelta

from app import storage
from app.config import settings
from app.privacy.worker import _due_jobs, run_once

log = logging.getLogger(__name__)
_stop = threading.Event()
_thread: threading.Thread | None = None


def _loop() -> None:
    # 재시작 직후 놓친 만료 대상을 즉시 복구한다.
    try:
        run_once(mode="recovery")
    except Exception:  # noqa: BLE001 — 다음 주기를 계속 시도
        log.exception("[privacy] 시작 시 복구 실행 실패")
    # Reserved case expiry runs on the 30-second tick. Discover abandoned
    # interviews periodically; this is separate from the heartbeat deadline.
    next_discovery = time.time() + settings.privacy_scheduler_interval_seconds
    while not _stop.wait(settings.privacy_retry_poll_seconds):
        try:
            if time.time() >= next_discovery:
                run_once(mode="automatic", discover=True)
                next_discovery = time.time() + settings.privacy_scheduler_interval_seconds
            elif _due_jobs(datetime.now()):
                run_once(mode="automatic", discover=False)
            else:
                state = storage.privacy_scheduler.get("singleton")
                if state is not None:
                    state.heartbeat_at = datetime.now()
                    state.next_run_at = datetime.now() + timedelta(seconds=settings.privacy_retry_poll_seconds)
                    storage.privacy_scheduler.save("singleton", state)
        except Exception:  # noqa: BLE001
            log.exception("[privacy] 자동 파기 회차 실패")


def start() -> threading.Thread | None:
    global _thread
    if not settings.privacy_scheduler_enabled:
        return None
    if _thread and _thread.is_alive():
        return _thread
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="privacy-purger", daemon=True)
    _thread.start()
    return _thread


def stop(timeout: float = 2.0) -> None:
    _stop.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=timeout)
