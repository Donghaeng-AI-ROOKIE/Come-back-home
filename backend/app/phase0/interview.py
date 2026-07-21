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
from app.geo.geocode import coerce_evidence, get_geocoder, to_attraction_points
from app.phase0.retrieval import get_embedder
from app.phase0.slots import Axis, Sink, SlotSpec, slot_by_key, slots_for
from app.schemas.common import GeoPoint
from app.schemas.persona import (
    AttractionPoint,
    InterviewSession,
    Persona,
    PersonaType,
    PreferredTarget,
)

import re
import threading

_EMB = get_embedder()

# 피벗(꼬리질문) 판정은 검색의 PIVOT_SIM 과 일치 — 강한 신호일 때만 '되받아 확인' 톤.
FOLLOWUP_SIM = retrieval.PIVOT_SIM
# 절대 백스톱(모든 슬롯 소진/충족으로 자연 종료가 먼저 걸린다). 유형별 슬롯×시도 상한 위.
MAX_QUESTIONS = 40

_IDENTITY = slot_by_key("identity")

# 유형 키워드 폴백 (Mi:dm 추출 실패/스텁 시).
# 축 고도화(2026-07): 발달장애 세트가 자폐를 포함 — '자폐'는 intellectual_disability 로 라우팅한다.
_TYPE_HINTS = [
    (PersonaType.dementia, ("치매", "알츠하이머", "어르신", "노인")),
    (PersonaType.intellectual_disability,
     ("지적장애", "지적 장애", "발달장애", "발달 장애", "자폐")),
]


def _detect_type(text: str) -> PersonaType | None:
    for ptype, hints in _TYPE_HINTS:
        if any(h in text for h in hints):
            return ptype
    return None


def _user_turns(session: InterviewSession) -> list[str]:
    return [m["text"] for m in session.messages if m["role"] == "user"]


# ── Mi:dm 호출 래퍼 — 실패를 세션 플래그로 노출 ─────────────────────
# midm 폴백은 침묵한다(빈 추출·씨앗 질문). 그대로 두면 장애가 "이상한 반복
# 인터뷰"로만 체감되므로(라이브 실측 410), 카운터 증가를 세션에 기록해
# API 응답(llm_degraded)으로 드러낸다.


def _extract_tracked(session: InterviewSession, slot: SlotSpec) -> dict:
    before = midm.call_failures
    out = midm.extract_answer(slot, session.messages)
    if midm.call_failures > before:
        session.llm_call_failures += midm.call_failures - before
        session.llm_degraded = True
    return out


def _slot_collected(session: InterviewSession, slot: SlotSpec) -> list[str]:
    """이 슬롯에서 지금까지 확보한 사실 — 갭 기반 꼬리질문의 재료.

    노트(재서술) + 장소 라벨. 충족 기준(filled_when)과 나란히 프롬프트에 실려
    '아직 빈 부분'을 모델이 스스로 고르게 한다.

    장소 수집 슬롯(sink=attraction)은 **세션 전체에서 모인 장소를 전부** 공유한다
    — 장소는 어느 슬롯 답변에서 나왔든 같은 저장소(draft_attractions)로 가므로,
    슬롯별로 갈라 보면 "자주 가는 곳"을 이미 들었는데 또 묻는다(라이브 실측 7차:
    자전적 기억 턴에 나온 망원시장을 routine 질문이 모르고 재질문).
    """
    out = list(session.slot_notes.get(slot.key, []))
    labels = [str(a.get("label")) for a in session.draft_attractions if a.get("label")]
    if slot.sink == Sink.attraction:
        out += [f"장소: {lb}" for lb in labels]
    else:
        quotes = set(session.slot_quotes.get(slot.key, []))
        if quotes:
            out += [f"장소: {lb}" for lb in labels
                    if any(lb in q for q in quotes)]   # 이 슬롯 발화에서 나온 장소만
    return out


def _phrase_tracked(session: InterviewSession, slot: SlotSpec, is_followup: bool) -> str:
    before = midm.call_failures
    raw = midm.phrase_question(
        session.persona_type, slot, is_followup, session.messages,
        known=session.draft_fields, collected=_slot_collected(session, slot),
    )
    if midm.call_failures > before:
        session.llm_call_failures += midm.call_failures - before
        session.llm_degraded = True
    return raw


