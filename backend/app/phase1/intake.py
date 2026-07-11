"""Phase 1 — 실종 신고 처리.

흐름 A: 실종신고(유형·사진·위치) → VARCO-Vision 인상착의 추출
흐름 B: 신고 문서 → Upstage 파싱 → 신고자 정보 추출
두 흐름이 합류해 Case 를 생성하고, 도로망 로딩(현재는 스텁)을 준비한다.
"""

from datetime import datetime

from app import storage
from app.config import settings
from app.geo import roadnet
from app.llm import upstage, varco
from app.schemas.case import Case, CaseStatus
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.report import MissingReport


def create_report(
    *,
    missing_type: PersonaType,
    lkp: GeoPoint,
    lkp_time: datetime,
    persona_id: str | None = None,
    photo_bytes: bytes | None = None,
    document_bytes: bytes | None = None,
) -> Case:
    """신고 접수 → Case 생성.

    - photo_bytes 가 있으면 VARCO-Vision 으로 인상착의 추출
    - document_bytes 가 있으면 Upstage 로 신고자 정보 추출
    """
    report = MissingReport(
        id=storage.new_id(),
        persona_id=persona_id,
        missing_type=missing_type,
        lkp=lkp,
        lkp_time=lkp_time,
    )

    if photo_bytes is not None:
        report.appearance = varco.extract_appearance(photo_bytes)
    if document_bytes is not None:
        report.reporter = upstage.parse_document(document_bytes)

    case = Case(
        id=storage.new_id(),
        report=report,
        status=CaseStatus.intake,
        lkp=report.lkp,
        lkp_time=report.lkp_time,
    )
    storage.cases.save(case.id, case)

    # 도로망 사전 로딩 — LKP 반경 보행 그래프를 미리 받아 캐시 (Phase 2 가 사용).
    # 실패해도 신고 접수는 막지 않는다 (시뮬레이션이 필요 시 재시도).
    if settings.roadnet_preload:
        try:
            roadnet.get_network(case.lkp)
        except Exception as e:  # noqa: BLE001 — 외부 API 실패 격리
            print(f"[roadnet] 사전 로딩 실패 (신고 접수는 계속): {e}")
    return case
