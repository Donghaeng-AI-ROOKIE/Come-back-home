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

from datetime import datetime, timedelta

from app import storage
from app.llm import midm
from app.phase0 import retrieval, safety
from app.geo.geocode import (
    base_place_name,
    clean_area_text,
    get_geocoder,
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
    "presupposition": True,      # 근거 없는 전제 질문("~라고 하실 때") 차단
    "existence_first": True,     # 여부 확인 전 세부(부정조건) 질문 차단
    "dedup": True,               # 세션 전체 질문 문장 중복 방지
}

_IDENTITY = slot_by_key("identity")

# 대상 유형 — 치매 단독 스코프(2026-08-03). 유형 판별·되묻기 경로는 제거했고
# 세션 생성 시 이 값으로 고정된다.
DEFAULT_PERSONA_TYPE = PersonaType.dementia


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


# 과거 장소는 고유명사가 없어 Mi:dm 이 장소로 안 뽑는다 — "예전에 살던 집"은
# 라이브 실측 0/3 으로 attraction_points 에 한 번도 안 잡혔고 노트로만 남았다.
# 그러면 되묻기도 못 걸려 끌림점이 영영 안 생긴다. 발화에서 직접 라벨을 만든다.
_PAST_PLACE_LABEL_RE = re.compile(
    r"((?:예전|옛날|이전|전)에?\s*(?:살던|다니던|일하던|계시던)\s*(?:집|곳|동네|직장|회사|가게)"
    r"|옛집|옛\s*직장|친정|고향\s*집|고향)")


def _geocodable(label: str) -> bool:
    """라벨만으로 좌표가 나오나 — 나오면 동네를 되물어 보호자를 번거롭게 할 이유가 없다.

    실패(네트워크·백엔드 장애)는 '모른다'로 보고 되묻기로 넘긴다 — 질문 한 번이
    좌표 없는 끌림점보다 싸다.
    """
    try:
        return _GEO.locate(label) is not None
    except Exception:  # noqa: BLE001 — 지오코더 장애가 인터뷰를 죽이면 안 됨
        return False


# 발견지는 evidence 최상위(0.9)라 놓치면 예측 가중치가 통째로 어긋난다. Mi:dm 이
# 새 장소를 못 뽑고 이전 턴 장소를 되뱉는 실측이 반복돼(2026-07-22 "대흥역에서
# 발견한 적이 있어요" → 망원시장 반환) 발화에서 직접 지명을 집는 백스톱을 둔다.
_PLACE_TOKEN_RE = re.compile(
    r"[가-힣A-Za-z0-9]{1,10}(?:역|시장|공원|학교|대학교|교회|성당|병원|아파트|마트|"
    r"백화점|정류장|터미널|사거리|삼거리|주민센터|도서관|경로당|복지관)")


def _ensure_found_place(
    session: InterviewSession, prev_slot: SlotSpec, extracted: dict, utterance: str,
) -> None:
    """과거 발견지가 추출에서 누락됐으면 발화의 지명을 직접 끌림점으로 만든다.

    추출 결과에 **이번 발화에 나온 장소가 하나도 없을 때만** 돈다 — 모델이 제대로
    뽑았으면 건드리지 않는다.
    """
    if prev_slot.key != "dementia_wandering_pattern":
        return
    if _evidence_from_utterance(utterance, prev_slot.key) != "previous_missing_found":
        return   # 발견 근거가 아니거나 부정문("발견된 적 없어요")
    norm_utt = _norm(utterance)
    for ap in extracted.get("attraction_points") or []:
        if _norm(ap.get("label")) and _norm(ap.get("label")) in norm_utt:
            return          # 모델이 이 발화의 장소를 제대로 뽑았다
    for token in _PLACE_TOKEN_RE.findall(utterance):
        if any(_norm(a.get("label")) == _norm(token) for a in session.draft_attractions):
            continue        # 이미 등록된 장소면 아래 병합 경로가 근거를 승급한다
        ap = {"label": token, "area_text": token, "place_type": "found_location",
              "evidence": "previous_missing_found", "origin_slot": prev_slot.key}
        session.draft_attractions.append(ap)
        extracted.setdefault("attraction_points", []).append(dict(ap))
        return              # 첫 지명 하나만 — 여러 개 집으면 오탐이 는다


