"""claims와 SFT 데이터의 구조·근거·누수·분포를 검증한다."""

from __future__ import annotations

import collections
import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
ALLOWED_LEVELS = {"상", "중", "하"}


def canonical(text: str) -> str:
    text = re.sub(r"(?<=\w)-\s+(?=\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    claims = load(HERE / "claims" / "claims.jsonl")
    claim_by_id = {row["claim_id"]: row for row in claims}
    assert len(claim_by_id) == len(claims)

    page_cache = {}
    for path in (HERE / "corpus" / "pages").glob("*.jsonl"):
        for row in load(path):
            page_cache[(row["paper_id"], row["pdf_page"])] = row["text"]
    for claim in claims:
        src = claim["source"]
        assert src["quote_verified"] is True
        assert canonical(src["quote"]) in canonical(page_cache[(src["paper_id"], src["pdf_page"])])

    report = {"claims": len(claims), "datasets": {}}
    for name in ("train_analyst", "val_analyst", "train_first_person", "val_first_person"):
        rows = load(HERE / "dataset" / f"{name}.jsonl")
        ids = [row["id"] for row in rows]
        # mixed는 같은 의미 샘플의 perspective별 id가 다르다.
        assert len(ids) == len(set(ids))
        counter = collections.Counter()
        assistant_hashes = collections.Counter()
        for row in rows:
            assert [m["role"] for m in row["messages"]] == ["system", "user", "assistant"]
            answer = json.loads(row["messages"][2]["content"])
            assert answer["confusion_level"] in ALLOWED_LEVELS
            assert answer["goal_label"] is None or answer["goal_label"] in row["messages"][1]["content"]
            if "behavior" in answer:   # 계약 v2 (1인칭) — 닫힌 어휘 + goal 일관성
                assert answer["behavior"] in {"끌림점 접근", "귀소 시도", "은신·멈춤", "계속 배회"}
                assert (answer["behavior"] == "끌림점 접근") == (answer["goal_label"] is not None)
                counter["behavior:" + answer["behavior"]] += 1
                # 행동↔문장 모순 검사 (외부 리뷰 지적 1 — v3에서 397건 검출된 유형)
                text = answer.get("inner", "") + " " + answer["status"]
                if answer["behavior"] == "은신·멈춤":
                    assert not re.search(r"이동을 계속|계속 걷|계속 이동|계속 움직", text), text
                elif answer["behavior"] == "계속 배회":
                    assert not re.search(r"멈춰|멈추고|머무|숨기|숨는다|숨고", text), text
                elif answer["behavior"] == "귀소 시도":
                    assert "집" in text, text
                # 조사 오류 검사 (지적 2 — "표지이 보인다" 유형)
                for m in re.finditer(r"([가-힣])이 (보인다|들린다)", text):
                    assert (ord(m.group(1)) - 0xAC00) % 28 != 0, text
            assert row["metadata"]["gold_overlap"] is False
            for claim_id in row["metadata"]["claim_ids"]:
                assert claim_id in claim_by_id
            counter["population:" + row["metadata"]["population"]] += 1
            counter["class:" + row["metadata"]["behavior_class"]] += 1
            counter["archetype:" + row["metadata"]["scenario_archetype"]] += 1
            counter["confusion:" + answer["confusion_level"]] += 1
            counter["goal:null" if answer["goal_label"] is None else "goal:label"] += 1
            assistant_hashes[row["messages"][2]["content"]] += 1
        report["datasets"][name] = {
            "rows": len(rows),
            "unique_ids": len(set(ids)),
            "unique_assistant_outputs": len(assistant_hashes),
            "max_identical_assistant_output": max(assistant_hashes.values()),
            "distribution": dict(sorted(counter.items())),
        }
    out = HERE / "dataset" / "report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

