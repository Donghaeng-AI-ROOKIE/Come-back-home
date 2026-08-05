"""인메모리 저장소.

백본 단계라 dict 기반. DB(SQLite/Postgres)로 옮길 때 이 모듈의
Repository 만 교체하면 나머지 코드는 그대로 동작한다.
"""

import uuid
from typing import Generic, TypeVar

T = TypeVar("T")


class Repository(Generic[T]):
    def __init__(self) -> None:
        self._items: dict[str, T] = {}

    def save(self, item_id: str, item: T) -> T:
        self._items[item_id] = item
        return item

    def get(self, item_id: str) -> T | None:
        return self._items.get(item_id)

    def list(self) -> list[T]:
        return list(self._items.values())

    def delete(self, item_id: str) -> None:
        self._items.pop(item_id, None)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


# 전역 저장소 인스턴스
personas = Repository()      # Persona
interviews = Repository()    # InterviewSession
cases = Repository()         # Case
debug_traces = Repository()  # PredictionDebug — E2E 대시보드용 (case_id 키)
audit_logs = Repository()    # AuditRecord — 파기 증적 (개인정보 미포함, 파기 후에도 유지)

# 안심 산책 (시민 참여) — 수색 케이스와 생명주기가 분리돼 있다.
walk_sessions = Repository()   # WalkSession (session_id 키)
# user_id → 제보 건수. **어느 케이스에 제보했는지는 담지 않는다** — 시민 신원과
# 사건을 잇는 기록을 만들면 케이스 파기 후에도 연결이 남아 목적을 넘는다.
# 마이페이지의 "제보 N건" 배지 하나를 위해 필요한 최소 정보만 센다.
walk_tip_counts = Repository()  # int (user_id 키)
