"""Phase 3 — 제보 수신부터 POA 갱신·층2 재실행까지의 전체 흐름.

제보 수신 → 신뢰도 p 산출 (Varco 사진 대조 + 챗봇 질문)
│
├─ p < 0.2 (허위/스팸)         → 파기. 아무 데도 반영 안 함
├─ 0.2 ≤ p < 0.8               → 층1: POA 베이지안 갱신만 (p 가중)
└─ p ≥ 0.8 + 위치·시각 특정     → 층1 갱신 + 새 LKP 확정
                                → 층2: Phase 2 재실행 → 잔여 제보 재적용
"""

from datetime import datetime

from app import storage
from app.phase2 import pipeline
from app.phase3 import poa_update, triggers, trust
from app.schemas.case import Case, CaseStatus
from app.schemas.common import GeoPoint
from app.schemas.tip import Tip, TipDecision


def process_tip(
    case: Case,
    *,
    text: str,
    location: GeoPoint | None = None,
    seen_at: datetime | None = None,
    tip_image: bytes | None = None,
    now: datetime | None = None,
) -> Tip:
    now = now or datetime.now()

    tip = Tip(
        id=storage.new_id(),
        case_id=case.id,
        text=text,
        location=location,
        seen_at=seen_at,
        has_photo=tip_image is not None,
    )

    # ① 신뢰도 p 산출 — 이진 판정이 아니라 p 값 그대로 아래로 전달.
    #    개연성 항에 필요한 현재 LKP·시각·유형을 함께 넘긴다 (kinematic 상한).
    tip.p = trust.score_tip(
        tip, case.report.appearance,
        lkp=case.lkp, lkp_time=case.lkp_time, persona_type=case.report.missing_type,
        tip_image=tip_image,
    )
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

    case.status = CaseStatus.searching
    storage.cases.save(case.id, case)
    return tip
