"""Phase 1 API — 실종 신고 접수."""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.schemas.environment import EnvironmentObservation, BehaviorObservation

from app import storage
from app.phase1 import intake
from app.schemas.case import Case, CaseStatus
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.report import Appearance

router = APIRouter(prefix="/phase1", tags=["Phase 1 — 신고 접수"])


class CreateReportIn(BaseModel):
    missing_type: PersonaType
    lkp: GeoPoint
    lkp_time: datetime
    persona_id: str | None = None
    # 보호자가 적은 실종 당시 상황 자유 서술. 지금은 저장만 하고 알림·안내문구
    # 등 다른 곳엔 아직 안 쓴다 — 소비처는 후속 결정.
    situation: str = ""
    # 보호자가 직접 입력한 인상착의. 생성·사진분석 모델을 거치지 않고 색상만
    # 규칙 기반으로 추출한다. 사진·문서 첨부는 받지 않는다(2026-08-07 결정 —
    # 실제로 동작한 적 없는 스텁이었다).
    appearance: Appearance | None = None
    environment_observations: list[EnvironmentObservation] = Field(default_factory=list, max_length=100)
    behavior_observations: list[BehaviorObservation] = Field(default_factory=list, max_length=100)


@router.post("/reports", response_model=Case, response_model_exclude={"continuous_state", "prior_context_key"})
def create_report(body: CreateReportIn):
    return intake.create_report(
        missing_type=body.missing_type,
        lkp=body.lkp,
        lkp_time=body.lkp_time,
        persona_id=body.persona_id,
        situation=body.situation,
        appearance=body.appearance,
        environment_observations=body.environment_observations,
        behavior_observations=body.behavior_observations,
    )


@router.get("/cases/{case_id}", response_model=Case, response_model_exclude={"continuous_state", "prior_context_key"})
def get_case(case_id: str):
    case = storage.cases.get(case_id)
    if case is None:
        raise HTTPException(404, "케이스 없음")
    return case


class LinkPersonaIn(BaseModel):
    persona_id: str


@router.patch("/cases/{case_id}/persona", response_model=Case, response_model_exclude={"continuous_state", "prior_context_key"})
@storage.serialize_case
def link_persona(case_id: str, body: LinkPersonaIn):
    """Attach post-report onboarding without creating another missing incident.

    Uses the existing case-ID access convention; this is not an ownership/auth upgrade.
    Existing links cannot silently be replaced, and closed cases cannot be changed.
    """
    persona = storage.personas.get(body.persona_id)
    if persona is None:
        raise HTTPException(404, "페르소나 없음")
    changed = False

    def attach(current):
        nonlocal changed
        if current.status in (CaseStatus.found, CaseStatus.closed):
            raise HTTPException(409, "종료된 사건에는 등록 정보를 연결할 수 없음")
        if current.report.persona_id not in (None, persona.id):
            raise HTTPException(409, "이미 다른 등록 정보가 연결된 사건")
        if current.report.missing_type != persona.type:
            raise HTTPException(422, "신고와 등록 정보의 유형이 다름")
        if current.report.persona_id == persona.id:
            return None
        changed = True
        linked = current
        linked.report.persona_id = persona.id
        return linked

    saved = storage.cases.update_existing(case_id, attach)
    case = saved or storage.cases.get(case_id)
    if case is None:
        raise HTTPException(404, "케이스 없음")
    if changed:
        from app.phase0.person_preparation import enqueue
        from app.phase0.persona_events import notify_persona_updated
        enqueue(persona.id)
        notify_persona_updated(persona.id, persona.version)
    return case
