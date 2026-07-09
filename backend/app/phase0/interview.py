"""Phase 0 — 보호자 온보딩: Mi:dm 챗봇 인터뷰 → 페르소나 DB.

흐름: 보호자 → KT Mi:dm 챗봇 (질문/답변 반복) → 인터뷰 종료 시 Persona 생성·저장.
"""

from app import storage
from app.llm import midm
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, InterviewSession, Persona, PersonaType


def start_interview(guardian_name: str) -> InterviewSession:
    session = InterviewSession(id=storage.new_id(), guardian_name=guardian_name)
    question, _ = midm.interview_turn(0)
    session.messages.append({"role": "assistant", "text": question})
    storage.interviews.save(session.id, session)
    return session


def answer_interview(session_id: str, user_text: str) -> InterviewSession:
    """보호자 답변 저장 후 다음 질문 진행. 마지막 질문이면 세션 종료."""
    session = storage.interviews.get(session_id)
    if session is None:
        raise KeyError(f"인터뷰 세션 없음: {session_id}")
    if session.done:
        return session

    session.messages.append({"role": "user", "text": user_text})
    turn = sum(1 for m in session.messages if m["role"] == "assistant")
    question, done = midm.interview_turn(turn)
    session.messages.append({"role": "assistant", "text": question})
    session.done = done
    storage.interviews.save(session.id, session)
    return session


def register_persona(
    session_id: str | None,
    *,
    name: str,
    age: int,
    ptype: PersonaType,
    home: GeoPoint,
    attraction_points: list[AttractionPoint] | None = None,
    behavior_notes: list[str] | None = None,
) -> Persona:
    """페르소나 등록.

    백본 단계에서는 구조화 필드를 직접 받는다. Mi:dm 연동 후에는
    인터뷰 대화 로그에서 이 필드들을 자동 추출하도록 확장.
    """
    persona = Persona(
        id=storage.new_id(),
        type=ptype,
        name=name,
        age=age,
        home=home,
        attraction_points=attraction_points or [],
        behavior_notes=behavior_notes or [],
    )
    storage.personas.save(persona.id, persona)

    if session_id:
        session = storage.interviews.get(session_id)
        if session is not None:
            session.persona_id = persona.id
            session.done = True
            storage.interviews.save(session.id, session)
    return persona
