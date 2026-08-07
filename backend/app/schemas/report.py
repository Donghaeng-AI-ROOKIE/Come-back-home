"""Phase 1 — 실종 신고 인테이크."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import GeoPoint, LocalNaiveDT
from app.schemas.persona import PersonaType


class Appearance(BaseModel):
    """보호자가 직접 입력한 인상착의.

    *_color 3개는 이 텍스트에서 규칙 기반으로 뽑는다. 사진 분석·생성 모델은 사용하지
    않는다(app.phase1.color_extract 참고).
    """
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
