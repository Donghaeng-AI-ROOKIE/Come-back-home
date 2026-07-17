"""Phase 0 — 온보딩 챗봇 가드레일 (2층).

「챗봇」 문서 원칙: 온보딩 인터뷰는 **페르소나 스키마 필드에 맞춰서만** 후속질문을
생성한다(자유 환각 방지). 이를 구조적으로 강제:

  층① rule-base  — 운영자가 사전 정의한 키워드 딕셔너리로 위험/부적절 발언 차단.
  층② 임베딩     — 생성된 질문이 '지금 겨냥한 슬롯'과 의미적으로 붙어 있는지
                   코사인으로 검증(off-schema drift 컷).

두 층 중 하나라도 걸리면 내부 필터링 → 해당 슬롯의 안전한 canned 질문으로 폴백.
따라서 최악의 경우에도 챗봇은 항상 스키마 안의 질문만 내보낸다.
"""

from __future__ import annotations

import re

from app.phase0.retrieval import Embedder, cosine
from app.phase0.slots import SlotSpec

# ── 층① 운영자 키워드 딕셔너리 ──────────────────────────────────────
# 온보딩 인터뷰가 절대 유도/생성하면 안 되는 어휘. 운영자가 관리(→ 설정/DB로 이전).
# 목적: 의료·법률 조언, 진단 단정, 자해·비난 유도 등 범위 밖 발화 차단.
BLOCKLIST: list[str] = [
    "진단", "처방", "약을 끊", "복용량", "치료법",         # 의료 조언 금지
    "고소", "소송", "책임", "과실",                        # 법률·책임 공방 금지
    "죽", "자해", "때리", "학대",                          # 위해·비난 유도 금지
]

# 보호자 입력에서 걸러야 할 개인정보 패턴 (저장 전 마스킹).
_PII_PATTERNS = [
    re.compile(r"\d{6}[-\s]?\d{7}"),          # 주민등록번호
    re.compile(r"01[016789][-\s]?\d{3,4}[-\s]?\d{4}"),  # 휴대폰번호
]

# 층② grounding 최소 코사인 — 생성 질문이 타깃 슬롯과 이만큼은 붙어 있어야 통과.
GROUNDING_THRESHOLD = 0.12


def sanitize_input(text: str) -> str:
    """보호자 입력의 민감 개인정보 마스킹(저장·프롬프트 반영 전)."""
    out = text
    for pat in _PII_PATTERNS:
        out = pat.sub("[민감정보]", out)
    return out


def passes_rules(text: str) -> bool:
    """층① — 블록리스트 어휘가 없으면 통과."""
    return not any(term in text for term in BLOCKLIST)


def is_grounded(question: str, slot: SlotSpec, embedder: Embedder) -> bool:
    """층② — 생성 질문이 타깃 슬롯 표면과 의미적으로 붙어 있으면 통과."""
    q_emb, s_emb = embedder.encode([question, slot.embed_text])
    return cosine(q_emb, s_emb) >= GROUNDING_THRESHOLD


def single_question(text: str) -> str:
    """복합 질문을 첫 질문 하나로 — '한 번에 한 질문' 원칙.

    씨앗 질문(회의록 원문)은 물음표 2~3개짜리 복합 문형이 있다. Mi:dm 참고용
    으로는 원문을 유지하되, 폴백으로 **직접 내보낼 때**만 첫 질문으로 자른다
    (잘린 각도는 probes 가 꼬리질문에서 파고든다).
    """
    if "?" in text:
        return text.split("?")[0].strip() + "?"
    return text


def guard_question(question: str, slot: SlotSpec, embedder: Embedder) -> tuple[str, bool]:
    """2층 검증 통과 질문을 반환. 실패 시 슬롯의 안전한 canned 질문으로 폴백.

    반환: (내보낼 질문, 폴백 발생 여부). 어느 경로든 단일 질문으로 잘라 내보낸다
    (스텁/폴백 경로의 씨앗 질문이 복합 문형이어도 설문지 낭독이 되지 않게).
    """
    if passes_rules(question) and is_grounded(question, slot, embedder):
        return single_question(question), False
    return single_question(slot.question), True  # 폴백: 스키마 안의 씨앗 질문
