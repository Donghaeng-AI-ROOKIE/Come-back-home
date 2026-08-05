"""Phase 2 파이프라인 — bottom-up·statistical 2-way α-pool 통합 → 최종 POA.

top-down(목적지 prior → topdown.topdown_poa)은 별도로 계산해 poa_topdown 으로
디버그·시각화에는 계속 노출하지만, 최종 결합(baseline/current POA)에는 포함하지
않는다 — top-down 은 few-shot CoT(=prior 생성) 그 자체이고, 이미 그 prior 가
bottom-up·statistical 양쪽에 반영되고 있어 별도 POA로 다시 더하면 이중 반영이다.

층2(Phase 2 재실행) 트리거 시에도 이 run_prediction 이 그대로 재호출된다.
재실행 시 case.lkp / case.lkp_time 이 새 LKP 로 교체된 상태여야 한다.
"""

import logging
from datetime import datetime
from time import perf_counter

from app import storage
from app.config import settings
from app.llm import exaone
from app.phase2 import combine, radius, simulation, topdown
from app.schemas.case import Case, CaseStatus
from app.schemas.debug import PredictionDebug, SimTrace
from app.schemas.prediction import MindState, POA, PredictionResult

log = logging.getLogger(__name__)


def _load_roadnet(case: Case, prior=None, persona=None, elapsed_hours: float | None = None):
    """도로망 로딩 (설정 시) — 실패해도 예측은 연속 공간 폴백으로 계속.

    반경은 P1-3 동적 스케일: prior 의 개인화 lognormal + 물리 상한의 p90 지원을
    덮는다 (radius.roadnet_radius_m — 하한 3km·상한 클램프·1km 양자화).
    prior 가 없으면(선로딩 등) 기존 고정 반경.

    도로망과 환경레이어는 실패를 분리 격리한다: 환경레이어(외부 WMS·의존성)가
    죽어도 도로망 그래프 MC 는 유지 — env() 는 빈 dict 로 동작하게 설계돼 있다.
    (실측: PIL 미설치 하나로 도로망 전체가 연속 공간 폴백되던 문제.)
    """
    if not settings.use_roadnet:
        return None, "off"
    r = None
    if (settings.roadnet_dynamic_radius and prior is not None
            and elapsed_hours is not None):
        r = radius.roadnet_radius_m(prior.radius_lognormal, elapsed_hours,
                                    radius.vmax_kmh(persona))
    try:
        from app.geo import roadnet

        net = roadnet.get_network(case.lkp, radius_m=r)
    except Exception as e:  # noqa: BLE001 — 외부 API 실패 격리
        # use_roadnet 기본값이 True 가 된 뒤로(PR #122) 이 경로는 실서비스 경로다.
        # print 만 남기면 "도로망을 안 쓴 예측"이 조용히 나가므로 사유를 반환한다.
        log.warning("도로망 로딩 실패 → 연속 공간 폴백 — %s: %s", type(e).__name__, e)
        return None, f"{type(e).__name__}: {e}"[:200]
    try:
        from app.geo import envlayer

        envlayer.attach(net, case.lkp, radius_m=r)  # 환경 속성 — 게이지·트리거가 사용
    except Exception as e:  # noqa: BLE001 — 환경레이어 실패는 도로망을 죽이지 않는다
        log.warning("환경레이어 부착 실패 → 환경 속성 없이 도로망 MC 계속 — %s", e)
    return net, ""


