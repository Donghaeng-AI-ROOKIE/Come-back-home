"""Phase 3 API — 알림 발송·시민 제보·POA 조회."""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import storage
from app.phase3 import alerts, tip_flow, triggers
from app.schemas.common import GeoPoint
from app.schemas.tip import Tip

router = APIRouter(prefix="/phase3", tags=["Phase 3 — 알림·제보·POA 갱신"])


class TipIn(BaseModel):
    text: str
    location: GeoPoint | None = None
    seen_at: datetime | None = None
    with_photo: bool = False   # 실제 구현 시 UploadFile 로 교체


def _get_case(case_id: str):
    case = storage.cases.get(case_id)
    if case is None:
        raise HTTPException(404, "케이스 없음")
    return case


@router.post("/cases/{case_id}/alerts")
def send_alerts(case_id: str):
    """1차 알림 — 현재 POA 상위 셀(누적 80%) 내 사용자에게 발송."""
    case = _get_case(case_id)
    if not case.current_poa:
        raise HTTPException(409, "POA 없음 — Phase 2 예측을 먼저 실행하세요")
    cells = alerts.select_alert_cells(case.current_poa)
    summary = case.report.appearance.summary if case.report.appearance else "인상착의 정보 없음"
    return alerts.send_alerts(case.id, cells, summary)


@router.post("/cases/{case_id}/tips", response_model=Tip)
def submit_tip(case_id: str, body: TipIn):
    """시민 제보 접수 → 신뢰도 p → 층1 갱신 (+조건 충족 시 층2 재실행)."""
    case = _get_case(case_id)
    if not case.current_poa:
        raise HTTPException(409, "POA 없음 — Phase 2 예측을 먼저 실행하세요")
    return tip_flow.process_tip(
        case,
        text=body.text,
        location=body.location,
        seen_at=body.seen_at,
        tip_image=b"stub" if body.with_photo else None,
    )


@router.get("/cases/{case_id}/poa")
def get_poa(case_id: str, top: int = 20):
    """현재 POA 상위 셀 조회 (지도 시각화용)."""
    case = _get_case(case_id)
    if not case.current_poa:
        raise HTTPException(409, "POA 없음 — Phase 2 예측을 먼저 실행하세요")
    ranked = sorted(case.current_poa.items(), key=lambda kv: kv[1], reverse=True)[:top]
    return {"case_id": case.id, "total_cells": len(case.current_poa),
            "top_cells": [{"cell": c, "prob": round(p, 6)} for c, p in ranked]}


@router.get("/cases/{case_id}/rerun-check")
def rerun_check(case_id: str):
    """층2 트리거(주기/분포이탈) 상태 확인 — 운영 대시보드·스케줄러용."""
    case = _get_case(case_id)
    rerun, reason = triggers.should_rerun_phase2(case)
    return {"case_id": case.id, "should_rerun": rerun, "reason": reason}
