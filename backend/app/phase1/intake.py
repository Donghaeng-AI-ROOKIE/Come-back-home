"""Phase 1 — 실종 신고 처리.

실종신고(유형·위치·보호자 직접 입력 인상착의) → 규칙 기반 색상 추출 → Case 생성,
도로망 로딩(현재는 스텁)을 준비한다. 사진·문서 첨부는 받지 않는다(2026-08-07
결정 — 실제로 동작한 적 없는 스텁이었다: 사진은 VARCO 제거로 이미 삭제됐고,
문서는 Upstage 연동이 TODO 상태로 항상 가짜 응답만 반환하고 있었다).
"""

from datetime import datetime

from app import storage
from app.config import settings
from app.geo import roadnet
from app.phase1.color_extract import extract_color
from app.phase3 import alerts
from app.schemas.case import Case, CaseStatus
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.report import Appearance, MissingReport


def create_report(
    *,
    missing_type: PersonaType,
    lkp: GeoPoint,
    lkp_time: datetime,
    persona_id: str | None = None,
    situation: str = "",
    appearance: Appearance | None = None,
) -> Case:
    """신고 접수 → Case 생성.

    - situation 은 보호자가 적은 실종 당시 상황 자유 서술(그대로 저장만 함,
      아직 알림·안내문구 등 다른 곳에서 안 씀 — 소비처는 후속 결정)
    - appearance 는 보호자가 직접 입력한 구조화 텍스트
    - 상의·하의·신발 색상은 외부 모델 없이 규칙 함수로 추출
    """
    report = MissingReport(
        id=storage.new_id(),
        persona_id=persona_id,
        missing_type=missing_type,
        lkp=lkp,
        lkp_time=lkp_time,
        situation=situation,
        appearance=appearance.model_copy(deep=True) if appearance is not None else None,
    )

    # 고정 실루엣 아바타용 색상 추출 — 보호자 입력만 사용하며 외부 모델·네트워크
    # 호출이 전혀 없다. summary 는 보호자에게 따로 받지 않는다 — 항목별 입력
    # (상의·하의·신발·기타특징)을 서버가 항상 합쳐서 만든다. 클라이언트가
    # 뭘 보내든 여기서 덮어쓴다(top_color 등과 동일한 원칙 — 서버가 유일한 소스).
    if report.appearance is not None:
        report.appearance.top_color = extract_color(report.appearance.top)
        report.appearance.bottom_color = extract_color(report.appearance.bottom)
        report.appearance.shoes_color = extract_color(report.appearance.shoes)
        parts = [
            report.appearance.top,
            report.appearance.bottom,
            report.appearance.shoes,
            report.appearance.etc,
        ]
        report.appearance.summary = ", ".join(p for p in parts if p)

    case = Case(
        id=storage.new_id(),
        report=report,
        status=CaseStatus.intake,
        lkp=report.lkp,
        lkp_time=report.lkp_time,
    )
    storage.cases.save(case.id, case)

    # 축 점수 백필 — 비동기 채점이 유실된 미채점 페르소나의 마지막 채점 기회
    # (Phase 2 가 점수를 소비하기 직전). 실패해도 접수는 계속.
    try:
        from app.phase0 import interview as phase0_interview
        phase0_interview.ensure_axis_scores(persona_id)
    except Exception as e:  # noqa: BLE001 — 채점 실패가 접수를 막으면 안 됨
        print(f"[axis] 축 점수 백필 실패 (접수는 계속): {e}")

    # 1차 안전반경 (Reflex Tasking) — 신고 즉시 IPP 주변 k-ring 알림.
    # Phase 2 예측이 나오기 전 골든타임 대응. 실패해도 접수는 계속.
    if settings.reflex_alert_on_intake:
        try:
            cells = alerts.select_reflex_cells(case.lkp)
            summary = report.appearance.summary if report.appearance else "인상착의 정보 없음"
            alerts.send_alerts(case.id, cells, summary, kind="reflex")
        except Exception as e:  # noqa: BLE001 — 알림 실패가 접수를 막으면 안 됨
            print(f"[reflex] 1차 알림 실패 (신고 접수는 계속): {e}")

    # 도로망 사전 로딩 — LKP 반경 보행 그래프를 미리 받아 캐시 (Phase 2 가 사용).
    # 실패해도 신고 접수는 막지 않는다 (시뮬레이션이 필요 시 재시도).
    if settings.roadnet_preload:
        try:
            roadnet.get_network(case.lkp)
        except Exception as e:  # noqa: BLE001 — 외부 API 실패 격리
            print(f"[roadnet] 사전 로딩 실패 (신고 접수는 계속): {e}")
    return case
