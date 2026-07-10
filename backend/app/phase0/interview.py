"""Phase 0 — 보호자 온보딩: 적응형 엘리시테이션 → 페르소나 초안.

매 턴 루프(노트 설계):
  1) 보호자 답변 정제(safety.sanitize_input, 개인정보 마스킹)
  2) 직전 겨냥 슬롯에 대해 Mi:dm 추출 → 충족 슬롯·누적 초안 갱신
  3) 히스토리-어웨어 검색으로 다음 슬롯 랭킹(retrieval) — '지금 화제' 관련 슬롯 선택
  4) Mi:dm 이 그 슬롯을 존댓말 질문으로 문장화 → 2층 가드레일 통과(safety)
  5) 남은 tier1~2 슬롯이 없으면 종료(초안 완성)

'첫 질문은 하드코딩'(identity) — 여기서 유형(persona_type)을 확정해야 이후 유형별
슬롯을 필터링할 수 있다. 초안(draft_*)은 Phase 2 이전 지오코딩 단계에서 Persona 로 확정.
"""

from __future__ import annotations

from app import storage
from app.llm import midm
from app.phase0 import retrieval, safety
from app.phase0.retrieval import get_embedder
from app.phase0.slots import SlotSpec, slot_by_key, slots_for
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, InterviewSession, Persona, PersonaType

_EMB = get_embedder()

# 피벗(꼬리질문) 판정은 검색의 PIVOT_SIM 과 일치 — 강한 신호일 때만 '되받아 확인' 톤.
FOLLOWUP_SIM = retrieval.PIVOT_SIM
# 최대 질문 수 안전장치 (무한 루프 방지).
MAX_QUESTIONS = 14

_IDENTITY = slot_by_key("identity")

# 유형 키워드 폴백 (Mi:dm 추출 실패/스텁 시).
_TYPE_HINTS = [
    (PersonaType.dementia, ("치매", "알츠하이머", "어르신", "노인")),
    (PersonaType.intellectual_disability, ("지적장애", "지적 장애", "발달장애")),
    (PersonaType.child, ("자폐", "아동", "아이", "아들", "딸", "어린이", "초등")),
]


def _detect_type(text: str) -> PersonaType | None:
    for ptype, hints in _TYPE_HINTS:
        if any(h in text for h in hints):
            return ptype
    return None


def _user_turns(session: InterviewSession) -> list[str]:
    return [m["text"] for m in session.messages if m["role"] == "user"]


_TYPE_KO = {
    PersonaType.dementia: "치매 어르신",
    PersonaType.child: "아동",
    PersonaType.intellectual_disability: "지적장애",
}

_AFFIRM = ("네", "예", "맞아", "맞습니다", "맞어", "응", "좋아", "그래", "등록", "확인", "ok", "yes")


def _is_affirmative(text: str) -> bool:
    t = text.strip().lower()
    if "아니" in t or "틀" in t or "빼" in t or "수정" in t:
        return False
    return any(t.startswith(a) or a in t for a in _AFFIRM)


# 요약에 보여줄 최대 개수 — 전부 나열하지 않고 핵심만 큐레이션(데이터는 전부 저장됨).
_MAX_PLACES = 3
_MAX_BEHAVIORS = 2


def build_summary(session: InterviewSession) -> str:
    """수집 내용의 '핵심만' 깔끔히 정리 + 확인 요청. (전부 나열 금지)

    대상자·집·핵심 장소는 예측의 뼈대라 항상, 행동은 가장 중요한 1~2개만.
    나머지는 '외 N개 저장' 으로 표시(데이터 자체는 draft_* 에 모두 남는다).
    """
    f = session.draft_fields
    lines: list[str] = ["📋 이렇게 등록할게요. 핵심만 정리했어요.", ""]

    who: list[str] = []
    if f.get("name"):
        who.append(str(f["name"]))
    if f.get("age"):
        who.append(f"{f['age']}세")
    who.append(_TYPE_KO.get(session.persona_type, "—"))
    lines.append(f"• 대상자: {', '.join(who)}")

    if f.get("home"):
        lines.append(f"• 지내시는 곳: {f['home']}")

    places = session.draft_attractions
    if places:
        lines.append("• 가시려 할 만한 곳:")
        for ap in places[:_MAX_PLACES]:
            area = ap.get("area_text")
            lines.append(f"   - {ap.get('label', '')}{f' ({area})' if area else ''}")
        if len(places) > _MAX_PLACES:
            lines.append(f"   …외 {len(places) - _MAX_PLACES}곳 저장")

    behaviors = session.draft_behaviors
    if behaviors:
        lines.append("• 특히 주의할 점:")
        for note in behaviors[:_MAX_BEHAVIORS]:
            lines.append(f"   - {note}")
        if len(behaviors) > _MAX_BEHAVIORS:
            lines.append(f"   …외 {len(behaviors) - _MAX_BEHAVIORS}가지 저장")

    lines.append("")
    lines.append("등록하신 정보가 이게 맞나요? 틀리거나 빠진 부분이 있으면 편하게 말씀해 주세요.")
    return "\n".join(lines)


def start_interview(guardian_name: str, persona_type: PersonaType | None = None) -> InterviewSession:
    session = InterviewSession(
        id=storage.new_id(), guardian_name=guardian_name, persona_type=persona_type
    )
    session.messages.append({"role": "assistant", "text": _IDENTITY.question})
    session.prev_target_key = _IDENTITY.key
    storage.interviews.save(session.id, session)
    return session


