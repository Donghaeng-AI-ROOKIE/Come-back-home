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


# ── 온보딩 없는 신고 흐름(2026-08) — 신규 엔드포인트. 위 기존 라우트는 그대로 두고
#    나란히 추가한다. 로그인 시스템이 없어 guardian_id 는 명시 파라미터로 받는다
#    (persona_id·session_id 등 기존 식별자들과 같은 전제 — 실제 인증이 붙으면
#    그 자리를 토큰에서 가져온 값으로 교체하면 된다).
#    ⚠ /personas/status 는 반드시 /personas/{persona_id} 보다 먼저 등록해야 한다 —
#    FastAPI 는 라우트를 등록 순서로 매칭하므로, 와일드카드 라우트가 먼저 오면
#    "/personas/status" 요청이 persona_id="status" 로 잘못 잡힌다. ─────────────

def _guardian_persona(guardian_id: str) -> Persona | None:
    """이 보호자의 persona — 여러 개면 가장 최근 것. guardian_id 인덱스가 없어
    전수 스캔(지금 규모에선 충분)."""
    if not guardian_id:
        return None
    matches = [p for p in storage.personas.list() if p.guardian_id == guardian_id]
    return matches[-1] if matches else None


@router.get("/personas/status")
def persona_status(guardian_id: str = ""):
    """이 보호자의 persona 진행 상태 — 프론트가 홈 배너·긴급신고 게이트 분기에 사용.

    available_mode == "update" 는 챗봇 재질문이 아니라 PersonaDetailScreen(구조화
    수정 화면, PATCH /phase0/personas/{id})으로 보내라는 신호다(2026-08-06 팀
    통합 결정 — 챗봇 재질문형 update 는 만들지 않기로 함)."""
    persona = _guardian_persona(guardian_id)
    status, mode = interview.persona_status_for(persona)
    return {
        "persona_id": persona.id if persona else None,
        "persona_status": status,
        "available_mode": mode,
        "completed_tiers": persona.completed_tiers if persona else [],
        "persona_version": persona.version if persona else None,
    }


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


class StartSessionIn(BaseModel):
    guardian_name: str
    guardian_id: str = ""
    mode: str = "create"     # create | supplement — 등록 정보 "수정"은 챗봇이 아니라
                             # PersonaDetailScreen(PATCH /personas/{id})이 담당한다.
    scope: str = "all"       # create 전용: "all"(12개) | "tier1"(5개, 신고 전 미니챗)
    persona_type: PersonaType | None = None


@router.post("/interviews/sessions")
def start_session(body: StartSessionIn):
    existing = _guardian_persona(body.guardian_id)
    status, _ = interview.persona_status_for(existing)

    if body.mode == "create":
        is_tier1 = body.scope == "tier1"
        session = interview.start_interview(
            body.guardian_name, body.persona_type,
            mode="create", target_tiers=[1] if is_tier1 else None,
            guardian_id=body.guardian_id, skip_confirmation=is_tier1,
        )
    elif body.mode == "supplement":
        if existing is None or status != "partial":
            raise HTTPException(
                409, f"supplement 모드는 partial 상태에서만 가능합니다(현재: {status})")
        session = interview.start_interview(
            body.guardian_name, existing.type,
            mode="supplement", target_tiers=[2, 3],
            guardian_id=body.guardian_id, persona_id=existing.id,
        )
    else:
        raise HTTPException(400, f"알 수 없는 mode: {body.mode}")

    last_q = session.messages[-1]["text"] if session.messages else ""
    total = len(slots_for(session.persona_type, session.target_tiers))
    return {
        "session_id": session.id,
        "mode": session.mode,
        "persona_status": status,
        "current_slot": session.prev_target_key,
        "progress": {"answered": len(session.filled_keys), "total": total},
        "question": last_q,
    }


class SessionMessageIn(BaseModel):
    text: str


@router.post("/interviews/sessions/{session_id}/messages")
def send_session_message(session_id: str, body: SessionMessageIn):
    """기존 interview.answer_interview() 를 그대로 호출한다 — 엔진 변경 없음,
    응답 형태만 progress/completed 로 감싼다."""
    try:
        session = interview.answer_interview(session_id, body.text)
    except KeyError:
        raise HTTPException(404, "인터뷰 세션 없음")
    last_q = session.messages[-1]["text"] if session.messages else ""
    total = len(slots_for(session.persona_type, session.target_tiers))
    persona_status_value = None
    if session.done and session.persona_id:
        persona = storage.personas.get(session.persona_id)
        if persona is not None:
            persona_status_value, _ = interview.persona_status_for(persona)
    return {
        "session_id": session.id,
        "next_question": last_q,
        "progress": {"answered": len(session.filled_keys), "total": total},
        "completed": session.done,
        "persona_id": session.persona_id,
        "persona_status": persona_status_value,
    }


@router.post("/interviews/sessions/{session_id}/complete")
def complete_session(session_id: str):
    """finalize 는 이미 대화 흐름(확인 게이트 또는 skip_confirmation) 안에서 끝난다 —
    이 엔드포인트는 그 최종 상태를 조회하는 용도다."""
    session = storage.interviews.get(session_id)
    if session is None:
        raise HTTPException(404, "인터뷰 세션 없음")
    if not session.done:
        raise HTTPException(409, "세션이 아직 완료되지 않았습니다 — 대화를 이어서 완료해 주세요")
    persona = storage.personas.get(session.persona_id) if session.persona_id else None
    status = interview.persona_status_for(persona)[0]
    return {
        "persona_id": session.persona_id,
        "persona_status": status,
        "persona_version": persona.version if persona else None,
    }
