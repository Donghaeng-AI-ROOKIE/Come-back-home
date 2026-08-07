"""Phase 0 — 히스토리-어웨어 슬롯 검색 (다음 질문 선택).

HAConvDR (Mo et al., Findings ACL 2024) 를 슬롯 선택 문제로 각색:
- 코퍼스     = 슬롯 뱅크 (slots.SLOTS 의 embed_text)
- 대화 쿼리  = 온보딩 대화 (보호자 답변 시퀀스)
- 목표       = "지금 보호자가 꺼낸 화제에 가장 관련 있는 미충족 슬롯"을 다음 질문으로

논문의 두 축을 그대로 반영:
  ① 문맥-디노이즈 쿼리 재구성 — 최신 답변 + '관련 있는' 과거 턴만 융합.
     세션 전체를 쿼리에 넣으면 topic drift 로 검색이 나빠지므로, 현재 답변과
     코사인 유사도가 낮은 과거 턴은 노이즈로 잘라낸다(denoise).
  ② 임팩트 기반 관련성 — 여기서는 온라인 heuristic (recency×coherence) 로 근사.
     라벨링된 eval 셋이 생기면 turn-impact 의사라벨로 교체 가능(TODO).

임베더는 교체형 인터페이스. 실제로는 API 임베더(현재 Upstage)를 붙인다.
키/모델 없이도 파이프라인이 돌도록 결정적 해시 스텁을 기본 제공한다.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

from app.phase0.slots import SLOTS, SlotSpec, slots_for
from app.schemas.persona import PersonaType

# ── 임베더 인터페이스 ────────────────────────────────────────────────


class Embedder(Protocol):
    """문장 → 벡터. 실제 한국어 임베더로 교체하는 지점.

    role: "query"(검색하는 쪽 — 발화·질문) 또는 "passage"(검색되는 쪽 — 슬롯뱅크·문서).
    Upstage 처럼 role별로 다른 모델을 쓰는 API에서만 의미가 있다. 로컬 임베더는 무시.
    """

    def encode(self, texts: list[str], role: str = "query") -> list[list[float]]: ...


class HashingEmbedder:
    """결정적 스텁 임베더 — 키/모델 없이 파이프라인을 돌리기 위한 것.

    토큰 해시 → 고정 차원 bag-of-hashed-tokens. 의미 유사도가 아니라 어휘
    중첩만 잡으므로 **실측 검색 품질을 대표하지 않는다**. 실제 한국어 임베더로
    교체 전까지의 자리끼움. (README/시뮬 문서에서 이 한계를 명시.)
    """

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _tokens(self, text: str) -> list[str]:
        return re.findall(r"[가-힣]+|[a-zA-Z]+|[0-9]+", text.lower())

    def encode(self, texts: list[str], role: str = "query") -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for tok in self._tokens(text):
                # 2-gram 음절까지 포함해 부분 중첩(어간)도 잡는다
                grams = [tok] + [tok[i : i + 2] for i in range(len(tok) - 1)]
                for g in grams:
                    h = int(hashlib.md5(g.encode()).hexdigest(), 16)
                    vec[h % self.dim] += 1.0
            out.append(vec)
        return out


class OpenAICompatEmbedder:
    """OpenAI 호환 /embeddings 엔드포인트 임베더 (실동작용, 현재 Upstage).

    model_passage: query/passage 를 별도 모델로 받는 제공자(Upstage 등)용.
    비우면 model 을 그대로 양쪽에 쓴다(그런 구분이 없는 제공자와 하위호환).
    """

    def __init__(
        self, base_url: str, model: str, api_key: str, timeout: float = 30.0,
        model_passage: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.model_passage = model_passage or model
        self.api_key = api_key
        self.timeout = timeout

    def _url(self) -> str:
        if self.base_url.endswith("/embeddings"):
            return self.base_url
        return f"{self.base_url}/embeddings"

    def encode(self, texts: list[str], role: str = "query") -> list[list[float]]:
        import json
        import urllib.request

        model = self.model_passage if role == "passage" else self.model
        payload = json.dumps({"model": model, "input": texts}).encode("utf-8")
        req = urllib.request.Request(
            self._url(),
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        # 입력 순서 보장 위해 index 정렬
        rows = sorted(data["data"], key=lambda r: r["index"])
        vecs = [r["embedding"] for r in rows]
        # 정규화 — LocalSTEmbedder(normalize_embeddings=True)와 동일하게 맞춘다.
        # Phase2 검색기(retriever.py)가 내적을 코사인으로 바로 쓰는 구조라, 여기서
        # 정규화 안 하면 순위는 안 바뀌어도(질의마다 상수배) score 값이 진짜 코사인이 아니게 된다.
        return [self._normalize(v) for v in vecs]

    @staticmethod
    def _normalize(v: list[float]) -> list[float]:
        norm = sum(x * x for x in v) ** 0.5
        return [x / norm for x in v] if norm else v


class LocalSTEmbedder:
    """로컬 sentence-transformers 한국어 임베더 (자체완결, 오프라인).

    embed_model 에 HF 모델명을 주면 그 모델을 로드해 인코딩한다.
    모델은 최초 1회 lazy 로드 후 캐시.

    **문장 임베딩도 캐시한다.** `build_history_aware_query` 가 매 턴 대화 히스토리
    전체를 다시 인코딩하는 구조라, 캐시가 없으면 N 턴 대화에서 인코딩이 N²/2 회로
    늘어난다. 로컬 임베더는 모델이 클수록 호출당 고정비가 커서 긴 인터뷰에서
    체감된다. 같은 문장은 항상 같은 벡터라 캐시해도 결과는 비트 단위로 동일하다.
    """

    # 세션 하나가 남기는 턴 수의 수십 배 — 오래 뜬 프로세스에서 무한히 자라지 않게
    _CACHE_MAX = 4096

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None
        self._cache: dict[str, list[float]] = {}

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: list[str], role: str = "query") -> list[list[float]]:
        # role 무시 — 로컬 임베더는 query/passage 구분이 없어 결과가 동일하다.
        missing = [t for t in dict.fromkeys(texts) if t not in self._cache]
        if missing:
            vecs = self._load().encode(missing, normalize_embeddings=True)
            if len(self._cache) + len(missing) > self._CACHE_MAX:
                self._cache.clear()          # 단순 비우기 — LRU 유지비가 이득보다 크다
            for t, v in zip(missing, vecs):
                self._cache[t] = v.tolist()
        return [self._cache[t] for t in texts]


def get_embedder() -> Embedder:
    """설정에 따라 임베더 선택.

    - embed_base_url + embed_model → 원격 OpenAI 호환 /embeddings
    - embed_model 만 (URL 없음)     → 로컬 sentence-transformers
    - 둘 다 없음                     → 해시 스텁(의미검색 불가)
    """
    from app.config import settings

    if settings.embed_base_url and settings.embed_model:
        return OpenAICompatEmbedder(
            settings.embed_base_url, settings.embed_model,
            settings.embed_api_key, settings.llm_timeout,
            model_passage=settings.embed_model_passage,
        )
    if settings.embed_model:
        return LocalSTEmbedder(settings.embed_model)
    return HashingEmbedder()


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ── 히스토리-어웨어 쿼리 (논문 ①: 문맥 디노이즈) ─────────────────────

# 화제이탈 grounding 가드 토글 (평가 하네스 전용, 기본 켜짐). False 면 과거 턴을
# 디노이즈 없이 전부 쿼리에 넣는다 — topic drift 로 검색이 나빠지는지 측정용.
DENOISE = True

# 현재 답변과 이 임계 미만으로 유사한 과거 턴은 topic drift 로 보고 버린다.
# ⚠ 임베더 종속 — 아래 "절대 임계 보정" 주석 참조.
COHERENCE_THRESHOLD = 0.35
# 과거 턴 기여를 거리(턴 수)에 따라 감쇠 — 최근 맥락일수록 크게.
# 유사도 스케일 무관이라 임베더를 바꿔도 유지.
RECENCY_DECAY = 0.6


def build_history_aware_query(
    user_turns: list[str], embedder: Embedder
) -> tuple[str, list[int]]:
    """최신 답변 + '관련 있는' 과거 턴만 융합한 검색 쿼리 텍스트를 만든다.

    반환: (쿼리 텍스트, 채택된 과거 턴 인덱스들) — 디노이즈 결과를 설명 가능하게.
    가장 마지막 턴이 앵커. 그 앞 턴들은 앵커와 코사인 ≥ 임계일 때만,
    recency 가중을 반영해 (가까울수록 여러 번) 포함한다.
    """
    if not user_turns:
        return "", []
    anchor = user_turns[-1]
    if len(user_turns) == 1:
        return anchor, []

    history = user_turns[:-1]
    # 둘 다 보호자 발화(검색 대상 문서가 아님) — query 로 통일.
    embs = embedder.encode([anchor, *history], role="query")
    anchor_emb, hist_embs = embs[0], embs[1:]

    kept: list[int] = []
    parts = [anchor]
    for offset, (turn, emb) in enumerate(zip(history, hist_embs)):
        idx = len(history) - 1 - offset  # 원래 인덱스
        dist = offset + 1                 # 앵커로부터의 턴 거리(1=바로 앞)
        if DENOISE and cosine(anchor_emb, emb) < COHERENCE_THRESHOLD:
            continue                      # 관련 없는 과거 턴 → 디노이즈
        weight = RECENCY_DECAY ** (dist - 1)
        repeat = max(1, round(weight * 2))  # 가까울수록 쿼리에 더 크게 반영
        parts.extend([turn] * repeat)
        kept.append(idx)
    return " ".join(parts), sorted(kept)


# ── 슬롯 랭킹 (다음 질문 후보) ───────────────────────────────────────


# 슬롯 정의 순서 인덱스 (템플릿 모드 tie-break 용).
_SLOT_INDEX = {s.key: i for i, s in enumerate(SLOTS)}

# ── 절대 임계 보정 (COHERENCE_THRESHOLD · PIVOT_SIM · RISK_GATE) ──────
#
# 이 셋은 **코사인 유사도 절대값**이라 임베더에 종속된다. 임베더를 바꾸면
# 유사도 분포가 통째로 이동하므로 값을 그대로 두면 가드가 조용히 무력화된다.
# 실측 예: 이전 임베더 기준 COHERENCE_THRESHOLD=0.15 를 그다음 임베더에 그대로
# 쓰면 과거 턴을 **0% 잘라내** 디노이즈가 사실상 꺼진 사례가 있었다.
#
# 현재 값(2026-08-04 재보정, Upstage 전환)은 실 Mi:dm 확정값이다.
#   보정 방법: 실제 대화에서 rank_next_slots 가 만든 융합 쿼리의 max-sim 분포를
#   수집해, 정보성 턴은 살리고 무정보 턴("잘 모르겠어요" 등)은 거르는 지점을 택함.
#   ⚠ 코퍼스 유사도로 대신 뽑으면 안 된다 — 융합 쿼리는 과거 턴 이어붙이기로
#     희석돼 단일 발화보다 유사도가 낮게 나온다.
#   ⚠ 스텁 모드 스윕으로 확정하면 안 된다 — 스텁은 질문 문구가 고정 템플릿이라
#     대화 궤적이 실 Mi:dm 과 다르고, 이번에도 스텁 예측과 실측이 갈린 값이 있었다
#     (GROUNDING_THRESHOLD, safety.py 참고 — 스텁은 0.45~0.50을 제안했으나
#     실측 최적은 0.40이었다).
#
# 실키 검증 근거 (시나리오 9개 × runs=3, experiments/slot_ranking/const_sweep.py):
#   PIVOT_SIM            라이브 분포에서 직접 선택 — 손익(정상피벗-헛피벗) 최댓값 지점
#   COHERENCE_THRESHOLD  0.35 — 0.30(너무 헐렁)·0.40(과도한 손실) 사이 절충점
#   RISK_GATE            직접 대조는 못 했으나(표본 작음) 위 둘과 비례 축소해 0.25
#
# 두 모드 전환:
#   sim ≥ PIVOT_SIM  → 피벗 모드(보호자 말이 강하게 이끈 슬롯으로 재정렬)
#   그 미만          → 템플릿 모드(tier·정의순으로 다음 슬롯 진행)
PIVOT_SIM = 0.32
RISK_GATE = 0.25                # 위험 부스트는 화제가 실제 관련될 때(sim≥게이트)만 적용
# 아래 둘은 유사도 스케일 무관 — 임베더를 바꿔도 재보정 불필요.
_TIER_BONUS = {1: 0.06, 2: 0.03, 3: 0.0}
ASKED_PENALTY = 0.12            # 물었는데 안 채워진 슬롯 1회당 감점 → 반복 탈출


class SlotScore:
    __slots__ = ("slot", "similarity", "tier_bonus", "risk", "penalty", "score")

    def __init__(self, slot: SlotSpec, similarity: float, asked_count: int = 0) -> None:
        self.slot = slot
        self.similarity = similarity                 # 히스토리-어웨어 쿼리와의 코사인
        self.tier_bonus = _TIER_BONUS[slot.tier.value]
        # 위험 부스트는 게이팅 — 화제가 실제로 이 슬롯과 관련될 때만(오프토픽 앞치기 방지).
        self.risk = slot.risk if similarity >= RISK_GATE else 0.0
        self.penalty = ASKED_PENALTY * asked_count   # 반복 질문 억제
        self.score = similarity + self.tier_bonus + self.risk - self.penalty

    def __repr__(self) -> str:
        return f"<{self.slot.key} sim={self.similarity:.3f} score={self.score:.3f}>"


def _template_key(slot: SlotSpec, asked_counts: dict[str, int]):
    # 템플릿 진행: 덜 물어본 것 → 낮은 tier → 정의순.
    return (asked_counts.get(slot.key, 0), slot.tier.value, _SLOT_INDEX[slot.key])


def rank_next_slots(
    ptype: PersonaType,
    user_turns: list[str],
    filled_keys: set[str],
    embedder: Embedder,
    *,
    top_k: int = 5,
    asked_counts: dict[str, int] | None = None,
    allowed_keys: set[str] | None = None,
) -> tuple[list[SlotScore], list[int]]:
    """다음 질문 후보 슬롯을 랭킹한다 (2모드).

    - 강한 신호(top sim ≥ PIVOT_SIM): 보호자가 방금 꺼낸 화제로 '피벗' — 검색 재정렬.
    - 약한 신호: 임의 슬롯 대신 '템플릿 순서'(tier·정의순)로 다음 슬롯 진행.
    이렇게 하면 평소엔 자연스러운 인터뷰 흐름, 단서가 나오면 즉시 꼬리질문.

    asked_counts: {slot_key: 물었지만 안 채워진 횟수} — 반복 탈출.
    allowed_keys: 미니챗·보완챗처럼 tier 로 범위를 좁힌 세션에서, 그 밖 슬롯을
    top_k 로 자르기 **전에** 제외한다. 사후 필터로는 못 막는 버그가 있었다 —
    치매 유형은 Tier1 슬롯 5개가 항상 템플릿 순서 맨 앞이라, 대화 시작 전(빈
    query_text)에는 top_k=5 가 통째로 Tier1로 채워진다. 보완챗(Tier2·3 전용)이
    이 5개를 받은 뒤 사후 필터링하면 전부 걸러져 후보가 0개가 되고, 첫 질문이
    빈 채로 나갔다(2026-08-07 실호출 테스트로 발견). 여기서 미리 제외해야
    top_k 안에 실제로 물을 수 있는 슬롯이 남는다.
    반환: (상위 후보 SlotScore, 디노이즈로 채택된 과거 턴 인덱스).
    """
    asked_counts = asked_counts or {}
    candidates = [s for s in slots_for(ptype) if s.key not in filled_keys]
    if allowed_keys is not None:
        candidates = [s for s in candidates if s.key in allowed_keys]
    if not candidates:
        return [], []

    query_text, kept_turns = build_history_aware_query(user_turns, embedder)

    def template_order() -> list[SlotScore]:
        ordered = sorted(candidates, key=lambda s: _template_key(s, asked_counts))
        return [SlotScore(s, 0.0, asked_counts.get(s.key, 0)) for s in ordered]

    # 대화 시작 전 → 순수 템플릿 순서 (첫 질문은 하드코딩 identity 부터).
    if not query_text.strip():
        return template_order()[:top_k], kept_turns

    slot_embs = embedder.encode([s.embed_text for s in candidates], role="passage")
    query_emb = embedder.encode([query_text], role="query")[0]
    scored = [
        SlotScore(s, cosine(query_emb, se), asked_counts.get(s.key, 0))
        for s, se in zip(candidates, slot_embs)
    ]

    if max(x.similarity for x in scored) >= PIVOT_SIM:
        scored.sort(key=lambda x: x.score, reverse=True)          # 피벗 모드
    else:
        scored.sort(key=lambda x: _template_key(x.slot, asked_counts))  # 템플릿 모드
    return scored[:top_k], kept_turns
