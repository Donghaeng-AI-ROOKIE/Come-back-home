"""Phase 0 — 보호자 온보딩: 적응형 엘리시테이션 → 페르소나 초안.

매 턴 루프(노트 설계):
  1) 보호자 답변 정제(safety.sanitize_input, 개인정보 마스킹)
  2) 직전 겨냥 슬롯에 대해 Mi:dm 추출 → 충족 슬롯·누적 초안 갱신
  3) 히스토리-어웨어 검색으로 다음 슬롯 랭킹(retrieval) — '지금 화제' 관련 슬롯 선택
  4) Mi:dm 이 그 슬롯을 존댓말 질문으로 문장화 → 2층 가드레일 통과(safety)
  5) 남은 tier1~2 슬롯이 없으면 종료(초안 완성)

'첫 질문은 하드코딩'(identity — 성함·나이). 대상 유형은 치매 단독이라(2026-08-03
팀 결정) 세션 생성 시점에 PersonaType.dementia 로 고정한다 — 유형을 되묻지 않는다.
초안(draft_*)은 Phase 2 이전 지오코딩 단계에서 Persona 로 확정.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import storage
from app.llm import midm
from app.phase0 import retrieval, safety
from app.geo.geocode import (
    HOME_ALT_MAX_LIST,
    _LOT_NUMBER_RE,
    GeoResult,
    clean_area_text,
    get_geocoder,
    has_region_token,
    region_tokens,
    token_in_text,
    locate_home,
    to_attraction_points,
)
from app.phase0.retrieval import get_embedder
from app.phase0.slots import SLOTS, Axis, Sink, SlotSpec, Tier, slot_by_key, slots_for
from app.schemas.common import GeoPoint
from app.schemas.persona import (
    AttractionPoint,
    InterviewSession,
    Persona,
    PersonaType,
)

import re
import threading

_EMB = get_embedder()

# 피벗(꼬리질문) 판정은 검색의 PIVOT_SIM 과 일치 — 강한 신호일 때만 '되받아 확인' 톤.
FOLLOWUP_SIM = retrieval.PIVOT_SIM
# 절대 백스톱(모든 슬롯 소진/충족으로 자연 종료가 먼저 걸린다). 유형별 슬롯×시도 상한 위.
MAX_QUESTIONS = 40

# ── 대화 가드 토글 (평가 하네스 전용) ──────────────────────────────────
# experiments/chatbot_eval 가 가드 실효성을 재려고 하나씩 끈다("가드 다이어트").
# **운영 기본은 전부 켜짐 — 모두 True 이면 동작이 종전과 완전히 동일**하다(프로덕션
# 영향 없음). 개별 가드를 끈 실행의 점수/효율 하락이 곧 그 가드의 실효성이다.
# 화제이탈 grounding 은 retrieval.DENOISE 로 별도 제어(순환참조 회피).
GUARDS = {
    "ignorance_exhaust": True,   # 무지 답변("모르겠어요") → 그 슬롯 즉시 소진
    "negation_fill": True,       # 부정 답변("없어요") → '해당 없음'으로 충족
    "affirmation_fill": True,    # 단순 긍정("네") → 여부 질문에 대한 답으로 충족
    "presupposition": True,      # 근거 없는 전제 질문("~라고 하실 때") 차단
    "existence_first": True,     # 여부 확인 전 세부(부정조건) 질문 차단
    "dedup": True,               # 세션 전체 질문 문장 중복 방지
    "clarify": True,             # "무슨 뜻이에요?" → 쉬운 말로 풀어 재질문
    # 하위 항목 파고들기(PR #64). 씨앗 질문이 첫 물음표에서 잘려 못 묻는 하위
    # 항목(예: 복약의 '거르면 어떤 증상')은 이 통로가 유일하다 — 끄지 말 것.
    # 슬롯별로 빼려면 SlotSpec.probe_followup 을 쓴다(예: lost_behavior).
    "probe": True,
}

_IDENTITY = slot_by_key("identity")

# 대상 유형 — 치매 단독 스코프(2026-08-03). 유형 판별·되묻기 경로는 제거했고
# 세션 생성 시 이 값으로 고정된다.
DEFAULT_PERSONA_TYPE = PersonaType.dementia


def _last_question(session: InterviewSession) -> str:
    """방금 들어온 보호자 답 바로 앞의 챗봇 발화."""
    return next((m["text"] for m in reversed(session.messages[:-1]) if m["role"] == "assistant"), "")


def _user_turns(session: InterviewSession) -> list[str]:
    return [m["text"] for m in session.messages if m["role"] == "user"]


# ── Mi:dm 호출 래퍼 — 실패를 세션 플래그로 노출 ─────────────────────
# midm 폴백은 침묵한다(빈 추출·씨앗 질문). 그대로 두면 장애가 "이상한 반복
# 인터뷰"로만 체감되므로(라이브 실측 410), 카운터 증가를 세션에 기록해
# API 응답(llm_degraded)으로 드러낸다.


# 질문에 붙는 답변 눈높이 예시 "(예: …)" — 보호자에게는 도움이 되지만, 대화 이력이
# 그대로 추출 입력이 되므로 예시 속 고유명사·상황이 추출을 오염한다. 실측 A/B
# (2026-07-21, Mi:dm 실호출): "원평중학교 앞에서 발견됐다"는 답변에서 발견 장소 추출이
# 예시문 있음 0/3 → 예시문 제거 2/3. 예시가 있으면 모델이 마지막 답변의 새 장소 대신
# 이전 턴 장소들을 재추출한다 = 과거 발견지(가장 강한 근거)가 통째로 유실된다.
_QUESTION_EXAMPLE_RE = re.compile(r"\s*[(（]\s*예\s*[:：].*?[)）]", re.DOTALL)


def _strip_question_examples(messages: list[dict]) -> list[dict]:
    """추출용 대화 사본 — 챗봇 발화의 "(예: …)"만 제거. 원본 messages 는 불변
    (보호자에게 보여준 대화 기록은 그대로 남아야 한다)."""
    out = []
    for m in messages:
        if m.get("role") == "assistant" and "예" in str(m.get("text", "")):
            out.append({**m, "text": _QUESTION_EXAMPLE_RE.sub("", str(m["text"])).strip()})
        else:
            out.append(m)
    return out


def _arealess_attractions(session: InterviewSession) -> list[dict]:
    """지역 표기가 없는 끌림점 — 이대로 두면 지오코딩이 실패해 조용히 사라진다.

    라이브 실측(2026-07-21): "예전에 살던 집"이 area_text 없이 확정돼 좌표화에
    실패했고, finalize 가 미해결 목록을 버려 페르소나 끌림점이 통째로 누락됐다.
    보호자는 주소를 물어본 적조차 없으니 고칠 기회도 없었다.
    """
    return [a for a in session.draft_attractions
            if a.get("label") and not clean_area_text(a.get("area_text"))]


# 과거 장소를 수집하는 슬롯 — "예전에 살던 집", "과거 발견지"처럼 **지금은 안 사는
# 곳**이라 지역 표기가 없으면 좌표를 만들 방법이 아예 없다. 그 자리에서 바로 묻는다.
_PAST_PLACE_SLOTS = ("autobiographical_destination_pull", "dementia_wandering_pattern")


def _area_grounded(area: str, utterance: str) -> bool:
    """지역 표기가 보호자 발화에 실제로 있었나 — 없으면 모델이 지어낸 값이다.

    라이브 실측(2026-07-21): "예전에 살던 집에 가야한다는 말을 종종 합니다"에
    Mi:dm 이 area_text 를 **현재 집 동네**("청주시 서원구 분평동")로 채웠다. 빈 값이
    아니라 그럴듯한 오답이라 되묻기가 발동하지 않았고, 과거 거주지가 수색 원점과
    같은 좌표에 찍혔다. 축 채점의 quote 실존 검증과 같은 원칙으로 막는다.
    """
    text = _norm(utterance)
    tokens = [_norm(t) for t in str(area or "").split() if len(_norm(t)) >= 2]
    return bool(tokens) and any(t in text for t in tokens)


def _geocodable(label: str) -> bool:
    """라벨만으로 좌표가 나오나 — 나오면 동네를 되물어 보호자를 번거롭게 할 이유가 없다.

    실패(네트워크·백엔드 장애)는 '모른다'로 보고 되묻기로 넘긴다 — 질문 한 번이
    좌표 없는 끌림점보다 싸다.
    """
    try:
        return _GEO.locate(label) is not None
    except Exception:  # noqa: BLE001 — 지오코더 장애가 인터뷰를 죽이면 안 됨
        return False


def _ask_area_for_new_place(
    session: InterviewSession, prev_slot: SlotSpec, extracted: dict, utterance: str,
) -> str | None:
    """과거 장소 슬롯에서 새 끌림점이 나왔는데 지역 표기가 없거나 근거 없으면 되물을 질문.

    보호자가 "그런 곳이 있다"고 답한 **그 턴에** 주소를 묻는다 — 요약 직전까지
    미루면 대화 맥락이 끊기고, 그때는 어느 장소 얘기였는지 서로 헷갈린다.
    """
    if prev_slot.key not in _PAST_PLACE_SLOTS:
        return None
    for raw_ap in extracted.get("attraction_points") or []:
        label = str(raw_ap.get("label") or "").strip()
        if not label or label in session.asked_area_labels:
            continue
        ap = next((a for a in session.draft_attractions
                   if _norm(a.get("label")) == _norm(label)), None)
        if ap is None:
            continue
        area = clean_area_text(ap.get("area_text"))
        if area and _area_grounded(area, utterance):
            continue          # 보호자가 직접 말한 지역 — 물을 필요 없다
        ap["area_text"] = ""  # 지어낸 값은 버린다(그대로 두면 엉뚱한 좌표가 된다)
        # 고유한 이름("대흥역 2번 출구")은 라벨만으로 좌표가 나오면 묻지 않는다. 이름 없이
        # 부른 곳(모델 판정 name_kind=generic: "교회", "예전 집")은 라벨 검색이 집 근처 아무
        # 곳이나 찾으므로(E2E 2026-09-26) 늘 동네를 묻는다.
        if ap.get("name_kind") != "generic" and _geocodable(label):
            continue
        session.asked_area_labels.append(label)
        session.pending_area_label = label
        return (f"'{label}'은 어느 동네인가요? 동 이름이나 근처 건물·가게 이름을 "
                "알려주시면 지도에 표시해 둘게요. (모르시면 '모르겠어요'라고 답해주세요)")
    return None


def _needs_probe(session: InterviewSession, slot: SlotSpec, answer_kind: str | None) -> bool:
    """이 슬롯을 한 번 더 파고들어야 하나 — 하위 항목(probes)이 안 채워진 얕은 답인가.

    라이브 실측(2026-07-21): Mi:dm 은 "혈압약을 저녁에만 드세요"에도 slot_filled=true
    를 낸다. 충족 처리된 슬롯은 _blocked_keys 로 후보에서 빠지므로 **probes 가 한
    번도 쓰이지 않는다** — 씨앗 질문은 clean_question 이 첫 물음표에서 자르기 때문에
    ("복용 중인 약이 있나요?" 뒤의 '거르면 어떤 증상' 이 잘림) 하위 항목은 꼬리질문이
    유일한 통로인데, 그 통로가 닫혀 있던 것이다. 슬롯당 1회만 보장한다.
    """
    if not GUARDS["probe"] or not slot.probe_followup:
        return False        # 가드 스윕이거나, 슬롯이 파고들기를 빼둔 경우
    if not slot.probes or slot.key in session.probed_keys:
        return False
    if slot.axis == Axis.profile:
        return False        # 이름·집은 파고들 하위 항목이 아니다
    if answer_kind in ("unknown", "none"):
        return False        # 모른다·해당 없다(모델 판정)는 더 물어도 얻을 게 없다
    return len(_slot_collected(session, slot)) < 2   # 확보한 사실이 1개 이하 = 얕음


# 꼬리질문이 원 질문의 재탕이면 안 된다 — 정확 일치만 잡는 _dedupe_question 으로는
# "낯선 사람이 다가와 말을 걸면 어떻게 반응하시나요?" vs "낯선 시민이 다가와 말을
# 걸면 어떤 행동을 보이시나요?" 를 못 거른다(라이브 실측 2026-07-22).
_PROBE_DUP_JACCARD = 0.5


def _clarify_question(session: InterviewSession, slot: SlotSpec, utterance: str) -> str:
    """못 알아들은 직전 질문을 쉬운 말로 풀어 다시 묻는다.

    LLM 이 보호자 말을 읽고 무엇을 묻는 것인지 설명한 뒤 재질문한다. 실패·스텁이면
    슬롯의 답변 눈높이 예시로 결정론적 폴백 — 어느 경로든 **같은 질문 되풀이는
    안 나가야** 한다(그게 보호자가 못 알아들은 바로 그 문장이다).
    """
    last_q = next((m["text"] for m in reversed(session.messages)
                   if m["role"] == "assistant"), "")
    before = midm.call_failures
    raw = midm.clarify_question(session.persona_type, slot, last_q, utterance)
    if midm.call_failures > before:
        session.llm_call_failures += midm.call_failures - before
        session.llm_degraded = True
    # 문장화 가드는 층①(블록리스트)만 태운다 — 이 문장은 '설명 + 질문' 2문장이라
    # 임베딩 grounding 에 걸리기 쉬운데, 걸러서 씨앗으로 폴백하면 못 알아들은 질문을
    # 그대로 되풀이하게 된다(가드가 증상을 만드는 꼴).
    if raw.strip() and safety.passes_rules(raw) and _norm_q(raw) != _norm_q(last_q):
        return raw
    example = (slot.answer_example or "").split(".")[0].strip()
    if example:
        return (f"제가 여쭌 건 '{slot.guardian_label or slot.label}'에 대한 거예요. "
                f"예를 들면 \"{example}\" 처럼요. 아시는 만큼만 편하게 알려주시겠어요?")
    return (f"제가 여쭌 건 '{slot.guardian_label or slot.label}'에 대한 거예요. "
            "아시는 만큼만 편하게 알려주시겠어요?")


def _slot_evidence(session: InterviewSession, slot: SlotSpec) -> list[str]:
    """이 슬롯에서 보호자가 실제로 한 말 — 재서술 노트 + **원발화**.

    노트만 보면 답을 놓친다: "네 신호도 잘 지키시고 위험 감지 능력은 좋아요"에
    Mi:dm 이 노트를 '위험 감지 능력은 좋아요'로만 남겨(신호 부분 소실) 파고들기가
    방금 답한 신호를 또 물었다(라이브 실측 2026-08-07). 원발화를 함께 준다.

    _slot_collected 와 분리해 둔다 — 그쪽은 '얕은가' 세는 데 쓰이므로 원발화까지
    세면 파고들기가 영영 발동하지 않는다.
    """
    out = list(_slot_collected(session, slot))
    for q in session.slot_quotes.get(slot.key, []):
        if q not in out:
            out.append(q)
    return out


def _probe_question(session: InterviewSession, slot: SlotSpec) -> str:
    """하위 항목 꼬리질문. **더 물을 게 없으면 빈 문자열**(호출자가 건너뛴다).

    각도 선택을 코드가 하지 않는다 — 어휘가 겹치는지로는 "그 자리에 서서 가만히
    계세요"가 '머무름·계속 이동·은신 중 우세 경향'의 답이라는 걸 영영 못 본다
    (라이브 실측 2026-08-07: 토큰 교집합 0). 뜻이 같은지는 모델이 판정한다.

    안전판: 어느 경로로도 **이미 나간 질문·probes 원문은 안 나간다.** 그런 경우엔
    파고들기를 포기한다 — 파고들기는 깊이를 더하는 보너스라, 재탕이나 내부 용어를
    내보내느니 넘어가는 편이 낫다(슬롯은 이미 충족 처리돼 잃는 것도 없다).
    """
    asked = [m["text"] for m in session.messages if m["role"] == "assistant"]
    recent = asked[-3:]
    evidence = _slot_evidence(session, slot)
    before = midm.call_failures
    # always_probe_first 슬롯은 판정을 건너뛰고 첫 각도를 묻는다 — 판정기가 애매한
    # 답을 '답했다'로 넘겨 정작 중요한 각도를 건너뛰던 슬롯용(medication 주석 참고).
    if slot.always_probe_first and slot.probes:
        angle = slot.probe_labels[0]
    else:
        gaps = midm.probe_gap(session.persona_type, slot, evidence)
        angle = gaps[0] if gaps else ""
    raw = (midm.probe_question(session.persona_type, slot, angle, evidence)
           if angle else "")
    if midm.call_failures > before:
        session.llm_call_failures += midm.call_failures - before
        session.llm_degraded = True
    if not raw.strip():
        return ""              # 남은 각도 없음 (또는 스텁·호출 실패)
    # 층①(블록리스트)만 태운다. 임베딩 grounding 은 파고들기에 맞지 않는다 —
    # 각도는 일부러 하위 주제로 파고들어서 부모 슬롯보다 다른 슬롯에 더 가깝게
    # 찍힌다(실측 2026-08-07: 멀쩡한 파고들기 질문 4/4가 전부 기각됐다. "밤에 혼자
    # 밖으로 나가시는 경우가 있나요?"가 복약 슬롯에서 탈락). 그렇게 씨앗으로
    # 폴백된 질문이 재탕 → probes 원문 폴백으로 이어진 것이 원래 증상의 사슬이었다.
    # 화제 이탈 위험은 여기선 구조적으로 낮다 — 물을 각도를 slot.probes 라는 닫힌
    # 목록에서 골라 프롬프트에 박아 주기 때문(자유 생성이 아니다).
    if not safety.passes_rules(raw):
        return ""
    question = safety.single_question(raw)
    # 이미 나간 질문과 견주기 전에 호칭을 맞춘다(저장되는 문장이 치환형이라).
    question = _personalize(question, session.persona_type)
    # 비교는 **알맹이끼리** — 이전 질문에 붙은 '(예: …)'·재질문 프리픽스가 그대로
    # 남아 있으면 합집합만 부풀어 자카드가 임계 밑으로 내려간다(라이브 실측
    # 2026-08-07: 씨앗 재탕인데 0.400·0.333 로 통과해 같은 질문이 세 번 나갔다).
    qt = _note_tokens(_bare_question(question))
    too_similar = any(
        pt and qt and len(qt & pt) / len(qt | pt) >= _PROBE_DUP_JACCARD
        for pt in (_note_tokens(_bare_question(a)) for a in recent))
    if too_similar:
        return ""
    if GUARDS["dedup"] and _norm_q(_bare_question(question)) in {
            _norm_q(_bare_question(a)) for a in asked}:
        return ""
    return question


def _resolve_pending_area(session: InterviewSession, utterance: str) -> None:
    """되물은 주소 답변을 해당 끌림점의 area_text 로 확정 — 되묻기는 장소당 1회.

    답에서 지역 표현을 고르는 일은 Mi:dm 이 한다(prompts.AREA_SYSTEM). 보호자는
    되묻기에 지명만 딱 답하지 않는다 — "'예전 가게'은 어느 동네인가요?"에 "망원시장에서
    생선가게를 하셨어요"라고 답한다(라이브 실측 2026-08-07). 코드는 모델이 고른 표현이
    답에 글자 그대로 있는지만 확인한다 — 없으면 지어낸 값이라 받지 않는다.
    """
    label = session.pending_area_label
    if not label:
        return
    session.pending_area_label = None
    area = _midm_tracked(session, lambda: midm.extract_area(label, utterance))
    if not area:
        return   # 모른다·지역 표현 없음 — 되묻기는 1회뿐이므로 여기서 포기(질문 반복 금지)
    if not _in_answer(area, utterance):
        session.extraction_audit.append(
            {"event": "area_not_in_answer", "label": label, "area": area})
        return
    for ap in session.draft_attractions:
        if _norm(ap.get("label")) == _norm(label) and not clean_area_text(ap.get("area_text")):
            ap["area_text"] = area
            return


def _extract_tracked(session: InterviewSession, slot: SlotSpec,
                     *, recheck_places: bool = False) -> dict:
    before = midm.call_failures
    conversation = _strip_question_examples(session.messages)
    known = list(dict.fromkeys(str(a.get("label")) for a in session.draft_attractions
                               if a.get("label")))
    extra = {k: v for k, v in (("recheck_places", recheck_places), ("known_places", known)) if v}
    out = midm.extract_answer(slot, conversation, **extra)
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


# 답변 유형(모름·해당 없음·긍정만·질문 되물음·이미 답함)은 Mi:dm 추출의 answer_kind 로
# 받는다(prompts.EXTRACT_SYSTEM). 예전에는 정규식이 "모르"·"없어요"·"네" 같은 표면형으로
# 분류했지만, 보호자 문장을 단어 목록으로 해석하지 않기로 했다(2026-09-26 사용자 결정).
# 각 유형이 인터뷰 흐름에 주는 효과(소진·충족·쉬운 말 재질문)는 그대로다 — 그 효과를
# 만든 라이브 실측 사례는 answer_interview 의 해당 분기 주석에 남겨 두었다.


# ── 이름·나이·집 주소 — 모델 추출값의 원문 대조 ──────────────────────
# 예전에는 Mi:dm 이 빈손이면 정규식으로 이름("○○님")·나이("○○세")·주소("○○동")를
# 직접 뽑았다(엔드포인트 장애 대비, 2026-07-16 실측). 보호자 문장을 단어 규칙으로
# 해석하지 않기로 하면서(2026-09-26 사용자 결정) 추출은 모델만 한다. 모델이 장애면
# 이 슬롯은 다시 묻는다 — 장애 중에는 등록이 끝나지 않는 대신, 틀린 값(특히 수색
# 원점이 되는 집 주소)을 규칙이 만들어 넣는 일은 없다.


def _model_age(value) -> int | None:
    """모델이 낸 나이 값 → 정수. 숫자(또는 '82세'처럼 단위만 붙은 숫자)가 아니면 None.

    고유어 나이("여든둘")를 숫자로 바꾸는 일은 모델에 맡긴다(prompts.EXTRACT_SYSTEM).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 0 < value < 130 else None
    m = re.fullmatch(r"\s*(\d{1,3})\s*(?:세|살)?\s*", str(value or ""))
    return int(m.group(1)) if m and 0 < int(m.group(1)) < 130 else None


