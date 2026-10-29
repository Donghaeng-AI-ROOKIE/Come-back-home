"""Phase 3 — 시민 제보와 판정 결과."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import GeoPoint, LocalNaiveDT


class TipDecision(str, Enum):
    discard = "discard"   # p < 0.2 — 파기, 미반영
    layer1 = "layer1"     # 0.2 ≤ p < 0.8 — POA 베이지안 갱신만
    layer2 = "layer2"     # p ≥ 0.8 + 위치·시각 특정 — 새 LKP 확정, Phase 2 재실행


class Tip(BaseModel):
    id: str
    case_id: str
    text: str                                  # 시민 제보 원문 (챗봇 수집)
    location: GeoPoint | None = None           # 목격 위치 (특정된 경우)
    # 시민이 말한 장소 이름("수리초등학교") — 구조화가 뽑은 장소에서 조사·위치어("앞"·"근처")를
    # 뗀 것. 보호자 제보 목록의 묶음 제목·묶는 기준이다(10/29 팀 점검: 좌표 칸·도로명으로만
    # 묶여 90m 떨어진 두 학교 제보가 둘 다 "수리산로"였다). 장소를 말하지 않았으면 빈 문자열.
    place: str = ""
    seen_at: LocalNaiveDT | None = None        # 목격 시각 (특정된 경우)
    p: float | None = None                     # 신뢰도 (시공간개연성 + 챗봇 질문으로 산출)
    decision: TipDecision | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    processing_status: str = "processed"


class TipReceipt(BaseModel):
    """Durable intake independent of long-running case prediction locks."""
    id: str
    case_id: str
    fingerprint: str
    text: str
    location: GeoPoint | None = None
    seen_at: LocalNaiveDT | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    state: Literal["queued", "running", "processed", "failed", "cancelled"] = "queued"
    attempts: int = 0
    error_code: str = ""