def _ensure_past_place(
    session: InterviewSession, prev_slot: SlotSpec, extracted: dict, utterance: str,
) -> None:
    """과거 장소 슬롯인데 끌림점이 안 생겼으면 발화에서 라벨을 만들어 넣는다.

    좌표는 아직 없다 — 바로 뒤 _ask_area_for_new_place 가 주소를 되묻는다.
    보호자가 "예전에 살던 집에 간다"고 말한 것은 **예측에 쓸 목적지 후보**이지
    행동 노트로만 남길 정보가 아니다.
    """
    if prev_slot.key != "autobiographical_destination_pull":
        return
    if extracted.get("attraction_points"):
        return
    m = _PAST_PLACE_LABEL_RE.search(utterance)
    if not m:
        return
    label = re.sub(r"\s+", " ", m.group(1)).strip()
    if any(_norm(a.get("label")) == _norm(label) for a in session.draft_attractions):
        return
    ap = {"label": label, "area_text": "", "place_type": "past_residence",
          "evidence": "mention_only", "origin_slot": prev_slot.key}
    _upgrade_evidence(ap, _evidence_from_utterance(utterance, prev_slot.key))
    session.draft_attractions.append(ap)
    extracted.setdefault("attraction_points", []).append(dict(ap))   # 되묻기 대상으로 인계


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
        if _geocodable(label):
            continue          # 라벨만으로 좌표가 나온다("대흥역 2번 출구") — 묻지 않는다
        session.asked_area_labels.append(label)
        session.pending_area_label = label
        return (f"'{label}'은 어느 동네인가요? 동 이름이나 근처 건물·가게 이름을 "
                "알려주시면 지도에 표시해 둘게요. (모르시면 '모르겠어요'라고 답해주세요)")
    return None


def _needs_probe(session: InterviewSession, slot: SlotSpec, utterance: str) -> bool:
    """이 슬롯을 한 번 더 파고들어야 하나 — 하위 항목(probes)이 안 채워진 얕은 답인가.

    라이브 실측(2026-07-21): Mi:dm 은 "혈압약을 저녁에만 드세요"에도 slot_filled=true
    를 낸다. 충족 처리된 슬롯은 _blocked_keys 로 후보에서 빠지므로 **probes 가 한
    번도 쓰이지 않는다** — 씨앗 질문은 clean_question 이 첫 물음표에서 자르기 때문에
    ("복용 중인 약이 있나요?" 뒤의 '거르면 어떤 증상' 이 잘림) 하위 항목은 꼬리질문이
    유일한 통로인데, 그 통로가 닫혀 있던 것이다. 슬롯당 1회만 보장한다.
    """
    if not slot.probes or slot.key in session.probed_keys:
        return False
    if slot.axis == Axis.profile:
        return False        # 이름·집은 파고들 하위 항목이 아니다
    if _is_pure_ignorance(utterance) or _is_negative_answer(utterance):
        return False        # "모르겠다"·"아니요"(해당 없음)는 더 물어도 얻을 게 없다
    return len(_slot_collected(session, slot)) < 2   # 확보한 사실이 1개 이하 = 얕음


# 꼬리질문이 원 질문의 재탕이면 안 된다 — 정확 일치만 잡는 _dedupe_question 으로는
# "낯선 사람이 다가와 말을 걸면 어떻게 반응하시나요?" vs "낯선 시민이 다가와 말을
# 걸면 어떤 행동을 보이시나요?" 를 못 거른다(라이브 실측 2026-07-22).
_PROBE_DUP_JACCARD = 0.5


