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
         "axis_field": s.axis_field, "tier": s.tier.value,
         # 앱 입력 보조(마이크 버튼)가 채워 넣을 답변 예시. 음성 인식이 붙기 전까지
         # 보호자가 "이 정도로 답하면 되는구나"를 보고 고쳐 쓰는 용도다 — 프론트가
         # 예시를 지어내면 슬롯과 어긋나므로 카탈로그의 것을 그대로 내려준다.
         "answer_example": s.answer_example}
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


@router.get("/personas", response_model=list[Persona], response_model_exclude=_PERSONA_EXCLUDE)
def list_personas():
    """등록된 페르소나 목록 — 보호자 홈의 '사전 등록된 가족'.

    인증이 없어 전체를 돌려준다. 보호자↔페르소나 소유 관계가 붙으면 여기서
    필터링해야 한다 — 지금은 단일 사용자 데모 전제다.
    """
    return storage.personas.list()


@router.get("/personas/{persona_id}", response_model=Persona, response_model_exclude=_PERSONA_EXCLUDE)
def get_persona(persona_id: str):
    persona = storage.personas.get(persona_id)
    if persona is None:
        raise HTTPException(404, "페르소나 없음")
    return persona


class UpdatePersonaIn(BaseModel):
    """부분 수정 — 준 필드만 바꾼다(None = 그대로).

    **인터뷰가 추출한 값을 보호자가 고치는 통로다.** Mi:dm 추출은 완벽하지 않고
    (2026-08-05 실측: 같은 답변이 슬롯 두 곳에 중복 저장, 발견 장소가 끌림점으로
    분류) 그 오류가 그대로 예측 근거가 된다. 보호자가 직접 고칠 수 있어야 한다.

    축 점수·근거(axis_*)는 여기서 못 고친다 — LLM 채점 결과이고 원발화(quote)와
    짝을 이뤄야 의미가 있어서, 값만 손대면 근거와 어긋난다.
    """
    name: str | None = None
    age: int | None = None
    home: GeoPoint | None = None
    attraction_points: list[AttractionPoint] | None = None
    behavior_notes: list[str] | None = None


@router.patch("/personas/{persona_id}", response_model=Persona,
              response_model_exclude=_PERSONA_EXCLUDE)
def update_persona(persona_id: str, body: UpdatePersonaIn):
    persona = storage.personas.get(persona_id)
    if persona is None:
        raise HTTPException(404, "페르소나 없음")
    updates = body.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        return persona
    updated = persona.model_copy(update=updates)
    storage.personas.save(persona_id, updated)
    return updated
