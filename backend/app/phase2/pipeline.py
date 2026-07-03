"""Phase 2 파이프라인 — 3-way 예측 → α-pool 통합 → POA×POD → 최종 POA.

층2(Phase 2 재실행) 트리거 시에도 이 run_prediction 이 그대로 재호출된다.
재실행 시 case.lkp / case.lkp_time 이 새 LKP 로 교체된 상태여야 한다.
"""

from datetime import datetime

from app import storage
from app.llm import exaone
from app.phase2 import combine, simulation, topdown
from app.schemas.case import Case, CaseStatus
from app.schemas.prediction import MindState, POA, PredictionResult


def run_prediction(case: Case, *, now: datetime | None = None, seed: int | None = None) -> PredictionResult:
    now = now or datetime.now()
    elapsed_hours = max((now - case.lkp_time).total_seconds() / 3600.0, 0.05)

    persona = storage.personas.get(case.report.persona_id) if case.report.persona_id else None

    # ① Few-shot CoT → prior (EXAONE, 좌표 아님)
    prior = exaone.generate_prior(persona, case.report)

    # 마음 상태 초기화 (이후 제보의 심리 단서로 갱신됨)
    mind = case.mind or MindState()

    # ② 3-way 예측
    poa_td = topdown.topdown_poa(case.lkp, prior, persona, elapsed_hours)
    poa_bu = simulation.run_monte_carlo(
        case.lkp, prior, persona, elapsed_hours, mode="agent", mind=mind, seed=seed)
    poa_stat = simulation.run_monte_carlo(
        case.lkp, prior, persona, elapsed_hours, mode="statistical", seed=seed)

    # ③ α-pool 통합 — 초기(제보 없음)엔 linear (넓게), 제보 누적 후 log-linear (좁게)
    pool_mode = "log_linear" if len(case.tips) >= 3 else "linear"
    combined = combine.alpha_pool([poa_td, poa_bu, poa_stat],
                                  alphas=[0.3, 0.5, 0.2], mode=pool_mode)

    # ④ POA × POD (POD 는 현재 균일 스텁)
    final = combine.apply_pod(combined, pod=None)

    # 케이스 상태 갱신 — baseline 은 KL 이탈 트리거의 비교 기준
    case.prior = prior
    case.mind = mind
    case.baseline_poa = dict(final)
    case.current_poa = dict(final)
    case.last_sim_at = now
    case.status = CaseStatus.predicted
    storage.cases.save(case.id, case)

    return PredictionResult(
        case_id=case.id,
        prior=prior,
        poa_topdown=POA(cells=poa_td, source="topdown"),
        poa_bottomup=POA(cells=poa_bu, source="bottomup"),
        poa_statistical=POA(cells=poa_stat, source="statistical"),
        poa_combined=POA(cells=final, source="combined"),
    )