def _probe_question(session: InterviewSession, slot: SlotSpec) -> str:
    """하위 항목 꼬리질문 — LLM 문장화를 쓰되, 원 질문의 재탕이면 각도를 직접 묻는다."""
    asked = [m["text"] for m in session.messages if m["role"] == "assistant"]
    recent = asked[-3:]
    raw = _phrase_tracked(session, slot, is_followup=True)
    question, _fb = safety.guard_question(
        raw, slot, _EMB, bank=_scoped_slots(session))
    qt = _note_tokens(question)
    too_similar = any(
        pt and qt and len(qt & pt) / len(qt | pt) >= _PROBE_DUP_JACCARD
        for pt in (_note_tokens(a) for a in recent))
    if too_similar or not question.strip():
        # 결정론적 폴백 — 아직 안 들은 각도를 그대로 묻는다. 어색해도 재탕보다 낫다.
        collected = " ".join(_slot_collected(session, slot))
        angle = next((pr for pr in slot.probes
                      if not any(tok in collected for tok in _note_tokens(pr))),
                     slot.probes[0])
        angle = re.sub(r"\s*\([a-z_]+\)\s*$", "", angle).strip()   # "(destination_retention)" 제거
        question = f"{angle}에 대해서도 알려주세요."
    return _dedupe_question(session, slot, question)


def _resolve_pending_area(session: InterviewSession, utterance: str) -> None:
    """되물은 주소 답변을 해당 끌림점의 area_text 로 확정 — LLM 추출에 의존하지 않는
    결정론적 백스톱(home 규칙 폴백과 같은 원칙). 장소 표현이 아니면 그냥 넘어간다."""
    label = session.pending_area_label
    if not label:
        return
    session.pending_area_label = None
    if _is_pure_ignorance(utterance) or _is_negative_answer(utterance):
        return   # "모르겠어요" — 되묻기는 1회뿐이므로 여기서 포기(질문 반복 금지)
    if not _valid_home_text(utterance):
        return   # 문장형·비장소 답변은 지오코딩 불가 — 받지 않는다
    area = _strip_tail_particles(clean_area_text(utterance))   # 질의로 나갈 값이라 조사 제거
    if not area:
        return
    for ap in session.draft_attractions:
        if _norm(ap.get("label")) == _norm(label) and not clean_area_text(ap.get("area_text")):
            ap["area_text"] = area
            return


def _extract_tracked(session: InterviewSession, slot: SlotSpec) -> dict:
    before = midm.call_failures
    out = midm.extract_answer(slot, _strip_question_examples(session.messages))
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


_TAIL_PARTICLE_RE = re.compile(r"(?:에|에서|이요|이에요|예요|입니다|이|가|은|는|요)\s*$")


def _strip_tail_particles(text: str) -> str:
    """말끝 조사 제거 — "산남동이요" → "산남동". 지오코딩 질의로 나갈 값에 필요."""
    return _TAIL_PARTICLE_RE.sub("", str(text or "").strip()).strip()


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
    core = _strip_tail_particles(t)
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
        lines.append(f"• 지내시는 곳: {f['home']}")

    places = session.draft_attractions
    if places:
        lines.append("• 가시려 할 만한 곳")
        for ap in places:
            area = ap.get("area_text")
            lines.append(f"   - {ap.get('label', '')}{f' ({area})' if area else ''}")

    grouped, loose = _group_behaviors(session)

    def _emit(label: str, notes: list[str]) -> None:
        if len(notes) == 1:
            lines.append(f"• {label}: {notes[0]}")      # 하나뿐이면 목록으로 늘리지 않는다
            return
        lines.append(f"• {label}")
        lines.extend(f"   - {n}" for n in notes)

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
        lines.extend(f"   - {n}" for n in loose)

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

