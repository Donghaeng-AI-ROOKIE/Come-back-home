"""Phase 2 API — 동선 예측 실행."""

from fastapi import APIRouter, HTTPException

from app import storage
from app.phase2 import pipeline
from app.schemas.prediction import PredictionResult

router = APIRouter(prefix="/phase2", tags=["Phase 2 — 동선 예측"])


@router.post("/cases/{case_id}/predict", response_model=PredictionResult)
def predict(case_id: str, seed: int | None = None):
    """3-way 예측(Top-down/Bottom-up/통계) → α-pool → POA×POD → 최종 POA."""
    case = storage.cases.get(case_id)
    if case is None:
        raise HTTPException(404, "케이스 없음")
    return pipeline.run_prediction(case, seed=seed)
