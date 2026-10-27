"""저장소 — 메모리 캐시 + (선택) SQLite 영속화.

## 왜 영속화가 필요한가

**이 서비스의 전제가 영속성이다.** 사전등록은 평시에 하고 실종은 몇 달 뒤에
일어난다. 프로세스 메모리에만 두면 보호자가 5분 들여 등록한 것이 서버 재시작
한 번에 사라진다 — 서비스가 성립하지 않는다.

## 왜 그동안 메모리였나 (그리고 무엇을 지켜야 하나)

메모리 저장은 개인정보 측면에서 오히려 안전한 선택이었다. 디스크에 아무것도
남지 않으니 "발견 즉시 파기"가 공짜로 성립했다. 영속화는 그 공짜를 없앤다.

그래서 여기서 지키는 규칙은 하나다 — **`delete()` 는 디스크에서도 실제로
지운다.** SQLite 는 `DELETE` 후에도 페이지에 원본 바이트가 남으므로,
파기 경로(privacy.lifecycle)가 요구할 때 `vacuum()` 으로 회수한다.
검증은 tests/test_storage_persist.py 가 파일을 바이너리로 열어 확인한다.

## 구조

Repository 인터페이스(save/get/list/delete)는 그대로다. 호출부는 바뀌지 않는다.

- 메모리 dict 가 항상 1차 — 조회 경로의 성능·동작을 유지한다.
- `settings.persist_storage` 가 켜져 있고 모델이 주어진 저장소만 디스크에 쓴다.
- 기동 시 파일에서 메모리로 복원한다.

**테스트는 항상 꺼짐**(conftest 가 `PERSIST_STORAGE=false` 강제) — 테스트가
서로의 디스크 상태를 오염시키면 순서에 따라 결과가 바뀐다.
"""

import json
from functools import wraps
import sqlite3
import threading
import time
import uuid
from pathlib import Path
import contextlib
from typing import Generic, TypeVar

from pydantic import BaseModel

from app.config import settings

T = TypeVar("T")

# 커넥션 1개를 공유한다. FastAPI 는 스레드풀에서 핸들러를 돌리므로
# check_same_thread=False + Lock 이 필요하다. SQLite 쓰기는 어차피 직렬이다.
_conn: sqlite3.Connection | None = None
_lock = threading.RLock()


def _db() -> sqlite3.Connection | None:
    """영속화가 켜져 있을 때만 커넥션을 만든다 (없으면 None → 메모리 전용)."""
    global _conn
    if not settings.persist_storage:
        return None
    with _lock:
        if _conn is None:
            path = Path(settings.storage_db_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path, check_same_thread=False)
            # WAL 은 쓰지 않는다. 별도 -wal 파일에 삭제된 원본이 남아, 파기 후에도
            # 디스크에서 읽히는 경로가 생긴다. 단일 프로세스라 성능 이득도 작다.
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA secure_delete=ON")   # 삭제된 페이지를 0으로 덮는다
            _conn = conn
        return _conn



_compaction = threading.local()


@contextlib.contextmanager
def batch_compaction():
    """Defer this thread's full DB rewrite until the purge batch finishes.

    Other threads keep their own compaction policy. Even a partial failed batch
    flushes its already-deleted records before leaving this context.
    """
    depth = getattr(_compaction, "depth", 0)
    _compaction.depth = depth + 1
    try:
        yield
    finally:
        _compaction.depth = depth
        if depth == 0 and getattr(_compaction, "dirty", False):
            _compaction.dirty = False
            vacuum()


def vacuum() -> None:
    """물리 회수 — `DELETE` 만으로는 페이지에 원본이 남는다.

    파기 경로가 호출한다(privacy.lifecycle). 전체 DB 를 다시 쓰므로 비싸다 —
    삭제할 때마다가 아니라 파기 트랜잭션 끝에 한 번 부른다.
    """
    if getattr(_compaction, "depth", 0):
        _compaction.dirty = True
        return
    conn = _db()
    if conn is None:
        return
    with _lock:
        conn.execute("VACUUM")
        conn.commit()