# evidence 규칙 백스톱 — Mi:dm 은 "발견됐다"가 아닌 것을 전부 최약으로 떨어뜨린다.
# 실측 A/B(2026-07-21, 각 4회): "원마루 공원에 자주 가세요", "예전에 살던 집에 가야
# 한다는 말을 종종 합니다" 모두 4/4 mention_only — 프롬프트 문구를 고쳐도 그대로였다.
# 근거 강도는 한국어 표면형이 뚜렷하므로(자주·종종·가려고 한다) 코드가 판정한다.
# 가드레일 원칙 그대로: LLM 판정은 받되, 규칙이 더 강한 근거를 찾으면 **승급만** 한다.
# '~에서 발견됐다'(피발견)만 근거로 본다. "새 공원을 발견하고 좋아하셨어요" 같은
# 타동사 용법(을/를 + 발견)은 장소 근거가 아니므로 제외 — 슬롯 종류에 의존하지
# 않고 문장 구조로 가른다(발견 진술은 lost_behavior 등 다른 슬롯에서도 나온다).
_EV_FOUND_RE = re.compile(r"(?<![을를])(?<![을를]\s)(발견|찾았|찾으셨)|파출소|지구대|경찰서")
_EV_REPEAT_RE = re.compile(
    r"자주|종종|매일|날마다|항상|늘\s|반복|가려고|가야\s*한|가시려|가신다|"
    r"찾아\s*나|나가려|보러\s*가|들르|다니려")
_EV_NEGATION_RE = re.compile(r"아니|않|없|안\s*가|말리")


def _evidence_from_utterance(utterance: str, slot_key: str) -> str | None:
    """보호자 발화 표면형으로 근거 강도 판정. 근거가 없으면 None(=LLM 판정 유지).

    부정문("가시려는 건 아니에요")은 그 문장 단위로 배제한다 — 반복 표현이 있어도
    지향을 부정하는 말이면 승급하지 않는다.
    """
    text = str(utterance or "")
    for sentence in re.split(r"[.!?\n]", text):
        # "발견된 적 없어요"처럼 부정하면 근거가 아니다 (반복 표현과 같은 원칙)
        if _EV_FOUND_RE.search(sentence) and not _EV_NEGATION_RE.search(sentence):
            return "previous_missing_found"
    for sentence in re.split(r"[.!?\n]", text):
        if _EV_REPEAT_RE.search(sentence) and not _EV_NEGATION_RE.search(sentence):
            return "caregiver_report"
    return None


def _verify_found_evidence(ap: dict, utterance: str, slot_key: str) -> None:
    """최상위 등급(previous_missing_found)은 발화 근거가 있을 때만 인정한다.

    가장 큰 가중치(0.9)라 오분류 비용이 가장 크다. 실측(2026-07-22): "과거에
    망원시장에서 **가게를 하신 적**이 있어서 거기에 가야 한다고…"를 Mi:dm 이
    previous_missing_found 로 분류해, 평소 다니는 시장이 과거 발견지로 둔갑했다.
    승급 규칙은 등급을 올리기만 하므로 이 오분류를 못 막는다 — 근거 실존 검증
    (축 채점의 quote 검증과 같은 원칙)으로 새로 들어온 판정만 되돌린다.
    """
    if ap.get("evidence") != "previous_missing_found":
        return
    if _evidence_from_utterance(utterance, slot_key) == "previous_missing_found":
        return   # 발화에 '발견' 근거가 실제로 있다
    ap["evidence"] = ("caregiver_report"
                      if _evidence_from_utterance(utterance, slot_key) == "caregiver_report"
                      else "mention_only")


def _upgrade_evidence(ap: dict, rule_grade: str | None, utterance: str = "") -> None:
    """규칙 판정이 LLM 판정보다 강하면 올린다 (내리지는 않는다).

    단 **이번 발화에 실제로 언급된 장소에만** 적용한다. Mi:dm 은 새 장소를 못 뽑을 때
    이전 턴 장소를 다시 뱉는데(라이브 실측 2026-07-22: "대흥역에서 발견한 적이
    있어요" → 망원시장 반환), 그때 발화의 '발견' 근거를 그 장소에 붙이면 **엉뚱한
    곳이 최고 가중치(0.9)를 받는다.** 실제로 망원시장이 과거 발견지로 둔갑했다.
    """
    if rule_grade is None:
        return
    label = _norm(ap.get("label"))
    if utterance and label and label not in _norm(utterance):
        base = _norm(base_place_name(str(ap.get("label") or "")))
        if not base or base not in _norm(utterance):
            return   # 이 발화가 말한 장소가 아니다 — 근거를 옮겨 붙이지 않는다
    current = ap.get("evidence")
    if _EVIDENCE_RANK.get(rule_grade, 9) < _EVIDENCE_RANK.get(current, 9):
        ap["evidence"] = rule_grade


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