# ── 규칙 기반 최소 추출 폴백 (identity/home 전용) ────────────────────
# name/age/home 추출이 Mi:dm 단일 장애점이면 엔드포인트가 죽는 순간 등록 퍼널
# 전체가 실패한다(라이브 실측). 필수 3필드만 규칙으로 최후 방어한다.
# 행동·장소 슬롯은 규칙 오추출 위험이 커서 다루지 않는다(소진 처리로 넘어감).

_AGE_RE = re.compile(r"(\d{1,3})\s*(?:세|살)")
# 이름으로 오인하기 쉬운 호칭·관계어 — 후보에서 제외
_NAME_STOP = {"어머니", "아버지", "할머니", "할아버지", "할머", "할아버",
              "어르신", "아드", "보호자", "선생", "환자"}
_NAME_RES = [
    re.compile(r"(?:이름은|성함은|이름이|성함이)\s*([가-힣]{2,4})"),
    re.compile(r"([가-힣]{2,3})(?:님|씨)(?:이고|이며|이에요|예요|입니다|인데|이|,|\.|\s|$)"),
    re.compile(r"([가-힣]{2,4})(?:이라고|라고)\s*(?:하|부|해)"),
]
# 지오코딩 가능한 주소 표면 — "성북구 정릉동", "면목로 12" 수준까지
_HOME_RE = re.compile(
    r"((?:[가-힣]+(?:특별시|광역시|시|도)\s+)?(?:[가-힣]+(?:구|군|시)\s+)?"
    r"[가-힣0-9]+(?:동|읍|면|리)(?:\s*\d+(?:-\d+)?)?"
    r"|[가-힣0-9]+(?:로|길)\s*\d+(?:-\d+)?)"
)


def _valid_home_text(value) -> bool:
    """home 필드 값이 지오코딩을 시도할 만한 '장소 표현'인지 — 문장형 답 차단.

    라이브 실측(2026-07-17 2차): "주로 머무시는 곳이 어디신가요?"에 "집에 주로
    계세요"라고 답하자 그 문장이 통째로 home 에 저장돼 filled 처리됨. 주소 표면
    (_HOME_RE)이 있으면 통과, 없으면 서술어가 없는 짧은 명사구(랜드마크)만 허용.
    """
    t = str(value or "").strip()
    if not t or any(k in t for k in ("모르", "몰라", "글쎄")):
        return False
    if _HOME_RE.search(t):
        return True
    core = re.sub(r"(?:에|에서|이요|이에요|예요|입니다|이|가|은|는|요)\s*$", "", t)
    if re.search(r"(?:계세|계셔|살|다니|지내|있어|있으|해요|세요|어요|네요|니다)", core):
        return False
    return 2 <= len(core) <= 20


# 순수 무지 답변("모르겠다니까요") — 재질문해도 얻을 게 없다. 정보가 섞인 답
# ("잘 모르겠는데 사고가 난 적은 없으세요")은 길이 때문에 걸리지 않는다.
_IGNORANCE_RE = re.compile(r"^(?:잘\s*)?(?:모르|몰라)[가-힣\s.!?~]*$")


def _is_pure_ignorance(text: str) -> bool:
    t = text.strip()
    return len(t) <= 15 and bool(_IGNORANCE_RE.match(t))


# 부정 답변("딱히 없어요", "아니요") = '해당 없음'이라는 **유효한 답**.
# 라이브 실측(2026-07-17 4차): "딱히 없어요"를 무시하고 재질문 → "무슨 말인지
# 모르겠어요", "복용약 없다"는데 "약을 거르셨을 때…" 후속 질문까지 나옴.
_NEGATION_RE = re.compile(
    r"(아니요|아니에요|아뇨|없어요|없습니다|없는데요|없다고|없음|안\s*계세요|안\s*가세요|안\s*드세요)")


def _is_negative_answer(text: str) -> bool:
    t = text.strip()
    return len(t) <= 12 and bool(_NEGATION_RE.search(t))


def _rule_extract_fields(slot_key: str, text: str) -> dict:
    fields: dict = {}
    if slot_key == "identity":
        m = _AGE_RE.search(text)
        if m:
            fields["age"] = f"{m.group(1)}세"
        for pat in _NAME_RES:
            for cand in pat.findall(text):
                if cand not in _NAME_STOP:
                    fields["name"] = cand
                    break
            if "name" in fields:
                break
    elif slot_key == "home":
        m = _HOME_RE.search(text)
        if m:
            fields["home"] = m.group(1).strip()
    return fields