def run_prediction(
    case: Case,
    *,
    now: datetime | None = None,
    seed: int | None = None,
    trace: bool = False,   # E2E 대시보드 — 워커 궤적·EXAONE 이벤트 수집 (결과 불변)
) -> PredictionResult:
    now = now or datetime.now()
    elapsed_hours = max((now - case.lkp_time).total_seconds() / 3600.0, 0.05)

    # 스테이지 타이머 (P1-5) — 시연 목표 초 결정·P2-1 budget 스윕의 실측 기반.
    # 결과에 영향 없는 계측 전용. exaone.call_log 의 elapsed_ms 와 합쳐 읽는다.
    timings: dict[str, float] = {}
    _t0 = _t = perf_counter()

    def _lap(stage: str) -> None:
        nonlocal _t
        timings[stage] = round((perf_counter() - _t) * 1000, 1)
        _t = perf_counter()

    persona = storage.personas.get(case.report.persona_id) if case.report.persona_id else None
    _lap("prepare_ms")

    # ① Few-shot CoT → prior (EXAONE, 좌표 아님)
    last_call = exaone.call_log[-1] if exaone.call_log else None
    prior = exaone.generate_prior(persona, case.report)
    prior_call = (exaone.call_log[-1]
                  if exaone.call_log and exaone.call_log[-1] is not last_call
                  and exaone.call_log[-1]["kind"] == "prior" else None)
    _lap("prior_ms")

    # 마음 상태 초기화 (이후 제보의 심리 단서로 갱신됨)
    mind = case.mind or MindState()

    # ② 예측 — 도로망이 있으면 두 MC 모두 그래프 위를 걷는다
    #    (통계 MC 도 같은 지형 제약이어야 "AI 기여도" 비교가 공정)
    net, roadnet_fallback = _load_roadnet(case, prior, persona, elapsed_hours)
    _lap("roadnet_ms")
    sim_trace = SimTrace() if trace else None
    poa_td = topdown.topdown_poa(case.lkp, prior, persona, elapsed_hours)  # 디버그·시각화 전용
    _lap("topdown_ms")
    poa_bu = simulation.run_monte_carlo(
        case.lkp, prior, persona, elapsed_hours, mode="agent", net=net, mind=mind, seed=seed,
        trace=sim_trace)
    _lap("bottomup_ms")
    poa_stat = simulation.run_monte_carlo(
        case.lkp, prior, persona, elapsed_hours, mode="statistical", net=net, seed=seed)
    _lap("statistical_ms")

    # ③ α-pool 통합 — bottom-up·statistical 2-way. bottom-up 이 AI 개인화가 있는
    #    쪽이라 더 큰 가중(0.7 : 0.3, 기존 3-way 비율 0.5:0.2 을 그대로 재정규화한 값).
    #    초기(제보 없음)엔 linear (넓게), 제보 누적 후 log-linear (좁게)
    pool_mode = "log_linear" if len(case.tips) >= 3 else "linear"
    combined = combine.alpha_pool([poa_bu, poa_stat],
                                  alphas=[0.7, 0.3], mode=pool_mode)

    # 케이스 상태 갱신 — baseline 은 KL 이탈 트리거의 비교 기준
    case.prior = prior
    case.mind = mind
    case.baseline_poa = dict(combined)
    case.current_poa = dict(combined)
    case.last_sim_at = now
    case.roadnet_used = net is not None
    case.roadnet_fallback_reason = roadnet_fallback
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

    _lap("combine_ms")
    timings["total_ms"] = round((perf_counter() - _t0) * 1000, 1)
    print("[timing] " + " ".join(f"{k}={v:.0f}" for k, v in timings.items()))

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
            timings=timings,
        ))

    return result


def poa_at_elapsed(case: Case, elapsed_hours: float, *, seed: int | None = 42) -> dict[str, float]:
    """"만약 t시간 경과라면" 의 POA — 시간축 슬라이더용.

    본 예측(run_prediction)과 다른 점:
    - **케이스 상태를 바꾸지 않는다.** current_poa·status·last_sim_at 전부 그대로다.
      알림·제보는 계속 실제 경과시간 기준 지도만 쓴다.
    - prior 를 다시 만들지 않는다. 이미 저장된 case.prior 를 재사용한다 — 같은
      사람의 성향은 시점이 바뀐다고 달라지지 않고, 시점마다 EXAONE 을 다시 부르면
      슬라이더 한 번에 LLM 호출이 4배로 는다.
    - seed 고정이 기본이다. 슬라이더를 좌우로 움직일 때 같은 시점이 매번 다르게
      보이면 "시간이 바꾼 것"과 "난수가 바꾼 것"을 구분할 수 없다.

    결과는 case.poa_by_hour 에 캐시한다(호출부 책임).
    """
    if case.prior is None:
        raise ValueError("prior 없음 — 먼저 예측을 실행해야 한다")
    persona = storage.personas.get(case.report.persona_id) if case.report.persona_id else None
    elapsed = max(elapsed_hours, 0.05)
    net, _ = _load_roadnet(case, case.prior, persona, elapsed)
    mind = case.mind or MindState()
    bu = simulation.run_monte_carlo(
        case.lkp, case.prior, persona, elapsed, mode="agent", net=net,
        mind=mind, seed=seed)
    stat = simulation.run_monte_carlo(
        case.lkp, case.prior, persona, elapsed, mode="statistical", net=net, seed=seed)
    return combine.alpha_pool([bu, stat], alphas=[0.7, 0.3], mode="linear")