def _looks_like_past_home(label: str) -> bool:
    """'예전에 살던 집'·'옛집'·'마포구 신수동 옛날 집'처럼 과거 거주지 라벨인가.

    Mi:dm 이 옛집을 나중 턴에 변종 라벨로 반복 재추출하는 실측(2026-07-23 D2:
    routine·복약 턴에 '예전 집'·'마포구 신수동 옛날 집'을 새 장소로 되뱉음)이 있다.
    비연속 부분열이라('예전집'⊄'예전에살던집') 라벨 포함매칭이 못 잡아 같은 집이
    3조각으로 쌓였다. 옛집류는 지역이 호환되면 한 장소로 병합한다(_merge_target).
    """
    n = _norm(label)
    return ("옛" in n or "예전" in n) and "집" in n


def _merge_target(ap: dict, by_key: dict) -> str | None:
    """새 끌림점을 병합할 기존 라벨 키 — 포함매칭 + 옛집류 + 지역-둔갑 병합. 없으면 None."""
    key = _norm(ap.get("label"))
    area = _norm(_clean_area(ap.get("area_text")))
    if not key:
        return None
    if key in by_key:
        return key
    for k, ex in by_key.items():
        # ① 포함 관계 라벨("대흥역" vs "대흥역 2번 출구") — 3자 미만은 오병합 위험
        if (k in key and len(k) >= 3) or (key in k and len(key) >= 3):
            return k
        ex_area = _norm(_clean_area(ex.get("area_text")))
        # ② 옛집류끼리 지역이 호환되면 같은 집 — 변종 라벨 재추출 흡수
        if _looks_like_past_home(ap.get("label")) and _looks_like_past_home(ex.get("label")):
            if not area or not ex_area or area in ex_area or ex_area in area:
                return k
        # ③ 지역이 라벨로 둔갑 — 새 라벨이 기존 장소의 지역 그 자체(되묻기 주소가
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
    for ap in extracted.get("attraction_points", []) or []:
        key = _norm(ap.get("label"))
        if not key:
            continue
        if home_txt and key in home_txt:
            continue
        ap["area_text"] = _clean_area(ap.get("area_text"))   # "언급 없음" → "" (병합·되묻기 판정의 전제)
        if utterance:
            _verify_found_evidence(ap, utterance, prev_slot.key)   # 최상위 등급 근거 검증
        _upgrade_evidence(ap, _evidence_from_utterance(utterance, prev_slot.key), utterance)
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
    # 노트 폴백 — Mi:dm 이 slot_filled 만 내고 behavior_notes 를 비워 보내는 실측
    # (2026-07-21 라이브, "혈압약을 저녁에만 드세요" → notes [] 3/3). 그대로 두면
    # 보호자가 말한 사실이 axis_evidence 에서 통째로 사라진다(대화는 했는데 저장이
    # 안 되는 상태). 재서술이 없으면 **원발화 자체**를 근거로 남긴다 — 축 채점은
    # 원발화를 1차 근거로 쓰므로 형태상 문제도 없다.
    # 단, 모델이 노트를 **냈는데** 중복·환각 필터에 걸린 경우는 폴백하지 않는다 —
    # 그건 이미 저장된 사실이거나 버려야 할 사실이지, 유실이 아니다.
    if (not got_note and not notes_in and prev_slot.axis != Axis.profile and utterance
            and extracted.get("slot_filled")
            and not _is_pure_ignorance(utterance) and not _is_negative_answer(utterance)
            and _is_informative_note(utterance, utterance)
            and not _is_dup_note(utterance, seen_notes)):
        tagged = f"{prev_slot.label}: {utterance}"
        if tagged not in session.draft_behaviors:
            session.draft_behaviors.append(tagged)
            session.slot_notes.setdefault(prev_slot.key, []).append(utterance)
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

    # 1) 직전 겨냥 슬롯 추출 (+ identity/home 은 규칙 폴백으로 최후 방어)
    prev_slot = slot_by_key(session.prev_target_key) if session.prev_target_key else None
    got_something = True   # 이번 답에서 뭐라도 건졌나 — 빈손이면 직전 슬롯 재선택 회피
    if prev_slot is not None:
        extracted = _extract_tracked(session, prev_slot)
        # 과거 장소 슬롯에서 장소가 담긴 답인데 빈손이면 1회 재시도 — Mi:dm 이
        # 같은 입력에도 이따금 빈 배열을 낸다(실측: 재시도 6/6 회복). 여기서 놓치면
        # 과거 발견지(가장 강한 근거)가 통째로 사라지므로 한 번 더 물어본다.
        if (prev_slot.key in _PAST_PLACE_SLOTS
                and not (extracted.get("attraction_points") or [])
                and _evidence_from_utterance(clean, prev_slot.key)
                and not _is_pure_ignorance(clean) and not _is_negative_answer(clean)):
            retry = _extract_tracked(session, prev_slot)
            if retry.get("attraction_points"):
                extracted = retry
        _merge_rule_fallback(session, prev_slot, extracted, clean)
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
        # 순수 무지 답변("모르겠다니까요")이면 그 슬롯은 즉시 소진 — 같은 것을
        # 또 물어 보호자를 지치게 하지 않는다(라이브 실측 2026-07-17 2차).
        if GUARDS["ignorance_exhaust"] and _is_pure_ignorance(clean) \
                and prev_slot.key not in session.filled_keys:
            session.asked_counts[prev_slot.key] = MAX_ASKS_PER_SLOT
        # 부정 답변("딱히 없어요")은 '해당 없음'으로 **충족** 처리 — 무지와 달리
        # 답을 받은 것이다. profile 슬롯(이름·집)은 부정으로 채울 수 없어 제외.
        if GUARDS["negation_fill"] and _is_negative_answer(clean) \
                and prev_slot.axis != Axis.profile \
                and prev_slot.key not in session.filled_keys:
            session.filled_keys.append(prev_slot.key)
            session.asked_counts.pop(prev_slot.key, None)
        # 과거 장소를 새로 얻었으면 그 자리에서 주소를 묻는다 — 좌표 없는 끌림점은
        # 예측에 못 들어가므로 "장소를 들었다"와 "끌림점이 생겼다"는 다른 일이다.
        _ensure_found_place(session, prev_slot, extracted, clean)
        _ensure_past_place(session, prev_slot, extracted, clean)
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
        if extracted.get("slot_filled") and _needs_probe(session, prev_slot, clean):
            session.probed_keys.append(prev_slot.key)
            probe_q = _probe_question(session, prev_slot)
            session.messages.append(
                {"role": "assistant", "text": _personalize(probe_q, session.persona_type)})
            session.prev_target_key = prev_slot.key
            storage.interviews.save(session.id, session)
            return session

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
    raw_q = _phrase_tracked(session, target, is_followup)
    question, _fallback = safety.guard_question(
        raw_q, target, _EMB, bank=_scoped_slots(session))
    if GUARDS["presupposition"] and not _presupposition_grounded(session, question):
        question = safety.single_question(target.question)   # 근거 없는 전제 → 씨앗 질문
    if GUARDS["existence_first"] and not _slot_collected(session, target) \
            and _NEG_CONDITIONAL_RE.search(question):
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
    if not GUARDS["dedup"]:
        return question   # 가드 스윕: 중복 방지 끔
    asked = {_norm_q(m["text"]) for m in session.messages if m["role"] == "assistant"}
    if _norm_q(question) not in asked:
        return question
    seed = safety.single_question(target.question)
    if _norm_q(seed) not in asked:
        return seed
    n = session.asked_counts.get(target.key, 0)
    return _REASK_PREFIXES[n % len(_REASK_PREFIXES)] + seed