def _merge_rule_fallback(session: InterviewSession, prev_slot: SlotSpec,
                         extracted: dict, utterance: str) -> None:
    """identity/home 은 Mi:dm 이 빈손이어도 규칙으로 최소 추출 — LLM 추출이 우선."""
    if prev_slot.key not in ("identity", "home"):
        return
    fields = extracted.setdefault("fields", {})
    for k, v in _rule_extract_fields(prev_slot.key, utterance).items():
        fields.setdefault(k, v)
    # home 은 장소 표현일 때만 수용 — Mi:dm 이 문장형 답("집에 주로 계세요")을
    # 그대로 home 으로 뽑아 지오코딩 불가 값이 filled 되는 것을 차단.
    if prev_slot.key == "home" and fields.get("home") \
            and not _valid_home_text(fields["home"]):
        fields.pop("home")
        extracted["slot_filled"] = False
    # 필수 필드가 (세션 누적 기준으로) 확보되면 충족 처리 — 스텁·장애 모드에서
    # 같은 것을 무한 재질문하다 소진되는 것을 막는다.
    def _have(key: str) -> bool:
        return bool(session.draft_fields.get(key) or fields.get(key))

    if prev_slot.key == "home" and _have("home"):
        extracted["slot_filled"] = True
    if prev_slot.key == "identity" and _have("name") and _have("age"):
        extracted["slot_filled"] = True


_TYPE_KO = {
    PersonaType.dementia: "치매 어르신",
    PersonaType.intellectual_disability: "지적장애",
}

# 확인 게이트 긍정 판정 — 발화 '전체'가 이 단어들로만 이뤄져야 긍정.
# 부분 문자열 매칭 금지: "…백범로가 정확한 주소예요"의 '예'가 긍정으로 오판돼
# 정정이 그대로 등록되던 라이브 실측 버그(2026-07-17). 애매하면 정정 경로가
# 안전한 기본값이다(재추출 후 재요약만 하고 저장하지 않으므로).
_AFFIRM_WORDS = {
    "네", "예", "넵", "응", "어", "그래", "그럼", "네네", "예예",
    "맞아", "맞아요", "맞습니다", "맞네요", "맞어", "맞음",
    "좋아", "좋아요", "좋습니다", "괜찮아요", "괜찮습니다",
    "이대로", "그대로", "등록", "등록해줘", "등록해주세요", "등록해",
    "확인", "확인했어요", "확인했습니다", "진행해주세요", "진행해줘",
    "해주세요", "해줘", "주세요", "부탁해요", "부탁드려요", "부탁드립니다",
    "ok", "yes",
}
_CORRECTION_HINTS = ("아니", "틀", "빼", "수정", "변경", "바꿔", "바꾸",
                     "고쳐", "고치", "잘못", "말고", "대신", "추가")


def _is_affirmative(text: str) -> bool:
    t = re.sub(r"[,.!?~]+", " ", text.strip().lower())
    if any(h in t for h in _CORRECTION_HINTS):
        return False
    words = t.split()
    return bool(words) and all(w in _AFFIRM_WORDS for w in words)


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


# evidence 강도 순위 (낮을수록 강함) — 중복 언급 시 더 강한 근거로만 승격
_EVIDENCE_RANK = {"previous_missing_found": 0, "caregiver_report": 1, "mention_only": 2}

# 노트 품질 필터 — 라이브 실측(2026-07-17): Mi:dm 이 "잘 모르겠어요"를 노트로
# 복사하고, 답변에 없는 프롬프트 예시 문구("길 잃으면 계속 걷는 편")까지 노트로
# 만들어냈다. (1) 무지·거부 표현 차단, (2) 발화 근거 검증 — 노트의 내용 토큰이
# 답변·직전 질문에 하나도 없으면 환각으로 본다. 어휘가 전혀 겹치지 않는 정당한
# 의역을 잃을 수 있는 트레이드오프지만, 환각이 예측 입력을 오염하는 쪽이 더 나쁘다.
_NON_FACT = ("모르", "몰라", "글쎄", "무슨 말", "못 알아", "기억이 안", "기억 안")


