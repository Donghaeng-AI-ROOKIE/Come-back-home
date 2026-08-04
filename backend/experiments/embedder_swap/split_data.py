"""QA 493쌍을 학습(train_use)/최종비교(test)로 나눈다.

test 는 SKT 파인튜닝이 전혀 보지 않아야 공정한 비교가 된다 — val 로 학습을
멈추므로(save_best_model) val 로 최종 비교하면 SKT 에 유리해진다. seed 고정이라
로컬·코랩 어디서 돌려도 같은 분할이 나온다.

사용:
  python -m experiments.embedder_swap.split_data --train train.jsonl
"""

from __future__ import annotations

import argparse
import random


def main() -> int:
    ap = argparse.ArgumentParser(description="QA train.jsonl을 train_use/test로 분리")
    ap.add_argument("--train", default="train.jsonl", help="원본 학습셋 (val은 이미 분리돼 있다고 가정)")
    ap.add_argument("--n-test", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    rows = open(args.train, encoding="utf-8").read().splitlines()
    random.seed(args.seed)
    random.shuffle(rows)

    open("test.jsonl", "w", encoding="utf-8").write("\n".join(rows[: args.n_test]))
    open("train_use.jsonl", "w", encoding="utf-8").write("\n".join(rows[args.n_test :]))
    print(f"train_use {len(rows) - args.n_test} · test {args.n_test}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
