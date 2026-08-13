"""SKT A.X-Encoder-base를 QA쌍(sar QA)으로 파인튜닝해 검색 임베더로 만든다.

A.X-Encoder는 원래 분류/NLU용이지 검색용이 아니다. MultipleNegativesRankingLoss로
(질문=user, 답=assistant) 쌍을 가깝게 학습시켜야 코사인 유사도 검색에 쓸 수 있다.
GPU 필요(로컬 CPU는 매우 느림) — 코랩 T4 기준 3epoch·396쌍에 약 74초.

⚠ val로 학습을 멈추므로(save_best_model=True), val은 최종 비교에 쓰면 안 된다.
   최종 비교는 이 val을 전혀 안 본 test로 한다 (split_data.py 로 만든 것).

사용 (코랩, train_use.jsonl·val.jsonl을 먼저 업로드):
  python -m experiments.embedder_swap.train_skt
"""

from __future__ import annotations

import argparse
import json


def load_pairs(path: str) -> list:
    from sentence_transformers import InputExample

    out = []
    for line in open(path, encoding="utf-8"):
        if not line.strip():
            continue
        msgs = json.loads(line)["messages"]
        q = next(m["content"] for m in msgs if m["role"] == "user")
        a = next(m["content"] for m in msgs if m["role"] == "assistant")
        out.append(InputExample(texts=[q, a]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="SKT A.X-Encoder-base를 검색 임베더로 파인튜닝")
    ap.add_argument("--base-model", default="skt/A.X-Encoder-base")
    ap.add_argument("--train", default="train_use.jsonl")
    ap.add_argument("--val", default="val.jsonl")
    ap.add_argument("--output", default="axencoder-sar-ft")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--warmup-steps", type=int, default=30)
    args = ap.parse_args()

    from torch.utils.data import DataLoader
    from sentence_transformers import SentenceTransformer, losses, models
    from sentence_transformers.evaluation import InformationRetrievalEvaluator

    train = load_pairs(args.train)
    val = load_pairs(args.val)
    print("train", len(train), "val", len(val))

    # model_kwargs: model_args는 최신 sentence-transformers에서 deprecated
    word = models.Transformer(
        args.base_model, max_seq_length=256, model_kwargs={"trust_remote_code": True}
    )
    pool = models.Pooling(word.get_word_embedding_dimension(), pooling_mode="mean")
    model = SentenceTransformer(modules=[word, pool])

    loader = DataLoader(train, shuffle=True, batch_size=args.batch_size)
    loss = losses.MultipleNegativesRankingLoss(model)
    q = {str(i): e.texts[0] for i, e in enumerate(val)}
    c = {str(i): e.texts[1] for i, e in enumerate(val)}
    r = {str(i): {str(i)} for i in range(len(val))}
    ev = InformationRetrievalEvaluator(q, c, r, name="val")

    model.fit(
        train_objectives=[(loader, loss)],
        evaluator=ev,
        evaluation_steps=50,
        epochs=args.epochs,
        warmup_steps=args.warmup_steps,
        output_path=args.output,
        save_best_model=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
