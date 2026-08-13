"""표면형 다양화 패스 — inner·status 를 EXAONE 으로 의미 보존 패러프레이즈.

왜: 합성 셋의 마지막 남은 약점은 템플릿 표면형이다(구조 다양성은 아키타입이,
의미 라벨은 게이지 결합이 해결). 문장만 모델이 다시 쓰게 하되, 의미 축
(behavior·goal_label·confusion_level)은 건드리지 못하게 하고 검증 실패분은
원문 유지로 폴백한다 — 다양화는 이득만, 손상은 구조적으로 불가.

검증(통과 못 하면 원문 유지):
  - JSON 파싱, inner·status 비어있지 않음, 길이 상한
  - goal 이 있으면 라벨 원문이 문장에서 사라지지 않았는지 (goal 문장의 정합)
  - 골드셋 라벨 혼입 금지

실행: cd backend && .venv/bin/python experiments/mind_tuning/paraphrase_pass.py [--limit N]
입력: dataset/train_first_person.jsonl → 출력: dataset/train_first_person_final.jsonl
"""
from __future__ import annotations

import argparse
import collections
import importlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from build_dataset import GOLD_LABELS  # noqa: E402

_SYSTEM = """\
너는 문장 다듬기 도우미다. 실종자 마음 시뮬레이션 데이터의 두 문장을 같은 뜻으로
자연스럽게 다시 쓴다.

규칙:
- inner 는 당사자의 속마음 1~2문장, status 는 상태 서술 한 구절 — 역할 유지.
- 뜻·행동·장소 이름·혼란 정도를 바꾸지 않는다. 새 장소나 사실을 지어내지 않는다.
- 말투는 자연스러운 구어로, 원문과 다른 표현을 쓴다.
- JSON 객체 {"inner": "...", "status": "..."} 만 출력한다."""


def _ok(new: dict, row_answer: dict) -> bool:
    inner, status = new.get("inner"), new.get("status")
    if not (isinstance(inner, str) and isinstance(status, str)
            and 5 <= len(inner) <= 160 and 5 <= len(status) <= 120):
        return False
    text = inner + " " + status
    goal = row_answer.get("goal_label")
    if goal and goal not in text:
        return False                      # 목표 문장에서 장소가 사라지면 정합 훼손
    return not any(lb in text for lb in GOLD_LABELS)


def main(limit: int | None) -> None:
    ex = importlib.import_module("app.llm.exaone")
    client = ex.ExaoneClient(model="exaone-base")
    rows = [json.loads(line) for line in
            (HERE / "dataset" / "train_first_person.jsonl").read_text(encoding="utf-8").splitlines()]
    if limit:
        rows = rows[:limit]
    stats: collections.Counter = collections.Counter()
    out_rows = []
    for i, row in enumerate(rows):
        answer = json.loads(row["messages"][2]["content"])
        user = json.dumps({"inner": answer["inner"], "status": answer["status"],
                           "참고(바꾸지 말 것)": {"행동": answer["behavior"],
                                             "장소": answer.get("goal_label")}},
                          ensure_ascii=False)
        try:
            raw = client.chat([{"role": "system", "content": _SYSTEM},
                               {"role": "user", "content": user}],
                              temperature=0.7, max_tokens=220)
            new = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        except Exception:  # noqa: BLE001 — 실패는 원문 유지로 폴백
            new = None
        if new and _ok(new, answer):
            answer["inner"], answer["status"] = new["inner"].strip(), new["status"].strip()
            row["messages"][2]["content"] = json.dumps(answer, ensure_ascii=False)
            row["metadata"]["paraphrased"] = True
            stats["교체"] += 1
        else:
            row["metadata"]["paraphrased"] = False
            stats["원문 유지"] += 1
        out_rows.append(row)
        if (i + 1) % 200 == 0:
            print(f"  {i + 1}/{len(rows)} — {dict(stats)}", flush=True)

    out = HERE / "dataset" / "train_first_person_final.jsonl"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out_rows) + "\n",
                   encoding="utf-8")
    uniq = len({r["messages"][2]["content"] for r in out_rows})
    print(f"[paraphrase] {dict(stats)} → {out.name} (고유 답 {uniq}/{len(out_rows)})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    main(ap.parse_args().limit)
