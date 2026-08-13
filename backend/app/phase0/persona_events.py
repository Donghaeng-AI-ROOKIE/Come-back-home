"""Phase 0 — persona 갱신 이벤트 → 진행중 수색 재예측 트리거.

온보딩 없는 신고 흐름(2026-08)에서, 신고 전 Tier1 미니챗으로 만든 최소 프로필에
보완챗(Tier2·3)이 나중에 덧붙을 때, 그 persona 로 이미 진행 중인 case 가 있으면
새 정보를 반영해 예측을 다시 돌린다. "1차/2차 재예측 스케줄"이 아니라 이 이벤트
하나가 유일한 트리거다 — 보완챗을 아예 안 해도 되고, 여러 번 나눠 해도 매번 한
번씩만 돈다.

작업 큐가 이 코드베이스에 없으므로(axis_scoring 의 _start_scoring 과 같은 이유),
백그라운드 스레드로 돌려 인터뷰 완료 응답을 막지 않는다. 실패는 로그만 남기고
삼킨다 — 재예측 실패가 방금 확정된 persona 저장을 되돌리면 안 되고, 실패해도
다음 제보·주기 트리거(triggers.should_rerun_phase2)가 그때 다시 예측을 살펴본다.
"""

import threading
from datetime import datetime

from app import storage
from app.schemas.case import Case, CaseStatus


def _active_cases_for(persona_id: str) -> list[Case]:
    """이 persona 로 진행 중인(발견·종결 아닌) case 전체.

    Case.report.persona_id 는 중첩 필드라 storage 에 별도 인덱스가 없다 — 지금
    규모(동시 진행 케이스 수)에서는 전수 스캔으로 충분하다.
    """
    return [
        c for c in storage.cases.list()
        if c.report.persona_id == persona_id
        and c.status not in (CaseStatus.found, CaseStatus.closed)
    ]


def _rerun_case(case_id: str, persona_version: int) -> None:
    from app.phase2 import pipeline
    from app.phase3 import poa_update

    case = storage.cases.get(case_id)
    if case is None:
        return
    try:
        pipeline.run_prediction(case, now=datetime.now())
        # 제보 무관 층2 재실행(tip_flow.py)과 같은 패턴 — 새 baseline 위에 기존
        # 제보를 다시 얹어 그동안 쌓인 반영분을 잃지 않는다.
        case.current_poa = poa_update.reapply_tips(
            case.baseline_poa or {}, case.tips, since=case.lkp_time)
        storage.cases.save(case.id, case)
    except Exception as e:  # noqa: BLE001 — 재예측 실패가 persona 저장을 되돌리면 안 됨
        print(f"[persona_events] persona v{persona_version} 갱신 재예측 실패 "
              f"(case={case_id}): {e}")


def notify_persona_updated(persona_id: str, new_version: int) -> None:
    """persona 가 supplement/update 로 병합 저장된 직후 호출.

    create(신규 등록 — 아직 신고가 없어 연결된 case 자체가 없는 상태)에서는
    호출하지 않는다(finalize_persona 가 그 구분을 이미 함).
    """
    for case in _active_cases_for(persona_id):
        threading.Thread(target=_rerun_case, args=(case.id, new_version), daemon=True).start()
