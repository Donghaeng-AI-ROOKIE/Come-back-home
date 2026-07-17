"""Phase 2 파이프라인 — 3-way 예측 → α-pool 통합 → 최종 POA.

층2(Phase 2 재실행) 트리거 시에도 이 run_prediction 이 그대로 재호출된다.
재실행 시 case.lkp / case.lkp_time 이 새 LKP 로 교체된 상태여야 한다.
"""

from datetime import datetime

from app import storage
from app.config import settings
from app.llm import exaone
from app.phase2 import combine, simulation, topdown
from app.schemas.case import Case, CaseStatus
from app.schemas.debug import PredictionDebug, SimTrace
from app.schemas.prediction import MindState, POA, PredictionResult


def _load_roadnet(case: Case):
    """도로망 로딩 (설정 시) — 실패해도 예측은 연속 공간 폴백으로 계속.

    도로망과 환경레이어는 실패를 분리 격리한다: 환경레이어(외부 WMS·의존성)가
    죽어도 도로망 그래프 MC 는 유지 — env() 는 빈 dict 로 동작하게 설계돼 있다.
    (실측: PIL 미설치 하나로 도로망 전체가 연속 공간 폴백되던 문제.)
    """
    if not settings.use_roadnet:
        return None
    try:
        from app.geo import roadnet

        net = roadnet.get_network(case.lkp)
    except Exception as e:  # noqa: BLE001 — 외부 API 실패 격리
        print(f"[roadnet] 로딩 실패 → 연속 공간 폴백: {e}")
        return None
    try:
        from app.geo import envlayer

        envlayer.attach(net, case.lkp)  # 환경 속성 — 게이지·트리거가 사용
    except Exception as e:  # noqa: BLE001 — 환경레이어 실패는 도로망을 죽이지 않는다
        print(f"[envlayer] 부착 실패 → 환경 속성 없이 도로망 MC 계속: {e}")
    return net


def run_prediction(
    case: Case,
    *,
    now: datetime | None = None,
    seed: int | None = None,
    trace: bool = False,   # E2E 대시보드 — 워커 궤적·EXAONE 이벤트 수집 (결과 불변)
) -> PredictionResult:
    now = now or datetime.now()
    elapsed_hours = max((now - case.lkp_time).total_seconds() / 3600.0, 0.05)

    persona = storage.personas.get(case.report.persona_id) if case.report.persona_id else None

    # ① Few-shot CoT → prior (EXAONE, 좌표 아님)
    last_call = exaone.call_log[-1] if exaone.call_log else None
    prior = exaone.generate_prior(persona, case.report)
    prior_call = (exaone.call_log[-1]
                  if exaone.call_log and exaone.call_log[-1] is not last_call
                  and exaone.call_log[-1]["kind"] == "prior" else None)

    # 마음 상태 초기화 (이후 제보의 심리 단서로 갱신됨)
    mind = case.mind or MindState()

    # ② 3-way 예측 — 도로망이 있으면 두 MC 모두 그래프 위를 걷는다
    #    (통계 MC 도 같은 지형 제약이어야 "AI 기여도" 비교가 공정)
    net = _load_roadnet(case)
    sim_trace = SimTrace() if trace else None
    poa_td = topdown.topdown_poa(case.lkp, prior, persona, elapsed_hours)
    poa_bu = simulation.run_monte_carlo(
        case.lkp, prior, persona, elapsed_hours, mode="agent", net=net, mind=mind, seed=seed,
        trace=sim_trace)
    poa_stat = simulation.run_monte_carlo(
        case.lkp, prior, persona, elapsed_hours, mode="statistical", net=net, seed=seed)

    # ③ α-pool 통합 — 초기(제보 없음)엔 linear (넓게), 제보 누적 후 log-linear (좁게)
    pool_mode = "log_linear" if len(case.tips) >= 3 else "linear"
    combined = combine.alpha_pool([poa_td, poa_bu, poa_stat],
                                  alphas=[0.3, 0.5, 0.2], mode=pool_mode)

    # 케이스 상태 갱신 — baseline 은 KL 이탈 트리거의 비교 기준
    case.prior = prior
    case.mind = mind
    case.baseline_poa = dict(combined)
    case.current_poa = dict(combined)
    case.last_sim_at = now
    case.status = CaseStatus.predicted
    storage.cases.save(case.id, case)

    result = PredictionResult(
        case_id=case.id,
        prior=prior,
        poa_topdown=POA(cells=poa_td, source="topdown"),
        poa_bottomup=POA(cells=poa_bu, source="bottomup"),
        poa_statistical=POA(cells=poa_stat, source="statistical"),
        poa_combined=POA(cells=combined, source="combined"),
    )

    if sim_trace is not None:
        storage.debug_traces.save(case.id, PredictionDebug(
            case_id=case.id,
            seed=seed,
            roadnet=net is not None,
            exaone_stub=exaone.is_stub,
            prior_prompt=prior_call["prompt"] if prior_call else None,
            prior_response_raw=prior_call["response"] if prior_call else None,
            walkers=sim_trace.walkers,
            mind_events=sim_trace.mind_events,
            result=result,
        ))

    return result