def _is_informative_note(note: str, context: str) -> bool:
    if any(k in note for k in _NON_FACT):
        return False
    if not context.strip():
        return True   # 근거 검증 불가(직접 호출·테스트 경로) — 통과
    tokens = re.findall(r"[가-힣a-zA-Z0-9]{2,}", note)
    return any(tok in context for tok in tokens) if tokens else False


def _note_tokens(text: str) -> set[str]:
    return set(re.findall(r"[가-힣a-zA-Z0-9]{2,}", text))


# 유사 중복 판정 임계 — 어미만 다른 같은 사실("~편이 아님" vs "~편이 아니에요",
# 자카드 0.75)은 잡고, 다른 사실("자주 가세요" vs "가면 오래 계세요", 0.17)은 살린다.
_NOTE_DUP_JACCARD = 0.6


def _is_dup_note(note: str, seen: list[str]) -> bool:
    """토큰 자카드 기반 유사 중복 — 완전일치 비교는 어미 변형과 부분 재진술을
    놓쳐 같은 사실이 슬롯만 바꿔 쌓였다(라이브 실측 2026-07-17 3차)."""
    nt = _note_tokens(note)
    if not nt:
        return True
    for prev in seen:
        pt = _note_tokens(prev)
        if pt and len(nt & pt) / len(nt | pt) >= _NOTE_DUP_JACCARD:
            return True
    return False


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
    # 같은 장소가 더 강한 근거로 재언급되면(예: 나중 턴에 "거기서 발견됐어요")
    # evidence 만 승격 — 근거는 추출 직후가 아니면 복원 불가하므로 여기서 지켜야 한다.
    # 중복 키 = 라벨만 — (라벨, 지역) 쌍으로 보면 같은 장소가 지역 표기만 달리 재언급될 때
    # ("망원시장(망원시장)" vs "망원시장(망원동)") 두 번 쌓인다(라이브 실측 4차).
    # 같은 라벨의 서로 다른 실제 장소는 드물다고 보고 라벨 기준으로 합친다.
    by_key = {_norm(a.get("label")): a for a in session.draft_attractions}
    # 거주지 자체는 끌림점이 아니다 — home 답변("신수동에 거주하시고…")에서 Mi:dm 이
    # 거주 동네를 끌림점으로도 추출해 수색 원점이 중복 가중되던 실측(2026-07-17 7차).
    home_txt = _norm(str(session.draft_fields.get("home")
                         or extracted.get("fields", {}).get("home") or ""))
    for ap in extracted.get("attraction_points", []) or []:
        key = _norm(ap.get("label"))
        if not key:
            continue
        if home_txt and key in home_txt:
            continue
        # 이 답변이 나온 슬롯 — unfamiliarity 게이지 폴백 판단(작업4)의 origin_slot 원료.
        ap.setdefault("origin_slot", prev_slot.key)
        # 포함 관계 라벨("대흥역" vs "대흥역 2번 출구")도 같은 장소로 병합 (실측 5차).
        # 3자 미만 라벨은 오병합 위험("시장" ⊂ "망원시장")이 커서 정확 일치만.
        match = key if key in by_key else next(
            (k for k in by_key
             if (k in key and len(k) >= 3) or (key in k and len(key) >= 3)), None)
        if match is None:
            by_key[key] = ap
            session.draft_attractions.append(ap)
            continue
        kept = by_key[match]
        if _EVIDENCE_RANK.get(ap.get("evidence"), 9) < _EVIDENCE_RANK.get(kept.get("evidence"), 9):
            kept["evidence"] = ap["evidence"]
        if not kept.get("area_text") and ap.get("area_text"):
            kept["area_text"] = ap["area_text"]   # 지역 표기는 있는 쪽을 보존
        if not kept.get("origin_slot") and ap.get("origin_slot"):
            kept["origin_slot"] = ap["origin_slot"]   # 어느 슬롯에서 처음 나왔는지도 first-wins
    # 카테고리 선호 (좌표화 불가 — 지하철·자동문 등) — label 기준 중복 제거 + 근거 승격
    pref_by_label = {_norm(t.get("label")): t for t in session.draft_preferred}
    for tg in extracted.get("preferred_targets", []) or []:
        label = _norm(tg.get("label"))
        if not label:
            continue
        if label not in pref_by_label:
            pref_by_label[label] = tg
            session.draft_preferred.append(tg)
        elif _EVIDENCE_RANK.get(tg.get("evidence"), 9) < _EVIDENCE_RANK.get(pref_by_label[label].get("evidence"), 9):
            pref_by_label[label]["evidence"] = tg["evidence"]
    got_note = False
    last_q = next((m["text"] for m in reversed(session.messages)
                   if m["role"] == "assistant"), "")
    # 슬롯 무관 원노트 중복 차단 — 같은 사실("많이 배회하세요")이 겨냥 슬롯만 바꿔
    # 여러 번 저장되던 라이브 실측(2026-07-17 2차). 어미 변형·부분 재진술까지
    # 자카드로 잡는다(3차). profile 슬롯(identity/home)은 필드 수집 전용이라
    # 행동 노트를 받지 않는다 — "현재 거주지: 길 잃었을 때…" 오귀속 방지.
    seen_notes = [n for notes in session.slot_notes.values() for n in notes]
    notes_in = ([] if prev_slot.axis == Axis.profile
                else extracted.get("behavior_notes", []) or [])
    for note in notes_in:
        if _is_dup_note(note, seen_notes) \
                or not _is_informative_note(note, f"{utterance} {last_q}"):
            continue
        # '질문 요약: 답변 요약' 형태로 저장 — 슬롯 라벨이 질문 요약 역할.
        # (라이브 실측: 맥락 없는 답변 원문이 그대로 쌓여 무슨 질문의 답인지 알 수 없었음)
        tagged = f"{prev_slot.label}: {note}"
        if tagged not in session.draft_behaviors:
            session.draft_behaviors.append(tagged)
            # 축 채점(axis_scoring) 입력은 원노트 유지 — 라벨 접두가 근거를 오염하지 않게
            session.slot_notes.setdefault(prev_slot.key, []).append(note)
            seen_notes.append(note)
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


