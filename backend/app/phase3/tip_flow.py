"""Phase 3 — 제보 수신부터 POA 갱신·층2 재실행·D3 알림까지의 전체 흐름.

제보 수신 → LLM 구조화(자유텍스트 1회, 위치 지오코딩 포함) → 신뢰도 p 산출
│
├─ 위치를 텍스트·명시값 어느 쪽으로도 못 얻음     → need_more(위치, force로 건너뛰기 가능)
├─ 위치O·시각X인데 폴백 p ≥ 0.8(층2 문턱)        → need_more(시각, force로 건너뛰기 가능)
├─ p < 0.2 (허위/스팸)         → 파기. 아무 데도 반영 안 함
├─ 0.2 ≤ p < 0.8               → 층1: POA 베이지안 갱신만 (p 가중)
└─ p ≥ 0.8 + 위치·시각 특정     → 층1 갱신 + 새 LKP 확정
                                → 층2: Phase 2 재실행 → 잔여 제보 재적용
── 매 POA 갱신 후 ── D3: 새 지역 등장 시에만 3차 알림 (last_alert_poa 갱신)

시각(seen_at)은 위치처럼 무조건 되묻지 않는다 — 없어도 층1 갱신은 정상 동작하고
(reachability 가 created_at 으로 폴백), 층2 자격만 없어질 뿐이다
(has_specific_location_time). 다만 seen_at ≤ created_at 이 항상 성립해
Δt(폴백) ≥ Δt(실제) → 개연성(폴백) ≥ 개연성(실제) 인 단조성이 있으므로,
폴백 p 가 이미 0.8 미만이면 실제 시각을 받아도 층2에 못 간다(되물어도 무의미).
그래서 "위치O·시각X·폴백 p ≥ 0.8"인 구간만 골라 시각을 되묻는다
(process_tip 내 게이트, 별도 함수 아님). 위치는 개연성 항 자체를 없애 제보 가치가 크게 줄지만,
시각은 반경만 넓히는 방향의 보수적 근사라 필수로 두지 않는 비대칭 설계다.
"""

from datetime import datetime

from app import storage
from app.config import settings
from app.geo import h3grid
from app.geo.geocode import ANCHOR_MAX_KM, get_geocoder
from app.llm import tip_llm
from app.phase2 import pipeline
from app.phase3 import alerts, poa_update, time_resolve, triggers, trust
from app.schemas.case import Case, CaseStatus
from app.schemas.common import GeoPoint
from app.schemas.tip import Tip, TipDecision

_GEO = get_geocoder(use_nominatim=True)


def _geocode_tip_location(location_text: str | None, anchor: GeoPoint) -> GeoPoint | None:
    """제보의 location_text(자유서술) → 좌표. Phase 0 온보딩 끌림점과 동일한
    앵커 반경 방어선(ANCHOR_MAX_KM)을 쓴다 — LKP 에서 너무 먼 매칭은 오검색으로
    보고 버린다("은행 앞" 전국 오검색 등, app.geo.geocode 참고)."""
    if not location_text:
        return None
    res = _GEO.locate(location_text, anchor)
    if res is None:
        return None
    if h3grid.haversine_km(anchor, res.point) > ANCHOR_MAX_KM:
        return None
    return res.point


