"""Phase 0 API — 온보딩 인터뷰·페르소나 등록."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import storage
from app.phase0 import interview
from app.phase0.slots import SLOTS, slots_for
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, InterviewSession, Persona, PersonaType

router = APIRouter(prefix="/phase0", tags=["Phase 0 — 온보딩"])


class StartInterviewIn(BaseModel):
    guardian_name: str
    persona_type: PersonaType | None = None   # UI 에서 유형을 먼저 고르면 전달(선택)


class AnswerIn(BaseModel):
    text: str


class RegisterPersonaIn(BaseModel):
    session_id: str | None = None
    name: str
    age: int
    type: PersonaType
    home: GeoPoint
    attraction_points: list[AttractionPoint] = []
    behavior_notes: list[str] = []


@router.post("/interviews", response_model=InterviewSession)
def start_interview(body: StartInterviewIn):
    return interview.start_interview(body.guardian_name, body.persona_type)


@router.post("/interviews/{session_id}/answers", response_model=InterviewSession)
def answer(session_id: str, body: AnswerIn):
    try:
        return interview.answer_interview(session_id, body.text)
    except KeyError:
        raise HTTPException(404, "인터뷰 세션 없음")


@router.get("/interviews/{session_id}", response_model=InterviewSession)
def get_interview(session_id: str):
    """인터뷰 세션 조회 — 대화 전문(messages) 포함. E2E 대시보드가 사용."""
    session = storage.interviews.get(session_id)
    if session is None:
        raise HTTPException(404, "인터뷰 세션 없음")
    return session


@router.get("/slots")
def list_slots(persona_type: PersonaType | None = None):
    """온보딩 슬롯 카탈로그 (축·라벨·필드명) — 대시보드가 페르소나를
    축 구조(공통 8 + 유형별 4)로 렌더링할 때 사용."""
    slots = slots_for(persona_type) if persona_type else SLOTS
    return [
        {"key": s.key, "label": s.label, "axis": s.axis.value,
         "axis_field": s.axis_field, "tier": s.tier.value}
        for s in slots
    ]


# axis_quotes = 보호자 원발화 그대로(quote 검증용 내부 값) — 프론트가 쓸 일이 없어
# API 응답에서 제외한다. 저장·파기·채점 로직에는 영향 없음(응답 스키마만 필터링).
_PERSONA_EXCLUDE = {"axis_quotes"}


@router.post("/personas", response_model=Persona, response_model_exclude=_PERSONA_EXCLUDE)
def register_persona(body: RegisterPersonaIn):
    return interview.register_persona(
        body.session_id,
        name=body.name, age=body.age, ptype=body.type, home=body.home,
        attraction_points=body.attraction_points, behavior_notes=body.behavior_notes,
    )


@router.get("/personas/{persona_id}", response_model=Persona, response_model_exclude=_PERSONA_EXCLUDE)
def get_persona(persona_id: str):
    persona = storage.personas.get(persona_id)
    if persona is None:
        raise HTTPException(404, "페르소나 없음")
    return persona
