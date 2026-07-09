"""Phase 0 API — 온보딩 인터뷰·페르소나 등록."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import storage
from app.phase0 import interview
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, InterviewSession, Persona, PersonaType

router = APIRouter(prefix="/phase0", tags=["Phase 0 — 온보딩"])


class StartInterviewIn(BaseModel):
    guardian_name: str


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
    return interview.start_interview(body.guardian_name)


@router.post("/interviews/{session_id}/answers", response_model=InterviewSession)
def answer(session_id: str, body: AnswerIn):
    try:
        return interview.answer_interview(session_id, body.text)
    except KeyError:
        raise HTTPException(404, "인터뷰 세션 없음")


@router.post("/personas", response_model=Persona)
def register_persona(body: RegisterPersonaIn):
    return interview.register_persona(
        body.session_id,
        name=body.name, age=body.age, ptype=body.type, home=body.home,
        attraction_points=body.attraction_points, behavior_notes=body.behavior_notes,
    )


@router.get("/personas/{persona_id}", response_model=Persona)
def get_persona(persona_id: str):
    persona = storage.personas.get(persona_id)
    if persona is None:
        raise HTTPException(404, "페르소나 없음")
    return persona
