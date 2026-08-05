"""Phase 3 API — 알림 발송·시민 제보·POA 조회."""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import storage
from app.geo import h3grid
from app.phase3 import alerts, devices, presence, storytelling, tip_flow, triggers
from app.privacy import lifecycle
from app.schemas.case import CaseStatus
from app.schemas.common import GeoPoint
from app.schemas.device import Engagement, Platform

router = APIRouter(prefix="/phase3", tags=["Phase 3 — 알림·제보·POA 갱신"])


class TipIn(BaseModel):
    text: str
    location: GeoPoint | None = None   # 명시 좌표(향후 지도 핀 등). 없으면 텍스트에서 지오코딩.
    seen_at: datetime | None = None
    force: bool = False                 # 위치 미확보 되묻기를 건너뛰고 그대로 확정
    # 마이페이지 "제보 N건" 배지용. **Tip 에 저장하지 않고 카운터만 올린다** —
    # 시민 신원과 사건을 잇는 기록을 남기면 케이스 파기 후에도 연결이 남는다
    # (storage.walk_tip_counts 주석 참조). 없으면 세지 않는다.
    reporter_user_id: str | None = None


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
    # poa 를 넘겨야 서버가 참여도별 확률 문턱을 적용할 수 있다(피로도 예산).
    result = alerts.send_alerts(case.id, cells, summary, poa=case.current_poa)
    case.last_alert_poa = dict(case.current_poa)
    case.last_alert_at = datetime.now()
    storage.cases.save(case.id, case)
    return result


@router.get("/alerts")
def list_active_alerts(cell_res7: str | None = None):
    """지금 살아 있는 경보 중 **이 res7 칸에 해당하는 것만.**

    ## 왜 조회 경로가 따로 필요한가
    푸시는 **보내는 그 순간**에만 도달한다 — 폰이 꺼져 있었거나, 알림을 쓸어
    없앴거나, 방금 앱을 깔았으면 아무것도 남지 않는다. 그런데 진입 관문은
    사용자가 **앱을 직접 연** 순간에 판정해야 하므로 물어볼 데가 있어야 한다.

    ## 🚨 전부 내려주지 않는다
    "활성 사건 목록"을 통째로 주면 앱이 전국 실종자 명단을 받게 되고, 폰이 그중
    자기 것을 고르는 구조가 된다 — 푸시에서 포기한 A안(서버가 위치를 모르고 폰이
    필터링)으로 되돌아가는 것이고, res7 로 최소화해 둔 것을 조회 경로가 조용히
    무효화한다. 발송과 **같은 기준**으로 서버가 고른다.

    ## 칸을 안 주면 빈 목록 (fail-closed)
    위치를 모르면 어느 사건이 이 사람에게 해당되는지 고를 수 없다. 아무거나
    돌려주면 **틀린 사건**을 보여주게 된다 — 못 보는 것보다 나쁘다
    (프론트 utils/alertGate.alertAppliesToMe 와 같은 판단).

    종결(발견·철회)된 사건은 빠진다. 파기 대기 중인 개인정보를 계속 노출하지
    않기 위해서이기도 하고, 찾은 사람을 계속 찾게 두면 안 되기 때문이기도 하다.
    """
    if not cell_res7:
        return []
    out = []
    for case in storage.cases.list():
        if case.status in (CaseStatus.found, CaseStatus.closed):
            continue
        info = alerts.describe_alert(case)
        if cell_res7 in info["target_cells"]:
            out.append(info)
    # 최근 발령 순 — 관문은 첫 항목부터 본다(utils/alertGate.pickGateCase).
    out.sort(key=lambda a: a["issued_at"], reverse=True)
    return out


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
    result = tip_flow.process_tip(
        case,
        text=body.text,
        location=body.location,
        seen_at=body.seen_at,
        force=body.force,
    )
    # process_tip 은 되묻기면 dict, 접수되면 Tip 객체를 준다 — 형이 갈리므로
    # dict 일 때만 status 를 본다. 되묻기(need_more)는 아직 접수가 아니라서
    # 세지 않는다: 위치를 못 준 채 여러 번 시도한 것이 제보 건수로 부풀면 안 된다.
    accepted = not (isinstance(result, dict) and result.get("status") == "need_more")
    if body.reporter_user_id and accepted:
        prev = storage.walk_tip_counts.get(body.reporter_user_id) or 0
        storage.walk_tip_counts.save(body.reporter_user_id, prev + 1)
    return result


