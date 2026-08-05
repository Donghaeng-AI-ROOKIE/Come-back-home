"""Phase 3 API — 알림 발송·시민 제보·POA 조회."""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import storage
from app.geo import h3grid
from app.phase3 import alerts, presence, tip_flow, triggers
from app.privacy import lifecycle
from app.schemas.case import CaseStatus
from app.schemas.common import GeoPoint

router = APIRouter(prefix="/phase3", tags=["Phase 3 — 알림·제보·POA 갱신"])


class TipIn(BaseModel):
    text: str
    location: GeoPoint | None = None   # 명시 좌표(향후 지도 핀 등). 없으면 텍스트에서 지오코딩.
    seen_at: datetime | None = None
    force: bool = False                 # 위치 미확보 되묻기를 건너뛰고 그대로 확정


class PresenceIn(BaseModel):
    # 클라이언트가 생성한 불투명 난수. 서버는 이것이 누구인지 모른다 — 계정·기기·
    # 위치 어디에도 연결하지 않는다(자세한 근거: phase3/presence.py).
    # 좌표 필드는 의도적으로 없다: 셀 단위 집계는 곧 위치정보다.
    token: str = Field(min_length=8, max_length=128)


def _get_case(case_id: str):
    case = storage.cases.get(case_id)
    if case is None:
        raise HTTPException(404, "케이스 없음")
    return case


def _require_active(case):
    """종결(발견/철회)된 케이스에 알림·제보가 계속 흐르면 개인정보 파기
    라이프사이클이 무효가 된다 — 인상착의 알림 발송, 제보로 인한 status
    되돌림(searching)을 여기서 차단. 조회(GET)는 막지 않는다."""
    try:
        lifecycle.ensure_not_closed(case)
    except lifecycle.AlreadyClosed as e:
        raise HTTPException(409, str(e))


@router.post("/cases/{case_id}/reflex-alerts")
def send_reflex_alerts(case_id: str):
    """1차 안전반경 즉시 알림 — POA 불필요 (신고 직후 골든타임용, 수동 재발송)."""
    case = _get_case(case_id)
    _require_active(case)
    cells = alerts.select_reflex_cells(case.lkp)
    summary = case.report.appearance.summary if case.report.appearance else "인상착의 정보 없음"
    return alerts.send_alerts(case.id, cells, summary, kind="reflex")


@router.post("/cases/{case_id}/alerts")
def send_alerts(case_id: str):
    """1차 알림 — 현재 POA 상위 셀(누적 80%) 내 사용자에게 발송.

    D3(3차, 새 지역 한정 알림)의 비교 기준(last_alert_poa)을 최초로 시딩하는
    지점이기도 하다 — 이 엔드포인트를 한 번도 호출하지 않으면 D3 는 계속
    비활성 상태로 남는다(비교 기준이 없으면 "새 지역"을 판정할 수 없으므로
    의도된 동작).
    """
    case = _get_case(case_id)
    _require_active(case)
    if not case.current_poa:
        raise HTTPException(409, "POA 없음 — Phase 2 예측을 먼저 실행하세요")
    cells = alerts.select_alert_cells(case.current_poa)
    summary = case.report.appearance.summary if case.report.appearance else "인상착의 정보 없음"
    result = alerts.send_alerts(case.id, cells, summary)
    case.last_alert_poa = dict(case.current_poa)
    case.last_alert_at = datetime.now()
    storage.cases.save(case.id, case)
    return result


@router.post("/cases/{case_id}/tips")
def submit_tip(case_id: str, body: TipIn):
    """시민 제보 접수(자유텍스트) → 신뢰도 p → 층1 갱신 (+조건 충족 시 층2 재실행).

    위치를 텍스트에서도 명시값에서도 못 얻으면 저장하지 않고
    {"status": "need_more", "missing": ["location"]} 를 반환한다 — 프론트가
    위치만 되물어 합친 전체 텍스트로 재제출하거나, force=True 로 그대로 확정한다.

    위치는 있는데 시각이 없고 폴백 기준 p 가 이미 층2 문턱(0.8) 이상이면
    {"status": "need_more", "missing": ["time"]} 를 반환한다 — 실제 시각을
    받아야 층2(새 LKP) 여부가 정확히 갈리는 구간이라서다. 이 역시
    force=True 로 건너뛸 수 있다(건너뛰면 층1로 접수).
    """
    case = _get_case(case_id)
    _require_active(case)
    if not case.current_poa:
        raise HTTPException(409, "POA 없음 — Phase 2 예측을 먼저 실행하세요")
    return tip_flow.process_tip(
        case,
        text=body.text,
        location=body.location,
        seen_at=body.seen_at,
        force=body.force,
    )


@router.get("/cases/{case_id}/poa")
def get_poa(case_id: str, top: int = 20):
    """현재 POA 상위 셀 조회 (지도 시각화용)."""
    case = _get_case(case_id)
    if not case.current_poa:
        raise HTTPException(409, "POA 없음 — Phase 2 예측을 먼저 실행하세요")
    ranked = sorted(case.current_poa.items(), key=lambda kv: kv[1], reverse=True)[:top]
    return {
        "case_id": case.id,
        "total_cells": len(case.current_poa),
        "top_cells": [
            {
                "cell": c,
                "prob": round(p, 6),
                # H3 셀 → 육각형 폴리곤(위경도 6꼭짓점). 프론트는 그대로 지도에 렌더 (변환 불필요).
                "polygon": [{"lat": v.lat, "lng": v.lng} for v in h3grid.cell_boundary(c)],
            }
            for c, p in ranked
        ],
    }


@router.post("/cases/{case_id}/presence")
def touch_presence(case_id: str, body: PresenceIn):
    """익명 참여 하트비트 + 현재 동시 참여자 수 ("지금 N명이 함께 보고 있어요").

    갱신과 조회를 한 응답에 담는 이유: 프론트는 이것만 주기 호출하면 되고
    폴링 왕복이 절반으로 준다.
    """
    case = _get_case(case_id)
    _require_active(case)
    return {"case_id": case.id, "watching": presence.heartbeat(case.id, body.token)}


@router.get("/cases/{case_id}/presence")
def get_presence(case_id: str):
    """동시 참여자 수 조회만 (하트비트 없음) — 운영 대시보드처럼
    '참여자로 세어지면 안 되는' 관찰자용."""
    case = _get_case(case_id)
    return {"case_id": case.id, "watching": presence.count(case.id)}


@router.get("/cases/{case_id}/rerun-check")
def rerun_check(case_id: str):
    """층2 트리거(주기/분포이탈) 상태 확인 — 운영 대시보드·스케줄러용."""
    case = _get_case(case_id)
    if case.status in (CaseStatus.found, CaseStatus.closed):
        # 종결 케이스를 스케줄러가 계속 재실행하면 파기 대기 중인 개인정보로
        # 예측을 돌리는 셈 — 트리거 판정 전에 차단
        return {"case_id": case.id, "should_rerun": False,
                "reason": f"종결된 케이스 ({case.status.value})"}
    rerun, reason = triggers.should_rerun_phase2(case)
    return {"case_id": case.id, "should_rerun": rerun, "reason": reason}
