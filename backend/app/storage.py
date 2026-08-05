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
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel

from app.config import settings

T = TypeVar("T")

# 커넥션 1개를 공유한다. FastAPI 는 스레드풀에서 핸들러를 돌리므로
# check_same_thread=False + Lock 이 필요하다. SQLite 쓰기는 어차피 직렬이다.
_conn: sqlite3.Connection | None = None
_lock = threading.Lock()


def _db() -> sqlite3.Connection | None:
    """영속화가 켜져 있을 때만 커넥션을 만든다 (없으면 None → 메모리 전용)."""
    global _conn
    if not settings.persist_storage:
        return None
    if _conn is None:
        path = Path(settings.storage_db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(path, check_same_thread=False)
        # WAL 은 쓰지 않는다. 별도 -wal 파일에 삭제된 원본이 남아, 파기 후에도
        # 디스크에서 읽히는 경로가 생긴다. 단일 프로세스라 성능 이득도 작다.
        _conn.execute("PRAGMA journal_mode=DELETE")
        _conn.execute("PRAGMA secure_delete=ON")   # 삭제된 페이지를 0으로 덮는다
    return _conn


def vacuum() -> None:
    """물리 회수 — `DELETE` 만으로는 페이지에 원본이 남는다.

    파기 경로가 호출한다(privacy.lifecycle). 전체 DB 를 다시 쓰므로 비싸다 —
    삭제할 때마다가 아니라 파기 트랜잭션 끝에 한 번 부른다.
    """
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
            return self._model.model_validate(data)
        return data

    def _load(self) -> None:
        """기동 후 첫 접근에 파일 → 메모리 1회 복원."""
        if self._loaded:
            return
        self._loaded = True          # 실패해도 재시도하지 않는다(무한 로딩 방지)
        conn = self._persistent()
        if conn is None:
            return
        with _lock:
            self._ensure_table(conn)
            rows = conn.execute(f"SELECT id, data FROM {self._table}").fetchall()
        for item_id, raw in rows:
            try:
                self._items[item_id] = self._decode(raw)
            except Exception as e:  # noqa: BLE001 — 한 행이 깨져도 나머지는 살린다
                print(f"[storage] {self._table}/{item_id} 복원 실패(건너뜀): {e}")

    # ── 인터페이스 (호출부는 이 4개만 안다) ──────────────────
    def save(self, item_id: str, item: T) -> T:
        self._load()
        self._items[item_id] = item
        conn = self._persistent()
        if conn is not None:
            with _lock:
                self._ensure_table(conn)
                conn.execute(
                    f"INSERT INTO {self._table} (id, data) VALUES (?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                    (item_id, self._encode(item)))
                conn.commit()
        return item

    def get(self, item_id: str) -> T | None:
        self._load()
        return self._items.get(item_id)

    def list(self) -> list[T]:
        self._load()
        return list(self._items.values())

    def delete(self, item_id: str) -> None:
        """메모리와 디스크 양쪽에서 지운다.

        물리 회수(VACUUM)는 여기서 하지 않는다 — 파기 1건마다 전체 DB 를 다시
        쓰면 비용이 크다. 파기 경로가 끝에 `storage.vacuum()` 을 한 번 부른다.
        """
        self._load()
        self._items.pop(item_id, None)
        conn = self._persistent()
        if conn is not None:
            with _lock:
                self._ensure_table(conn)
                conn.execute(f"DELETE FROM {self._table} WHERE id = ?", (item_id,))
                conn.commit()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def reset_for_tests() -> None:
    """테스트 격리용 — 메모리와 커넥션을 비운다. 운영 경로에서 쓰지 않는다."""
    global _conn
    for repo in (personas, interviews, cases, debug_traces, audit_logs,
                 walk_sessions, walk_tip_counts):
        repo._items.clear()
        repo._loaded = False
    if _conn is not None:
        _conn.close()
        _conn = None


# 전역 저장소 인스턴스
# table 이 지정된 것만 디스크에 남는다 — 무엇을 남길지가 곧 개인정보 정책이다.
from app.schemas.case import Case
from app.schemas.debug import PredictionDebug
from app.schemas.persona import InterviewSession, Persona
from app.schemas.privacy import AuditRecord
from app.schemas.walk import WalkSession

# 평시 장기보관 — 이게 남지 않으면 사전등록이라는 기능 자체가 성립하지 않는다.
personas = Repository(Persona, "personas")
# 보호자 원발화(axis_quotes)를 담는다. 페르소나 확정 후 파기 대상이지만, 등록
# 도중 서버가 재시작되면 처음부터 다시 답해야 하므로 진행 중인 세션은 남긴다.
interviews = Repository(InterviewSession, "interviews")
# 사건 단위 — 종결 후 TTL 만료 시 파기(privacy.lifecycle).
cases = Repository(Case, "cases")
# 워커 궤적·LLM 트레이스. **일부러 영속화하지 않는다** — 시연 대시보드용 파생물이라
# 재시작 시 사라져도 되고, LLM 원문까지 디스크에 남길 이유가 없다.
debug_traces = Repository(PredictionDebug)
# 파기 증적 — 개인정보가 없어 파일 보존이 파기 원칙과 모순되지 않는다.
# 별도로 JSONL 에도 append 된다(privacy.lifecycle._append_audit_file).
audit_logs = Repository(AuditRecord, "audit_logs")

# 안심 산책 (시민 참여) — 수색 케이스와 생명주기가 분리돼 있다.
walk_sessions = Repository(WalkSession, "walk_sessions")
# user_id → 제보 건수. **어느 케이스에 제보했는지는 담지 않는다** — 시민 신원과
# 사건을 잇는 기록을 만들면 케이스 파기 후에도 연결이 남아 목적을 넘는다.
# 마이페이지의 "제보 N건" 배지 하나를 위해 필요한 최소 정보만 센다.
walk_tip_counts = Repository(table="walk_tip_counts")  # int (user_id 키)