def _grounded_fields(session: InterviewSession, fields: dict, utterance: str) -> dict:
    """모델이 뽑은 name/age/home 중 이 답에 근거가 있는 것만 남긴다.

    - 이름: 답에 글자 그대로 있어야 한다(지어낸 이름 차단).
    - 나이: 숫자여야 하고, 답에 아라비아 숫자가 있으면 그중 하나와 같아야 한다.
    - 집 주소: 주소 표현의 낱말이 답에 있어야 한다(라이브 실측 2026-07-21: 과거 거주지
      답에 모델이 **현재 집 동네**를 채워 넣었다). 지도 검증은 _check_home 에서 한 번 수행한다.
    받지 않은 값은 extraction_audit 에 남긴다.
    """
    kept: dict = {}
    for key, value in _flatten_fields(fields or {}).items():
        if key not in ("name", "age", "home"):
            kept[key] = value
            continue
        if _norm(str(value)) == _norm(str(session.draft_fields.get(key) or "")).removesuffix("세") \
                or _norm(str(value)) == _norm(str(session.draft_fields.get(key) or "")):
            continue   # 이미 받은 값을 모델이 다음 턴에 다시 낸 것 — 새 정보도 오류도 아니다
        if key == "name":
            ok = _in_answer(value, utterance)
        elif key == "age":
            age = _model_age(value)
            digits = re.findall(r"\d+", utterance)
            ok = age is not None and (not digits or str(age) in digits)
            value = f"{age}세" if ok else value
        else:
            ok = _area_grounded(str(value), utterance)
        if ok:
            kept[key] = value
        else:
            session.extraction_audit.append(
                {"event": "field_not_in_answer", "field": key, "value": str(value)})
    return kept


# 지도 확인 실패로 집을 되묻는 상한. 그 뒤로는 **미확인인 채** 통과시킨다 — 지오코더가
# 죽었을 때(카카오·OSM 장애는 조용한 미탐으로 돌아온다) 정확한 주소를 몇 번이나
# 다시 적어도 계속 되묻는 막다른 길을 막기 위해서다. 통과한 값은 finalize 가
# 기존대로 다시 좌표화를 시도하고, 그래도 실패하면 확인 게이트가 재질문한다.
_HOME_CHECK_MAX_FAILURES = 2


_TAIL_PARTICLE_RE = re.compile(r"(?:에|에서|이요|이에요|예요|입니다|이|가|은|는|요)\s*$")


def _strip_tail_particles(text: str) -> str:
    """말끝 조사 제거 — "산남동이요" → "산남동". 지오코딩 질의로 나갈 값에 필요."""
    return _TAIL_PARTICLE_RE.sub("", str(text or "").strip()).strip()


def _has_region_token(text: str) -> bool:
    """시·구·동·도로명 등 지역 표기가 답에 있나 — 상호만 적은 답("우리집")과 가른다.

    _HOME_RE 는 여기 못 쓴다 — 부분 문자열 검색이라 "우리집"의 '우리'를 '…리'로 잡는다.
    """
    return has_region_token(_strip_tail_particles(text))


def _check_home(session: InterviewSession, utterance: str = "", *, answer_kind: str = "informative") -> str | None:
    """home 초안을 **답을 받은 그 턴에** 지도로 확인 — 통과하면 None, 아니면 되물을 문장.

    utterance 가 주어지고 초안에 home 이 **없으면** 발화 자체를 후보로 삼는다 — Mi:dm 2.5 는
    "포켓몬랜드"를 아예 추출하지 않아(빈 결과) 검증할 텍스트가 없었고, 기존 흐름은
    "집이 안 채워졌으면 다음 슬롯으로" 넘어가 버렸다(라이브 실측 2026-09-26). 집은
    건너뛸 수 없는 고정 2번 질문이라 빈손도 그 자리에서 되묻는다. 무지·부정·항의
    발화는 주소 시도가 아니므로 제외(그건 기존 소진 규칙이 다룬다).

    구버전은 표면 검사(_valid_home_text)만 하고 좌표화는 finalize(요약 확인 뒤)에서만
    했다. 그래서 "포켓몬랜드"가 짧은 명사구라는 이유로 통과해 다음 질문으로 넘어가고,
    10여 개 질문을 다 끝낸 요약 확인에서야 "집 위치 미확보"가 떴다(2026-09-26).
    수색 원점은 프로필의 뼈대라 여기서 바로 잡는다.

    통과 기준은 '찾았다'만으로 부족하다. 카카오 키워드 검색은 퍼지해서 "우리집"→강남
    식당, "하늘나라"→충주 추모공원처럼 **엉뚱한 좌표를 조용히** 돌려준다(실측). 그래서
    (1) 주소·동 단위 매칭이거나 (2) 답에 지역 표기(시·구·동·도로명)가 있을 때만
    받는다. 상호만 적은 답은 같은 이름이 전국에 흔해 어차피 지역을 물어야 맞다.

    실패하면 초안에서 빼고(first-wins 가 새 답을 막지 않게) home 을 되묻되, 재질문
    예산은 소진시키지 않는다 — 집은 건너뛸 수 있는 슬롯이 아니다. 대신 상한
    (_HOME_CHECK_MAX_FAILURES)을 넘으면 미확인 상태로 통과시킨다(지오코더 장애 대비).
    """
    text = str(session.draft_fields.get("home") or "").strip()
    from_utterance = False
    if not text:
        u = str(utterance or "").strip()
        if not u or answer_kind != "informative":
            return None
        text, from_utterance = _strip_tail_particles(u), True
    if session.home_geo and session.home_geo.get("query") == text:
        return None                     # 이미 확인된 값 — 정정 없이 재진입한 경우
    try:
        res = locate_home(_GEO, text)
    except Exception:  # noqa: BLE001 — 지오코더 장애가 인터뷰를 죽이면 안 됨
        res = None
    if res is not None and (res.precision in ("address", "dong") or _has_region_token(text)):
        # 찾았고 지역도 있다 — 그런데 **몇 곳**을 가리키는가. "산남동"은 파주와 청주,
        # "마포구 스타벅스"는 15개 지점인데 지오코더는 첫 결과만 준다.
        resolution = _disambiguate_home(session, res, text)
        if isinstance(resolution, str):
            return resolution
        if isinstance(resolution, GeoResult):
            res = resolution
        session.home_geo = {
            "query": text, "lat": res.point.lat, "lng": res.point.lng,
            "precision": res.precision, "source": res.source,
            "matched": res.matched, "address": res.address,
        }
        _clear_home_choice(session)
        if from_utterance:
            # 추출기는 빈손이었지만 발화가 주소·지역 조건을 충족하며 지도에 잡혔다
            session.draft_fields["home"] = text
            if "home" not in session.filled_keys:
                session.filled_keys.append("home")
            session.asked_counts.pop("home", None)
        return None
    if session.home_check_failures >= _HOME_CHECK_MAX_FAILURES:
        session.home_geo = None         # 미확인 통과 — finalize 가 다시 시도한다
        return None
    _reject_home(session)
    session.home_check_failures += 1
    if res is None:
        return (f"'{text}'은(는) 지도에서 찾지 못했어요. 시·구·동 이름이나 도로명 주소로 "
                "다시 알려주세요. (예: 서울 중랑구 면목동, 서울시 마포구 백범로 35)")
    return (f"'{text}'만으로는 위치를 특정하기 어려워요. 어느 시·구·동에 있는지 함께 "
            f"알려주세요. (예: ○○시 ○○동 {text})")


