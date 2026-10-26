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
from app.privacy import lifecycle
from app.config import settings
from app.llm import exaone
from app.phase2 import combine, radius, simulation, topdown, initial_person
from app.llm.initial_behavior import simulation_persona
from app.phase0.person_preparation import apply_prepared
from app.phase2 import situation_link, continuous_prediction
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
    if settings.personal_walk_cache_path:
        from app.geo import roadnet
        try:
            net=roadnet.verified_network(settings.personal_walk_cache_path)
            south,west,north,east=net.coverage_bbox
            if south <= case.lkp.lat <= north and west <= case.lkp.lng <= east:
                from app.geo.road_anchors import connect_anchors
                points=[case.lkp]+[a.location for a in (persona.attraction_points if persona else [])]
                net=connect_anchors(net, points)
                if net.road_distance_km(case.lkp,case.lkp) is not None:
                    return net,''
            # A regional fixture is an optimization, not a nationwide coverage
            # restriction. Outside it, use the report-centred cache/downloader.
            log.info("Configured regional road map does not cover the report; loading local roads")
        except (OSError,ValueError,KeyError) as exc:
            log.warning("Configured regional road map unavailable (%s); loading local roads", type(exc).__name__)
    r = None
    if (settings.roadnet_dynamic_radius and prior is not None
            and elapsed_hours is not None):
        r = radius.roadnet_radius_m(prior.radius_lognormal, elapsed_hours,
                                    radius.vmax_kmh(persona))
    try:
        from app.geo.road_bundles import get_preloaded_network
        from app.geo.road_anchors import connect_anchors
        prepared = get_preloaded_network(case.lkp, r or settings.roadnet_radius_m)
        if prepared is not None:
            points = [case.lkp] + [a.location for a in (persona.attraction_points if persona else [])]
            bundle_source = getattr(prepared, "bundle_source", "preloaded")
            bundle_hash = getattr(prepared, "bundle_sha256", "")
            prepared = connect_anchors(prepared, points)
            prepared.bundle_source = bundle_source
            prepared.bundle_sha256 = bundle_hash
            if prepared.road_distance_km(case.lkp, case.lkp) is not None:
                return prepared, ""
    except Exception as exc:
        log.warning("Preloaded regional road bundle unavailable (%s)", type(exc).__name__)
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


def _initial_prior(persona, report, links):
    """Preserve the existing numeric baseline while applying grounded K evidence.

    The matched OSM audit does not establish that replacing SAR's numeric prior
    with the placeholder strategy distribution is non-inferior. Keep that
    replacement out of this fix; retaining SAR is not a claim of its superiority.
    """
    prior = exaone.generate_prior(persona, report)
    sar_snapshot={k:prior.model_dump(mode='json')[k] for k in (
        'strategy_probs','attraction_weights','radius_lognormal','attraction_levels','source','fallback_reason')}
    default = exaone._default_prior(persona, report)
    prepared = apply_prepared(persona, report, prior, default, links)
    prepared.sar_numeric_baseline=sar_snapshot
    if prepared.initial_interpretation.get('status') == 'applied':
        prepared.source = 'prepared_person'
        prepared.initial_interpretation.update(
            initial_prior_path='prepared_person', numeric_baseline_source=prior.source,
            sar_source=prior.source, SAR_called_during_prediction=not exaone.is_stub)
        return prepared
    prior.sar_numeric_baseline=sar_snapshot
    prior.initial_interpretation = dict(prepared.initial_interpretation,
        initial_prior_path='legacy_SAR_fallback', numeric_baseline_source=prior.source,
        SAR_called_during_prediction=not exaone.is_stub)
    return prior


