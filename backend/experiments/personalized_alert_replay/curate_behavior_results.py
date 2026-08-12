"""원본과 사전 제한 재시도에서 시나리오별 첫 유효 A/B/C 행을 고른다.

성공할 때까지 반복하지 않는다. 입력 파일 순서대로 첫 유효 행만 채택하고,
끝까지 유효하지 않은 시나리오는 제외 목록에 기록한다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def _load(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", required=True, help="우선순위순 쉼표 구분 JSONL")
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit", required=True)
    args = parser.parse_args()

    paths = [RESULTS / item.strip() for item in args.inputs.split(",") if item.strip()]
    attempts: dict[str, list[tuple[str, dict]]] = {}
    expected: list[str] = []
    for path in paths:
        for row in _load(path):
            scenario_id = row["scenario_id"]
            if scenario_id not in attempts:
                expected.append(scenario_id)
                attempts[scenario_id] = []
            attempts[scenario_id].append((path.name, row))

    selected: list[dict] = []
    audit_rows = []
    for scenario_id in expected:
        candidates = attempts[scenario_id]
        valid = [
            (source, row) for source, row in candidates
            if row["arms"]["B"]["valid"] and row["arms"]["C"]["valid"]
        ]
        if valid:
            # 원본이 유효하면 원본, 아니면 제한된 재시도의 첫 유효 결과.
            source, row = valid[0]
            selected.append(row)
            status = "selected"
        else:
            source = None
            status = "excluded_no_valid_exaone_pair"
        audit_rows.append({
            "scenario_id": scenario_id,
            "status": status,
            "selected_source": source,
            "attempts": [{
                "source": candidate_source,
                "b_valid": candidate["arms"]["B"]["valid"],
                "c_valid": candidate["arms"]["C"]["valid"],
                "c_prior_sources": candidate["arms"]["C"].get("prior_sources", []),
                "c_fallback_reasons": candidate["arms"]["C"].get("fallback_reasons", []),
            } for candidate_source, candidate in candidates],
        })

    output = RESULTS / args.output
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected),
        encoding="utf-8",
    )
    audit = RESULTS / args.audit
    audit.write_text(json.dumps({
        "selection_rule": "first valid B/C pair by input order; no retry-until-success",
        "inputs": [path.name for path in paths],
        "selected_scenarios": len(selected),
        "expected_scenarios": len(expected),
        "rows": audit_rows,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"saved={output} selected={len(selected)}/{len(expected)} audit={audit}")


if __name__ == "__main__":
    main()
