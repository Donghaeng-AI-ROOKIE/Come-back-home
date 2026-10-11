"""Phase 2 API — 동선 예측 실행."""

from fastapi import APIRouter, HTTPException, BackgroundTasks

from app import storage
from app.phase2 import pipeline
from app.privacy import lifecycle
from app.schemas.prediction import PredictionResult

router = APIRouter(prefix="/phase2", tags=["Phase 2 — 동선 예측"])


@router.post("/cases/{case_id}/predict", response_model=PredictionResult)
def predict(case_id: str, seed: int | None = None, background_tasks: BackgroundTasks = None):
    """예측(Top-down prior + Bottom-up/통계 2-way α-pool) → 최종 POA."""
    case = storage.cases.get(case_id)
    if case is None:
        raise HTTPException(404, "케이스 없음")
    try:
        # 종결 케이스 예측 차단 — run_prediction 이 status 를 predicted 로
        # 덮어써 종결을 부활시키는 것 방지 (개인정보 파기 라이프사이클)
        lifecycle.ensure_not_closed(case)
        result = pipeline.run_prediction(case, seed=seed)
        from app.phase3.alerts import notify_prediction
        if background_tasks is not None:
            background_tasks.add_task(notify_prediction, case)
        else:
            notify_prediction(case)
        return result
    except lifecycle.AlreadyClosed as e:
        raise HTTPException(409, str(e))
    except pipeline.continuous_prediction.IncompletePredictionError:
        raise HTTPException(503, {'reason':'prediction_incomplete',
                                  'quality':case.prediction_quality})