@router.get("/cases/{case_id}/poa")
def get_poa(case_id: str, top: int = 20, elapsed_hours: float | None = None):
    """POA 상위 셀 조회 (지도 시각화용).

    `elapsed_hours` 를 주면 **"만약 t시간 경과라면"** 의 지도를 돌려준다 —
    시간축 슬라이더용이다. 기존 통계(Koester 링)는 시점과 무관한 하나의 분포지만,
    우리는 경과시간이 예측에 들어가므로 시점마다 분포가 다르다(30분 최대 1.44km
    vs 1시간 2.88km — 상한부터 두 배 차이다).

    첫 조회는 계산하느라 ~7초 걸리고 이후는 캐시(case.poa_by_hour)에서 즉시 나온다.
    **케이스 상태는 바뀌지 않는다** — 알림·제보는 계속 실제 경과시간 지도만 쓴다.
    """
    case = _get_case(case_id)
    if not case.current_poa:
        raise HTTPException(409, "POA 없음 — Phase 2 예측을 먼저 실행하세요")

    poa = case.current_poa
    shown_elapsed = (
        round((case.last_sim_at - case.lkp_time).total_seconds() / 3600.0, 2)
        if case.last_sim_at else None)
    if elapsed_hours is not None:
        key = f"{elapsed_hours:g}"
        cached = case.poa_by_hour.get(key)
        if cached is None:
            from app.phase2 import pipeline

            try:
                cached = pipeline.poa_at_elapsed(case, elapsed_hours)
            except ValueError as e:
                raise HTTPException(409, str(e)) from e
            case.poa_by_hour[key] = cached
            storage.cases.save(case.id, case)
        poa = cached
        shown_elapsed = elapsed_hours

    ranked = sorted(poa.items(), key=lambda kv: kv[1], reverse=True)[:top]
    return {
        "case_id": case.id,
        "total_cells": len(poa),
        # 이 POA 가 개인화된 prior 로 만들어졌는지. EXAONE 호출이 실패해도 예측은
        # 통계 기본값으로 계속 돌기 때문에, 이 값을 안 내려주면 앱이 "AI 예측"이라고
        # 표시하면서 실제로는 프로파일 평균을 보여주게 된다 (2026-08-05 실측 사례).
        "prior_source": case.prior.source if case.prior else "unknown",
        "prior_fallback_reason": case.prior.fallback_reason if case.prior else "",
        # 도로망 위에서 걸었는지. 로딩 실패 시 연속 공간 폴백이 조용히 일어나
        # "도로 제약 없는 예측"이 나가므로 같이 내려준다 (Case.roadnet_used 주석).
        "roadnet_used": case.roadnet_used,
        "roadnet_fallback_reason": case.roadnet_fallback_reason,
        # 이 지도가 **언제 계산된 것인지**. 자동 갱신(phase2.refresher)이 붙었어도
        # 화면에 안 보이면 수색대는 지도가 최신인지 알 수 없다. 갱신 실패로 오래된
        # 지도를 계속 보고 있어도 모르게 되므로 계약에 올린다.
        "computed_at": case.last_sim_at,
        # 예측에 쓰인 경과시간(시간). "5시간 시점 지도"라는 것을 화면이 말할 수 있게.
        "elapsed_hours": shown_elapsed,
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


class DeviceIn(BaseModel):
    # Expo Push 토큰 (ExponentPushToken[...]).
    token: str = Field(min_length=8, max_length=256)
    platform: Platform
    # 현재 위치의 H3 res7 셀. **폰이 좌표를 이 해상도로 바꿔서 보낸다** —
    # 정밀 좌표는 기기를 떠나지 않는다. 서버는 현재 값만 덮어쓰고 이력을 안 남긴다.
    # 못 구했으면 생략(그 기기는 타겟 발송에서 빠진다).
    cell_res7: str | None = Field(default=None, max_length=32)
    # 참여도 등급 3값. 원시 이력(열람·제보 횟수)은 폰에만 있고 이 요약값만 온다.
    engagement: Engagement = Engagement.normal


@router.post("/devices")
def register_device(body: DeviceIn):
    """기기 등록 — 푸시 발송 대상에 추가. 앱 실행 시마다 호출해도 안전(upsert).

    ⚠️ 이 시점부터 서버는 지속적 기기 식별자를 갖는다. 푸시의 본질이라 회피할 수
    없고, 남는 선택지는 토큰에 무엇을 붙이지 않느냐뿐이다.
    """
    device = devices.register(body.token, body.platform, body.cell_res7, body.engagement)
    return {
        "registered": True,
        "platform": device.platform,
        "since": device.registered_at,
        "targetable": device.cell_res7 is not None,
    }


@router.delete("/devices/{token}")
def unregister_device(token: str):
    """등록 해제 — 알림 수신 거부·앱 삭제 시. 지속적 식별자이므로
    지우는 경로가 반드시 있어야 한다."""
    return {"unregistered": devices.unregister(token)}


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


@router.get("/cases/{case_id}/guidance")
def get_guidance(case_id: str):
    """수색 안내 문구 — "어디를 봐야 하는지".

    **수색 탭 전용이다.** 푸시 본문에는 넣지 않는다 — 잠금화면은 폰을 집어든 누구나
    보고 그 알림은 구 단위 수천 명에게 가므로, 같은 문장이라도 노출 범위가 다르다.
    푸시로 확대할지는 기획 결정 대기(노션 참고).

    페르소나가 없으면(사전 미등록) 경과시간 기반 범위 안내만 나간다.

    `pending=True` 면 LLM 이 문구를 다듬는 중이라 곧 더 나은 문구가 준비된다 —
    앱은 그동안만 다시 묻는다. 기다리지 않는 이유는 storytelling 모듈 주석 참고.
    """
    case = _get_case(case_id)
    persona = (
        storage.personas.get(case.report.persona_id) if case.report.persona_id else None
    )
    text, pending = storytelling.guidance_with_refine(case, persona)
    return {
        "case_id": case.id,
        "guidance": text,
        "personalized": persona is not None,
        "pending": pending,
    }


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