# 자택 정정으로 인정할 신호 — '지금 사는 집'을 명시할 때만 수색 원점을 바꾼다.
_HOME_CORRECTION_RE = re.compile(
    r"(지금|현재|요즘|사시는|사는|거주|계시는)\s*(집|곳|데)|자택|본가|사시는데")


# 삭제는 되돌릴 수 없다 — 보호자가 실제로 뺄 것을 요구했을 때만 인정한다.
# 라이브 실측(2026-07-21): "원평중학교가 아니라 원평초등학교예요"(이름 정정)에
# 모델이 remove 를 내서 장소가 이름 교체 없이 통째로 사라졌다.
_REMOVE_CUE_RE = re.compile(r"빼|삭제|지워|지우|제외|없애|안\s*가|이제\s*안|해당\s*없")


def _mentioned_place(session: InterviewSession, utterance: str) -> dict | None:
    """발화가 지목한 등록 장소 (가장 긴 라벨 우선). 없으면 None."""
    text = _norm(utterance)
    hits = [a for a in session.draft_attractions
            if a.get("label") and len(_norm(a.get("label"))) >= 3
            and _norm(a.get("label")) in text]
    return max(hits, key=lambda a: len(_norm(a.get("label")))) if hits else None


def _is_place_correction(session: InterviewSession, utterance: str) -> bool:
    """등록된 끌림점 이름을 지목한 발화인가 — 그렇다면 자택 정정이 아니다.

    라이브 실측(2026-07-21): "예전에 살던 집은 산남동이 아니라 수곡동이에요"라는
    **끌림점** 정정에 슬롯 랭킹이 home 을 골라, 수색 원점이 조용히 수곡동으로
    바뀌었다. 확인 게이트는 overwrite=True 라 first-wins 보호가 풀려 있어
    (끌림점은 그대로인 채) 자택만 틀어지는 최악의 조합이 된다.
    """
    if _HOME_CORRECTION_RE.search(utterance):
        return False       # '지금 사는 집' 을 명시했으면 자택 정정이 맞다
    return _mentioned_place(session, utterance) is not None


