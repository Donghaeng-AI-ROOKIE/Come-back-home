"""수색 케이스 — Phase 1에서 생성되어 Phase 2·3 상태를 모두 담는 중심 객체."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.common import GeoPoint
from app.schemas.prediction import MindState, PriorParams
from app.schemas.report import MissingReport
from app.schemas.tip import Tip


class CaseStatus(str, Enum):
    intake = "intake"          # Phase 1 접수됨
    predicted = "predicted"    # Phase 2 예측 완료
    searching = "searching"    # Phase 3 알림·제보 루프 중
    found = "found"
    closed = "closed"


class CloseReason(str, Enum):
    found = "found"          # 발견 — 목적 달성
    withdrawn = "withdrawn"  # 신고 철회


class Case(BaseModel):
    id: str
    report: MissingReport
    status: CaseStatus = CaseStatus.intake

    # 개인정보 파기 라이프사이클 (privacy/lifecycle.py) — 종결 시각 기준으로
    # TTL(보관 만료) 카운트다운이 시작된다
    created_at: datetime = Field(default_factory=datetime.now)
    closed_at: datetime | None = None
    close_reason: CloseReason | None = None

    # 현재 앵커 — 층2 트리거 시 고신뢰 목격 위치·시각으로 교체된다
    lkp: GeoPoint
    lkp_time: datetime

    # Phase 2 산출물
    prior: PriorParams | None = None
    mind: MindState | None = None
    baseline_poa: dict[str, float] | None = None   # 마지막 시뮬 직후 분포 (KL 이탈 비교 기준)
    current_poa: dict[str, float] | None = None    # 층1 갱신이 누적된 최신 분포
    last_sim_at: datetime | None = None

    # Phase 3 누적
    tips: list[Tip] = []
