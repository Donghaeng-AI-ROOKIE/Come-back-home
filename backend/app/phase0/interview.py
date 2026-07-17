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

from datetime import datetime, timedelta

from app import storage
from app.llm import midm
from app.phase0 import retrieval, safety
from app.geo.geocode import get_geocoder, to_attraction_points
from app.phase0.retrieval import get_embedder
from app.phase0.slots import SlotSpec, slot_by_key, slots_for
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, InterviewSession, Persona, PersonaType

import re
import threading

_EMB = get_embedder()

# 피벗(꼬리질문) 판정은 검색의 PIVOT_SIM 과 일치 — 강한 신호일 때만 '되받아 확인' 톤.
FOLLOWUP_SIM = retrieval.PIVOT_SIM
# 절대 백스톱(모든 슬롯 소진/충족으로 자연 종료가 먼저 걸린다). 유형별 슬롯×시도 상한 위.
MAX_QUESTIONS = 40

_IDENTITY = slot_by_key("identity")

# 유형 키워드 폴백 (Mi:dm 추출 실패/스텁 시).
# 축 고도화(2026-07): 발달장애 세트가 자폐를 포함 — '자폐'는 child 가 아니라
# intellectual_disability 로 라우팅한다. 아동 특화 슬롯 세트는 제외됐지만
# child 유형 자체는 타 Phase 호환을 위해 폴백으로 남는다(공통 슬롯만 받음).
_TYPE_HINTS = [
    (PersonaType.dementia, ("치매", "알츠하이머", "어르신", "노인")),
    (PersonaType.intellectual_disability,
     ("지적장애", "지적 장애", "발달장애", "발달 장애", "자폐")),
    (PersonaType.child, ("아동", "아이", "아들", "딸", "어린이", "초등")),
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
        age_num = re.sub(r"[^0-9]", "", str(f["age"]))   # "78세" → "78" (중복 '세' 방지)
        who.append(f"{age_num}세" if age_num else str(f["age"]))
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


def _norm(s: str) -> str:
    return re.sub(r"[\s()]+", "", str(s or ""))


def _apply_extraction(
    session: InterviewSession, prev_slot: SlotSpec, extracted: dict,
    *, overwrite: bool = False, utterance: str = "",
) -> None:
    # 필드는 first-wins — 한 번 정해진 name/age/home/type 을 이후 답변이 덮어쓰지 못하게.
    # (특히 현재 집을 과거 거주지 답변이 덮어쓰던 버그 방지.)
    # 단 확인 게이트의 '정정' 발화는 보호자가 명시적으로 고치는 것 — overwrite=True 로
    # 덮어쓴다. (라이브 실측 버그: 요약 후 나이 정정이 first-wins 에 막혀 무시됨.)
    for k, v in (extracted.get("fields", {}) or {}).items():
        if v:
            if overwrite:
                session.draft_fields[k] = v
            else:
                session.draft_fields.setdefault(k, v)
    # 끌림점 — 정규화한 label/area 기준 중복 제거(정릉시장 poi/address 중복 방지).
    seen = {(_norm(a.get("label")), _norm(a.get("area_text"))) for a in session.draft_attractions}
    for ap in extracted.get("attraction_points", []) or []:
        key = (_norm(ap.get("label")), _norm(ap.get("area_text")))
        if key not in seen:
            seen.add(key)
            session.draft_attractions.append(ap)
    got_note = False
    for note in extracted.get("behavior_notes", []) or []:
        if note not in session.draft_behaviors:
            session.draft_behaviors.append(note)
            # 어느 슬롯 답변에서 나온 노트인지 기록 → finalize 에서 축별 근거로 묶임
            session.slot_notes.setdefault(prev_slot.key, []).append(note)
            got_note = True
    # 근거를 낳은 답변은 원문도 보존 — 노트는 Mi:dm 재서술이라 정보가 깎이고,
    # 축 점수 채점(axis_scoring)은 원발화 인용 검증을 환각 필터로 쓴다.
    # 장소 추출물만 나온 답변도 보존(자전적기억·선호대상 축 근거 공백 완화).
    if utterance and (got_note or extracted.get("attraction_points")
                      or extracted.get("slot_filled")):
        quotes = session.slot_quotes.setdefault(prev_slot.key, [])
        if utterance not in quotes:
            quotes.append(utterance)
    if extracted.get("slot_filled") and prev_slot.key not in session.filled_keys:
        session.filled_keys.append(prev_slot.key)
        session.asked_counts.pop(prev_slot.key, None)   # 채워지면 반복 페널티 해제


# 슬롯 하나를 이만큼 물어도 안 채워지면 '소진'으로 보고 넘어간다(무한루프 방지).
MAX_ASKS_PER_SLOT = 2


def _exhausted_keys(session: InterviewSession) -> set[str]:
    return {k for k, c in session.asked_counts.items() if c >= MAX_ASKS_PER_SLOT}


def _blocked_keys(session: InterviewSession) -> set[str]:
    """더 물을 필요 없는 슬롯 = 채워짐 ∪ 소진됨."""
    return set(session.filled_keys) | _exhausted_keys(session)


def _next_slot(session: InterviewSession) -> tuple[SlotSpec, bool] | None:
    """검색으로 다음 슬롯 + 꼬리질문 여부. 채움/소진된 슬롯은 제외. 없으면 None."""
    ranked, _ = retrieval.rank_next_slots(
        session.persona_type, _user_turns(session), _blocked_keys(session), _EMB,
        top_k=5, asked_counts=session.asked_counts,
    )
    if not ranked:
        return None
    top = ranked[0]
    return top.slot, top.similarity >= FOLLOWUP_SIM


def _is_complete(session: InterviewSession) -> bool:
    """종료 판정: 유형-유효 슬롯이 **전부 채워지거나 소진**되면 끝.

    온보딩은 응급(골든타임)이 아니라 사전 등록이므로, 개인화를 위해 페르소나
    버퍼(슬롯)를 최대한 다 채운다. 안 채워지는 슬롯은 MAX_ASKS_PER_SLOT 만큼
    시도 후 소진 처리해 무한루프를 막는다.
    """
    blocked = _blocked_keys(session)
    return all(s.key in blocked for s in slots_for(session.persona_type))


def answer_interview(session_id: str, user_text: str) -> InterviewSession:
    """보호자 답변 반영 → 다음 질문. 핵심 슬롯이 다 차거나 상한 도달 시 종료."""
    session = storage.interviews.get(session_id)
    if session is None:
        raise KeyError(f"인터뷰 세션 없음: {session_id}")
    if session.done:
        return session
    # 개인정보 파기 — 방치 세션 TTL(privacy.purge_expired)의 기준 시각 갱신
    session.last_active_at = datetime.now()

    # 요약 확인 대기 중이면 '네/정정'만 처리하고 리턴
    if session.awaiting_confirmation:
        return _handle_confirmation(session, safety.sanitize_input(user_text))

    clean = safety.sanitize_input(user_text)
    session.messages.append({"role": "user", "text": clean})

    # 1) 직전 겨냥 슬롯 추출
    prev_slot = slot_by_key(session.prev_target_key) if session.prev_target_key else None
    if prev_slot is not None:
        extracted = midm.extract_answer(prev_slot, session.messages)
        _apply_extraction(session, prev_slot, extracted, utterance=clean)

    # 2) 유형 확정 (identity 턴). 미확정이면 유형부터 다시 묻는다.
    if session.persona_type is None:
        session.persona_type = (
            _detect_type(clean)
            or _to_type(session.draft_fields.get("type"))
        )
        if session.persona_type is None:
            q = "어떤 상황이신지 한 번만 더 알려주세요 — 치매 어르신과 발달장애가 있는 분 중 어디에 해당하시나요?"
            session.messages.append({"role": "assistant", "text": q})
            session.prev_target_key = _IDENTITY.key
            storage.interviews.save(session.id, session)
            return session

    # 2.5) 이름 다음 필수 앵커 = 현재 집. 검색에 맡기지 않고 명시적으로 먼저 묻는다
    #      (과거 거주지 답변이 현재 집을 덮어쓰던 혼동 방지 + 수색 원점 정확도).
    if "home" not in session.filled_keys and session.asked_counts.get("home", 0) == 0:
        home_slot = slot_by_key("home")
        raw_q = midm.phrase_question(
            session.persona_type, home_slot, False, session.messages, known=session.draft_fields
        )
        question, _fb = safety.guard_question(raw_q, home_slot, _EMB)
        session.messages.append({"role": "assistant", "text": question})
        session.prev_target_key = "home"
        session.asked_counts["home"] = 1
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
        try:
            finalize_persona(session)   # draft → 지오코딩 → 확정 Persona 저장
            msg = "확인 감사합니다. 이 내용으로 프로필을 등록했어요. 🙏"
        except ValueError as e:
            session.awaiting_confirmation = False
            session.done = True
            msg = f"등록 중 문제가 있었어요({e}). 집 위치를 한 번만 더 확인해 주세요."
        session.messages.append({"role": "assistant", "text": msg})
        storage.interviews.save(session.id, session)
        return session

    # 정정: 발화와 가장 관련있는 슬롯으로 재추출해 반영 → 다시 요약.
    # 정정은 명시적 수정 의사이므로 first-wins 를 넘어 덮어쓴다 (overwrite=True).
    ranked, _ = retrieval.rank_next_slots(
        session.persona_type, [clean], set(), _EMB, top_k=1
    )
    if ranked:
        ext = midm.extract_answer(ranked[0].slot, session.messages)
        _apply_extraction(session, ranked[0].slot, ext, overwrite=True, utterance=clean)
    session.messages.append({"role": "assistant", "text": build_summary(session)})
    storage.interviews.save(session.id, session)
    return session


def _to_type(value) -> PersonaType | None:
    try:
        return PersonaType(value) if value else None
    except ValueError:
        return None


_GEO = get_geocoder(use_nominatim=True)   # 카카오 → nominatim → gazetteer


def _parse_age(value) -> int:
    if isinstance(value, int):
        return value
    m = re.search(r"\d+", str(value or ""))
    return int(m.group()) if m else 0


_SCORING_IN_PROGRESS = "채점 진행 중(백그라운드)"   # 값 그대로 유지 — 기존 테스트가 이 문자열을 검사
_SCORING_DONE = "채점 완료"
_SCORING_ERROR = "채점 실패"
_SCORING_SKIPPED = "채점 생략(스텁)"

# ensure_axis_scores 의 체크(진행중 표시 확인)-후-셋(표시 저장)을 원자화한다.
# 락 없이는 근접 시각의 중복 호출(같은 사람에 대한 신고 2건 등)이 둘 다 통과해
# 채점을 이중으로 걸 수 있다(이중 EXAONE 쿼터 소모) — 셀프리뷰 발견, 2026-07-17.
_scoring_trigger_lock = threading.Lock()


def _in_progress_marker(now: datetime) -> dict:
    return {"status": _SCORING_IN_PROGRESS, "started_at": now.isoformat()}


def _is_stale(report: dict, now: datetime) -> bool:
    """IN_PROGRESS 마커가 죽은 채점(스레드 하드킬·서버 재시작)으로 볼 수 있는지.

    시작 시각이 없거나 파싱 불가한 마커도 stale 취급(레거시·오염 방어).
    임계값은 살아있는 채점의 최악(healthy-slow)에 마진을 둔 값 — 상세 근거는
    config.py의 axis_scoring_stale_seconds 주석 참고.
    """
    from app.config import settings
    ts = report.get("started_at")
    if not ts:
        return True
    try:
        started = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return True
    return now - started > timedelta(seconds=settings.axis_scoring_stale_seconds)


def _start_scoring(persona_id: str, *, force_async: bool = False) -> None:
    """설정에 따라 동기/비동기로 채점 실행 (finalize·백필 공용).

    force_async=True 는 골든타임 경로(신고 접수 백필) 전용 — AXIS_SCORING_ASYNC
    설정값과 무관하게 항상 백그라운드로 돌려, 그 설정이 언젠가 off 로 바뀌더라도
    신고 접수 응답이 EXAONE 채점 때문에 블로킹되지 않게 한다(셀프리뷰 발견).
    """
    from app.config import settings
    if force_async or settings.axis_scoring_async:
        threading.Thread(target=_score_and_save, args=(persona_id,), daemon=True).start()
    else:
        _score_and_save(persona_id)


def ensure_axis_scores(persona_id: str | None) -> None:
    """미채점 persona 백필 — 점수 소비 직전(실종 신고 접수)의 마지막 채점 기회.

    비동기 채점은 서버 재시작·EXAONE 장애로 유실되면 영구 미채점이 된다.
    점수가 비어 있는데 근거는 있는 persona 를 만나면 채점을 다시 건다.
    진행 중 표시가 있으면 중복 실행하지 않는다(이중 채점·이중 쿼터 방지 — 락으로 보호).
    단, 그 표시가 stale(채점 스레드가 죽어 마커만 남음)이면 재시도한다.
    완료(all-F 포함) 표시가 있으면 재채점하지 않는다 — 입력이 안 바뀌었는데 매 신고마다
    다시 채점하는 건 낭비다(EXAONE 은 temp 0 에서도 비결정성이 실측돼 결과가 항상
    똑같이 재현된다는 보장은 없지만, 그렇다고 매번 다시 돌릴 근거도 아니다).
    신고 접수(골든타임) 경로에서만 불리므로 항상 강제 비동기로 채점을 건다.
    """
    from app.config import settings
    if not (persona_id and settings.axis_scoring_enabled):
        return
    with _scoring_trigger_lock:
        persona = storage.personas.get(persona_id)
        if persona is None or persona.axis_scores:
            return
        if not (persona.axis_quotes or persona.axis_evidence):
            return   # 채점할 근거 자체가 없음 (구조화 직접 등록 페르소나 등)
        report = persona.axis_scoring_report
        status = report.get("status")
        now = datetime.now()
        if status == _SCORING_DONE:
            return   # all-F 로 끝난 완료도 재채점 안 함 (입력 불변 — 매번 다시 돌릴 이유 없음)
        if status == _SCORING_IN_PROGRESS and not _is_stale(report, now):
            return   # 아직 신선한 진행 중 표시 — finalize 가 건 채점이 도는 중
        persona.axis_scoring_report = _in_progress_marker(now)
        storage.personas.save(persona.id, persona)
    _start_scoring(persona.id, force_async=True)


def _score_and_save(persona_id: str) -> None:
    """축 점수 채점 후 Persona 재저장 — 비동기 모드에서는 백그라운드 스레드로 돈다.

    저장소에서 새로 읽어 스레드 간 객체 공유를 피한다. 실패는 리포트로만 남긴다
    (채점 실패가 이미 확정된 등록을 되돌리면 안 됨). 완료·실패 각각 상태와
    시각을 리포트에 남겨 ensure_axis_scores 가 재시도 여부를 판단할 수 있게 한다.
    """
    from app.phase0 import axis_scoring
    persona = storage.personas.get(persona_id)
    if persona is None:
        return
    try:
        scores, report = axis_scoring.score_axes_for(persona)
        if "skipped" in report:
            report = {**report, "status": _SCORING_SKIPPED}
        else:
            report = {**report, "status": _SCORING_DONE, "scored_at": datetime.now().isoformat()}
        persona.axis_scores = scores
        persona.axis_scoring_report = report
    except Exception as e:  # noqa: BLE001
        persona.axis_scoring_report = {
            "status": _SCORING_ERROR,
            "error": f"{type(e).__name__}: {e}",
            "failed_at": datetime.now().isoformat(),
        }
    # 채점(최대 수십 초) 도중 보호자가 삭제를 요청했을 수 있다 — 삭제된 persona 를
    # 되살리지 않도록 저장 직전 재확인(개인정보 파기 경합 방지, 셀프리뷰 발견).
    if storage.personas.get(persona_id) is None:
        return
    storage.personas.save(persona_id, persona)


def finalize_persona(session: InterviewSession, geocoder=None) -> Persona:
    """확인 완료된 인터뷰 초안(draft_*) → 지오코딩 → 확정 Persona 저장.

    home 을 먼저 좌표화(필수)하고, 그 좌표를 앵커로 끌림점을 근접 검색한다.
    home 미확보·좌표화 실패 시 ValueError — 끌림점 폴백은 하지 않는다:
    Mi:dm 이 home 을 끌림점으로 오추출한 라이브 케이스에서 과거 거주지가
    무경고로 수색 원점이 되던 치명 버그 (원점 오염). ValueError 는 확인 게이트가
    받아 보호자에게 집 위치를 재질문한다.
    geocoder 미지정 시 모듈 기본(_GEO, 카카오 체인) 사용 — 테스트는 gazetteer 주입.
    """
    geo = geocoder or _GEO
    f = session.draft_fields

    # ① home 먼저 — 수색 원점이자 끌림점 근접 검색의 앵커
    home_res = geo.locate(f["home"]) if f.get("home") else None
    if home_res is None:
        raise ValueError("집 위치 미확보 — 집 주소/동네를 다시 확인해 주세요")
    home = home_res.point

    # ② 끌림점 — home 앵커로 반경 내 근접 검색 (전국 키워드 오검색 차단)
    points, _unresolved = to_attraction_points(session.draft_attractions, geo, anchor=home)
    # 중복 제거 — 같은 이름(또는 같은 좌표)이 poi/address 로 두 번 잡히면 더 정밀한 것만.
    _rank = {"poi": 0, "address": 1, "dong": 2, "approx": 3, "unknown": 4}
    uniq: dict[object, AttractionPoint] = {}
    for p in points:
        key = _norm(p.label) or (round(p.location.lat, 4), round(p.location.lng, 4))
        if key not in uniq or _rank.get(p.precision, 9) < _rank.get(uniq[key].precision, 9):
            uniq[key] = p
    points = list(uniq.values())

    # ③ 축별 근거 — 슬롯별 노트·원발화를 축 DB 필드명으로 묶는다(축 점수 컴파일 입력)
    axis_evidence: dict[str, list[str]] = {}
    for key, notes in session.slot_notes.items():
        spec = slot_by_key(key)
        if spec is not None and spec.axis_field:
            axis_evidence.setdefault(spec.axis_field, []).extend(notes)
    axis_quotes: dict[str, list[str]] = {}
    for key, quotes in session.slot_quotes.items():
        spec = slot_by_key(key)
        if spec is not None and spec.axis_field:
            axis_quotes.setdefault(spec.axis_field, []).extend(quotes)

    persona = Persona(
        id=storage.new_id(),
        type=session.persona_type,
        name=str(f.get("name") or "미상"),
        age=_parse_age(f.get("age")),
        home=home,
        attraction_points=points,
        behavior_notes=list(session.draft_behaviors),
        axis_evidence=axis_evidence,
        axis_quotes=axis_quotes,
    )

    # ④ 축 점수 컴파일 — 기능 플래그(기본 off, 회의에서 B×P1 채택 시 켠다).
    # 확정(보호자 "네") 이후에만 채점하며, 기본은 비동기: 채점(EXAONE 21회,
    # 실측 40초~1분)이 마지막 확인 응답을 막지 않게 등록을 먼저 저장하고
    # 점수는 백그라운드로 채운다. 실패는 리포트에만 남긴다(등록을 되돌리지 않음).
    from app.config import settings
    if settings.axis_scoring_enabled:
        persona.axis_scoring_report = _in_progress_marker(datetime.now())

    storage.personas.save(persona.id, persona)
    session.persona_id = persona.id
    session.done = True
    session.awaiting_confirmation = False
    storage.interviews.save(session.id, session)

    if settings.axis_scoring_enabled:
        _start_scoring(persona.id)
    return persona


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
