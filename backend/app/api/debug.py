"""디버그·시연 API — E2E 대시보드(/dashboard) 전용.

예측 파이프라인을 트레이스 모드로 실행하고, 대시보드가 한 번에 그릴 수 있는
번들(페르소나 + 인터뷰 전문 + 4층 POA + 워커 궤적 + EXAONE 이벤트)을 내려준다.
실서비스 API 가 아니라 팀 내부 이해·검증용이다.
"""

from fastapi import APIRouter, HTTPException

from app import storage
from app.geo import h3grid
from app.phase2 import pipeline
from app.schemas.debug import PredictionDebug

router = APIRouter(prefix="/debug", tags=["Debug — E2E 대시보드"])

_MAX_CELLS_PER_LAYER = 400  # 응답 크기 가드 — 확률 상위 셀만 (커버리지는 함께 표기)


def _expand_cells(cells: dict[str, float]) -> dict:
    """POA dict → 지도용 [{cell, prob, polygon}] (확률 내림차순, 상위 N)."""
    ranked = sorted(cells.items(), key=lambda kv: kv[1], reverse=True)
    top = ranked[:_MAX_CELLS_PER_LAYER]
    return {
        "total_cells": len(ranked),
        "coverage": sum(p for _, p in top),
        "cells": [
            {
                "cell": c,
                "prob": p,
                "polygon": [{"lat": pt.lat, "lng": pt.lng} for pt in h3grid.cell_boundary(c)],
            }
            for c, p in top
        ],
    }


@router.post("/cases/{case_id}/predict", response_model=PredictionDebug)
def predict_traced(case_id: str, seed: int | None = None):
    """트레이스 모드 예측 — 워커 궤적·EXAONE 이벤트를 수집해 저장 후 반환."""
    case = storage.cases.get(case_id)
    if case is None:
        raise HTTPException(404, "케이스 없음")
    pipeline.run_prediction(case, seed=seed, trace=True)
    return storage.debug_traces.get(case_id)


@router.get("/cases/{case_id}/bundle")
def bundle(case_id: str):
    """대시보드 1회 로딩 번들 — 케이스·페르소나·인터뷰·트레이스·POA 레이어."""
    case = storage.cases.get(case_id)
    if case is None:
        raise HTTPException(404, "케이스 없음")

    persona = storage.personas.get(case.report.persona_id) if case.report.persona_id else None
    # 이 페르소나를 만든 인터뷰 세션 (없으면 None — 데모 seed 는 인터뷰 없이 생성됨)
    session = next((s for s in storage.interviews.list()
                    if s.persona_id and persona and s.persona_id == persona.id), None)

    debug: PredictionDebug | None = storage.debug_traces.get(case_id)
    poa_layers = {}
    if debug and debug.result:
        poa_layers = {
            "combined": _expand_cells(debug.result.poa_combined.cells),
            "topdown": _expand_cells(debug.result.poa_topdown.cells),
            "bottomup": _expand_cells(debug.result.poa_bottomup.cells),
            "statistical": _expand_cells(debug.result.poa_statistical.cells),
        }
    elif case.current_poa:
        poa_layers = {"combined": _expand_cells(case.current_poa)}

    return {
        "case": {
            "id": case.id,
            "status": case.status,
            "lkp": case.lkp,
            "lkp_time": case.lkp_time,
            "missing_type": case.report.missing_type,
            "last_sim_at": case.last_sim_at,
            "n_tips": len(case.tips),
        },
        "persona": persona,
        "interview": session,
        "prior": debug.result.prior if debug and debug.result else case.prior,
        "debug": {
            "generated_at": debug.generated_at,
            "seed": debug.seed,
            "roadnet": debug.roadnet,
            "exaone_stub": debug.exaone_stub,
            "prior_prompt": debug.prior_prompt,
            "prior_response_raw": debug.prior_response_raw,
            "walkers": debug.walkers,
            "mind_events": debug.mind_events,
        } if debug else None,
        "poa_layers": poa_layers,
    }


@router.get("/overview")
def overview():
    """대시보드 셀렉터용 — 저장소에 있는 페르소나·인터뷰·케이스 목록."""
    return {
        "personas": [
            {"id": p.id, "name": p.name, "age": p.age, "type": p.type,
             "n_attractions": len(p.attraction_points), "n_notes": len(p.behavior_notes)}
            for p in storage.personas.list()
        ],
        "interviews": [
            {"id": s.id, "guardian_name": s.guardian_name, "done": s.done,
             "persona_id": s.persona_id, "n_messages": len(s.messages)}
            for s in storage.interviews.list()
        ],
        "cases": [
            {"id": c.id, "status": c.status, "persona_id": c.report.persona_id,
             "lkp": c.lkp, "lkp_time": c.lkp_time,
             "has_trace": storage.debug_traces.get(c.id) is not None}
            for c in storage.cases.list()
        ],
    }
