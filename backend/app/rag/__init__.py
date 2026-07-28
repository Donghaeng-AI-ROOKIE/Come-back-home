"""RAG — 논문 코퍼스 검색으로 EXAONE 추론에 근거를 붙인다.

역할 분담(2026-07-27 결정):
  RAG = 사실·근거   / 파인튜닝(LoRA) = 출력 형식·행동

인덱스는 `sar-finetune/build_rag.py` 가 만든 npz 한 개다(벡터 + 메타).
DB 서버가 필요 없는 규모(수천 청크)라 파일 하나를 메모리에 올려 쓴다.
"""
from app.rag.grounding import check_numeric_grounding, summarize
from app.rag.retriever import Retriever, get_retriever, format_block

__all__ = ["Retriever", "get_retriever", "format_block",
           "check_numeric_grounding", "summarize"]