@storage.serialize_case
def run_prediction(
    case: Case,
    *,
    now: datetime | None = None,
    seed: int | None = None,
    trace: bool = False,   # E2E 대시보드 — 워커 궤적·EXAONE 이벤트 수집 (결과 불변)
) -> PredictionResult:
    lifecycle.ensure_not_closed(case)
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

    # Stored K traits are compiled locally. The incident's destination link is
    # separately grounded in the report; it is not inferred from SAR weights.
    links = situation_link.cached(case, persona)
    last_call = exaone.call_log[-1] if exaone.call_log else None
    prior_key = continuous_prediction.prior_key(case, persona)
    if case.prior is not None and case.prior_context_key == prior_key:
        prior = case.prior.model_copy(deep=True)
    else:
        prior = _initial_prior(persona, case.report, links)
    source_persona = persona
    prior_call = (exaone.call_log[-1]
                  if exaone.call_log and exaone.call_log[-1] is not last_call
                  and exaone.call_log[-1]["kind"] == "prior" else None)
    _lap("prior_ms")

    persona = simulation_persona(persona, prior)
    _lap("initial_person_ms")

    # Direction state supplied to the personal channel; statistical stays neutral.
    mind = case.mind or MindState()

    # ② 예측 — 도로망이 있으면 두 MC 모두 그래프 위를 걷는다
    #    (통계 MC 도 같은 지형 제약이어야 "AI 기여도" 비교가 공정)
    net, roadnet_fallback = _load_roadnet(case, prior, persona, elapsed_hours)
    _lap("roadnet_ms")
    sim_trace = SimTrace() if trace else None
    poa_td = topdown.topdown_poa(case.lkp, prior, persona, elapsed_hours)  # 디버그·시각화 전용
    _lap("topdown_ms")
    staged_case = case.model_copy(deep=True)
    poa_bu, poa_stat, quality = continuous_prediction.run_pair(staged_case, source_persona, prior, net, elapsed_hours, seed=seed)
    if net is not None:
        quality['road_anchor_connections']=getattr(net,'anchor_connections',[])
        if getattr(net, 'bundle_source', None):
            quality['roadnet_source'] = net.bundle_source
            quality['roadnet_sha256'] = net.bundle_sha256
    if poa_bu is None:
        poa_bu = simulation.run_monte_carlo(
        case.lkp, prior, persona, elapsed_hours, mode="agent", net=net, mind=mind, seed=seed,
        trace=sim_trace, environment_observations=case.report.environment_observations,
        started_at=case.lkp_time)
    if quality.get('unresolved_mass',0)>1e-9:
        case.prediction_quality=quality
        storage.cases.save(case.id,case)
        raise continuous_prediction.IncompletePredictionError('continuous prediction contains unresolved map probability mass')
    _lap("bottomup_ms")
    if poa_stat is None:
        poa_stat = simulation.run_monte_carlo(
            case.lkp, prior, persona, elapsed_hours, mode="statistical", net=net, seed=seed,
            environment_observations=case.report.environment_observations, started_at=case.lkp_time)
    _lap("statistical_ms")

    # ③ α-pool: statistical uses original onboarded SAR numbers; personal uses
    #    sourced conditional mind rules.
    #    The configured weight is applied to both predictions and previews.
    #    초기(제보 없음)엔 linear (넓게), 제보 누적 후 log-linear (좁게)
    # The literature channel reserves nonpersonal support; log pooling would
    # erase every literature-only cell at the personal channel's zero support.
    literature = settings.statistical_channel_definition == 'literature_distance_prior'
    pool_mode = "log_linear" if len(case.tips) >= 3 and not literature else "linear"
    combined = combine.alpha_pool([poa_bu, poa_stat],
                                  alphas=[settings.personal_channel_weight, 1-settings.personal_channel_weight], mode=pool_mode)

    # 케이스 상태 갱신 — baseline 은 KL 이탈 트리거의 비교 기준
    case.continuous_state = staged_case.continuous_state
    case.prior_context_key = prior_key
    case.prediction_quality = quality
    case.poa_by_hour = {}
    case.prior = prior
    case.mind = mind
    case.baseline_poa = dict(combined)
    from app.phase3.poa_update import reapply_tips
    case.current_poa = reapply_tips(combined, case.tips, since=case.lkp_time)
    case.last_sim_at = now
    case.roadnet_used = net is not None
    case.roadnet_fallback_reason = roadnet_fallback
    case.status = CaseStatus.predicted
    storage.cases.save(case.id, case)
    if quality.get("mind_fill_pending"):
        # The map above did not wait for the model; a background fill asks the
        # reserved conditions and recomputes this horizon when answers arrive.
        from app.llm import runtime_mind_jobs
        runtime_mind_jobs.submit(case.id)

    result = PredictionResult(
        case_id=case.id,
        quality=quality,
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


@storage.serialize_case
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
    lifecycle.ensure_not_closed(case)
    if case.prior is None:
        raise ValueError("prior 없음 — 먼저 예측을 실행해야 한다")
    persona = storage.personas.get(case.report.persona_id) if case.report.persona_id else None
    elapsed = max(elapsed_hours, 0.05)
    source_persona = persona
    persona = simulation_persona(persona, case.prior)
    net, _ = _load_roadnet(case, case.prior, persona, elapsed)
    mind = case.mind or MindState()
    bu, stat, quality = continuous_prediction.run_pair(case, source_persona, case.prior, net, elapsed, seed=seed, persist=False)
    if quality.get("unresolved_mass",0)>1e-9:
        raise continuous_prediction.IncompletePredictionError("preview contains unresolved map probability mass")
    if bu is None:
        bu = simulation.run_monte_carlo(
        case.lkp, case.prior, persona, elapsed, mode="agent", net=net,
        mind=mind, seed=seed,
        environment_observations=case.report.environment_observations, started_at=case.lkp_time)
    if stat is None:
        stat = simulation.run_monte_carlo(
            case.lkp, case.prior, persona, elapsed, mode="statistical", net=net, seed=seed,
            environment_observations=case.report.environment_observations, started_at=case.lkp_time)
    return combine.alpha_pool([bu, stat], alphas=[settings.personal_channel_weight, 1-settings.personal_channel_weight], mode="linear")
