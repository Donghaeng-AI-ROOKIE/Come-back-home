"""임베더가 질문에 맞는 논문 근거를 RAG 코퍼스에서 얼마나 잘 찾는지 잰다(Recall@1/@4).

corpus = rag_index.npz 안의 논문 청크(2,488개, 원문 텍스트만 재사용) + test.jsonl의
정답 50개. 각 질문이 자기 정답을 코퍼스 전체(2,538개 후보) 중 상위 4개로 찾는지 센다.
정답은 사람이 미리 짝지은 것이라 순환평가는 아니다. GPU 권장(2,488개를 매번 다시
벡터화 — 인덱스에 있던 KURE 벡터는 재사용하지 않는다. 임베더별로 공정 비교하려면
그래야 한다) — 로컬 CPU는 느리다.

⚠ Recall@1이 모든 임베더에서 0%에 가깝게 나오는 건 정상일 수 있다 — test의 "정답"
   (사람이 풀어쓴 답변)과 거의 같은 내용의 원본 논문 청크가 코퍼스 안에 함께 있어서,
   그 원문이 근소한 차이로 1등을 채가는 경합 구도로 추정된다. 모델 간 비교는 Recall@4로.

사용 (코랩, rag_index.npz·test.jsonl을 먼저 업로드):
  python -m experiments.embedder_swap.rag_recall --model axencoder-sar-ft
  python -m experiments.embedder_swap.rag_recall --model nlpai-lab/KURE-v1
  python -m experiments.embedder_swap.rag_recall --model skt/A.X-Encoder-base   # 튜닝 전 원본, 비교용

  # Upstage는 UPSTAGE_API_KEY 환경변수 필요. 코랩 Secrets 쓰면 실행 전에:
  #   import os; from google.colab import userdata
  #   os.environ["UPSTAGE_API_KEY"] = userdata.get("UPSTAGE_API_KEY")
  python -m experiments.embedder_swap.rag_recall --upstage
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request

import numpy as np


def upstage_embed(texts: list[str], model: str, api_key: str, batch: int = 100) -> np.ndarray:
    vecs = []
    for i in range(0, len(texts), batch):
        payload = json.dumps({"model": model, "input": texts[i : i + batch]}).encode()
        req = urllib.request.Request(
            "https://api.upstage.ai/v1/embeddings",
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        d = json.loads(urllib.request.urlopen(req, timeout=60).read())
        rows = sorted(d["data"], key=lambda r: r["index"])
        vecs += [r["embedding"] for r in rows]
    arr = np.asarray(vecs, dtype="float32")
    arr /= np.linalg.norm(arr, axis=1, keepdims=True)  # 코사인 위해 정규화
    return arr


def main() -> int:
    ap = argparse.ArgumentParser(description="RAG Recall@1/@4 측정 — 임베더 비교")
    ap.add_argument("--model", help="로컬 sentence-transformers 모델명/경로 (HF 모델명 또는 axencoder-sar-ft)")
    ap.add_argument("--upstage", action="store_true", help="Upstage API로 측정 (UPSTAGE_API_KEY 환경변수 필요)")
    ap.add_argument("--rag-index", default="rag_index.npz")
    ap.add_argument("--test", default="test.jsonl")
    args = ap.parse_args()

    if not args.model and not args.upstage:
        ap.error("--model 또는 --upstage 중 하나는 지정해야 한다")

    z = np.load(args.rag_index, allow_pickle=True)
    chunks = [m["text"] for m in json.loads(str(z["meta"]))]
    test = [json.loads(l) for l in open(args.test, encoding="utf-8") if l.strip()]
    Q = [next(m["content"] for m in r["messages"] if m["role"] == "user") for r in test]
    A = [next(m["content"] for m in r["messages"] if m["role"] == "assistant") for r in test]

    corpus = chunks + A
    gold = {i: len(chunks) + i for i in range(len(A))}

    if args.upstage:
        api_key = os.environ["UPSTAGE_API_KEY"]
        print("### 임베더: Upstage (embedding-query/embedding-passage)")
        C = upstage_embed(corpus, "embedding-passage", api_key)
        Qv = upstage_embed(Q, "embedding-query", api_key)
    else:
        from sentence_transformers import SentenceTransformer

        print(f"### 임베더: {args.model}")
        emb = SentenceTransformer(args.model)
        C = emb.encode(corpus, normalize_embeddings=True)
        Qv = emb.encode(Q, normalize_embeddings=True)

    sims = Qv @ C.T
    hit1 = hit4 = 0
    for i in range(len(Q)):
        top = np.argsort(-sims[i])[:4]
        if gold[i] == top[0]:
            hit1 += 1
        if gold[i] in top:
            hit4 += 1
    print(f"Recall@1 = {hit1}/{len(Q)} = {hit1/len(Q):.1%}")
    print(f"Recall@4 = {hit4}/{len(Q)} = {hit4/len(Q):.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