def _reject_home(session: InterviewSession) -> None:
    """집 초안을 걷어내고 다음 답을 다시 집으로 받게 한다 — 되묻기 공통 정리.

    first-wins 병합이 새 답을 막지 않도록 초안에서 빼고, 2.5 게이트가 씨앗 질문을
    또 내보내지 않도록 asked_counts 는 1로 둔다(소진 MAX 는 아니게 — 집은 건너뛸 수
    없는 슬롯이다).
    """
    session.draft_fields.pop("home", None)
    if "home" in session.filled_keys:
        session.filled_keys.remove("home")
    session.home_geo = None
    session.prev_target_key = "home"
    session.asked_counts["home"] = 1


# ── 집 주소 다중 후보 되묻기 ──────────────────────────────────────────
# 지오코더는 첫 결과 하나만 돌려준다(size=1). "산남동"은 파주·청주에 있고
# "마포구 스타벅스"는 15개 지점인데, 지역 표기가 있다는 이유로 첫 결과가 조용히
# 집으로 등록됐다(실측 2026-10-01: 산남동→파주, 마포구 스타벅스→망원한강공원점).
# 요약의 "지도 확인:" 한 줄이 유일한 방어였다. 답이 가리키는 후보 집합을 세어
# 2곳 이상이면 그 자리에서 한 번 되묻는다. (끌림점의 Mi:dm 후보 고르기(_PlaceChooser)
# 는 finalize 의 장소용이고 집은 여전히 locate_home 첫 결과다 — 겹치지 않는다.)
#
# 한 집 답에 되묻는 상한. 6개 이상 → 보탬("합정동이요") → 나열 → 확정이 2회다.
# 그래도 못 좁히면 첫 결과로 통과시킨다 — 되묻기가 등록을 막아선 안 된다.
_HOME_CHOICE_MAX_ROUNDS = 2

