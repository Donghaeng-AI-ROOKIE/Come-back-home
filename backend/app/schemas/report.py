"""Phase 1 — 실종 신고 인테이크."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import GeoPoint, LocalNaiveDT
from app.schemas.persona import PersonaType


class Appearance(BaseModel):
    """인상착의. top/bottom/shoes/physical/summary 는 VARCO-Vision(VLM)이 사진에서
    추출한 텍스트(생성이 아니라 추출) — *_color 3개는 그 텍스트에서 규칙 기반으로
    뽑은 색상 태그로, VARCO 와 무관하다(app.phase1.color_extract 참고, 모델 안 씀)."""
    top: str = ""
    bottom: str = ""
    shoes: str = ""
    accessories: list[str] = []
    physical: str = ""       # 키·체형·머리 등
    summary: str = ""        # 알림 문구용 한 줄 요약
    # 고정 실루엣 아바타 렌더링용 색상 태그. 프론트가 이 문자열을 hex 로 변환해
    # SVG 를 채운다 — 백엔드는 이미지를 만들지 않는다.
    top_color: str = "unknown"
    bottom_color: str = "unknown"
    shoes_color: str = "unknown"


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
    lkp_time: LocalNaiveDT
    appearance: Appearance | None = None
    reporter: ReporterInfo | None = None
    created_at: datetime = Field(default_factory=datetime.now)
