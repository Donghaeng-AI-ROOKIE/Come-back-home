"""Phase 0 — 보호자 사전 등록으로 만들어지는 페르소나."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.common import GeoPoint


class PersonaType(str, Enum):
    dementia = "dementia"                          # 치매 노인
    child = "child"                                # 아동
    intellectual_disability = "intellectual_disability"  # 지적장애인


class AttractionPoint(BaseModel):
    """끌림점 — 과거 직장, 옛집, 자주 가던 공원 등. Phase 2 prior의 핵심 입력."""
    label: str
    location: GeoPoint
    weight: float = 1.0   # 상대 중요도 (EXAONE prior 생성 시 재조정됨)


class Persona(BaseModel):
    id: str
    type: PersonaType
    name: str
    age: int
    home: GeoPoint
    attraction_points: list[AttractionPoint] = []
    behavior_notes: list[str] = []   # "해질녘에 옛 직장 방향으로 걷는 습관" 등 인터뷰 추출 사실
    created_at: datetime = Field(default_factory=datetime.now)


class InterviewSession(BaseModel):
    """Mi:dm 챗봇 인터뷰 세션 — 종료 시 Persona 로 변환된다."""
    id: str
    guardian_name: str
    messages: list[dict] = []        # {"role": "assistant"|"user", "text": ...}
    done: bool = False
    persona_id: str | None = None