def _guard_home_overwrite(session: InterviewSession, extracted: dict, utterance: str) -> None:
    """장소를 지목한 정정이면 home 필드 변경을 버린다 (수색 원점 보호)."""
    fields = extracted.get("fields") or {}
    if "home" in fields and _is_place_correction(session, utterance):
        fields.pop("home")


def _apply_correction(session: InterviewSession, utterance: str) -> bool:
    """확인 게이트 전용 정정 — 장소 이름·위치 변경과 삭제까지 처리. 반영했으면 True.

    LLM 은 '무엇을 어떻게'만 닫힌 어휘로 내고(prompts.CORRECTION_SYSTEM), 적용은
    여기서 결정론적으로 한다 — 기존 가드레일 원칙(정성 판단은 LLM, 반영은 코드).
    """
    labels = [str(a.get("label")) for a in session.draft_attractions if a.get("label")]
    before = midm.call_failures
    result = midm.extract_correction(labels, utterance)
    if midm.call_failures > before:
        session.llm_call_failures += midm.call_failures - before
        session.llm_degraded = True

    changed = False
    ops = list(result.get("place_ops") or [])
    for key, value in (result.get("fields") or {}).items():
        if key == "home" and _is_place_correction(session, utterance):
            # 장소의 동네 정정을 모델이 home 으로 잘못 보내는 실측(2/2) — 수색 원점을
            # 지키는 데서 끝내지 않고, 지목된 장소의 지역 정정으로 되돌려 살린다.
            # (그냥 버리면 보호자에게는 "또 안 먹혔다"로 보인다.)
            place = _mentioned_place(session, utterance)
            if place is not None and not any(
                    o["op"] in ("set_area", "rename", "remove")
                    and _norm(o.get("target")) == _norm(place.get("label")) for o in ops):
                ops.append({"op": "set_area", "target": str(place["label"]), "value": value})
            continue
        if key == "home" and not _valid_home_text(value):
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
            session.draft_attractions.append({
                "label": label, "area_text": clean_area_text(op.get("area")),
                "evidence": "caregiver_report", "origin_slot": "routine_destinations"})
            changed = True
            continue
        target = next((a for a in session.draft_attractions
                       if _norm(a.get("label")) == _norm(op["target"])), None)
        if target is None:
            continue
        if kind == "remove":
            if not _REMOVE_CUE_RE.search(utterance):
                continue   # 보호자가 빼달라고 한 적 없다 — 이름 정정을 삭제로 낸 오분류
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
            area = _strip_tail_particles(clean_area_text(op["value"]))
            if area:
                target["area_text"] = area
                changed = True
    return changed


