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
    precision: str = "unknown"   # 지오코딩 정밀도 poi>address>dong>approx — Phase 2 반경 보정용


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
    """Mi:dm 챗봇 인터뷰 세션 — 종료 시 Persona 로 변환된다.

    적응형 엘리시테이션 상태를 함께 들고 다닌다: 검색이 다음 슬롯을 고르고
    Mi:dm 이 추출/문장화하며 채워진 슬롯·누적 추출을 여기 쌓는다.
    """
    id: str
    guardian_name: str
    persona_type: PersonaType | None = None   # 첫 답에서 확정
    messages: list[dict] = []        # {"role": "assistant"|"user", "text": ...}
    filled_keys: list[str] = []      # 충족된 슬롯 key
    asked_counts: dict[str, int] = {}    # 물었지만 안 채워진 슬롯 횟수(반복 억제)
    prev_target_key: str | None = None   # 직전에 겨냥한 슬롯 (추출 대상)
    # 누적 추출 (종료 시 Persona 로 변환)
    draft_fields: dict = {}                       # name/age/home
    draft_attractions: list[dict] = []            # [{"label","area_text"}]
    draft_behaviors: list[str] = []
    awaiting_confirmation: bool = False   # 요약 확인("이게 맞나요?") 대기 중
    done: bool = False
    persona_id: str | None = None
    # 개인정보 파기 — 미완료인 채 방치된 세션(draft 에 이름·주소 초안이 남는다)을
    # TTL 로 쓸어내기 위한 마지막 활동 시각 (privacy/lifecycle.purge_expired)
    last_active_at: datetime = Field(default_factory=datetime.now)
