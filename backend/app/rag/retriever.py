"""논문 코퍼스 검색기 — 케이스당 1회 검색해 캐시, 여러 LLM 호출이 재사용.

왜 케이스당 1회인가:
  `reinterpret_mind` 는 한 예측에서 `mind_call_budget`(기본 10) 만큼 호출된다.
  호출마다 검색하면 임베딩 왕복이 그대로 지연으로 쌓인다. 실종자 프로파일은
  케이스 안에서 바뀌지 않으므로 발췌도 바뀔 이유가 없다.

왜 인덱스에 임베더 이름을 박아 두는가:
  질의와 문서가 다른 모델로 인코딩되면 코사인 값이 의미를 잃는다. 그런데도
  조용히 동작해 성능만 나빠지는 유형의 사고라, 불일치를 로드 시점에 잡는다.

인덱스가 없거나 임베더를 못 올리면 **조용히 비활성**된다(빈 발췌 반환).
RAG 는 보강이지 전제가 아니며, 데모 중 인덱스 파일 부재로 예측이 죽으면 안 된다.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass

from app.config import settings

log = logging.getLogger(__name__)


@dataclass
class Passage:
    text: str
    source: str
    kind: str          # "paper" | "qa"
    score: float


class Retriever:
    """npz 인덱스 + 임베더. 스레드 안전(시뮬레이션 워커가 병렬로 부른다)."""

    def __init__(self, index_path: str, embed_model: str = "") -> None:
        self.index_path = index_path
        self._lock = threading.Lock()
        self._loaded = False
        self._ok = False
        self._vecs = None
        self._meta: list[dict] = []
        # embed_model: 불일치 감지용 비교값(현재 설정의 passage 모델 식별자)일 뿐,
        # 실제로 어떤 임베더를 쓸지는 get_embedder()(전역 설정)가 결정한다 — API
        # 임베더는 이름만으론 재구성 못 해서(base_url·키 필요) 예전처럼 인덱스에
        # 적힌 이름으로 임베더를 새로 만드는 방식을 못 쓴다.
        self._model_name = embed_model
        self._embedder = None
        self._cache: dict[str, list[Passage]] = {}

    # ── 로딩 ────────────────────────────────────────────────────────
    def _load(self) -> bool:
        if self._loaded:
            return self._ok
        with self._lock:
            if self._loaded:
                return self._ok
            self._loaded = True
            try:
                import numpy as np

                if not os.path.exists(self.index_path):
                    log.warning("RAG 인덱스 없음 — 검색 비활성: %s", self.index_path)
                    return False
                z = np.load(self.index_path, allow_pickle=True)
                self._vecs = np.asarray(z["vecs"], dtype="float32")
                self._meta = json.loads(str(z["meta"]))
                index_model = str(z["model"])
                if self._model_name and self._model_name != index_model:
                    log.warning(
                        "RAG 임베더 불일치 — 인덱스=%s, 설정=%s. 설정 쪽을 따른다 "
                        "(재검색 결과가 인덱스 구축 당시와 달라질 수 있음).",
                        index_model, self._model_name)

                from app.phase0.retrieval import get_embedder
                self._embedder = get_embedder()
                self._ok = True
                log.info("RAG 인덱스 로드 — 청크 %d개, 인덱스 임베더=%s",
                         len(self._meta), index_model)
            except Exception as e:  # noqa: BLE001 — 검색 실패가 예측을 막으면 안 됨
                log.warning("RAG 인덱스 로드 실패 — 검색 비활성: %r", e)
                self._ok = False
            return self._ok

    @property
    def available(self) -> bool:
        return self._load()

    # ── 검색 ────────────────────────────────────────────────────────
    def search(self, query: str, top_k: int = 0) -> list[Passage]:
        """코사인 상위 k개 발췌. 같은 질의는 캐시에서 돌려준다."""
        if not query.strip() or not self._load():
            return []
        top_k = top_k or settings.rag_top_k
        key = f"{top_k}␟{query}"
        hit = self._cache.get(key)
        if hit is not None:
            return hit

        import numpy as np

        try:
            qv = np.asarray(self._embedder.encode([query], role="query")[0], dtype="float32")
        except Exception as e:  # noqa: BLE001
            log.warning("RAG 질의 임베딩 실패: %r", e)
            return []
        sims = self._vecs @ qv                      # 문서·질의 모두 정규화되어 있음
        idx = np.argsort(-sims)[: top_k * 3]        # 출처 다양화 여유분

        out: list[Passage] = []
        per_source: dict[str, int] = {}
        for i in idx:
            m = self._meta[int(i)]
            src = m["source"]
            # 한 논문이 top-k 를 독식하면 근거의 폭이 좁아진다 — 출처당 상한을 둔다
            if per_source.get(src, 0) >= settings.rag_max_per_source:
                continue
            per_source[src] = per_source.get(src, 0) + 1
            out.append(Passage(text=m["text"], source=src,
                               kind=m["kind"], score=float(sims[int(i)])))
            if len(out) >= top_k:
                break
        with self._lock:
            self._cache[key] = out
        return out

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()


# ── 프롬프트 삽입 ───────────────────────────────────────────────────

def format_block(passages: list[Passage], max_chars: int = 0) -> str:
    """발췌를 `[참고 지식]` 블록으로. 빈 리스트면 빈 문자열(= 삽입 안 함)."""
    if not passages:
        return ""
    max_chars = max_chars or settings.rag_max_chars
    lines, used = [], 0
    for p in passages:
        t = p.text.strip().replace("\n", " ")
        if used + len(t) > max_chars:
            t = t[: max(0, max_chars - used)]
            if len(t) < 120:                        # 토막만 남으면 넣지 않는다
                break
        lines.append(f"- {t}")
        used += len(t)
        if used >= max_chars:
            break
    if not lines:
        return ""
    return (
        "[참고 지식] 아래는 실종자 수색·배회 행동 연구에서 검색된 발췌다. "
        "판단의 근거로 쓰되, 발췌에 없는 내용을 발췌에서 나온 것처럼 쓰지 않는다.\n"
        + "\n".join(lines)
    )


_singleton: Retriever | None = None
_singleton_lock = threading.Lock()


def get_retriever() -> Retriever | None:
    """설정이 켜져 있을 때만 검색기를 준다. 꺼져 있으면 None."""
    global _singleton
    if not settings.rag_enabled:
        return None
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                # 인덱스는 passage(문서) 벡터라 비교도 passage 모델 기준으로.
                _singleton = Retriever(
                    settings.rag_index_path,
                    settings.embed_model_passage or settings.embed_model,
                )
    return _singleton