class Repository(Generic[T]):
    """메모리 dict + (선택) SQLite 백킹.

    model 이 없으면(예: int 카운터) JSON 원시값으로 저장한다. table 이 없으면
    영속화하지 않는다 — 재시작 시 사라져도 되는 것(디버그 트레이스 등)은
    일부러 비워 둔다.
    """

    def __init__(self, model: type[T] | None = None, table: str | None = None) -> None:
        self._items: dict[str, T] = {}
        self._model = model
        self._table = table
        self._loaded = False
        self._mutation_lock = threading.RLock()

    # ── 내부 ────────────────────────────────────────────────
    def _persistent(self) -> sqlite3.Connection | None:
        return _db() if self._table else None

    def _ensure_table(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {self._table} "
            "(id TEXT PRIMARY KEY, data TEXT NOT NULL)")

    def _encode(self, item: T) -> str:
        if isinstance(item, BaseModel):
            return item.model_dump_json()
        return json.dumps(item, ensure_ascii=False, default=str)

    def _decode(self, raw: str) -> T:
        data = json.loads(raw)
        if self._model is not None and issubclass(self._model, BaseModel):
            item = self._model.model_validate(data)
            if hasattr(item, "_was_stored"):
                item._was_stored = True
            return item
        return data

    def _load(self) -> None:
        """Publish a complete cache only after one successful serialized load."""
        with self._mutation_lock:
            if self._loaded:
                return
            conn = self._persistent()
            if conn is None:
                self._loaded = True
                return
            with _lock:
                self._ensure_table(conn)
                rows = conn.execute(f"SELECT id, data FROM {self._table}").fetchall()
            for item_id, raw in rows:
                try:
                    self._items[item_id] = self._decode(raw)
                except Exception as exc:
                    print(f"[storage] {self._table} restore skipped: {type(exc).__name__}")
            self._loaded = True

    # ── 인터페이스 (호출부는 이 4개만 안다) ──────────────────
    def save(self, item_id: str, item: T) -> T:
        with self._mutation_lock:
            return self._save(item_id, item)

    def update_existing(self, item_id: str, transform) -> T | None:
        """Atomic guarded background update; None from transform means discard."""
        with self._mutation_lock:
            current = self.get(item_id)
            if current is None:
                return None
            updated = transform(current)
            return self._save(item_id, updated) if updated is not None else None

    def _save(self, item_id: str, item: T) -> T:
        if hasattr(item, "_was_stored"):
            item._was_stored = True
        self._load()
        conn = self._persistent()
        if conn is not None:
            with _lock:
                self._ensure_table(conn)
                conn.execute(
                    f"INSERT INTO {self._table} (id, data) VALUES (?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                    (item_id, self._encode(item)))
                conn.commit()
        self._items[item_id] = item
        return item

    def get(self, item_id: str) -> T | None:
        with self._mutation_lock:
            self._load()
            return self._items.get(item_id)

    def saved_copy(self, item_id: str) -> T | None:
        """Last committed version, decoded fresh from disk.

        The cached object is mutated in place while a writer holds its case lock
        (re-prediction). The row only changes on save, so it is a consistent
        snapshot. None when persistence is off or the row is absent.
        """
        conn = self._persistent()
        if conn is None:
            return None
        with _lock:
            self._ensure_table(conn)
            row = conn.execute(f"SELECT data FROM {self._table} WHERE id = ?", (item_id,)).fetchone()
        return self._decode(row[0]) if row else None

    def list(self) -> list[T]:
        with self._mutation_lock:
            self._load()
            return list(self._items.values())

    def delete(self, item_id: str) -> None:
        with self._mutation_lock:
            self._delete(item_id)

    def _delete(self, item_id: str) -> None:
        """메모리와 디스크 양쪽에서 지운다.

        물리 회수(VACUUM)는 여기서 하지 않는다 — 파기 1건마다 전체 DB 를 다시
        쓰면 비용이 크다. 파기 경로가 끝에 `storage.vacuum()` 을 한 번 부른다.
        """
        self._load()
        conn = self._persistent()
        if conn is not None:
            with _lock:
                self._ensure_table(conn)
                conn.execute(f"DELETE FROM {self._table} WHERE id = ?", (item_id,))
                conn.commit()
        self._items.pop(item_id, None)


# Bounded stripes serialize prediction with post-report profile linking. Reentrant
# because background update and API entry points both call run_prediction.
_case_locks = [threading.RLock() for _ in range(64)]


def case_lock(case_id: str) -> threading.RLock:
    """The stripe `serialize_case` holds for this case."""
    return _case_locks[hash(case_id) % len(_case_locks)]


# 잠금을 오래 기다리거나 오래 쥔 경우만 남긴다. 10/27 운영 측정에서 제보 하나가
# 분석을 끝내고도 재예측 시작까지 88초를 기다렸는데, 그 사이 모델 호출도 예측
# 기록도 없어 누가 무엇을 쥐고 있었는지 알 수 없었다. 워커 로그는 WARNING 이상만
# 남기므로 파이프라인의 [timing] 줄처럼 print 로 낸다.
LOCK_WAIT_LOG_MS = 1000
LOCK_HOLD_LOG_MS = 5000


class timed_lock:
    """`with timed_lock(lock, "누가", case_id) as held:` — 기다린 시간은 held.wait_ms."""

    def __init__(self, lock, by: str, case_id: str = "") -> None:
        self.lock, self.by, self.case_id = lock, by, case_id
        self.wait_ms = 0.0
        self._held_at = 0.0

    def __enter__(self):
        start = time.monotonic()
        self.lock.acquire()
        self._held_at = time.monotonic()
        self.wait_ms = (self._held_at - start) * 1000
        if self.wait_ms >= LOCK_WAIT_LOG_MS:
            print(f"[lock-wait] by={self.by} case={self.case_id} wait_ms={self.wait_ms:.0f}")
        return self

    def __exit__(self, *exc) -> None:
        hold_ms = (time.monotonic() - self._held_at) * 1000
        self.lock.release()
        if hold_ms >= LOCK_HOLD_LOG_MS:
            print(f"[lock-hold] by={self.by} case={self.case_id} hold_ms={hold_ms:.0f}")


def serialize_case(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        case_or_id = args[0] if args else kwargs.get("case", kwargs.get("case_id"))
        key = case_or_id if isinstance(case_or_id, str) else case_or_id.id
        with timed_lock(case_lock(key), fn.__qualname__, key):
            return fn(*args, **kwargs)
    return wrapped


# Linking a persona and deleting it must not race across cloud lanes.
persona_link_lock = threading.RLock()


def serialize_persona_links(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with persona_link_lock:
            return fn(*args, **kwargs)
    return wrapped


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def reset_for_tests() -> None:
    """테스트 격리용 — 메모리와 커넥션을 비운다. 운영 경로에서 쓰지 않는다."""
    global _conn
    for repo in (personas, interviews, cases, tip_receipts, debug_traces, audit_logs,
                 privacy_runs, privacy_jobs, privacy_scheduler, privacy_alerts,
                 walk_sessions, walk_tip_counts):
        repo._items.clear()
        repo._loaded = False
    if _conn is not None:
        _conn.close()
        _conn = None


# 전역 저장소 인스턴스
# table 이 지정된 것만 디스크에 남는다 — 무엇을 남길지가 곧 개인정보 정책이다.
from app.schemas.account import Account, Session
from app.schemas.case import Case
from app.schemas.debug import PredictionDebug
from app.schemas.device import Device
from app.schemas.tip import TipReceipt
from app.schemas.persona import InterviewSession, Persona
from app.schemas.privacy import (
    AuditRecord, PrivacyAlert, PrivacyJob, PrivacyRun, PrivacySchedulerState,
)
from app.schemas.walk import WalkSession

# 평시 장기보관 — 이게 남지 않으면 사전등록이라는 기능 자체가 성립하지 않는다.
personas = Repository(Persona, "personas")
# 보호자 원발화(axis_quotes)를 담는다. 페르소나 확정 후 파기 대상이지만, 등록
# 도중 서버가 재시작되면 처음부터 다시 답해야 하므로 진행 중인 세션은 남긴다.
interviews = Repository(InterviewSession, "interviews")
# 사건 단위 — 종결 후 TTL 만료 시 파기(privacy.lifecycle).
cases = Repository(Case, "cases")
tip_receipts = Repository(TipReceipt, "tip_receipts")
# 워커 궤적·LLM 트레이스. **일부러 영속화하지 않는다** — 시연 대시보드용 파생물이라
# 재시작 시 사라져도 되고, LLM 원문까지 디스크에 남길 이유가 없다.
debug_traces = Repository(PredictionDebug)
# 파기 증적 — 개인정보가 없어 파일 보존이 파기 원칙과 모순되지 않는다.
# 별도로 JSONL 에도 append 된다(privacy.lifecycle._append_audit_file).
audit_logs = Repository(AuditRecord, "audit_logs")
# 자동 파기 제어 상태. 본체 개인정보와 분리해 회차·재시작 상태만 보존한다.
privacy_runs = Repository(PrivacyRun, "privacy_runs")
privacy_jobs = Repository(PrivacyJob, "privacy_jobs")
privacy_scheduler = Repository(PrivacySchedulerState, "privacy_scheduler")
privacy_alerts = Repository(PrivacyAlert, "privacy_alerts")

# 안심 산책 (시민 참여) — 수색 케이스와 생명주기가 분리돼 있다.
walk_sessions = Repository(WalkSession, "walk_sessions")
# user_id → 제보 건수. **어느 케이스에 제보했는지는 담지 않는다** — 시민 신원과
# 사건을 잇는 기록을 만들면 케이스 파기 후에도 연결이 남아 목적을 넘는다.
# 마이페이지의 "제보 N건" 배지 하나를 위해 필요한 최소 정보만 센다.
walk_tip_counts = Repository(table="walk_tip_counts")  # int (user_id 키)

# 계정 — 아이디/비밀번호. password_hash 는 scrypt 결과라 원문 복원이 불가능하다
# (schemas/account.py). 재시작해도 로그인이 유지돼야 하므로 영속 대상이다.
accounts = Repository(Account, "accounts")
# 로그인 토큰 → 계정. 서버가 재시작돼도 앱이 다시 로그인하지 않도록 남긴다.
sessions = Repository(Session, "sessions")
# 산책 루트 조회 결과(동네 격자 키 → 목록). 외부 Overpass 가 자주 죽는데,
# 한 번 받아 둔 동네는 계속 동작해야 한다. 개인정보가 아니라 공공 지도 데이터다.
nearby_walks_cache = Repository(table="nearby_walks_cache")

# 푸시 발송 대상 — **영속화 필수.** 재시작마다 등록이 날아가면 그 뒤로는 아무도
# 알림을 못 받고, 사용자는 앱을 다시 열기 전까지 그 사실조차 모른다.
# 다만 이 테이블이 디스크에 남는다는 건 **지속적 기기 식별자가 파일로 남는다**는
# 뜻이다 — 그래서 토큰에 위치·제보 이력·계정을 붙이지 않는 경계가 더 중요해진다
# (schemas/device.py 참고). 해제 경로(DELETE /phase3/devices/{token}) 필수.
devices = Repository(Device, "devices")