def _next_slot(
    session: InterviewSession, *, avoid_prev: bool = False
) -> tuple[SlotSpec, bool] | None:
    """검색으로 다음 슬롯 + 꼬리질문 여부. 채움/소진된 슬롯은 제외. 없으면 None.

    avoid_prev: 직전 답변이 빈손(추출 0)이었을 때 켠다 — 답변 어휘가 방금 물은
    슬롯과 유사해 피벗이 같은 슬롯을 곧바로 재선택하면 같은 질문 낭독이 된다
    (라이브 실측 Q5=Q6). 다른 슬롯을 먼저 소화하고, 직전 슬롯만 남았을 때만 허용.
    추출이 뭐라도 건졌을 때는 같은 슬롯 꼬리질문(파고들기)이 유효하므로 끄지 않는다.
    """
    blocked = _blocked_keys(session)
    avoid = (blocked | {session.prev_target_key}) \
        if (avoid_prev and session.prev_target_key) else blocked
    ranked, _ = retrieval.rank_next_slots(
        session.persona_type, _user_turns(session), avoid, _EMB,
        top_k=5, asked_counts=session.asked_counts,
    )
    if not ranked and avoid != blocked:
        ranked, _ = retrieval.rank_next_slots(
            session.persona_type, _user_turns(session), blocked, _EMB,
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

    # 1) 직전 겨냥 슬롯 추출 (+ identity/home 은 규칙 폴백으로 최후 방어)
    prev_slot = slot_by_key(session.prev_target_key) if session.prev_target_key else None
    got_something = True   # 이번 답에서 뭐라도 건졌나 — 빈손이면 직전 슬롯 재선택 회피
    if prev_slot is not None:
        extracted = _extract_tracked(session, prev_slot)
        _merge_rule_fallback(session, prev_slot, extracted, clean)
        got_something = bool(
            extracted.get("fields") or extracted.get("attraction_points")
            or extracted.get("preferred_targets") or extracted.get("behavior_notes")
            or extracted.get("slot_filled")
        )
        _apply_extraction(session, prev_slot, extracted, utterance=clean)
        # 순수 무지 답변("모르겠다니까요")이면 그 슬롯은 즉시 소진 — 같은 것을
        # 또 물어 보호자를 지치게 하지 않는다(라이브 실측 2026-07-17 2차).
        if _is_pure_ignorance(clean) and prev_slot.key not in session.filled_keys:
            session.asked_counts[prev_slot.key] = MAX_ASKS_PER_SLOT
        # 부정 답변("딱히 없어요")은 '해당 없음'으로 **충족** 처리 — 무지와 달리
        # 답을 받은 것이다. profile 슬롯(이름·집)은 부정으로 채울 수 없어 제외.
        if _is_negative_answer(clean) and prev_slot.axis != Axis.profile \
                and prev_slot.key not in session.filled_keys:
            session.filled_keys.append(prev_slot.key)
            session.asked_counts.pop(prev_slot.key, None)

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
        # 첫 두 질문(identity·home)은 **고정** — 등록의 뼈대(이름·나이·유형·수색
        # 원점)라 세션마다 문장이 흔들리면 안 된다(2026-07-17 사용자 결정).
        # identity 는 start_interview 가 원문 그대로 묻고, home 도 문장화 없이
        # 씨앗 원문으로 묻는다.
        session.messages.append({"role": "assistant", "text": home_slot.question})
        session.prev_target_key = "home"
        session.asked_counts["home"] = 1
        storage.interviews.save(session.id, session)
        return session

    # 3) 종료 판정
    n_questions = sum(1 for m in session.messages if m["role"] == "assistant")
    nxt = _next_slot(session, avoid_prev=not got_something)
    if nxt is None or _is_complete(session) or n_questions >= MAX_QUESTIONS:
        # 요약 전 '추가 장소 스윕' 1회 보장 — 끌림점은 예측의 뼈대인데, 슬롯 충족
        # 판정(Mi:dm)이 한 곳만 듣고 닫아버리면 더 못 모은다(라이브 실측 8차).
        # LLM 판정과 무관하게 마지막에 한 번은 반드시 묻는다. 답은 자주 가는 곳
        # 슬롯으로 추출되고, "없어요"면 다음 턴에 요약으로 넘어간다.
        if not session.asked_more_places:
            session.asked_more_places = True
            labels = list(dict.fromkeys(
                str(a.get("label")) for a in session.draft_attractions if a.get("label")))
            q = (f"말씀해주신 곳({', '.join(labels)}) 외에 대상자가 평소 자주 가시거나 "
                 "좋아하시는 곳이 또 있을까요?" if labels else
                 "대상자가 평소 자주 가시거나 좋아하시는 곳이 또 있을까요?")
            session.messages.append(
                {"role": "assistant", "text": _personalize(q, session.persona_type)})
            session.prev_target_key = "routine_destinations"
            storage.interviews.save(session.id, session)
            return session
        # 종료 대신 '요약 → 확인' 단계로 진입
        session.awaiting_confirmation = True
        session.messages.append({"role": "assistant", "text": build_summary(session)})
        storage.interviews.save(session.id, session)
        return session

    # 4) 다음 슬롯 문장화 + 가드레일
    target, is_followup = nxt
    raw_q = _phrase_tracked(session, target, is_followup)
    question, _fallback = safety.guard_question(
        raw_q, target, _EMB, bank=slots_for(session.persona_type))
    if not _presupposition_grounded(session, question):
        question = safety.single_question(target.question)   # 근거 없는 전제 → 씨앗 질문
    if not _slot_collected(session, target) and _NEG_CONDITIONAL_RE.search(question):
        question = safety.single_question(target.question)   # 여부 확인 전의 세부 질문 → 씨앗
    question = _dedupe_question(session, target, question)
    if _norm_q(question) == _norm_q(safety.single_question(target.question)):
        question = _seed_with_example(target)   # 씨앗이 그대로 나가면 예시를 붙인다
    question = _personalize(question, session.persona_type)

    session.messages.append({"role": "assistant", "text": question})
    session.prev_target_key = target.key
    session.asked_counts[target.key] = session.asked_counts.get(target.key, 0) + 1
    storage.interviews.save(session.id, session)
    return session


# '안 했을 때' 세부 질문("약을 드시지 않으면…", "거르시면…")은 기본 사실(복용
# 여부)이 확보된 뒤에만 — 슬롯 첫 진입에서 존재 전제 세부부터 묻던 라이브 실측
# (2026-07-17 6차) 수정. 긍정 조건("길을 잃으시면")은 시나리오 전제라 해당 없음.
_NEG_CONDITIONAL_RE = re.compile(
    r"(?:거르|않으시?면|않을\s*때|안\s*드시|못\s*[가-힣]{1,6}시?면|없으시?면)")


# 전제 질문 가드 — "~한다고 말씀하실 때"류는 보호자가 실제로 그렇게 말한 뒤에만
# 허용된다. 프롬프트 규칙(prompts.PHRASE_SYSTEM)만으로는 Mi:dm 이 계속 생성하는
# 것이 라이브 실측(2026-07-17 3차)으로 확인돼 코드 가드를 추가.
_PRESUP_RE = re.compile(r"(.{2,}?)(?:다고|라고)\s*(?:말씀|하셨|하시|얘기|이야기)")


def _presupposition_grounded(session: InterviewSession, question: str) -> bool:
    """질문이 전제하는 발화("…에 가야 한다고 말씀하실 때")가 보호자 발화에
    실제로 있었는지 — 전제 절 토큰의 절반 이상이 대화에 등장해야 통과."""
    m = _PRESUP_RE.search(question)
    if not m:
        return True
    said = " ".join(_user_turns(session))
    tokens = re.findall(r"[가-힣a-zA-Z0-9]{2,}", m.group(1))
    if not tokens:
        return True
    hits = sum(1 for t in tokens if t[:2] in said)
    return hits / len(tokens) >= 0.5


# 씨앗 질문(회의록 원문)의 "대상자" 문체를 유형별 호칭으로 — 폴백으로 원문이
# 그대로 나가면 "어르신" 톤의 Mi:dm 질문들과 어긋난다(라이브 실측 4차).
_HONORIFIC = {
    PersonaType.dementia: {"대상자가": "어르신이", "대상자는": "어르신은",
                           "대상자를": "어르신을", "대상자의": "어르신의", "대상자에게": "어르신께"},
    PersonaType.intellectual_disability: {"대상자가": "그분이", "대상자는": "그분은",
                                          "대상자를": "그분을", "대상자의": "그분의", "대상자에게": "그분께"},
}


def _personalize(question: str, ptype: PersonaType | None) -> str:
    for src, dst in _HONORIFIC.get(ptype, {}).items():
        question = question.replace(src, dst)
    return question


_REASK_PREFIXES = [
    "죄송해요, 한 번만 더 여쭐게요. ",
    "확인이 필요해서 다시 여쭤봅니다. 아시는 만큼만 편하게 알려주세요. ",
]


def _norm_q(q: str) -> str:
    # "(예: …)" 는 비교에서 제외 — 예시 유무만 다른 같은 질문을 중복으로 본다
    return re.sub(r"[\s,.!?~'\"]+", "", re.sub(r"\(예:.*?\)", "", q))


def _seed_with_example(slot: SlotSpec) -> str:
    """씨앗 질문 + '(예: …)'.

    복합 원문을 한 질문으로 자르면 보기가 함께 사라져 무엇을 묻는지 모호해진다
    (라이브 실측 5차: "길을 잃으시면 보통 어떻게 하시나요?" — 원문의 선택지가
    잘려나감). 축 눈높이 예시(answer_example 첫 문장)를 붙여 답변 방향을 잡아준다.
    Mi:dm 생성 질문에는 붙이지 않는다(앵커링 방지 정책 유지) — 씨앗이 그대로
    나가는 폴백·스텁 경로 전용."""
    q = safety.single_question(slot.question)
    example = (slot.answer_example or "").split(".")[0].strip()
    return f"{q} (예: {example})" if example else q


def _dedupe_question(session: InterviewSession, target: SlotSpec, question: str) -> str:
    """세션 전체에서 같은 질문 문장의 재사용을 막는다.

    1차 버전은 '직전 질문'만 비교했는데, 라이브 실측(2026-07-17 2차)에서
    같은 질문("신호를 지키시나요")이 몇 턴 간격을 두고 4번 반복됐다.
    같은 문장이 이미 나갔으면: 씨앗 질문 → 그것도 나갔으면 재질문 프리픽스.
    """
    asked = {_norm_q(m["text"]) for m in session.messages if m["role"] == "assistant"}
    if _norm_q(question) not in asked:
        return question
    seed = safety.single_question(target.question)
    if _norm_q(seed) not in asked:
        return seed
    n = session.asked_counts.get(target.key, 0)
    return _REASK_PREFIXES[n % len(_REASK_PREFIXES)] + seed


def _handle_confirmation(session: InterviewSession, clean: str) -> InterviewSession:
    """요약 확인 응답 처리: 긍정→등록 완료 / 정정→관련 슬롯 반영 후 재요약."""
    session.messages.append({"role": "user", "text": clean})

    if _is_affirmative(clean):
        try:
            finalize_persona(session)   # draft → 지오코딩 → 확정 Persona 저장
            msg = "확인 감사합니다. 이 내용으로 프로필을 등록했어요. 🙏"
        except ValueError as e:
            # 데드엔드 금지(라이브 실측): 구버전은 여기서 done=True 로 닫아,
            # "다시 확인해 달라"는 안내와 달리 이후 입력을 전부 무시했다.
            # 세션을 열어둔 채 home 재질문 흐름으로 복귀한다.
            session.awaiting_confirmation = False
            session.draft_fields.pop("home", None)   # 좌표화 실패 값이 first-wins 로 새 답을 막지 않게
            if "home" in session.filled_keys:
                session.filled_keys.remove("home")
            home_slot = slot_by_key("home")
            session.prev_target_key = home_slot.key
            session.asked_counts[home_slot.key] = 1  # 2.5 게이트가 곧바로 또 묻지 않게
            msg = (f"등록 중 문제가 있었어요({e}). "
                   f"{safety.single_question(home_slot.question)}")
        session.messages.append({"role": "assistant", "text": msg})
        storage.interviews.save(session.id, session)
        return session

    # 정정: 발화와 가장 관련있는 슬롯으로 재추출해 반영 → 다시 요약.
    # 정정은 명시적 수정 의사이므로 first-wins 를 넘어 덮어쓴다 (overwrite=True).
    ranked, _ = retrieval.rank_next_slots(
        session.persona_type, [clean], set(), _EMB, top_k=1
    )
    if ranked:
        ext = _extract_tracked(session, ranked[0].slot)
        _merge_rule_fallback(session, ranked[0].slot, ext, clean)   # 주소 정정 등 규칙 백스톱
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
    """축 점수 채점 + route_familiarity 컴파일 후 Persona 재저장 — 비동기 모드에서는
    백그라운드 스레드로 돈다.

    저장소에서 새로 읽어 스레드 간 객체 공유를 피한다. 실패는 리포트로만 남긴다
    (채점 실패가 이미 확정된 등록을 되돌리면 안 됨). 완료·실패 각각 상태와
    시각을 리포트에 남겨 ensure_axis_scores 가 재시도 여부를 판단할 수 있게 한다.
    route_familiarity 는 별도 완료 상태를 추적하지 않는다 — 실패해도 unfamiliarity()
    가 거리 기반 근사로 안전하게 폴백하므로 재시도 인프라를 둘 이유가 약하다.
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
    # route_familiarity 컴파일(작업5) — 같은 백그라운드 트리거에 얹는다(별도 비동기
    # 인프라 신설 안 함). 컴파일러 자체가 실패를 빈 리스트로 흡수하지만, 여기서도
    # 한 번 더 감싸 위에서 이미 확정된 axis_scores 저장이 이 블록 때문에 막히지 않게 한다.
    try:
        from app.phase0.route_familiarity_compiler import compile_route_familiarity

        persona.route_familiarity = compile_route_familiarity(persona)
    except Exception:  # noqa: BLE001 — 실패해도 축 채점 결과 저장은 계속 진행
        pass
    # 개인 환경 반응 컴파일(과제1) — 같은 트리거에 얹는다. 축 기준표에 없는
    # "무엇에 반응하는가"를 behavior_notes 에서 뽑는다. 실패는 빈 리스트로
    # 흡수되고, 소비처가 중립 1.0 을 돌려주므로 예측이 도입 이전과 같아진다.
    try:
        from app.phase0.env_response_compiler import compile_env_responses

        persona.env_responses = compile_env_responses(persona)
    except Exception:  # noqa: BLE001 — 실패해도 앞선 결과 저장은 계속 진행
        pass
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

    # ③ 카테고리 선호 — 좌표화 대상이 아니므로 지오코딩 없이 스키마 검증만
    preferred = [
        PreferredTarget(
            label=str(t.get("label")),
            target_type=str(t.get("target_type") or ""),
            evidence=coerce_evidence(t.get("evidence")),
        )
        for t in session.draft_preferred if t.get("label")
    ]

    # ④ 축별 근거 — 슬롯별 노트·원발화를 축 DB 필드명으로 묶는다(축 점수 컴파일 입력)
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
        preferred_targets=preferred,
        axis_evidence=axis_evidence,
        axis_quotes=axis_quotes,
    )

    # ⑤ 축 점수 컴파일 — 기능 플래그(기본 off, 회의에서 B×P1 채택 시 켠다).
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
