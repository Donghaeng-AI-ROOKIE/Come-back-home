"""Phase 3 — 시민 제보와 판정 결과."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.common import GeoPoint


class TipDecision(str, Enum):
    discard = "discard"   # p < 0.2 — 파기, 미반영
    layer1 = "layer1"     # 0.2 ≤ p < 0.8 — POA 베이지안 갱신만
    layer2 = "layer2"     # p ≥ 0.8 + 위치·시각 특정 — 새 LKP 확정, Phase 2 재실행


class Tip(BaseModel):
    id: str
    case_id: str
    text: str                                  # 시민 제보 원문 (챗봇 수집)
    location: GeoPoint | None = None           # 목격 위치 (특정된 경우)
    seen_at: datetime | None = None            # 목격 시각 (특정된 경우)
    has_photo: bool = False
    p: float | None = None                     # 신뢰도 (Varco 사진 대조 + 챗봇 질문으로 산출)
    decision: TipDecision | None = None
    created_at: datetime = Field(default_factory=datetime.now)
