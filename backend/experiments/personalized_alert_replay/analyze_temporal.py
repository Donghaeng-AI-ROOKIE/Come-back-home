"""시간매칭 A/B/C를 동일 38셀 정책과 운영 80% 커버리지 정책으로 분리 집계."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def _load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _coverage_cells(surface: dict[str, float], coverage: float = 0.8) -> set[str]:
    selected = set()
    accumulated = 0.0
    for cell, probability in sorted(surface.items(), key=lambda item: item[1], reverse=True):
        selected.add(cell)
        accumulated += probability
        if accumulated >= coverage:
            break
    return selected


def _operational(rows: list[dict], arm: str, *, outside_only: bool) -> dict:
    hits = 0
    cell_counts = []
    for row in rows:
        for snapshot in row["arms"][arm]["temporal"]["snapshots"]:
            if outside_only and not snapshot["truth_outside_d1"]:
                continue
            selected = _coverage_cells(snapshot["surface_cells"])
            hits += snapshot["truth_cell"] in selected
            cell_counts.append(len(selected))
    return {
        "hits": hits,
        "n": len(cell_counts),
        "hit_rate": hits / max(len(cell_counts), 1),
        "mean_cells": sum(cell_counts) / max(len(cell_counts), 1),
        "total_cells": sum(cell_counts),
    }


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows = _load(RESULTS / args.input)
    all_policy = {arm: _operational(rows, arm, outside_only=False) for arm in "ABC"}
    outside_policy = {arm: _operational(rows, arm, outside_only=True) for arm in "ABC"}
    valid = sum(row["arms"]["B"]["valid"] and row["arms"]["C"]["valid"] for row in rows)
    timepoints = sum(len(row["arms"]["A"]["temporal"]["snapshots"]) for row in rows)

    fixed_hits = {
        arm: sum(
            snapshot["hit"]
            for row in rows
            for snapshot in row["arms"][arm]["temporal"]["snapshots"]
        )
        for arm in "ABC"
    }
    truth_probability = {
        arm: sum(
            snapshot["truth_probability"]
            for row in rows
            for snapshot in row["arms"][arm]["temporal"]["snapshots"]
        ) / timepoints
        for arm in "ABC"
    }
    outside_snapshots = [
        snapshot
        for row in rows
        for snapshot in row["arms"]["A"]["temporal"]["snapshots"]
        if snapshot["truth_outside_d1"]
    ]
    outside_probability = {}
    for arm in "ABC":
        values = [
            snapshot["truth_probability"]
            for row in rows
            for snapshot in row["arms"][arm]["temporal"]["snapshots"]
            if snapshot["truth_outside_d1"]
        ]
        outside_probability[arm] = sum(values) / max(len(values), 1)

    jaccard = {
        arm: sum(
            row["arms"][arm]["temporal"]["mean_d2_jaccard_vs_previous"]
            for row in rows
        ) / len(rows)
        for arm in "ABC"
    }
    behavior_types = sorted({row.get("truth_behavior", "move") for row in rows})
    lines = [
        "# EXAONE E2E 시간축 개인화 알림 탐색 실험",
        "",
        f"- 표본: Persona {len(rows)}명 × 0·45·90·135분 = {timepoints} 시간점",
        f"- 정답 행동 유형: {', '.join(behavior_types)}",
        f"- 유효성: {valid}/{len(rows)} 시나리오 B·C 모두 EXAONE+OSMnx, 폴백 0건",
        "- 정답: Persona 이동반경 내 독립 OSM 도보경로를 165분에 이동·휴식하며 재생",
        "- 시간매칭: 각 t분 POA의 알림셀을 바로 그 t분 실제위치와 1:1 비교",
        "",
        "## 1. 동일 예산 정책 — 매 시점 D1 19셀 + D2 19셀",
        "",
        "| 지표 | A 거리 | B EXAONE 비개인화 | C EXAONE 개인화 |",
        "|---|---:|---:|---:|",
        "| 동시간대 알림셀 적중 | "
        + " | ".join(f"{fixed_hits[arm]}/{timepoints} ({_pct(fixed_hits[arm] / timepoints)})" for arm in "ABC") + " |",
        "| 실제위치 평균 확률 | "
        + " | ".join(_pct(truth_probability[arm]) for arm in "ABC") + " |",
        f"| D1 밖 실제위치 평균 확률(n={len(outside_snapshots)}) | "
        + " | ".join(_pct(outside_probability[arm]) for arm in "ABC") + " |",
        "| 이전 시점 D2와 Jaccard(높을수록 덜 변함) | "
        + " | ".join(_pct(jaccard[arm]) for arm in "ABC") + " |",
        "",
        "## 2. 현재 운영 정책 — POA 누적 80% 커버리지",
        "",
        "| 범위 | 군 | 적중 | 시점당 평균 알림셀 | 총 알림셀·시점 |",
        "|---|---|---:|---:|---:|",
    ]
    labels = {"A": "A 거리", "B": "B 비개인화", "C": "C 개인화"}
    for scope, data in (("전체", all_policy), ("D1 밖", outside_policy)):
        for arm in "ABC":
            item = data[arm]
            lines.append(
                f"| {scope} | {labels[arm]} | {item['hits']}/{item['n']} "
                f"({_pct(item['hit_rate'])}) | {item['mean_cells']:.1f} | {item['total_cells']} |"
            )
    b_cells = all_policy["B"]["mean_cells"]
    c_cells = all_policy["C"]["mean_cells"]
    saving = 1 - c_cells / b_cells
    hit_delta = all_policy["C"]["hits"] - all_policy["B"]["hits"]
    fixed_delta = fixed_hits["C"] - fixed_hits["B"]
    lines += [
        "",
        "## 해석",
        "",
        f"- 운영 정책에서 C는 B보다 적중이 {hit_delta:+d}회였고, "
        f"평균 알림셀을 {b_cells:.1f}→{c_cells:.1f}로 {_pct(saving)} 줄였다.",
        f"- C의 동시간대 실제위치 평균확률은 B의 "
        f"{truth_probability['C'] / max(truth_probability['B'], 1e-12):.2f}배였다.",
        f"- 고정 38셀에서 C는 B보다 적중이 {fixed_delta:+d}회였다.",
        f"- {len(rows)}명·1회 prior 표본이므로 확증 결론은 아니다. 반복시드·교차 Persona 실험이 필요하다.",
    ]
    output = RESULTS / args.output
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"saved={output}")


if __name__ == "__main__":
    main()
