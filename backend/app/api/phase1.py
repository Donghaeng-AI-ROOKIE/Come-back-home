"""Phase 1 API — 실종 신고 접수."""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import storage
from app.phase1 import intake
from app.schemas.case import Case
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.report import Appearance

router = APIRouter(prefix="/phase1", tags=["Phase 1 — 신고 접수"])


class CreateReportIn(BaseModel):
    missing_type: PersonaType
    lkp: GeoPoint
    lkp_time: datetime
    persona_id: str | None = None
    # 보호자가 적은 실종 당시 상황 자유 서술. 지금은 저장만 하고 알림·안내문구
    # 등 다른 곳엔 아직 안 쓴다 — 소비처는 후속 결정.
    situation: str = ""
    # 보호자가 직접 입력한 인상착의. 생성·사진분석 모델을 거치지 않고 색상만
    # 규칙 기반으로 추출한다. 실제 사진 업로드는 별도 저장 경로가 생길 때 연결한다.
    appearance: Appearance | None = None
    with_document: bool = False


@router.post("/reports", response_model=Case)
def create_report(body: CreateReportIn):
    return intake.create_report(
        missing_type=body.missing_type,
        lkp=body.lkp,
        lkp_time=body.lkp_time,
        persona_id=body.persona_id,
        situation=body.situation,
        appearance=body.appearance,
        document_bytes=b"stub" if body.with_document else None,
    )


@router.get("/cases/{case_id}", response_model=Case)
def get_case(case_id: str):
    case = storage.cases.get(case_id)
    if case is None:
        raise HTTPException(404, "케이스 없음")
    return case
