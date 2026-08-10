"""Phase 1 API — 실종 신고 접수."""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import storage
from app.phase1 import intake
from app.schemas.case import Case
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType

router = APIRouter(prefix="/phase1", tags=["Phase 1 — 신고 접수"])


class CreateReportIn(BaseModel):
    missing_type: PersonaType
    lkp: GeoPoint
    lkp_time: datetime
    persona_id: str | None = None
    # 백본 단계: 파일 업로드 대신 유무 플래그로 스텁 경로 태움.
    # 실제 구현 시 multipart UploadFile 로 교체.
    with_photo: bool = False
    with_document: bool = False
    # 앱의 수기 입력 경로. 사진이 없어도 핵심 단서를 사건에 저장한다.
    appearance_text: str = ""
    situation: str = ""


@router.post("/reports", response_model=Case)
def create_report(body: CreateReportIn):
    return intake.create_report(
        missing_type=body.missing_type,
        lkp=body.lkp,
        lkp_time=body.lkp_time,
        persona_id=body.persona_id,
        photo_bytes=b"stub" if body.with_photo else None,
        document_bytes=b"stub" if body.with_document else None,
        appearance_text=body.appearance_text,
        situation=body.situation,
    )


@router.get("/cases/{case_id}", response_model=Case)
def get_case(case_id: str):
    case = storage.cases.get(case_id)
    if case is None:
        raise HTTPException(404, "케이스 없음")
    return case