_ORDINALS = {"첫번째": 1, "첫째": 1, "하나": 1, "두번째": 2, "둘째": 2, "세번째": 3, "셋째": 3,
             "네번째": 4, "넷째": 4, "다섯번째": 5, "다섯째": 5,
             "①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5}
_CHOICE_NUMBER_RE = re.compile(r"^(\d+)(?:번|번째)?$")


def _home_alternatives(res: GeoResult, text: str) -> list | None:
    """후보 집합 조회 — 백엔드가 못 하거나 장애면 None(되묻지 않고 오늘처럼)."""
    fn = getattr(_GEO, "home_alternatives", None)
    if fn is None:
        return None
    try:
        return fn(res, text)
    except Exception:  # noqa: BLE001 — 후보 조회 장애가 첫 결과 통과를 막으면 안 됨
        return None


def _non_region_part(text: str) -> str:
    """지역 토큰을 뺀 나머지 — "마포구 스타벅스" → "스타벅스", "산남동" → ""."""
    region = set(region_tokens(text))
    toks = [_strip_tail_particles(t) for t in str(text or "").split()]
    return " ".join(t for t in toks if t and t not in region)


def _clear_home_choice(session: InterviewSession) -> None:
    session.home_choices = []
    session.home_choice_text = ""
    session.home_choice_rounds = 0


def _disambiguate_home(session: InterviewSession, res: GeoResult, text: str) -> str | GeoResult | None:
    """여러 후보면 되묻기, 유일한 다른 후보면 GeoResult, 원래 결과면 None.

    후보 0 = 첫 결과가 답에 적힌 지역 **밖**("강동구 ○○분식"이 타 구로 걸림) —
    지오코더 미탐과 같은 급으로 실패 예산(_HOME_CHECK_MAX_FAILURES)을 쓴다.
    2~HOME_ALT_MAX_LIST 는 번호 보기로 나열, 그 이상은 나열 대신 더 구체적으로
    말해 달라고 하되 실제 후보에서 뽑은 예시를 붙여 답 형식을 바로 알게 한다.
    """
    if session.home_choice_rounds >= _HOME_CHOICE_MAX_ROUNDS:
        return None
    if res.precision == "poi" and _LOT_NUMBER_RE.match(_non_region_part(text) or "x"):
        # "마포구 백범로 35"처럼 지역 표기 + 번지뿐인 답은 주소다. 키워드검색이 먼저 돌아
        # 그 건물 안 POI 가 걸리면 건물 번호를 상호로 보고 "'35'이(가) 여러 곳이에요"라고
        # 물었다(실측 2026-10-27). 지오코더(_looks_like_region)가 이제 주소검색을 먼저
        # 돌리지만, 주소검색이 미탐이라 키워드로 내려온 경우의 마지막 방어선.
        return None
    alts = _home_alternatives(res, text)
    if alts is None:
        return None
    if len(alts) == 1:
        # Region filtering may discard the original first hit. Persist the
        # surviving candidate, not the out-of-region result we just rejected.
        a = alts[0]
        if (res.address == a.address and res.precision == a.precision
                and (res.precision == 'address' or res.matched == a.label)):
            return None  # The original hit already names the surviving place.
        return GeoResult(a.point, precision=a.precision, source=a.source,
                         matched=a.label, address=a.address, query=text)
    region = " ".join(region_tokens(text))
    rest = _non_region_part(text)
    if not alts:
        if session.home_check_failures >= _HOME_CHECK_MAX_FAILURES:
            return None
        _reject_home(session)
        session.home_check_failures += 1
        if region and rest:
            return (f"'{region}'에서는 '{rest}'을(를) 찾지 못했어요. 지역이나 이름을 다시 "
                    f"확인해 주세요. (예: {region} ○○동 {rest})")
        return (f"'{text}'은(는) 지도에서 찾지 못했어요. 시·구·동 이름이나 도로명 주소로 "
                "다시 알려주세요. (예: 서울 중랑구 면목동, 서울시 마포구 백범로 35)")
    _reject_home(session)
    session.home_choice_text = text
    session.home_choice_rounds += 1
    if len(alts) <= HOME_ALT_MAX_LIST:
        session.home_choices = [
            {"label": a.label, "address": a.address, "lat": a.point.lat, "lng": a.point.lng,
             "precision": a.precision, "source": a.source} for a in alts]
        listed = "\n".join(f"{i}. {a.label}" for i, a in enumerate(alts, 1))
        return (f"'{text}'에 해당하는 곳이 여러 곳이에요. 어디인가요?\n{listed}\n"
                "번호나 이름으로 답해 주세요.")
    session.home_choices = []
    if res.precision == "address" or not rest:
        ex = ", ".join(a.address for a in alts[:2] if a.address)
        return (f"'{text}'은(는) 전국에 여러 곳이에요. 시·군·구를 함께 알려주세요. "
                f"(예: {ex})")
    # POI — 첫 후보의 동을 빌려 "마포구 망원동 스타벅스"처럼 보탬 형식을 보여준다
    dong = next((t for t in region_tokens(alts[0].address)
                 if t.endswith(("동", "읍", "면", "리")) and not token_in_text(t, text)), "")
    examples = [" ".join(x for x in (region, dong, rest) if x)] if dong else []
    examples.append(alts[0].label)
    return (f"'{region}'에 '{rest}'이(가) 여러 곳이에요. 동 이름이나 지점 이름을 함께 "
            f"알려주세요. (예: {', '.join(examples)})")


def _region_rank(tok: str) -> int:
    """병합 정렬용 — 시/도(0) → 시/군/구(1) → 동(2) → 도로(3). 접미사 없는 "대전"은 맨 앞."""
    if tok.endswith(("구", "군")) or tok in ("중구", "동구", "서구", "남구", "북구"):
        return 1
    if tok.endswith(("동", "읍", "면", "리")):
        return 2
    if tok.endswith(("로", "길")):
        return 3
    if tok.endswith(("시", "도")):
        return 0
    return -1


def _merge_home_refinement(prev: str, addition: str) -> str:
    """"마포구 스타벅스" + "합정동" → "마포구 합정동 스타벅스", "중앙동" + "대전 동구" → "대전 동구 중앙동".

    되묻기 뒤의 짧은 보탬을 새 답으로 취급하면 "합정동" 동 중심이 집이 되고 상호가
    사라진다. 지역 토큰들을 행정 단위 순으로 세우고 나머지(상호)는 뒤에 둔다.

    보탬은 **없던 행정 단위**를 채운다(동에 구를, 구에 동을). 같은 단위가 또 오면
    ("산남동" 뒤에 "성북구 정릉동") 고쳐 말한 새 답이지 보탬이 아니다 — 합치면
    "성북구 산남동 정릉동"이 된다. 그 경우와 보탤 게 없는 경우는 원문을 그대로
    돌려준다 — 호출부가 무변경을 보고 새 답 경로로 넘긴다.
    """
    prev_toks = prev.split()
    region_prev = [t for t in prev_toks if has_region_token(t)]
    rest = [t for t in prev_toks if t not in region_prev]
    new = [t for t in (_strip_tail_particles(t) for t in addition.split()) if t and t not in prev_toks]
    if not new:
        return prev
    prev_levels = {_region_rank(t) for t in region_prev}
    if any(_region_rank(t) in prev_levels for t in new if has_region_token(t)):
        return prev
    # 상호가 있던 답에 지역 아닌 낱말이 또 오면("합정동 이마트") 가게를 바꾼 새 답이다.
    # 순수 주소 답("중앙동")에는 접미사 없는 시/도 이름("대전 동구")을 허용해야 한다.
    if rest and any(not has_region_token(t) for t in new):
        return prev
    return " ".join(sorted(region_prev + new, key=_region_rank) + rest)


def _pick_home_choice(session: InterviewSession, utterance: str) -> dict | None:
    """나열한 보기 중 답이 가리키는 하나 — 번호("2", "2번", "둘째") 또는 이름 부분일치."""
    choices = session.home_choices
    if not choices:
        return None
    compact = _strip_tail_particles(utterance).replace(" ", "")
    m = _CHOICE_NUMBER_RE.match(compact)
    n = int(m.group(1)) if m else _ORDINALS.get(compact)
    if n and 1 <= n <= len(choices):
        return choices[n - 1]
    toks = [t for t in (_strip_tail_particles(t) for t in utterance.split()) if len(t) >= 2]
    hits = [c for c in choices
            if any(token_in_text(t, f"{c['label']} {c['address']}") for t in toks)]
    return hits[0] if len(hits) == 1 else None


def _accept_home_choice(session: InterviewSession, choice: dict) -> None:
    """보기 하나로 집을 확정 — 텍스트는 유일한 표기로 바꿔 요약·finalize·재검증이 같은 곳을 본다."""
    home_text = choice["address"] if choice["precision"] == "address" else choice["label"]
    session.draft_fields["home"] = home_text
    session.home_geo = {
        "query": home_text, "lat": choice["lat"], "lng": choice["lng"],
        "precision": choice["precision"], "source": choice.get("source", "kakao"),
        "matched": choice["label"], "address": choice["address"],
    }
    if "home" not in session.filled_keys:
        session.filled_keys.append("home")
    session.asked_counts.pop("home", None)
    _clear_home_choice(session)


def _resolve_home_choice(session: InterviewSession, utterance: str) -> str | bool | None:
    """되묻기 뒤 답 해석. True = 확정(추출 건너뜀), str = 다시 되물을 문장, None = 새 답으로 취급.

    세 갈래 — (1) 보기 매치, (2) 지역 토큰만 보탠 답은 되물은 원문에 합쳐 재조회,
    (3) 그 외는 처음부터 다시(집 답 전체를 새로 말한 경우). 이 함수는 **추출 전에**
    불려야 한다 — "파주요"를 Mi:dm 에 넘기면 새 집이나 끌림점으로 뽑는다.
    """
    u = _strip_tail_particles(utterance)
    pick = _pick_home_choice(session, u)
    if pick is not None:
        _accept_home_choice(session, pick)
        return True
    if session.home_choice_text and has_region_token(u) and len(u.split()) <= 3:
        merged = _merge_home_refinement(session.home_choice_text, u)
        if merged != session.home_choice_text:
            session.draft_fields["home"] = merged
            reask = _check_home(session)
            if reask:
                return reask
            if "home" not in session.filled_keys:
                session.filled_keys.append("home")
            session.asked_counts.pop("home", None)
            return True
    session.home_choices = []
    session.home_choice_text = ""
    return None


def _ground_profile_fields(session: InterviewSession, prev_slot: SlotSpec,
                           extracted: dict, utterance: str) -> None:
    """추출된 기본 정보를 원문에 대조하고, 신원·집 슬롯의 충족 여부를 정한다.

    충족 판정은 **값이 확보됐는가**만 본다(세션 누적 기준) — 문장을 해석하지 않는다.
    """
    fields = _grounded_fields(session, extracted.get("fields") or {}, utterance)
    extracted["fields"] = fields

    def _have(key: str) -> bool:
        return bool(session.draft_fields.get(key) or fields.get(key))

    if prev_slot.key == "home":
        # 모델이 충족이라 해도 근거 있는 주소가 없으면 다시 묻는다(문장형 답이 주소로
        # 저장돼 충족되던 실측 2026-07-17 — "집에 주로 계세요").
        extracted["slot_filled"] = _have("home")
    if prev_slot.key == "identity" and _have("name") and _have("age"):
        extracted["slot_filled"] = True


_TYPE_KO = {
    PersonaType.dementia: "치매 어르신",
}

# 확인 게이트의 판정(이대로 등록 / 고칠 내용 있음 / 고치겠다고만 함)도 Mi:dm 정정
# 호출의 intent 로 받는다(prompts.CORRECTION_SYSTEM). 예전 규칙이 막던 실측 사례:
# - "…백범로가 정확한 주소예요"의 '예'가 긍정으로 오판돼 정정이 그대로 등록됐다
#   (2026-07-17) → 고칠 내용이 조금이라도 있으면 confirm 이 아니라고 모델에 지시.
# - "아니요, 수정할게요"(무엇을 고칠지 없음)에 같은 요약이 다시 떠 보호자가 멈췄다
#   (2026-08-07) → correct_unspecified 면 고칠 수 있는 항목을 보여주고 되묻는다.


def _ask_what_to_correct(session: InterviewSession) -> str:
    """무엇을 고칠지 되묻는다 — 고칠 수 있는 항목을 그대로 보여준다."""
    grouped, _ = _group_behaviors(session)
    parts = ["성함·나이", "지내시는 곳"]
    if session.draft_attractions:
        parts.append("가시려 할 만한 곳")
    for key in grouped:
        slot = slot_by_key(key)
        if slot is not None:
            parts.append(slot.guardian_label or slot.label)
    listed = "\n".join(f"• {p}" for p in dict.fromkeys(parts))
    return (
        "어느 부분을 고칠까요? 고치실 내용을 함께 말씀해 주시면 바로 반영할게요.\n\n"
        f"{listed}\n\n"
        '예: "집 주소가 틀렸어요, 마포구 신수동이에요" / "망원시장은 빼주세요"'
    )


def _split_tagged_note(note: str) -> tuple[str | None, str]:
    """'{슬롯 라벨}: {노트}' → (슬롯 key, 노트). 접두가 없으면 (None, 원문).

    저장 형식은 _apply_extraction 이 붙이는 라벨 접두(dashboard.html 도 같은 규칙으로
    귀속시킨다). 접두를 떼야 요약에서 슬롯 제목을 한 번만 쓰고 사실만 나열할 수 있다.
    """
    for slot in SLOTS:
        prefix = f"{slot.label}: "
        if note.startswith(prefix):
            return slot.key, note[len(prefix):].strip()
    return None, note


def _group_behaviors(session: InterviewSession) -> tuple[dict[str, list[str]], list[str]]:
    """행동 노트를 슬롯별로 묶는다. 반환 = ({슬롯 key: 노트들}, 접두 없는 노트들).

    draft_behaviors 를 그대로 읽는다(slot_notes 가 아니라) — 확인 게이트는 **실제로
    저장될 내용**을 보여주는 자리이고, 시드·구버전 세션처럼 slot_notes 가 없는
    데이터도 빠짐없이 나와야 하기 때문.

    같은 본문은 한 번만 싣는다 — 추출이 한 답변을 두 번 저장하는 경우가 있어
    (2026-08-05 라이브 실측) 그대로 두면 확인 화면에 같은 줄이 두 번 뜬다.
    표시용 중복 제거라 draft_behaviors 원본은 건드리지 않는다 — 페르소나에는
    그대로 들어가고, 보호자가 지우고 싶으면 등록 상세 화면에서 고친다.
    """
    grouped: dict[str, list[str]] = {}
    loose: list[str] = []
    for note in session.draft_behaviors:
        key, body = _split_tagged_note(str(note))
        if not body:
            continue
        bucket = loose if key is None else grouped.setdefault(key, [])
        if body not in bucket:
            bucket.append(body)
    return grouped, loose


# 필드 슬롯은 '채움 판정'이 아니라 값 자체로 본다 — Mi:dm 이 slot_filled 를 냈지만
# 이름이 안 뽑힌 실측(스텁·장애 모드에서도 재현)에서 요약이 이름 없이 등록을 확인받는다.
_PROFILE_REQUIRED = {"identity": ("name", "age"), "home": ("home",)}


def _unfilled_slots(session: InterviewSession, grouped: dict[str, list[str]]) -> list[SlotSpec]:
    """아직 아무것도 못 받은 슬롯 — 보호자가 보충할 기회를 주기 위해 요약에 노출.

    '못 받았다'의 기준은 filled_keys 만이 아니다. 소진(MAX_ASKS_PER_SLOT)됐거나
    한 번도 안 물은 슬롯도 비어 있는 것은 같고, 반대로 채움 판정이 없어도 노트·
    장소가 남았으면 요약 본문에 이미 보이므로 빈칸이 아니다(같은 항목이 위아래에
    동시에 나오는 모순 방지).

    _scoped_slots(session) 로 이 세션의 target_tiers 안에서만 찾는다 — 전체
    slots_for(ptype) 를 쓰면 미니챗(Tier1)이 이번엔 안 물은 Tier2·3 를, 보완챗
    (Tier2·3)이 이미 다른 세션(미니챗)에서 답한 Tier1 을 "아직 안 알려주신 것"
    으로 잘못 나열한다 — 그 세션의 draft_fields·filled_keys 에 없으니 미입력처럼
    보이지만 실제로는 이전 세션에 저장돼 있다.
    """
    f = session.draft_fields
    place_slots = {str(a.get("origin_slot")) for a in session.draft_attractions}
    out: list[SlotSpec] = []
    for slot in _scoped_slots(session):
        required = _PROFILE_REQUIRED.get(slot.key)
        if required is not None:
            if not all(f.get(k) for k in required):
                out.append(slot)
            continue
        if slot.key in session.filled_keys or grouped.get(slot.key) or slot.key in place_slots:
            continue
        out.append(slot)
    return out


# 압축본이 이보다 길면 줄인 게 아니다 — 원문을 그대로 보여준다.
_DIGEST_MAX = 30


def _digest_notes(session: InterviewSession, notes: list[str]) -> dict[str, str]:
    """확인 요약 표시용 압축 {원문: 짧은 표현}. 못 줄인 것은 원문을 그대로 담는다.

    보호자 발화가 통째로 나열되면 확인 화면이 읽히지 않는다("약을 거르시면 많이
    어지러워 하세요" → "거르면 어지럼증"). **표시만** 바꾼다 — draft_behaviors 와
    slot_quotes 는 손대지 않는다(축 채점 근거·발화 인용 검증이 원문을 쓴다).

    한 번 정한 표현은 캐시해 재사용한다. 정정할 때마다 다시 부르지 않고, 같은
    항목이 재렌더마다 다른 문구로 읽히지 않게 하려는 것이다.
    """
    cache = session.note_digests
    todo = [n for n in dict.fromkeys(notes) if n and n not in cache]
    if todo:
        before = midm.call_failures
        out = midm.condense_notes(todo)
        if midm.call_failures > before:
            session.llm_call_failures += midm.call_failures - before
            session.llm_degraded = True
        for src, digest in zip(todo, out or [""] * len(todo)):
            ok = (digest and len(digest) <= _DIGEST_MAX and len(digest) < len(src)
                  and safety.passes_rules(digest))
            cache[src] = digest if ok else src   # 실패도 캐시 — 렌더마다 재호출 방지
    return cache


def build_summary(session: InterviewSession) -> str:
    """수집 내용 **전부** + 빈칸 안내 + 확인 요청.

    "이게 맞나요?"라고 물으려면 확인할 것을 다 보여줘야 한다 — 접어놓고 묻는 것은
    확인 절차가 아니다(구버전은 장소 3곳·행동 2개만 보이고 나머지를 '외 N가지 저장'
    으로 감췄다). 슬롯 12개 규모라 전량 표시해도 길지 않다.

    행동 노트는 슬롯 단위로 묶어 제목을 한 번만 쓰고, 제목은 내부 라벨이 아니라
    보호자용 표현(SlotSpec.display_label)을 쓴다. 노트 본문은 보호자 발화/Mi:dm
    재서술 그대로 — 확인 게이트에서 문장을 다시 지어내면 확인의 근거가 흔들린다.
    """
    f = session.draft_fields
    lines: list[str] = ["📋 이렇게 등록할게요. 확인 부탁드려요.", ""]

    who: list[str] = []
    if f.get("name"):
        who.append(str(f["name"]))
    if f.get("age"):
        age_num = re.sub(r"[^0-9]", "", str(f["age"]))   # "78세" → "78" (중복 '세' 방지)
        who.append(f"{age_num}세" if age_num else str(f["age"]))
    who.append(_TYPE_KO.get(session.persona_type, "—"))
    lines.append(f"• 대상자: {', '.join(who)}")

    if f.get("home"):
        # 지도에서 어디로 찾았는지 되비춘다 — 검색이 엉뚱한 곳에 걸렸을 때 보호자가
        # 알아챌 수 있는 유일한 지점이 이 확인 화면이다.
        geo = session.home_geo if (session.home_geo or {}).get("query") == f["home"] else None
        found = str((geo or {}).get("address") or (geo or {}).get("matched") or "").strip()
        if geo is None:
            lines.append(f"• 지내시는 곳: {f['home']} (지도에서 아직 확인되지 않음)")
        elif found and _norm(found) != _norm(str(f["home"])):
            lines.append(f"• 지내시는 곳: {f['home']} (지도 확인: {found})")
        else:
            lines.append(f"• 지내시는 곳: {f['home']}")

    places = session.draft_attractions
    if places:
        lines.append("• 가시려 할 만한 곳")
        for ap in places:
            label = str(ap.get("label", "")).strip()
            # 지역이 장소명과 같으면 괄호를 달지 않는다 — "정릉천 산책로 (정릉천
            # 산책로)"처럼 같은 말이 두 번 나온다(2026-08-05 실측). 추출이
            # 지역을 못 집으면 장소명을 그대로 area_text 로 넣기 때문이다.
            area = str(ap.get("area_text") or "").strip()
            suffix = f" ({area})" if area and area != label else ""
            lines.append(f"   - {label}{suffix}")

    grouped, loose = _group_behaviors(session)
    # 표시용 압축 — 저장된 노트는 그대로 두고 화면에서만 짧게(_digest_notes 주석).
    digest = _digest_notes(
        session, [n for ns in grouped.values() for n in ns] + list(loose))

    def _emit(label: str, notes: list[str]) -> None:
        shown_notes = [digest.get(n, n) for n in notes]
        if len(shown_notes) == 1:
            lines.append(f"• {label}: {shown_notes[0]}")  # 하나뿐이면 목록으로 늘리지 않는다
            return
        lines.append(f"• {label}")
        lines.extend(f"   - {n}" for n in shown_notes)

    shown: set[str] = set()
    for slot in slots_for(session.persona_type):
        notes = grouped.get(slot.key)
        if notes:
            _emit(slot.display_label, notes)
            shown.add(slot.key)
    # 유형 밖 슬롯의 노트도 흘리지 않는다 — slots_for 는 유형별로 걸러지므로(치매
    # 단독인 지금은 전 슬롯 통과) 대상 확장 시 저장된 노트가 요약에서만 조용히
    # 사라질 수 있다. '전량 표시'가 이 함수의 계약이라 남은 것을 여기서 흡수한다.
    for key, notes in grouped.items():
        if key not in shown:
            slot = slot_by_key(key)
            _emit(slot.display_label if slot else key, notes)
    if loose:
        lines.append("• 그 밖에 알려주신 것")
        lines.extend(f"   - {digest.get(n, n)}" for n in loose)

    missing = _unfilled_slots(session, grouped)
    if missing:
        lines.append("")
        lines.append("아직 안 알려주신 것 (지금 말씀하셔도 되고, 나중에 채우셔도 됩니다)")
        lines.extend(f"   - {s.display_label}" for s in missing)

    lines.append("")
    lines.append("등록하신 정보가 이게 맞나요? 틀리거나 빠진 부분이 있으면 편하게 말씀해 주세요.")
    return "\n".join(lines)


def start_interview(
    guardian_name: str,
    persona_type: PersonaType | None = None,
    *,
    mode: str = "create",
    target_tiers: list[int] | None = None,
    guardian_id: str = "",
    skip_confirmation: bool = False,
    persona_id: str | None = None,
) -> InterviewSession:
    """새 인터뷰 세션 시작.

    새 키워드 인자(mode/target_tiers/guardian_id/skip_confirmation/persona_id)는
    전부 기본값이 기존 동작과 동일 — 인자 없이 호출하면(기존 모든 호출부) 예전과
    한 글자도 다르지 않다.

    target_tiers 가 Tier1(성함·나이 포함)을 포함하지 않으면(보완챗 — Tier1은 이미
    다른 세션에서 답했다) 하드코딩된 identity 첫 질문을 건너뛰고 스코프 안에서
    첫 질문을 고른다. persona_id 를 미리 주면(supplement/update) 세션이 시작부터
    그 persona 에 연결돼, 완료 시 finalize_persona 가 새로 만들지 않고 병합한다.
    """
    # 유형은 치매 단독 — 인자는 API 하위호환으로만 남기고, 미지정이면 기본값으로 고정한다.
    session = InterviewSession(
        id=storage.new_id(), guardian_name=guardian_name,
        persona_type=persona_type or DEFAULT_PERSONA_TYPE,
        mode=mode, target_tiers=target_tiers, guardian_id=guardian_id,
        skip_confirmation=skip_confirmation, persona_id=persona_id,
    )
    if target_tiers is not None and Tier.route.value not in target_tiers:
        nxt = _next_slot(session)
        if nxt is not None:
            target, _ = nxt
            session.messages.append(
                {"role": "assistant", "text": safety.single_question(target.question)})
            session.prev_target_key = target.key
    else:
        session.messages.append({"role": "assistant", "text": _IDENTITY.question})
        session.prev_target_key = _IDENTITY.key
    storage.interviews.save(session.id, session)
    return session


# tier 집합만으로 persona 상태를 판정 — 슬롯별 answered/value 세분 저장 없이도
# "1차 미니챗만 끝났나·전부 끝났나"를 구분하기에 충분하다(설계 스코프 축소).
_ALL_TIERS = {Tier.route.value, Tier.capacity.value, Tier.refine.value}


def persona_status_for(persona: Persona | None) -> tuple[str, str]:
    """(persona_status, available_mode) — none/create, partial/supplement, complete/update.

    completed_tiers 가 비어 있는데 persona 는 존재하면(예: register_persona 구조화
    직접등록처럼 이 인터뷰 흐름을 안 거친 persona) 이미 필드가 다 있다고 보고
    complete 취급한다 — tier 정보가 없다고 재등록을 강요하지 않는다.
    """
    if persona is None:
        return "none", "create"
    tiers = set(persona.completed_tiers)
    if not tiers or _ALL_TIERS <= tiers:
        return "complete", "update"
    if Tier.route.value in tiers:
        return "partial", "supplement"
    return "none", "create"


def _norm(s: str) -> str:
    return re.sub(r"[\s()]+", "", str(s or ""))


# area_text 플레이스홀더 정규화는 지오코딩 계층이 단일 소스 (geo.geocode.clean_area_text).
_clean_area = clean_area_text


# evidence 강도 순위 (낮을수록 강함) — 중복 언급 시 더 강한 근거로만 승격
_EVIDENCE_RANK = {"previous_missing_found": 0, "caregiver_report": 1, "mention_only": 2}

_GRADED_EVIDENCE = ("previous_missing_found", "caregiver_report")


def _compact(text) -> str:
    """원문 대조용 — 공백·문장부호 차이만 지운다(글자는 바꾸지 않는다)."""
    return re.sub(r"[\s.,!?~'\"“”‘’()\[\]·…-]+", "", str(text or ""))


def _in_answer(fragment, text) -> bool:
    """모델이 원문에서 가져왔다고 낸 표현이 그 글에 글자 그대로 있는가."""
    f = _compact(fragment)
    return bool(f) and f in _compact(text)


def _midm_tracked(session: InterviewSession, call):
    """Mi:dm 호출 실패(침묵 폴백)를 세션 플래그로 드러낸다 — _extract_tracked 와 같은 원칙."""
    before = midm.call_failures
    out = call()
    if midm.call_failures > before:
        session.llm_call_failures += midm.call_failures - before
        session.llm_degraded = True
    return out


def _ground_point(session: InterviewSession, ap: dict, utterance: str, last_q: str) -> bool:
    """추출된 장소 하나를 이 답변 원문에 대조한다. 이 답변에서 나온 장소가 아니면 False.

    장소와 근거 강도의 **해석은 Mi:dm 이 한다**. 코드는 모델이 낸 이름·원문 구절(quote)이
    답에 실제로 있는지만 본다(보호자 문장을 단어 목록으로 분류하지 않는다).

    - 라벨이 이 답에 없으면 받지 않는다. 직전 질문의 장소를 가리키는 답은 그 질문과
      원문 quote를 함께 확인한다. 무관한 발화 quote만 붙인 이전 장소 재출력은 버린다. 라이브 실측(2026-07-22): "대흥역에서 발견한 적이 있어요"에 Mi:dm 이 이전
      턴의 망원시장을 냈다.
    - 근거 강도(발견지·반복 지향)는 quote 가 답에 있고 장소 이름이 답이나 직전 질문에
      있을 때만 인정한다. 위 실측에서 '발견' 근거가 엉뚱한 망원시장에 붙어 0.9 를 받았다.
    - 발견지(가중치 최상위)는 좁은 질문으로 한 번 더 확인한다(midm.verify_found). 실측
      (2026-07-22): "망원시장에서 가게를 하신 적이 있어서 거기에 가야 한다고…"가 발견지로
      분류됐다.
    내린 근거는 extraction_audit 에 남긴다(무엇을 왜 내렸는지 추적 가능하게).
    """
    label, quote = str(ap.get("label") or ""), str(ap.get("quote") or "")
    if not (_label_grounded(label, utterance)
            or (_in_answer(label, last_q) and _in_answer(quote, utterance))):
        session.extraction_audit.append(
            {"event": "point_not_in_answer", "label": label, "quote": quote})
        return False
    claimed = ap.get("evidence")
    if claimed not in _GRADED_EVIDENCE:
        ap["evidence"] = "mention_only"
        return True
    reason = None
    if not _in_answer(quote, utterance):
        reason = "quote_not_in_answer"
    elif not (_in_answer(label, utterance) or _in_answer(label, last_q)):
        reason = "place_not_named_here"
    elif claimed == "previous_missing_found":
        found = _midm_tracked(session, lambda: midm.verify_found(label, last_q, utterance))
        if found is not True:
            reason = "found_not_confirmed" if found is False else "found_check_unavailable"
    if reason:
        ap["evidence"] = "mention_only"
        session.extraction_audit.append(
            {"event": "evidence_downgraded", "label": label, "claimed": claimed, "reason": reason})
    return True


def _new_places_in_answer(session: InterviewSession, extracted: dict, utterance: str) -> bool:
    """이 답변에서 **새로** 나온 장소가 추출에 하나라도 있나 — 재추출 여부 판단용.

    이미 등록된 장소를 이름이 답에 없는데 다시 낸 것은 새 장소가 아니다(위 망원시장 실측).
    """
    known = {_norm(a.get("label")) for a in session.draft_attractions}
    for ap in extracted.get("attraction_points") or []:
        label = str(ap.get("label") or "")
        if _in_answer(label, utterance):
            return True
        if _norm(label) not in known and _in_answer(ap.get("quote"), utterance):
            return True
    return False


# 노트 근거 검증 — 라이브 실측(2026-07-17): Mi:dm 이 답변에 없는 프롬프트 예시 문구
# ("길 잃으면 계속 걷는 편")까지 노트로 만들어냈다. 노트의 내용 토큰이 답변·직전
# 질문에 하나도 없으면 환각으로 본다. 어휘가 전혀 겹치지 않는 정당한 의역을 잃을 수
# 있는 트레이드오프지만, 환각이 예측 입력을 오염하는 쪽이 더 나쁘다.
# 무지·거부 답("잘 모르겠어요")을 단어로 거르던 목록은 없앴다 — answer_kind 가
# unknown·unclear_question·already_answered 이면 호출부가 노트를 받지 않는다.
def _note_grounded(note: str, context: str) -> bool:
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


def _label_grounded(label: str, utterance: str) -> bool:
    """끌림점 라벨이 **이번 발화**에 실제로 있나 — 없으면 이전 대화에서 되뱉은 것이다.

    프롬프트(prompts.build_extract_input)가 "이전 대화에서 이미 나온 장소는 다시 넣지
    마라"고 해도 Mi:dm 2.5 는 장소가 하나도 없는 복약 답변("혈압약이랑 치매약을…")에
    '면목동 방앗간'을 붙여 보냈다(run_eval D1 추적 2026-09-26). 그 결과 같은 방앗간이
    '옛 방앗간'·'면목동 방앗간' 두 개로 쌓이고 과다추출로 잡혔다. _area_grounded 와
    같은 원칙 — 발화에 없는 값은 모델이 지어낸 것. 라벨 전체 또는 토큰의 **앞 2자**
    (어간 근사: '예전에'→'예전', '살던'→'살던')가 하나라도 발화에 있으면 통과 —
    관대한 쪽이다. "예전에 살던 집"은 "예전 집에 가야한다고"에서 살아남아야 한다.
    """
    n, u = _norm(label), _norm(utterance)
    if not n or not u:
        return True
    if n in u:
        return True
    return any(tok[:2] in u for tok in re.findall(r"[가-힣A-Za-z0-9]{2,}", str(label)))


# 집 위치를 설명하는 꼬리표 — "정릉초등학교 **근처**예요"의 학교는 가는 곳이 아니다.
_LOCATOR_SUFFIXES = ("근처", "옆", "앞", "뒤", "부근", "인근", "건너편", "맞은편", "사거리")


def _is_home_locator(label: str, utterance: str) -> bool:
    """집 답변에서 라벨 바로 뒤에 위치 꼬리표가 붙었나 — 그러면 집을 가리키는 기준점이다.

    Mi:dm 2.5 는 "성북구 정릉동이요. 정릉초등학교 근처예요"에서 정릉초등학교를 끌림점으로
    뽑을 때가 있다(run_eval 9개 중 7개, 2.0 은 0건). 집 턴의 장소를 전부 버리면
    "주중 낮에는 주간보호센터에 계십니다"(슬롯 probes 가 묻는 것)까지 잃으므로, 꼬리표가
    붙은 기준점만 거른다.
    """
    # 라벨 자체가 꼬리표를 달고 올 때가 있다("정릉초등학교 근처" — 라이브 실측 2026-09-26).
    # 그러면 발화에서 라벨 뒤는 "예요"라 위 규칙을 빠져나가므로, 꼬리표를 뗀 핵심
    # 지명으로 다시 본다. 뗀 결과가 달라졌다는 것 자체가 기준점 표현이라는 뜻이다.
    core = str(label or "").strip()
    for suffix in _LOCATOR_SUFFIXES:
        if core.endswith(suffix):
            core = core[:-len(suffix)].strip()
            break
    if core != str(label or "").strip():
        return True
    n, u = _norm(core), _norm(utterance)
    if not n or n not in u:
        return False
    tail = u[u.index(n) + len(n):]
    return tail.startswith(_LOCATOR_SUFFIXES)


def _merge_target(ap: dict, by_key: dict) -> str | None:
    """새 끌림점을 병합할 기존 라벨 키 — 모델의 same_as + 라벨 포함 + 지역-둔갑. 없으면 None.

    같은 곳을 다른 말로 부른 것("옛날 집" = "예전에 살던 집")은 모델이 same_as 로 짚는다
    (prompts.EXTRACT_SYSTEM, 등록된 장소 목록을 함께 준다). 실측(2026-07-23 D2): Mi:dm 이
    옛집을 나중 턴에 '예전 집'·'마포구 신수동 옛날 집'으로 되뱉어 같은 집이 3조각으로
    쌓였다. 예전에는 라벨에 '옛·예전'과 '집'이 있는지 코드가 봤다. 이제 답에 없는 재출력은
    원문 대조(_ground_point)가 버리고, 답에 다시 나온 같은 곳은 모델이 same_as 로 묶는다.
    """
    key = _norm(ap.get("label"))
    if not key:
        return None
    if key in by_key:
        return key
    same = _norm(ap.get("same_as"))
    if same and same in by_key:
        return same
    for k, ex in by_key.items():
        # ① 포함 관계 라벨("대흥역" vs "대흥역 2번 출구") — 3자 미만은 오병합 위험
        if (k in key and len(k) >= 3) or (key in k and len(key) >= 3):
            return k
        ex_area = _norm(_clean_area(ex.get("area_text")))
        # ② 지역이 라벨로 둔갑 — 새 라벨이 기존 장소의 지역 그 자체(되묻기 주소가
        #    이후 턴에 별개 장소로 재추출됨). "신수동"⊂"마포구 신수동" 도 흡수.
        if ex_area and len(key) >= 2 and (key == ex_area or key in ex_area):
            return k
    return None


def _apply_extraction(
    session: InterviewSession, prev_slot: SlotSpec, extracted: dict,
    *, overwrite: bool = False, utterance: str = "",
) -> None:
    # 필드는 first-wins — 한 번 정해진 name/age/home/type 을 이후 답변이 덮어쓰지 못하게.
    # (특히 현재 집을 과거 거주지 답변이 덮어쓰던 버그 방지.)
    # 단 확인 게이트의 '정정' 발화는 보호자가 명시적으로 고치는 것 — overwrite=True 로
    # 덮어쓴다. (라이브 실측 버그: 요약 후 나이 정정이 first-wins 에 막혀 무시됨.)
    for k, v in _flatten_fields(extracted.get("fields", {}) or {}).items():
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
    last_q = next((m["text"] for m in reversed(session.messages)
                   if m["role"] == "assistant"), "")
    for ap in extracted.get("attraction_points", []) or []:
        key = _norm(ap.get("label"))
        if not key:
            continue
        if home_txt and key in home_txt:
            continue
        if utterance and prev_slot.key == "home" and _is_home_locator(str(ap.get("label")), utterance):
            continue  # 집 기준점은 목적지가 아니다 (#257).
        ap["area_text"] = _clean_area(ap.get("area_text"))
        # 이 답변 원문에 대조 — 재출력·지어낸 장소는 버리고, 근거 없는 강도는 내린다.
        if utterance and not _ground_point(session, ap, utterance, last_q):
            continue
        # 지역 표기도 답에 있어야 한다. 모델이 "언급 없음" 같은 자리표시나 현재 집 동네를
        # 채우는 실측(2026-07-21)이 있었다 — 예전에는 자리표시 단어 목록으로 걸렀다.
        if utterance and ap["area_text"] and not _area_grounded(ap["area_text"], utterance):
            session.extraction_audit.append(
                {"event": "area_not_in_answer", "label": str(ap.get("label")),
                 "area": ap["area_text"]})
            ap["area_text"] = ""
        # 이 답변이 나온 슬롯 — unfamiliarity 게이지 폴백 판단(작업4)의 origin_slot 원료.
        ap.setdefault("origin_slot", prev_slot.key)
        # 포함 관계 라벨("대흥역" vs "대흥역 2번 출구") + 옛집류 변종 + 지역-둔갑 병합.
        # 3자 미만 라벨은 오병합 위험("시장" ⊂ "망원시장")이 커서 정확 일치만(_merge_target).
        match = _merge_target(ap, by_key)
        if match is None:
            by_key[key] = ap
            session.draft_attractions.append(ap)
            continue
        kept = by_key[match]
        if _EVIDENCE_RANK.get(ap.get("evidence"), 9) < _EVIDENCE_RANK.get(kept.get("evidence"), 9):
            kept["evidence"] = ap["evidence"]
        # 지역 표기는 있는 쪽을 보존. 단 확인 게이트의 '정정'(overwrite)은 이미 있는
        # 표기도 덮는다 — 보호자가 "그 집 주소는 산남동이에요"라고 고쳐 말해도
        # 기존 값이 있다는 이유로 무시되던 실측 버그(2026-07-21).
        if ap.get("area_text") and (overwrite or not kept.get("area_text")):
            kept["area_text"] = ap["area_text"]
        if not kept.get("origin_slot") and ap.get("origin_slot"):
            kept["origin_slot"] = ap["origin_slot"]   # 어느 슬롯에서 처음 나왔는지도 first-wins
        if not kept.get("name_kind") and ap.get("name_kind"):
            kept["name_kind"] = ap["name_kind"]       # 고유 이름/일반 명칭 판정도 처음 것을 유지
        # 같은 장소의 첫 추출에는 유형이 없고 후속 답변에서 유형을 얻는 경우.
        # 모델이 실제로 낸 값만 보존한다. 라벨 단어로 추정하거나 기존 유형을
        # 조용히 덮어쓰지 않는다. 2026-10-08 실제 온보딩 캡처에서 소실 재현.
        incoming_type = ap.get("place_type")
        if (not kept.get("place_type") and isinstance(incoming_type, str)
                and incoming_type.strip()):
            kept["place_type"] = incoming_type.strip()
            session.extraction_audit.append({
                "event": "place_type_backfilled", "label": kept.get("label"),
                "place_type": kept["place_type"], "origin_slot": prev_slot.key,
                "quote": str(ap.get("quote") or ""),
            })
    got_note = False
    # 모른다·질문을 되물음·이미 답함(모델 판정)은 사실이 아니다 — 노트를 받지 않는다.
    # 실측(2026-07-17): Mi:dm 이 "잘 모르겠어요"를 노트로 복사했다.
    kind = extracted.get("answer_kind")
    no_facts = kind in ("unknown", "unclear_question", "already_answered")
    # 슬롯 무관 원노트 중복 차단 — 같은 사실("많이 배회하세요")이 겨냥 슬롯만 바꿔
    # 여러 번 저장되던 라이브 실측(2026-07-17 2차). 어미 변형·부분 재진술까지
    # 자카드로 잡는다(3차). profile 슬롯(identity/home)은 필드 수집 전용이라
    # 행동 노트를 받지 않는다 — "현재 거주지: 길 잃었을 때…" 오귀속 방지.
    seen_notes = [n for notes in session.slot_notes.values() for n in notes]
    notes_in = ([] if prev_slot.axis == Axis.profile or no_facts
                else extracted.get("behavior_notes", []) or [])
    for note in notes_in:
        if _is_dup_note(note, seen_notes) \
                or not _note_grounded(note, f"{utterance} {last_q}"):
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
    # 노트 폴백 — Mi:dm 이 slot_filled 만 내고 behavior_notes 를 비워 보내는 실측
    # (2026-07-21 라이브, "혈압약을 저녁에만 드세요" → notes [] 3/3). 그대로 두면
    # 보호자가 말한 사실이 axis_evidence 에서 통째로 사라진다(대화는 했는데 저장이
    # 안 되는 상태). 재서술이 없으면 **원발화 자체**를 근거로 남긴다 — 축 채점은
    # 원발화를 1차 근거로 쓰므로 형태상 문제도 없다.
    # 단, 모델이 노트를 **냈는데** 중복·환각 필터에 걸린 경우는 폴백하지 않는다 —
    # 그건 이미 저장된 사실이거나 버려야 할 사실이지, 유실이 아니다.
    # `slot_filled` 을 조건에서 뺐다(2026-08-07). Mi:dm 이 멀쩡한 답변에 추출을
    # 통째로 빈손으로 내는 실측이 있다 — "네 신호도 잘 지키시고 위험 감지 능력은
    # 있으세요"에 노트 0·slot_filled=false → 슬롯이 안 닫혀 같은 질문이 다시 나갔고
    # 보호자가 한 말은 어디에도 저장되지 않았다. 모델 판정과 무관하게, 실질적인
    # 답변이면 원발화를 근거로 남긴다(아래에서 충족 처리까지 이어진다).
    # 단순 긍정("네 맞아요")·항의("답변 했잖아")는 사실이 아니다 — 폴백을 넓히면서
    # 이런 답이 행동 노트로 저장되던 것을 막는다(2026-08-07 실측: "불안하실 때
    # 하시는 행동: 네 맞아요", "위험한 곳을 피하실 수 있는지: 답변 완료").
    # 그래서 모델이 사실이 담긴 답(informative)이라고 판정한 경우에만 원발화를 남긴다.
    # 판정이 없으면(호출 실패) 남기지 않는다 — 원문은 slot_turns 에 이미 있다.
    # 슬롯 충족은 answer_interview 의 negation_fill·affirmation_fill 경로가 따로 판단한다.
    if (not got_note and not notes_in and prev_slot.axis != Axis.profile and utterance
            and kind == "informative"
            and not _is_dup_note(utterance, seen_notes)):
        tagged = f"{prev_slot.label}: {utterance}"
        if tagged not in session.draft_behaviors:
            session.draft_behaviors.append(tagged)
            session.slot_notes.setdefault(prev_slot.key, []).append(utterance)
            got_note = True

    # 노트를 실제로 저장했는데 모델이 slot_filled 를 안 낸 경우 — 충족으로 본다.
    # 라이브 실측(2026-08-07): "네 신호도 잘 지키시고 그런 것들에서 위험했던 적은
    # 없어요"에 Mi:dm 이 notes=['신호를 잘 지킴'] 를 내면서 slot_filled=false 를 냈다.
    # 슬롯을 닫는 건 slot_filled 뿐이라 후보 풀에 남았고, **같은 질문이 8턴 뒤에
    # 그대로 다시 나갔다**(보호자 답변: "답변 했잖아"). 내용을 받고도 닫지 않으면
    # 보호자에겐 대화가 안 먹힌 것으로 보인다. 위쪽 노트 폴백(slot_filled=true 인데
    # notes 가 빈 경우)의 거울상 — 같은 원칙으로 코드가 판정을 메운다.
    # 얕게 채워진 경우는 _needs_probe 가 안 들은 각도를 1회 파고들므로 깊이도
    # 잃지 않는다(같은 질문 재탕 대신 다른 각도가 나간다).
    if got_note and not extracted.get("slot_filled"):
        extracted["slot_filled"] = True

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


def _scoped_slots(session: InterviewSession) -> list[SlotSpec]:
    """이 세션이 물을 수 있는 슬롯 후보 — session.target_tiers 로 좁힌 slots_for.

    target_tiers 가 None(기본값, 기존 온보딩 전체 흐름)이면 slots_for 와 완전히
    동일(전체 슬롯) — 신고 전 미니챗([1]만)·보완챗([2,3]만) 같은 부분 인터뷰에서만
    실제로 좁아진다. 답변 처리·추출·가드 알고리즘 자체는 손대지 않고 후보 목록만
    제한한다.
    """
    return slots_for(session.persona_type, session.target_tiers)


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
    # target_tiers 로 좁힌 세션(미니챗·보완챗)이면 그 tier 밖 슬롯은 애초에 후보에서
    # 뺀다 — rank_next_slots 에 allowed_keys 로 넘겨 top_k 로 자르기 전에 걸러지게
    # 한다(사후 필터로는 top_k=5 가 전부 Tier1로 채워지는 경우를 못 막았다).
    allowed_keys = (
        {s.key for s in _scoped_slots(session)} if session.target_tiers is not None else None
    )

    ranked, _ = retrieval.rank_next_slots(
        session.persona_type, _user_turns(session), avoid, _EMB,
        top_k=5, asked_counts=session.asked_counts, allowed_keys=allowed_keys,
    )
    if not ranked and avoid != blocked:
        ranked, _ = retrieval.rank_next_slots(
            session.persona_type, _user_turns(session), blocked, _EMB,
            top_k=5, asked_counts=session.asked_counts, allowed_keys=allowed_keys,
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
    return all(s.key in blocked for s in _scoped_slots(session))


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

    # 1) 직전 겨냥 슬롯 추출 (이름·나이·집 주소는 원문 대조 후 반영)
    prev_slot = slot_by_key(session.prev_target_key) if session.prev_target_key else None
    # 보호자 답은 어떤 판정보다 먼저, 질문과 함께 그대로 남긴다. 모름·부정·짧은 답의
    # 뜻은 K 가 원문으로 해석한다. 신원·집 주소는 개인정보 필드라 행동 근거에서 제외.
    if prev_slot is not None and prev_slot.axis != Axis.profile:
        session.slot_turns.append({"slot": prev_slot.key, "question": _last_question(session),
                                   "answer": clean, "recorded_at": datetime.now(timezone.utc).isoformat()})

    got_something = True   # 이번 답에서 뭐라도 건졌나 — 빈손이면 직전 슬롯 재선택 회피
    # 0.7) 집 되묻기("산남동 — 파주요, 청주요?")에 대한 답은 **추출 전에** 가로챈다.
    #      "2번이요"·"청주요"·"합정동이요"는 새 사실이 아니라 보기 선택이다.
    chosen = False
    if prev_slot is not None and prev_slot.key == "home" and session.home_choice_rounds > 0:
        outcome = _resolve_home_choice(session, clean)
        if isinstance(outcome, str):
            session.messages.append({"role": "assistant", "text": outcome})
            storage.interviews.save(session.id, session)
            return session
        chosen = outcome is True
    if prev_slot is not None and not chosen:
        extracted = _extract_tracked(session, prev_slot)
        # 답변 유형은 모델 판정(answer_kind). None 이면(호출 실패) 유형별 처리를 하지
        # 않는다 — 같은 슬롯을 한 번 더 묻고, 계속 실패하면 재질문 예산이 소진시킨다.
        kind = extracted.get("answer_kind")

        # 0.5) "그게 무슨 뜻이에요?" — 답을 못 받은 게 아니라 질문이 잘못 나간 것이다.
        #      추출 결과는 쓰지 않고(내용이 없다) 재질문 예산도 깎지 않은 채, 쉬운 말로
        #      풀어 한 번 더 묻는다. 슬롯당 1회 — 그래도 못 알아들으면 예산 경로로 넘어간다.
        #      라이브 실측(2026-08-07): "구체적 목격 사례가 무슨 의민지 모르겠어요"에
        #      아무 설명 없이 다음 슬롯으로 넘어가, 보호자 질문이 통째로 무시됐다.
        if (GUARDS["clarify"] and kind == "unclear_question" and not session.pending_area_label
                and prev_slot.key not in session.clarified_keys):
            session.clarified_keys.append(prev_slot.key)
            q = _clarify_question(session, prev_slot, clean)
            session.messages.append(
                {"role": "assistant", "text": _personalize(q, session.persona_type)})
            session.prev_target_key = prev_slot.key
            storage.interviews.save(session.id, session)
            return session

        # 과거 장소 슬롯에서 사실이 담긴 답인데 이 답의 장소가 하나도 안 잡혔으면 1회
        # 재추출 — Mi:dm 이 같은 입력에도 이따금 빈 배열을 내고(실측: 재시도 6/6 회복),
        # 이름 없는 과거 장소("예전에 살던 집")는 장소로 안 뽑거나(0/3), 이전 턴 장소를
        # 대신 낸다(대흥역 답에 망원시장). 여기서 놓치면 과거 발견지·옛집 같은 가장 강한
        # 목적지가 통째로 사라진다. 재추출은 무엇이 빠졌는지 알려 모델이 다시 판단한다.
        if (prev_slot.key in _PAST_PLACE_SLOTS and kind == "informative"
                and not session.pending_area_label
                and not _new_places_in_answer(session, extracted, clean)):
            retry = _extract_tracked(session, prev_slot, recheck_places=True)
            if _new_places_in_answer(session, retry, clean):
                extracted = {**retry, "answer_kind": kind}
        _ground_profile_fields(session, prev_slot, extracted, clean)
        got_something = bool(
            extracted.get("fields") or extracted.get("attraction_points")
            or extracted.get("behavior_notes")
            or extracted.get("slot_filled")
        )
        if session.pending_area_label:
            # 되묻기 답변("산남동이요")은 주소일 뿐 새 장소가 아니다 — 그대로 두면
            # Mi:dm 이 "산남동"을 별개 끌림점으로 추가한다.
            extracted["attraction_points"] = []
        _apply_extraction(session, prev_slot, extracted, utterance=clean)
        _resolve_pending_area(session, clean)
        if prev_slot.key == "home":
            home_reask = _check_home(session, utterance=clean, answer_kind=kind)
            if home_reask:
                session.messages.append({"role": "assistant", "text": home_reask})
                storage.interviews.save(session.id, session)
                return session
        # 모른다고만 한 답("모르겠다니까요")이면 그 슬롯은 즉시 소진 — 같은 것을
        # 또 물어 보호자를 지치게 하지 않는다(라이브 실측 2026-07-17 2차).
        # "답변 했잖아"(이미 답했다는 항의)도 새 사실이 없으므로 더 묻지 않는다.
        # 실측에서 이 발화가 사실로 저장돼 요약에 "위험한 곳을 피하실 수 있는지:
        # 답변 완료"로 찍혔다(2026-08-07).
        if GUARDS["ignorance_exhaust"] and kind in ("unknown", "already_answered") \
                and prev_slot.key not in session.filled_keys:
            session.asked_counts[prev_slot.key] = MAX_ASKS_PER_SLOT
        # 해당 없다는 답("딱히 없어요")은 '해당 없음'으로 **충족** 처리 — 모름과 달리
        # 답을 받은 것이다(라이브 실측 2026-07-17 4차: "딱히 없어요"를 무시하고 재질문).
        # profile 슬롯(이름·집)은 부정으로 채울 수 없어 제외.
        if GUARDS["negation_fill"] and kind == "none" \
                and prev_slot.axis != Axis.profile \
                and prev_slot.key not in session.filled_keys:
            session.filled_keys.append(prev_slot.key)
            session.asked_counts.pop(prev_slot.key, None)
        # 긍정만 한 답("네")도 **유효한 답**이다. 씨앗 질문 상당수가 여부를 묻는
        # 문형("…피할 수 있나요?", "…경우가 있나요?")이라 보호자는 한 마디로 답한다.
        # 부정만 충족 처리하고 긍정은 안 하던 비대칭 때문에 슬롯이 안 닫혀 위험 인지
        # 질문이 세 번 나갔고, 보호자가 "답변 했잖아"라고 했다(라이브 실측 2026-08-07).
        # 노트는 남기지 않는다 — 원문은 질문과 함께 slot_turns 에 있다.
        if GUARDS["affirmation_fill"] and kind == "yes_only" \
                and prev_slot.axis != Axis.profile \
                and prev_slot.key not in session.filled_keys:
            session.filled_keys.append(prev_slot.key)
            session.asked_counts.pop(prev_slot.key, None)
        # 과거 장소를 새로 얻었으면 그 자리에서 주소를 묻는다 — 좌표 없는 끌림점은
        # 예측에 못 들어가므로 "장소를 들었다"와 "끌림점이 생겼다"는 다른 일이다.
        area_q = _ask_area_for_new_place(session, prev_slot, extracted, clean)
        if area_q:
            session.messages.append({"role": "assistant", "text": area_q})
            storage.interviews.save(session.id, session)
            return session
        # 얕은 답이면 같은 슬롯의 하위 항목(probes)을 1회 파고든다 — Mi:dm 의
        # slot_filled 판정만 믿으면 하위 항목을 영영 못 묻는다(위 _needs_probe 주석).
        # 빈손 답변은 파고들지 않는다 — 그건 '충족 실패'라 기존 재질문 예산
        # (asked_counts·MAX_ASKS_PER_SLOT)이 담당한다. 파고들기는 모델이 '다 받았다'
        # (slot_filled)고 판정했는데 실제로는 얕은 경우만이다.
        if extracted.get("slot_filled") and _needs_probe(session, prev_slot, kind):
            # 슬롯당 1회 — 물었든 '물 게 없다'로 접었든 소진 처리한다(모델 재호출 방지).
            session.probed_keys.append(prev_slot.key)
            probe_q = _probe_question(session, prev_slot)
            if probe_q:
                session.messages.append(
                    {"role": "assistant", "text": _personalize(probe_q, session.persona_type)})
                session.prev_target_key = prev_slot.key
                storage.interviews.save(session.id, session)
                return session
            # 빈손이면 파고들지 않고 다음 슬롯으로 — 재탕·내부 용어를 내보내지 않는다.

    # 2) 유형 — 치매 단독이라 되묻지 않는다. 과거 세션(유형 미지정 저장본)이 복원될
    #    수 있으므로 여기서 한 번 더 기본값을 보장한다(slots_for(None) = 빈 목록 방지).
    if session.persona_type is None:
        session.persona_type = DEFAULT_PERSONA_TYPE

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
        # 요약 전 '주소 없는 끌림점' 되묻기 — 장소당 1회. 좌표가 없으면 그 장소는
        # 예측에 못 들어가고 finalize 에서 조용히 버려지므로, 닫기 전에 한 번은 묻는다.
        pending = [a for a in _arealess_attractions(session)
                   if str(a.get("label")) not in session.asked_area_labels]
        if pending:
            label = str(pending[0]["label"])
            session.asked_area_labels.append(label)
            session.pending_area_label = label
            session.messages.append({"role": "assistant", "text": (
                f"'{label}'은 어느 동네인가요? 동 이름이나 근처 건물·가게 이름이면 됩니다. "
                "(모르시면 '모르겠어요'라고 답해주세요)")})
            # 추출은 그 장소가 나온 슬롯 맥락에서 — 답이 그 슬롯 근거로도 쌓이게 한다.
            session.prev_target_key = str(pending[0].get("origin_slot")
                                          or "autobiographical_destination_pull")
            storage.interviews.save(session.id, session)
            return session
        # 긴급 미니챗(신고 전 Tier1) 전용 — 요약 확인 왕복을 생략하고 마지막 답변
        # 직후 바로 확정한다. 그 외 흐름(create/scope=all·supplement·update)은
        # 아래의 기존 '요약 → 확인' 게이트를 그대로 거친다.
        if session.skip_confirmation:
            try:
                finalize_persona(session)
                msg = "확인 감사합니다. 신고 화면으로 이동합니다."
            except ValueError as e:
                # finalize 실패(예: home 좌표화 실패) — _handle_confirmation 의 동일
                # 처리와 일관되게 세션을 열어둔 채 home 재질문으로 복귀시킨다.
                session.draft_fields.pop("home", None)
                session.home_geo = None
                if "home" in session.filled_keys:
                    session.filled_keys.remove("home")
                home_slot = slot_by_key("home")
                session.prev_target_key = home_slot.key
                session.asked_counts[home_slot.key] = 1
                msg = (f"등록 중 문제가 있었어요({e}). "
                       f"{safety.single_question(home_slot.question)}")
            session.messages.append({"role": "assistant", "text": msg})
            storage.interviews.save(session.id, session)
            return session

        # 종료 대신 '요약 → 확인' 단계로 진입
        session.awaiting_confirmation = True
        session.messages.append({"role": "assistant", "text": build_summary(session)})
        storage.interviews.save(session.id, session)
        return session

    # 4) 다음 슬롯 문장화 + 가드레일
    target, is_followup = nxt
    ptype = session.persona_type
    # 호칭 치환("대상자는" → "어르신은")은 **중복 판정보다 먼저** 한다. 저장되는
    # 문장은 치환된 것인데 비교값이 씨앗 원문이면 같은 질문을 못 알아본다 — 라이브
    # 실측(2026-08-07): 위험 인식 질문이 토씨 하나 안 틀리고 두 번 나갔고 재질문
    # 프리픽스조차 안 붙었다. 씨앗에 "대상자"가 들어간 슬롯 6개(12개 중)가 영향.
    seed_q = _personalize(safety.single_question(target.question), ptype)
    raw_q = _phrase_tracked(session, target, is_followup)
    question, _fallback = safety.guard_question(
        raw_q, target, _EMB, bank=_scoped_slots(session))
    if GUARDS["presupposition"] and not _presupposition_grounded(session, question):
        question = seed_q   # 근거 없는 전제 → 씨앗 질문
    if GUARDS["existence_first"] and not _slot_collected(session, target) \
            and _NEG_CONDITIONAL_RE.search(question):
        question = seed_q   # 여부 확인 전의 세부 질문 → 씨앗
    question = _dedupe_question(session, target, _personalize(question, ptype))
    if _norm_q(question) == _norm_q(seed_q):
        question = _personalize(_seed_with_example(target), ptype)   # 씨앗이 그대로 나가면 예시를 붙인다

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
}


def _personalize(question: str, ptype: PersonaType | None) -> str:
    for src, dst in _HONORIFIC.get(ptype, {}).items():
        question = question.replace(src, dst)
    return question


_REASK_PREFIXES = [
    "죄송해요, 한 번만 더 여쭐게요. ",
    "확인이 필요해서 다시 여쭤봅니다. 아시는 만큼만 편하게 알려주세요. ",
]


def _bare_question(q: str) -> str:
    """질문의 알맹이 — 재질문 프리픽스와 "(예: …)" 를 벗긴다.

    같은 질문인지 토큰으로 견줄 때 쓴다. 이 껍데기들은 질문 내용이 아니라 포장인데,
    토큰 수가 적지 않아(프리픽스만 8토큰) 그대로 두면 자카드 분모를 부풀린다.
    """
    out = re.sub(r"\(예:.*?\)", "", q)
    for p in _REASK_PREFIXES:
        if out.startswith(p):
            out = out[len(p):]
            break
    return out.strip()


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

    비교도 반환도 **호칭을 치환한 뒤**의 문장으로 한다 — 저장되는 것이 그 형태라,
    씨앗 원문("대상자는…")으로 견주면 이미 나간 질문을 놓친다(2026-08-07 실측).
    호출자는 치환된 question 을 넘겨야 한다(_personalize 는 멱등이라 이중 적용 무해).
    """
    if not GUARDS["dedup"]:
        return question   # 가드 스윕: 중복 방지 끔
    asked = {_norm_q(m["text"]) for m in session.messages if m["role"] == "assistant"}
    if _norm_q(question) not in asked:
        return question
    seed = _personalize(safety.single_question(target.question), session.persona_type)
    if _norm_q(seed) not in asked:
        return seed
    n = session.asked_counts.get(target.key, 0)
    return _REASK_PREFIXES[n % len(_REASK_PREFIXES)] + seed


def _mentioned_place(session: InterviewSession, utterance: str) -> dict | None:
    """발화가 지목한 등록 장소 (가장 긴 라벨 우선). 없으면 None."""
    text = _norm(utterance)
    hits = [a for a in session.draft_attractions
            if a.get("label") and len(_norm(a.get("label"))) >= 3
            and _norm(a.get("label")) in text]
    return max(hits, key=lambda a: len(_norm(a.get("label")))) if hits else None


def _home_change_check(session: InterviewSession, utterance: str) -> bool | None:
    """정정 발화의 집 주소 변경이 정말 '지금 사는 집'을 고치는 것인가.

    라이브 실측(2026-07-21): "예전에 살던 집은 산남동이 아니라 수곡동이에요"라는
    **끌림점** 정정에 슬롯 랭킹이 home 을 골라, 수색 원점이 조용히 수곡동으로
    바뀌었다. 확인 게이트는 overwrite=True 라 first-wins 보호가 풀려 있어
    (끌림점은 그대로인 채) 자택만 틀어지는 최악의 조합이 된다.
    등록된 장소를 지목한 발화일 때만 모델에게 한 번 더 묻는다(True=집 변경, False=그
    장소 얘기, None=확인 못 함). 장소를 지목하지 않았으면 모델의 home 판정 그대로(True).
    """
    place = _mentioned_place(session, utterance)
    if place is None:
        return True
    return _midm_tracked(session, lambda: midm.yes_no(
        f"보호자가 고치려는 것이 대상자가 지금 사는 집의 주소인가요? "
        f"'{place['label']}'의 위치를 고치는 말이면 아니오입니다.", utterance))


def _guard_home_overwrite(session: InterviewSession, extracted: dict, utterance: str) -> None:
    """집 주소 변경이 확인되지 않으면 버린다 (수색 원점 보호)."""
    fields = extracted.get("fields") or {}
    if "home" in fields and _home_change_check(session, utterance) is not True:
        fields.pop("home")


def _apply_correction(session: InterviewSession, utterance: str, result: dict) -> bool:
    """확인 게이트 전용 정정 — 장소 이름·위치 변경과 삭제까지 처리. 반영했으면 True.

    LLM 은 '무엇을 어떻게'만 닫힌 어휘로 내고(prompts.CORRECTION_SYSTEM → result),
    적용은 여기서 결정론적으로 한다 — 기존 가드레일 원칙(정성 판단은 LLM, 반영은 코드).
    """
    changed = False
    ops = list(result.get("place_ops") or [])
    for key, value in _grounded_fields(session, result.get("fields") or {}, utterance).items():
        home_check = _home_change_check(session, utterance) if key == "home" else True
        if home_check is None:
            continue   # 집 변경인지 확인 못 했다 — 수색 원점은 건드리지 않는다
        if home_check is False:
            # 장소의 동네 정정을 모델이 home 으로 잘못 보내는 실측(2/2) — 수색 원점을
            # 지키는 데서 끝내지 않고, 지목된 장소의 지역 정정으로 되돌려 살린다.
            # (그냥 버리면 보호자에게는 "또 안 먹혔다"로 보인다.)
            place = _mentioned_place(session, utterance)
            if place is not None and not any(
                    o["op"] in ("set_area", "rename", "remove")
                    and _norm(o.get("target")) == _norm(place.get("label")) for o in ops):
                ops.append({"op": "set_area", "target": str(place["label"]), "value": value})
            continue
        if session.draft_fields.get(key) != value:
            session.draft_fields[key] = value
            changed = True

    for op in ops:
        kind = op["op"]
        if kind == "add":
            label = op["value"]
            if any(_norm(a.get("label")) == _norm(label) for a in session.draft_attractions):
                continue
            area = clean_area_text(op.get("area"))
            session.draft_attractions.append({
                "label": label, "area_text": area if _area_grounded(area, utterance) else "",
                "evidence": "caregiver_report", "origin_slot": "routine_destinations"})
            changed = True
            continue
        target = next((a for a in session.draft_attractions
                       if _norm(a.get("label")) == _norm(op["target"])), None)
        if target is None:
            continue
        if kind == "remove":
            # 삭제는 되돌릴 수 없다 — 모델에게 한 번 더 확인하고, 아니면(또는 확인 못 하면)
            # 지우지 않는다. 실측(2026-07-21): 이름 정정 한 마디에 장소가 통째로 사라졌다.
            asked = str(target.get("label") or "")
            question = (f"보호자가 '{asked}'을(를) 등록된 장소 목록에서 빼 달라고 했나요? "
                        "이름이나 위치를 고치는 말이면 아니오입니다.")
            removal = _midm_tracked(session, lambda q=question: midm.yes_no(q, utterance))
            if removal is not True:
                session.extraction_audit.append(
                    {"event": "remove_not_confirmed", "label": asked})
                continue
            session.draft_attractions.remove(target)
            changed = True
        elif kind == "rename":
            old_label = str(target.get("label") or "")
            target["label"] = op["value"]
            # 지역 표기가 옛 이름을 담고 있으면 같이 따라간다 — 안 그러면 "원평초등학교"로
            # 고친 뒤에도 area_text("원평중학교 앞")가 남아 옛 장소로 좌표가 잡힌다.
            if old_label and _norm(old_label) in _norm(target.get("area_text")):
                target["area_text"] = op["value"]
            changed = True
        elif kind == "set_area":
            # 지역 표현은 모델이 조사 없이 낸다(prompts.CORRECTION_SYSTEM). 답에 근거가
            # 없는 값(지어낸 동네)은 받지 않는다.
            area = clean_area_text(op["value"])
            if area and _area_grounded(area, utterance):
                target["area_text"] = area
                changed = True
    return changed


def _handle_confirmation(session: InterviewSession, clean: str) -> InterviewSession:
    """요약 확인 응답 처리: 긍정→등록 완료 / 정정→관련 슬롯 반영 후 재요약."""
    previous_home = session.draft_fields.get("home")
    session.messages.append({"role": "user", "text": clean})
    session.slot_turns.append({"slot": "confirmation", "question": "등록 요약을 보고 확인·정정하는 단계",
                               "answer": clean, "recorded_at": datetime.now(timezone.utc).isoformat()})

    # 확인·정정 판정은 Mi:dm 이 한다(intent). 고칠 내용이 함께 나왔으면 확인이 아니다.
    labels = [str(a.get("label")) for a in session.draft_attractions if a.get("label")]
    result = _midm_tracked(session, lambda: midm.extract_correction(labels, clean))
    intent = result.get("intent")
    if intent == "confirm" and not result.get("fields") and not result.get("place_ops"):
        try:
            finalize_persona(session)   # draft → 지오코딩 → 확정 Persona 저장
            # Tier1만 다루는 미니챗(신고 전)은 확정 뒤 신고 폼으로 넘어간다는 걸
            # 알려야 한다 — 전체/보완챗 문구("프로필을 등록했어요")를 그대로 쓰면
            # 보호자가 "이제 뭘 하지"에서 멈춘다.
            msg = ("확인 감사합니다. 신고 화면으로 이동합니다."
                   if session.target_tiers == [Tier.route.value]
                   else "확인 감사합니다. 이 내용으로 프로필을 등록했어요. 🙏")
        except ValueError as e:
            # 데드엔드 금지(라이브 실측): 구버전은 여기서 done=True 로 닫아,
            # "다시 확인해 달라"는 안내와 달리 이후 입력을 전부 무시했다.
            # 세션을 열어둔 채 home 재질문 흐름으로 복귀한다.
            session.awaiting_confirmation = False
            session.draft_fields.pop("home", None)   # 좌표화 실패 값이 first-wins 로 새 답을 막지 않게
            session.home_geo = None
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

    # "아니요, 수정할게요" — 무엇을 고칠지가 없다. 요약을 다시 띄우면 보호자는
    # 같은 화면 앞에서 멈춘다. 고칠 수 있는 항목을 보여주고 되묻는다.
    # awaiting_confirmation 은 그대로 두므로 다음 발화가 정정 경로로 들어온다.
    if intent == "correct_unspecified":
        session.messages.append(
            {"role": "assistant", "text": _ask_what_to_correct(session)})
        storage.interviews.save(session.id, session)
        return session

    # 판정이 없으면(호출 실패) 등록을 확정하지도, 정정을 짐작하지도 않는다 — 다시 묻는다.
    if intent is None:
        session.messages.append({"role": "assistant", "text": (
            "죄송해요, 방금 답변을 제대로 확인하지 못했어요. 이대로 등록할지, 고칠 부분이 "
            "있는지 한 번만 다시 말씀해 주세요.")})
        storage.interviews.save(session.id, session)
        return session

    # 정정: 전용 경로(장소 변경 지시 포함)를 먼저 적용하고, 아무것도 못 건지면
    # 슬롯 재추출로 폴백한다(행동 내용을 고친 경우 — 장소·기본 정보 지시가 없다).
    if not _apply_correction(session, clean, result):
        ranked, _ = retrieval.rank_next_slots(
            session.persona_type, [clean], set(), _EMB, top_k=1
        )
        if ranked:
            ext = _extract_tracked(session, ranked[0].slot)
            _ground_profile_fields(session, ranked[0].slot, ext, clean)
            _guard_home_overwrite(session, ext, clean)
            _apply_extraction(session, ranked[0].slot, ext, overwrite=True, utterance=clean)

    # 정정으로 집 주소가 바뀌었으면 요약을 다시 띄우기 전에 지도로 확인한다 —
    # 못 찾는 값을 요약에 실으면 "네"까지 간 뒤 finalize 에서야 되묻게 된다.
    home_reask = (_check_home(session)
                  if session.draft_fields.get("home") != previous_home else None)
    if home_reask:
        session.awaiting_confirmation = False
        session.messages.append({"role": "assistant", "text": home_reask})
        storage.interviews.save(session.id, session)
        return session

    # 정정으로 새로 들어온 장소에 지역 표기가 없으면 요약 대신 주소부터 묻는다 —
    # 확인 단계에서 추가된 곳도 좌표가 없으면 그대로 사라지기 때문(요약 전 게이트와 동일 원칙).
    pending = [a for a in _arealess_attractions(session)
               if str(a.get("label")) not in session.asked_area_labels]
    if pending:
        label = str(pending[0]["label"])
        session.asked_area_labels.append(label)
        session.pending_area_label = label
        session.awaiting_confirmation = False
        session.prev_target_key = str(pending[0].get("origin_slot") or "routine_destinations")
        session.messages.append({"role": "assistant", "text": (
            f"'{label}'은 어느 동네인가요? 동 이름이나 근처 건물·가게 이름이면 됩니다. "
            "(모르시면 '모르겠어요'라고 답해주세요)")})
        storage.interviews.save(session.id, session)
        return session

    session.messages.append({"role": "assistant", "text": build_summary(session)})
    storage.interviews.save(session.id, session)
    return session


_GEO = get_geocoder(use_nominatim=True)   # 카카오 → nominatim → gazetteer


class _PlaceChooser:
    """지도 검색 후보 중 보호자가 말한 곳을 Mi:dm 이 고른다. 랜드마크 검색어는 보호자 말이나 장소
    이름에 글자 그대로 있어야 쓴다(모델이 새 이름을 만들면 버린다)."""

    def pick(self, draft: dict, results: list, landmark: str | None = None) -> int | None:
        label, quote = str(draft.get("label") or ""), str(draft.get("quote") or "")
        options = [{"name": r.matched or "", **{k: (r.detail or {}).get(k) for k in ("category", "address", "distance_m")}}
                   for r in results]
        idx = midm.pick_place(label, quote, options, landmark)
        if idx is None or landmark:
            # 랜드마크 이름은 이미 보호자 말에 글자 그대로 있다(landmark 에서 대조) — 같은 이름 가운데 고르는 일이라
            # 다시 묻지 않는다. 10회차: '일산쌍용아파트'가 '쌍용아파트 앞 오거리' 옆이냐는 질문에 '보호자가 그 이름을
            # 말하지 않았다'며 아니라고 답해 맞는 좌표를 버렸다.
            return idx
        # 직접 고른 곳은 한 번 더 묻는다 — 9회차: '일산시장 앞 오거리'에 2.2km 떨어진 '문화공원 오거리공원'을
        # 골랐다(같은 프롬프트로 '쌍용아파트 앞 오거리'에는 없음이라고 답했다). 확인되지 않으면 고르지 않는다.
        o = options[idx]
        question = (f"보호자가 말한 '{label}'은(는) 지도의 '{o['name']}'({o.get('category') or '분류 없음'}) "
                    "그 자체이거나 바로 붙어 있는 곳인가요?")
        return idx if midm.yes_no(question, quote or label) is True else None

    def landmark(self, draft: dict) -> str | None:
        label, quote = str(draft.get("label") or ""), str(draft.get("quote") or "")
        q = midm.landmark_query(label, quote)
        if not q or _compact(q) == _compact(label) or not (_in_answer(q, label) or _in_answer(q, quote)):
            return None
        return q


_CHOOSER = _PlaceChooser()


def _flatten_fields(fields: dict) -> dict:
    """추출 결과의 중첩 dict 를 한 단계 편다.

    Mi:dm 이 슬롯 키를 그대로 감싸 `{"identity": {"name": "김순자", "age": "82세"}}`
    처럼 돌려주는 경우가 있다. 그대로 넣으면 `draft_fields["name"]` 이 비어
    **페르소나 이름이 "미상"으로 저장된다**(2026-08-05 라이브 실측 — 대화에서는
    이름을 정확히 추출했는데 등록 결과에는 안 들어갔다).

    안쪽 값을 우선한다: 바깥 키(`identity`)는 슬롯 이름이고 우리가 원하는 것은
    그 안의 필드(`name`·`age`)다. 이미 평탄한 키가 있으면 덮지 않는다 —
    호출부의 first-wins/overwrite 판단을 여기서 가로채면 안 된다.
    """
    flat: dict = {}
    for key, value in fields.items():
        if isinstance(value, dict):
            for inner_key, inner_value in value.items():
                if inner_value:
                    flat.setdefault(inner_key, inner_value)
        else:
            flat[key] = value
    # 평탄한 키가 나중에 나와도 중첩본을 덮지 않도록 마지막에 한 번 더 채운다.
    for key, value in fields.items():
        if not isinstance(value, dict) and value:
            flat[key] = value
    return flat


def _parse_age(value) -> int:
    """저장된 나이 값 → 정수. 추출 단계에서 숫자로 확정되므로 숫자가 없으면 0(미상)."""
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
    persona = persona.model_copy(deep=True)
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
    # 행동 경향 컴파일(작업 P1-3) — lost_behavior + dementia_wandering_pattern 을
    # 단일 신호로 합쳐 Phase2 strategy_probs 틸트에 연결한다. 실패는 None 유지로
    # 흡수되고, 소비처(guardrail)가 None 이면 무변화를 돌려주므로 예측이
    # 도입 이전과 같아진다.
    try:
        from app.phase0.behavior_compiler import compile_behavior_tendency

        persona.behavior_tendency = compile_behavior_tendency(persona)
    except Exception:  # noqa: BLE001 — 실패해도 앞선 결과 저장은 계속 진행
        pass
    # 채점(최대 수십 초) 도중 보호자가 삭제를 요청했을 수 있다 — 삭제된 persona 를
    # 되살리지 않도록 저장 직전 재확인(개인정보 파기 경합 방지, 셀프리뷰 발견).
    def merge_scoring(current):
        if current.version != persona.version:return None
        fields=('axis_scores','axis_scoring_report','route_familiarity','env_responses','behavior_tendency')
        return current.model_copy(deep=True,update={k:getattr(persona,k) for k in fields})
    storage.personas.update_existing(persona_id,merge_scoring)


def finalize_persona(session: InterviewSession, geocoder=None) -> Persona:
    """확인 완료된 인터뷰 초안(draft_*) → 지오코딩 → 확정 Persona 저장.

    home 을 먼저 좌표화(필수)하고, 그 좌표를 앵커로 끌림점을 근접 검색한다.
    home 미확보·좌표화 실패 시 ValueError — 끌림점 폴백은 하지 않는다:
    Mi:dm 이 home 을 끌림점으로 오추출한 라이브 케이스에서 과거 거주지가
    무경고로 수색 원점이 되던 치명 버그 (원점 오염). ValueError 는 확인 게이트가
    받아 보호자에게 집 위치를 재질문한다.
    geocoder 미지정 시 모듈 기본(_GEO, 카카오 체인) 사용 — 테스트는 gazetteer 주입.

    session.persona_id 가 **세션 생성 시점부터 이미 설정돼 있으면**(supplement·update —
    온보딩 없는 신고 흐름, 2026-08) 새로 만들지 않고 그 persona 에 이번 세션에서
    수집한 것만 병합한다. create(지금까지의 유일한 흐름)는 이 값이 비어 있으므로
    아래 분기가 지금과 완전히 동일하게 동작한다.
    """
    geo = geocoder or _GEO
    f = session.draft_fields
    existing = storage.personas.get(session.persona_id) if session.persona_id else None

    # ① home — 이번 세션에서 새로 답했으면 좌표화, 아니면(보완챗처럼 이번엔 안
    #    물었을 때) 기존 persona 의 home 을 그대로 쓴다. 둘 다 없으면 지금까지와
    #    같은 ValueError.
    if f.get("home"):
        checked = session.home_geo if (session.home_geo or {}).get("query") == str(f["home"]) else None
        if checked:
            # 답변 턴에 이미 확인한 좌표(_check_home) — 요약에 보여준 그 지점을 그대로
            # 쓴다. 다시 조회하면 백엔드 사정에 따라 다른 곳이 찍힐 수 있다.
            home = GeoPoint(lat=float(checked["lat"]), lng=float(checked["lng"]))
        else:
            # 맨 문자열 한 번이 아니라 후보 사다리로 — 아파트 이름이 붙은 정상 주소가
            # 통째로 실패해 등록이 막히던 문제(geocode.home_candidates 참고).
            home_res = locate_home(geo, str(f["home"]))
            if home_res is None:
                raise ValueError("집 위치 미확보 — 집 주소/동네를 다시 확인해 주세요")
            home = home_res.point
    elif existing is not None:
        home = existing.home
    else:
        raise ValueError("집 위치 미확보 — 집 주소/동네를 다시 확인해 주세요")

    # ② 끌림점 — home 앵커로 반경 내 근접 검색 (전국 키워드 오검색 차단). 이번
    #    세션에서 새로 나온 것만 대상 — 기존 끌림점은 아래 병합 단계에서 보존.
    points, unresolved = to_attraction_points(session.draft_attractions, geo, anchor=home,
                                              chooser=_CHOOSER if geocoder is None else None)
    if unresolved:
        # 되묻기(_arealess_attractions)까지 거치고도 좌표가 안 나온 장소 — 예측에서
        # 빠진다. 조용히 사라지면 원인 추적이 불가능하므로 최소한 로그로 남긴다.
        print("[phase0] 끌림점 좌표화 실패 → 예측 제외: "
              + ", ".join(f"{u.get('label')}({u.get('area_text') or '지역 미상'})"
                          for u in unresolved))
    # 중복 제거 — 같은 이름(또는 같은 좌표)이 poi/address 로 두 번 잡히면 더 정밀한 것만.
    _rank = {"poi": 0, "address": 1, "dong": 2, "approx": 3, "unknown": 4}
    uniq: dict[object, AttractionPoint] = {}
    for p in points:
        key = _norm(p.label) or (round(p.location.lat, 4), round(p.location.lng, 4))
        if key not in uniq or _rank.get(p.precision, 9) < _rank.get(uniq[key].precision, 9):
            uniq[key] = p
    new_points = list(uniq.values())

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

    if existing is not None:
        # supplement/update — 같은 id 에 병합. 이번 세션에서 안 건드린 값은 전부
        # 보존한다(끌림점·행동노트·축근거는 합집합, 이름/나이는 새로 답했을 때만 교체).
        persona = existing.model_copy(deep=True)
        existing_labels = {_norm(p.label) for p in persona.attraction_points}
        for p in new_points:
            key = _norm(p.label)
            if key and key not in existing_labels:
                persona.attraction_points.append(p)
                existing_labels.add(key)
        for note in session.draft_behaviors:
            if note not in persona.behavior_notes:
                persona.behavior_notes.append(note)
        for key, notes in axis_evidence.items():
            bucket = persona.axis_evidence.setdefault(key, [])
            bucket.extend(n for n in notes if n not in bucket)
        for key, quotes in axis_quotes.items():
            bucket = persona.axis_quotes.setdefault(key, [])
            bucket.extend(q for q in quotes if q not in bucket)
        if f.get("name"):
            persona.name = str(f["name"])
        if f.get("age"):
            persona.age = _parse_age(f["age"])
        if session.guardian_id:
            persona.guardian_id = session.guardian_id   # 비었으면 기존 값 보존
        persona.home = home
        persona.version += 1
    else:
        # create — 지금까지와 완전히 동일한 신규 생성 경로(guardian_id 만 추가).
        persona = Persona(
            id=storage.new_id(),
            type=session.persona_type,
            name=str(f.get("name") or "미상"),
            age=_parse_age(f.get("age")),
            guardian_id=session.guardian_id,
            home=home,
            attraction_points=new_points,
            behavior_notes=list(session.draft_behaviors),
            axis_evidence=axis_evidence,
            axis_quotes=axis_quotes,
        )

    # 축이 아닌 행동 슬롯의 원발화도 초기 행동 해석에 전달한다.
    # 신원·집 주소 전용 답은 제외. 슬롯은 출처일 뿐 행동 분류 규칙이 아니다.
    for key, quotes in session.slot_quotes.items():
        if key in {"identity", "home"}:
            continue
        bucket = persona.onboarding_quotes.setdefault(key, [])
        bucket.extend(q for q in quotes if q not in bucket)

    for turn in session.slot_turns:
        if turn not in persona.onboarding_turns:
            persona.onboarding_turns.append(dict(turn))

    # completed_tiers — 이번 세션이 커버한 tier 를 합집합으로 반영. target_tiers 가
    # None(기존 흐름·create/scope=all)이면 3개 tier 전부 커버한 것으로 본다.
    covered = session.target_tiers if session.target_tiers is not None else [1, 2, 3]
    persona.completed_tiers = sorted(set(persona.completed_tiers) | set(covered))

    # ④ 축 점수 컴파일 — 기능 플래그(기본 off, 회의에서 B×P1 채택 시 켠다).
    # 확정(보호자 "네") 이후에만 채점하며, 기본은 비동기: 채점(EXAONE 18회,
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
    from app.phase0 import person_preparation
    person_preparation.enqueue(persona.id)

    if existing is not None:
        # supplement/update 로 이미 있는 persona 를 갱신한 경우만 — 그 persona 로
        # 진행 중인 case 가 있으면 재예측을 건다(create 는 아직 신고 전이라 case 자체가
        # 없으므로 호출 불필요). 로컬 import — phase0→phase2/3 순환참조 회피(기존
        # intake.py 의 phase0_interview 지연 임포트와 같은 이유).
        from app.phase0 import persona_events
        persona_events.notify_persona_updated(persona.id, persona.version)

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
    guardian_id: str = "",
) -> Persona:
    """페르소나 등록 (구조화 필드 직접 입력).

    인터뷰 초안(draft_*)의 area_text 를 좌표로 바꾸는 지오코딩 단계가 붙으면
    이 함수를 통해 확정 Persona 를 만든다. (지오코딩은 별도 TODO.)

    `guardian_id` 는 **누구의 가족인지**다. 비워 두면 소유자 없는 페르소나가 되고,
    목록 조회에서 아무에게도 안 보인다 — 등록 경로가 반드시 채워야 한다.
    세션이 있으면 세션에 적힌 값을 우선한다(챗봇 등록이 그 경로다).
    """
    owner = guardian_id
    if session_id and not owner:
        s = storage.interviews.get(session_id)
        if s is not None:
            owner = s.guardian_id or ""
    persona = Persona(
        id=storage.new_id(),
        type=ptype,
        name=name,
        age=age,
        home=home,
        guardian_id=owner,
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
    from app.phase0 import person_preparation
    person_preparation.enqueue(persona.id)
    return storage.personas.get(persona.id) or persona