def _handle_confirmation(session: InterviewSession, clean: str) -> InterviewSession:
    """요약 확인 응답 처리: 긍정→등록 완료 / 정정→관련 슬롯 반영 후 재요약."""
    session.messages.append({"role": "user", "text": clean})

    if _is_affirmative(clean):
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

    # 정정: 전용 경로(장소 변경 지시 포함)를 먼저 시도하고, 아무것도 못 건지면
    # 기존 슬롯 재추출로 폴백한다(스텁·호출 실패 대비).
    if not _apply_correction(session, clean):
        ranked, _ = retrieval.rank_next_slots(
            session.persona_type, [clean], set(), _EMB, top_k=1
        )
        if ranked:
            ext = _extract_tracked(session, ranked[0].slot)
            _merge_rule_fallback(session, ranked[0].slot, ext, clean)   # 주소 정정 등 규칙 백스톱
            _guard_home_overwrite(session, ext, clean)
            _apply_extraction(session, ranked[0].slot, ext, overwrite=True, utterance=clean)

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


# 고유어 나이 수사 — Mi:dm 이 나이 칸에 "여든둘"·"일흔여덟"처럼 한글 수사를 그대로
# 넣는 실측(2026-07-23 골드셋: 이름 100% 인데 나이 대부분 0% — 숫자 파싱 실패).
# 아라비아 숫자가 없을 때만 고유어를 정수로 변환한다.
_KO_AGE_TENS = {"아흔": 90, "여든": 80, "일흔": 70, "예순": 60, "쉰": 50,
                "마흔": 40, "서른": 30, "스물": 20, "열": 10}
_KO_AGE_ONES = {"아홉": 9, "여덟": 8, "일곱": 7, "여섯": 6, "다섯": 5,
                "넷": 4, "네": 4, "셋": 3, "세": 3, "둘": 2, "두": 2, "하나": 1, "한": 1}


def _korean_age_to_int(value) -> int:
    """고유어 나이 → 정수. '일흔여덟'→78, '여든둘'→82, '스물다섯'→25. 못 읽으면 0."""
    t = re.sub(r"\s+", "", str(value or ""))
    total, matched = 0, False
    for tens, val in _KO_AGE_TENS.items():
        if tens in t:
            total += val
            t = t.replace(tens, "", 1)
            matched = True
            break
    # 일의 자리는 십의 자리 바로 뒤(접두)에서만 — "여든둘이세요"의 조사 '세요'가
    # 셋(3)으로 오매칭되지 않게 startswith 로 본다.
    for ones, val in _KO_AGE_ONES.items():
        if t.startswith(ones):
            total += val
            matched = True
            break
    return total if matched else 0


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
    if isinstance(value, int):
        return value
    s = str(value or "")
    m = re.search(r"\d+", s)
    if m:
        return int(m.group())
    return _korean_age_to_int(s)   # 아라비아 숫자 없으면 고유어 폴백


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
        home_res = geo.locate(f["home"])
        if home_res is None:
            raise ValueError("집 위치 미확보 — 집 주소/동네를 다시 확인해 주세요")
        home = home_res.point
    elif existing is not None:
        home = existing.home
    else:
        raise ValueError("집 위치 미확보 — 집 주소/동네를 다시 확인해 주세요")

    # ② 끌림점 — home 앵커로 반경 내 근접 검색 (전국 키워드 오검색 차단). 이번
    #    세션에서 새로 나온 것만 대상 — 기존 끌림점은 아래 병합 단계에서 보존.
    points, unresolved = to_attraction_points(session.draft_attractions, geo, anchor=home)
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
        persona = existing
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