def process_tip(
    case: Case,
    *,
    text: str,
    location: GeoPoint | None = None,
    seen_at: datetime | None = None,
    force: bool = False,
    now: datetime | None = None,
) -> Tip | dict:
    now = now or datetime.now()

    # 구조화 1회 — 슬롯 JSON + 구체성 등급이 같은 호출 결과라 여기서 한 번만 부르고
    # 아래 score_tip 에 그대로 주입한다(재호출 방지).
    structured = tip_llm.structure_tip(text)

    if location is None:
        location = _geocode_tip_location(structured.get("location_text"), case.lkp)
    if seen_at is None:
        seen_at = time_resolve.resolve_seen_at(structured, now=now, lkp_time=case.lkp_time)

    if location is None and not structured.get("location_text") and not force:
        return {"status": "need_more", "missing": ["location"]}

    tip = Tip(
        id=storage.new_id(),
        case_id=case.id,
        text=text,
        location=location,
        seen_at=seen_at,
    )

    # ① 신뢰도 p 산출 — 이진 판정이 아니라 p 값 그대로 아래로 전달.
    #    개연성 항에 필요한 현재 LKP·시각·유형을 함께 넘긴다 (kinematic 상한).
    tip.p = trust.score_tip(
        tip,
        lkp=case.lkp, lkp_time=case.lkp_time, persona_type=case.report.missing_type,
        structured=structured,
    )

    # 시각 되묻기 게이트 — 위치는 있고 시각만 없는데, 폴백(created_at) 기준
    # 산출한 p 가 이미 층2 문턱을 넘은 강한 제보만 되묻는다(단조성 근거는
    # 모듈 docstring). 폴백 p 가 문턱 미만이면 실제 시각을 받아도 층2 불가 →
    # 되물어도 무의미하므로 그대로 층1로 진행한다.
    if (not force
            and tip.location is not None
            and tip.seen_at is None
            and tip.p >= settings.tip_lkp_threshold):
        return {"status": "need_more", "missing": ["time"], "reason": "layer2_needs_time"}

    tip.decision = poa_update.classify_tip(tip.p, trust.has_specific_location_time(tip))
    case.tips.append(tip)

    if tip.decision == TipDecision.discard:
        storage.cases.save(case.id, case)
        return tip

    # ② 층1 — 베이지안 POA 갱신 (위치 있는 제보만 분포를 기울일 수 있음)
    if tip.location is not None and case.current_poa:
        case.current_poa = poa_update.layer1_update(case.current_poa, tip.location, tip.p)

    # ③ 층2 — 새 LKP 확정 시 Phase 2 재실행
    if tip.decision == TipDecision.layer2:
        assert tip.location is not None and tip.seen_at is not None
        case.lkp = tip.location
        case.lkp_time = tip.seen_at
        pipeline.run_prediction(case, now=now)  # baseline/current POA 재생성
        # 층2 직후: 새 baseline 위에 새 LKP 시각 이후의 잔여 유효 제보 재적용
        case.current_poa = poa_update.reapply_tips(
            case.baseline_poa or {}, case.tips, since=tip.seen_at)
    else:
        # ④ 제보와 무관한 층2 트리거(주기 도달 / 분포 이탈)도 함께 검사
        rerun, reason = triggers.should_rerun_phase2(case, now)
        if rerun:
            pipeline.run_prediction(case, now=now)
            case.current_poa = poa_update.reapply_tips(
                case.baseline_poa or {}, case.tips, since=case.lkp_time)

    # ⑤ D3 — 3차 알림(새 지역 한정) 평가. last_alert_poa 가 없으면(수동 POA
    #    알림을 한 번도 보낸 적 없으면) 비교 기준이 없어 평가하지 않는다 —
    #    비교 기준 없이는 "새 지역"을 판정할 수 없으므로 의도된 동작.
    if case.current_poa and case.last_alert_poa:
        js = triggers.jensen_shannon_divergence(case.current_poa, case.last_alert_poa)
        if js >= settings.js_divergence_threshold:
            new_cells = alerts.select_new_region_cells(case.current_poa, case.last_alert_poa)
            if new_cells:
                summary = (
                    case.report.appearance.summary if case.report.appearance
                    else "인상착의 정보 없음"
                )
                alerts.send_alerts(case.id, new_cells, summary, kind="new_region")
                case.last_alert_poa = dict(case.current_poa)
                case.last_alert_at = now

    case.status = CaseStatus.searching
    storage.cases.save(case.id, case)
    return tip