def _apply_extraction(session: InterviewSession, prev_slot: SlotSpec, extracted: dict) -> None:
    session.draft_fields.update(extracted.get("fields", {}) or {})
    for ap in extracted.get("attraction_points", []) or []:
        if ap not in session.draft_attractions:
            session.draft_attractions.append(ap)
    for note in extracted.get("behavior_notes", []) or []:
        if note not in session.draft_behaviors:
            session.draft_behaviors.append(note)
    if extracted.get("slot_filled") and prev_slot.key not in session.filled_keys:
        session.filled_keys.append(prev_slot.key)
        session.asked_counts.pop(prev_slot.key, None)   # 채워지면 반복 페널티 해제


def _next_slot(session: InterviewSession) -> tuple[SlotSpec, bool] | None:
    """검색으로 다음 슬롯 + 꼬리질문 여부. 후보 없으면 None."""
    ranked, _ = retrieval.rank_next_slots(
        session.persona_type, _user_turns(session), set(session.filled_keys), _EMB,
        top_k=5, asked_counts=session.asked_counts,
    )
    if not ranked:
        return None
    top = ranked[0]
    return top.slot, top.similarity >= FOLLOWUP_SIM


MIN_TIER2 = 3   # 종료에 필요한 최소 tier2(성격·신체) 슬롯 수


def _is_complete(session: InterviewSession) -> bool:
    """종료 판정: tier1(경로·장소) 전부 + tier2 최소 MIN_TIER2 충족.

    모든 슬롯을 다 채우려 하면 인터뷰가 너무 길어진다. 예측의 뼈대(장소)는
    빠짐없이, 스타일 보정(성격·신체)은 핵심 몇 개만 확보되면 요약으로 넘어간다.
    """
    filled = set(session.filled_keys)
    slots = slots_for(session.persona_type)
    tier1_done = all(s.key in filled for s in slots if s.tier.value == 1)
    tier2_done = sum(1 for s in slots if s.tier.value == 2 and s.key in filled)
    return tier1_done and tier2_done >= MIN_TIER2


def answer_interview(session_id: str, user_text: str) -> InterviewSession:
    """보호자 답변 반영 → 다음 질문. 핵심 슬롯이 다 차거나 상한 도달 시 종료."""
    session = storage.interviews.get(session_id)
    if session is None:
        raise KeyError(f"인터뷰 세션 없음: {session_id}")
    if session.done:
        return session

    # 요약 확인 대기 중이면 '네/정정'만 처리하고 리턴
    if session.awaiting_confirmation:
        return _handle_confirmation(session, safety.sanitize_input(user_text))

    clean = safety.sanitize_input(user_text)
    session.messages.append({"role": "user", "text": clean})

    # 1) 직전 겨냥 슬롯 추출
    prev_slot = slot_by_key(session.prev_target_key) if session.prev_target_key else None
    if prev_slot is not None:
        extracted = midm.extract_answer(prev_slot, session.messages)
        _apply_extraction(session, prev_slot, extracted)

    # 2) 유형 확정 (identity 턴). 미확정이면 유형부터 다시 묻는다.
    if session.persona_type is None:
        session.persona_type = (
            _detect_type(clean)
            or _to_type(session.draft_fields.get("type"))
        )
        if session.persona_type is None:
            q = "어떤 상황이신지 한 번만 더 알려주세요 — 치매 어르신, 아동, 지적장애 중 어디에 해당하시나요?"
            session.messages.append({"role": "assistant", "text": q})
            session.prev_target_key = _IDENTITY.key
            storage.interviews.save(session.id, session)
            return session

    # 3) 종료 판정
    n_questions = sum(1 for m in session.messages if m["role"] == "assistant")
    nxt = _next_slot(session)
    if nxt is None or _is_complete(session) or n_questions >= MAX_QUESTIONS:
        # 종료 대신 '요약 → 확인' 단계로 진입
        session.awaiting_confirmation = True
        session.messages.append({"role": "assistant", "text": build_summary(session)})
        storage.interviews.save(session.id, session)
        return session

    # 4) 다음 슬롯 문장화 + 가드레일
    target, is_followup = nxt
    raw_q = midm.phrase_question(
        session.persona_type, target, is_followup, session.messages, known=session.draft_fields
    )
    question, _fallback = safety.guard_question(raw_q, target, _EMB)

    session.messages.append({"role": "assistant", "text": question})
    session.prev_target_key = target.key
    session.asked_counts[target.key] = session.asked_counts.get(target.key, 0) + 1
    storage.interviews.save(session.id, session)
    return session


def _handle_confirmation(session: InterviewSession, clean: str) -> InterviewSession:
    """요약 확인 응답 처리: 긍정→등록 완료 / 정정→관련 슬롯 반영 후 재요약."""
    session.messages.append({"role": "user", "text": clean})

    if _is_affirmative(clean):
        session.awaiting_confirmation = False
        session.done = True
        session.messages.append({
            "role": "assistant",
            "text": "확인 감사합니다. 이 내용으로 프로필을 등록할게요. 🙏",
        })
        storage.interviews.save(session.id, session)
        return session

    # 정정: 발화와 가장 관련있는 슬롯으로 재추출해 반영 → 다시 요약
    ranked, _ = retrieval.rank_next_slots(
        session.persona_type, [clean], set(), _EMB, top_k=1
    )
    if ranked:
        ext = midm.extract_answer(ranked[0].slot, session.messages)
        _apply_extraction(session, ranked[0].slot, ext)
    session.messages.append({"role": "assistant", "text": build_summary(session)})
    storage.interviews.save(session.id, session)
    return session


def _to_type(value) -> PersonaType | None:
    try:
        return PersonaType(value) if value else None
    except ValueError:
        return None


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
    """페르소나 등록 (구조화 필드 직접 입력).

    인터뷰 초안(draft_*)의 area_text 를 좌표로 바꾸는 지오코딩 단계가 붙으면
    이 함수를 통해 확정 Persona 를 만든다. (지오코딩은 별도 TODO.)
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
