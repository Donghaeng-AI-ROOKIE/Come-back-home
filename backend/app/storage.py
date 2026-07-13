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
