"""질문-매칭 리스폰더 — 챗봇 질문을 읽고 대본에서 답을 고른다.

소실된 e2e7.py RULES 의 재건. 핵심 원칙(메모리 [[airookie-eval-harness-plan]]):
**고정 배열로 순서대로 답하면 안 된다.** 챗봇의 슬롯 선택은 검색 기반이라
질문 순서가 비결정적이다. 반드시 '지금 무엇을 묻는지'를 보고 답을 골라야 한다.

특수 턴(요약 확인·주소 되묻기·추가 장소 스윕·유형 되묻기)을 먼저 가로채고,
나머지는 슬롯 어휘 매칭으로 화제를 식별해 scenario.answers[slot_key] 를 낸다.

스텁 모드: 챗봇 질문 = 슬롯 씨앗 질문(+개인화/예시)이라 매칭이 강하게 걸린다.
실 Mi:dm 모드: 질문이 재문장화되므로 어휘 자카드로 느슨하게 매칭한다(임계값 하향).
"""

from __future__ import annotations

import re

from app.phase0.slots import slots_for
from app.schemas.persona import PersonaType

_TOKEN_RE = re.compile(r"[가-힣a-zA-Z0-9]{2,}")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(str(text or "")))


# 슬롯 식별 최소 히트 — 슬롯 내용어가 질문에 이만큼 나타나야 그 슬롯으로 본다.
# argmax 위의 문턱. 실 Mi:dm 재문장화가 짧아 2로 둔다(1이면 오매칭 급증).
_MIN_HITS = 2


def _slot_vocab(slot) -> set[str]:
    """슬롯 내용어 집합 — 질문·라벨·키워드를 토큰화해 모은다(2자 이상만).

    keywords 는 "예전 집"·"살던 곳" 같은 다단어 문자열이라 토큰화가 필수.
    """
    vocab = _tokens(slot.question) | _tokens(slot.label)
    for kw in slot.keywords:
        vocab |= _tokens(kw)
    return {v for v in vocab if len(v) >= 2}


def match_slot(question: str, persona_type: str) -> str | None:
    """챗봇 질문이 어느 슬롯을 겨냥하는지 — 슬롯 내용어가 질문에 나타난 수로 판정.

    **부분문자열 매칭**을 쓴다: 한국어는 조사가 붙어("예전에"·"곳에"·"장소가")
    토큰 정확일치가 막힌다(실 Mi:dm 실측: 자전적기억·routine 질문이 이 이유로
    폴백). 슬롯 내용어가 질문 문자열의 부분열이면 히트로 센다.
    """
    ptype = PersonaType(persona_type)
    q = str(question or "")
    if not q:
        return None
    best_key, best_hits = None, 0
    for slot in slots_for(ptype):
        hits = sum(1 for v in _slot_vocab(slot) if v in q)
        if hits > best_hits:
            best_key, best_hits = slot.key, hits
    return best_key if best_hits >= _MIN_HITS else None


_AREA_RE = re.compile(r"['‘]([^'’]+)['’]\s*은?\s*어느\s*동네")
_SUMMARY_MARK = ("이렇게 등록할게요", "이게 맞나요", "맞나요?")
_MORE_PLACES = ("또 있을까요", "또 있나요", "자주 가시거나 좋아하시는 곳이 또")
_TYPE_REASK = ("치매 어르신", "발달장애")


def is_summary_gate(question: str) -> bool:
    """요약 확인 게이트 질문인가 — 러너가 정정 시퀀스로 처리한다(리스폰더는 무상태)."""
    q = str(question or "")
    return any(m in q for m in _SUMMARY_MARK)


def respond(question: str, scenario) -> str:
    """챗봇 질문 → 보호자 답변(대본에서 선택). 요약 게이트는 runner 가 처리."""
    q = str(question or "")

    # 2) 주소 되묻기 — "'방앗간'은 어느 동네인가요?"
    m = _AREA_RE.search(q)
    if m:
        label = m.group(1).strip()
        # 라벨 부분 매칭 — 되묻는 라벨이 대본 키와 정확히 안 맞아도 최선을 고른다
        for key, ans in scenario.area_answers.items():
            if key in label or label in key:
                return ans
        return "잘 모르겠어요."

    # 3) 추가 장소 스윕
    if any(m in q for m in _MORE_PLACES):
        return scenario.extra_places

    # 4) 유형 되묻기 (identity 에서 유형 미확정 시)
    if all(t in q for t in _TYPE_REASK) and "해당" in q:
        return scenario.answers.get("identity", scenario.fallback)

    # 5) 슬롯 화제 매칭
    key = match_slot(q, scenario.persona_type)
    if key and key in scenario.answers:
        return scenario.answers[key]

    return scenario.fallback
