"""Phase 1 — 실종 신고 인테이크."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType


class Appearance(BaseModel):
    """VARCO-Vision(VLM)이 사진에서 추출한 인상착의. 생성이 아니라 추출."""
    top: str = ""
    bottom: str = ""
    shoes: str = ""
    accessories: list[str] = []
    physical: str = ""       # 키·체형·머리 등
    summary: str = ""        # 알림 문구용 한 줄 요약


class ReporterInfo(BaseModel):
    """Upstage 문서 파싱으로 추출한 신고자·신고서 정보."""
    name: str = ""
    relation: str = ""
    phone: str = ""
    extra: dict = {}


class MissingReport(BaseModel):
    id: str
    persona_id: str | None = None      # 사전 등록된 페르소나가 있으면 연결
    missing_type: PersonaType
    lkp: GeoPoint                       # Last Known Position (최종 목격 지점)
    lkp_time: datetime
    appearance: Appearance | None = None
    reporter: ReporterInfo | None = None
    created_at: datetime = Field(default_factory=datetime.now)
