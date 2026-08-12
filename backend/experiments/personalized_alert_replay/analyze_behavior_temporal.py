"""10 Persona 행동층별 시간축 A/B/C 결과를 paired 방식으로 집계한다."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from experiments.personalized_alert_replay.analyze_temporal import _coverage_cells

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
ARMS = "ABC"
BEHAVIORS = ("stay", "move", "backtrack", "hide")
LABELS = {
    "A": "A 거리",
    "B": "B EXAONE 비개인화",
    "C": "C EXAONE 개인화",
    "stay": "정지",
    "move": "지속 이동",
    "backtrack": "왕복·순환",
    "hide": "은폐",
}


def _load(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _snapshots(rows: list[dict], arm: str, behavior: str | None = None):
    for row in rows:
        if behavior is not None and row["truth_behavior"] != behavior:
            continue
        for snapshot in row["arms"][arm]["temporal"]["snapshots"]:
            yield row, snapshot


def _metrics(rows: list[dict], arm: str, behavior: str | None = None) -> dict:
    fixed_hits = operational_hits = outside_fixed = outside_operational = 0
    count = outside_count = 0
    probabilities: list[float] = []
    outside_probabilities: list[float] = []
    operational_cells: list[int] = []
    outside_operational_cells: list[int] = []
    for _, snapshot in _snapshots(rows, arm, behavior):
        selected = _coverage_cells(snapshot["surface_cells"])
        fixed_hits += bool(snapshot["hit"])
        operational_hits += snapshot["truth_cell"] in selected
        operational_cells.append(len(selected))
        probabilities.append(snapshot["truth_probability"])
        count += 1
        if snapshot["truth_outside_d1"]:
            outside_fixed += bool(snapshot["d2_hit"])
            outside_operational += snapshot["truth_cell"] in selected
            outside_operational_cells.append(len(selected))
            outside_probabilities.append(snapshot["truth_probability"])
            outside_count += 1
    return {
        "n": count,
        "fixed_hits": fixed_hits,
        "fixed_rate": fixed_hits / max(count, 1),
        "operational_hits": operational_hits,
        "operational_rate": operational_hits / max(count, 1),
        "operational_cells": sum(operational_cells) / max(len(operational_cells), 1),
        "mean_probability": sum(probabilities) / max(len(probabilities), 1),
        "outside_n": outside_count,
        "outside_fixed_hits": outside_fixed,
        "outside_fixed_rate": outside_fixed / max(outside_count, 1),
        "outside_operational_hits": outside_operational,
        "outside_operational_rate": outside_operational / max(outside_count, 1),
        "outside_operational_cells": (
            sum(outside_operational_cells) / max(len(outside_operational_cells), 1)
        ),
        "outside_probability": (
            sum(outside_probabilities) / max(len(outside_probabilities), 1)
        ),
    }


def _paired(rows: list[dict], policy: str) -> dict:
    b_only = c_only = both = neither = 0
    for row in rows:
        b_snaps = row["arms"]["B"]["temporal"]["snapshots"]
        c_snaps = row["arms"]["C"]["temporal"]["snapshots"]
        for b, c in zip(b_snaps, c_snaps, strict=True):
            if policy == "fixed":
                b_hit, c_hit = bool(b["hit"]), bool(c["hit"])
            else:
                b_hit = b["truth_cell"] in _coverage_cells(b["surface_cells"])
                c_hit = c["truth_cell"] in _coverage_cells(c["surface_cells"])
            if b_hit and c_hit:
                both += 1
            elif b_hit:
                b_only += 1
            elif c_hit:
                c_only += 1
            else:
                neither += 1
    return {"both": both, "b_only": b_only, "c_only": c_only, "neither": neither}


def _matched_b_budget(rows: list[dict]) -> dict:
    """각 시점 C에서 B 운영 정책과 동일한 셀 수만 상위순으로 선택."""
    hits = outside_hits = outside_n = 0
    count = 0
    probabilities = []
    for row in rows:
        b_snaps = row["arms"]["B"]["temporal"]["snapshots"]
        c_snaps = row["arms"]["C"]["temporal"]["snapshots"]
        for b, c in zip(b_snaps, c_snaps, strict=True):
            budget = len(_coverage_cells(b["surface_cells"]))
            selected = {
                cell for cell, _ in sorted(
                    c["surface_cells"].items(), key=lambda item: item[1], reverse=True,
                )[:budget]
            }
            hit = c["truth_cell"] in selected
            hits += hit
            count += 1
            probabilities.append(c["truth_probability"])
            if c["truth_outside_d1"]:
                outside_hits += hit
                outside_n += 1
    return {
        "hits": hits,
        "n": count,
        "rate": hits / max(count, 1),
        "outside_hits": outside_hits,
        "outside_n": outside_n,
        "outside_rate": outside_hits / max(outside_n, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows = _load(RESULTS / args.input)
    persona_count = len({row["profile_id"] for row in rows})
    strata = sorted({row["stratum"] for row in rows})
    behaviors = defaultdict(list)
    for row in rows:
        behaviors[row["truth_behavior"]].append(row)

    overall = {arm: _metrics(rows, arm) for arm in ARMS}
    by_behavior = {
        behavior: {arm: _metrics(rows, arm, behavior) for arm in ARMS}
        for behavior in BEHAVIORS
    }
    by_stratum = {
        stratum: {
            arm: _metrics([row for row in rows if row["stratum"] == stratum], arm)
            for arm in ARMS
        }
        for stratum in strata
    }
    macro = {
        arm: {
            key: sum(by_behavior[behavior][arm][key] for behavior in BEHAVIORS) / len(BEHAVIORS)
            for key in (
                "fixed_rate", "operational_rate", "operational_cells", "mean_probability",
            )
        }
        for arm in ARMS
    }
    fixed_pair = _paired(rows, "fixed")
    op_pair = _paired(rows, "operational")
    matched_c = _matched_b_budget(rows)
    valid = sum(row["arms"]["B"]["valid"] and row["arms"]["C"]["valid"] for row in rows)
    fallbacks = sum(
        bool(reason)
        for row in rows
        for arm in "BC"
        for reason in row["arms"][arm].get("fallback_reasons", [])
    )

    lines = [
        "# 10개 행동층 합성 Persona 시간축 A/B/C 실험",
        "",
        f"- 표본: Persona {persona_count}명, 유효 시나리오 {len(rows)}개 × 4시점 = {len(rows) * 4}개 짝지은 평가점",
        "- 행동층: 정지·지속 이동·왕복·순환·은폐",
        f"- 방향층: {', '.join(strata)}",
        f"- 유효성: {valid}/{len(rows)}개 채택 시나리오 B·C 모두 EXAONE+OSMnx, 채택 데이터 fallback {fallbacks}건",
        "- 시간점: 신고 후 0·45·90·135분의 예측지도와 같은 시각의 독립 OSM 정답위치 비교",
        "- 주의: 4개 시간점은 같은 Persona 안에서 상관되므로 40개를 독립 표본으로 간주하지 않음",
        "",
        "## 전체 결과",
        "",
        "| 정책·지표 | A 거리 | B 비개인화 | C 개인화 |",
        "|---|---:|---:|---:|",
        "| 동일 38셀 위치 포함 | " + " | ".join(
            f"{overall[a]['fixed_hits']}/{overall[a]['n']} ({_pct(overall[a]['fixed_rate'])})"
            for a in ARMS
        ) + " |",
        "| 실제 위치 평균 확률 | " + " | ".join(
            _pct(overall[a]["mean_probability"]) for a in ARMS
        ) + " |",
        "| 운영 80% 위치 포함 | " + " | ".join(
            f"{overall[a]['operational_hits']}/{overall[a]['n']} ({_pct(overall[a]['operational_rate'])})"
            for a in ARMS
        ) + " |",
        "| 운영 80% 평균 알림 셀 | " + " | ".join(
            f"{overall[a]['operational_cells']:.1f}" for a in ARMS
        ) + " |",
        "| D1 밖 운영 80% 위치 포함 | " + " | ".join(
            f"{overall[a]['outside_operational_hits']}/{overall[a]['outside_n']} "
            f"({_pct(overall[a]['outside_operational_rate'])})" for a in ARMS
        ) + " |",
        f"| B 운영 셀 수에 맞춘 C 위치 포함 | - | "
        f"{overall['B']['operational_hits']}/{overall['B']['n']} ({_pct(overall['B']['operational_rate'])}) | "
        f"{matched_c['hits']}/{matched_c['n']} ({_pct(matched_c['rate'])}) |",
        "",
        "### B와 C의 같은 시간점 짝지은 비교",
        "",
        "| 정책 | 둘 다 적중 | B만 적중 | C만 적중 | 둘 다 실패 |",
        "|---|---:|---:|---:|---:|",
        f"| 동일 38셀 | {fixed_pair['both']} | {fixed_pair['b_only']} | "
        f"{fixed_pair['c_only']} | {fixed_pair['neither']} |",
        f"| 운영 80% | {op_pair['both']} | {op_pair['b_only']} | "
        f"{op_pair['c_only']} | {op_pair['neither']} |",
        "",
        "## 행동 유형별 결과",
        "",
        "| 행동층 | 군 | 동일 38셀 적중 | 운영 80% 적중 | 운영 평균 셀 | 실제위치 평균확률 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for behavior in BEHAVIORS:
        for arm in ARMS:
            item = by_behavior[behavior][arm]
            lines.append(
                f"| {LABELS[behavior]} | {LABELS[arm]} | "
                f"{item['fixed_hits']}/{item['n']} ({_pct(item['fixed_rate'])}) | "
                f"{item['operational_hits']}/{item['n']} ({_pct(item['operational_rate'])}) | "
                f"{item['operational_cells']:.1f} | {_pct(item['mean_probability'])} |"
            )
    lines += [
        "",
        "## 방향층별 결과",
        "",
        "| 방향층 | 군 | 동일 38셀 적중 | 운영 80% 적중 | 운영 평균 셀 | 실제위치 평균확률 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for stratum in strata:
        for arm in ARMS:
            item = by_stratum[stratum][arm]
            lines.append(
                f"| {stratum} | {LABELS[arm]} | "
                f"{item['fixed_hits']}/{item['n']} ({_pct(item['fixed_rate'])}) | "
                f"{item['operational_hits']}/{item['n']} ({_pct(item['operational_rate'])}) | "
                f"{item['operational_cells']:.1f} | {_pct(item['mean_probability'])} |"
            )
    lines += [
        "",
        "## 행동층 동일가중 매크로 평균",
        "",
        "지속 이동형이 4명으로 다른 유형보다 많기 때문에, 네 행동층을 각각 25%로 동일하게 반영했다.",
        "",
        "| 군 | 동일 38셀 적중률 | 운영 80% 적중률 | 운영 평균 셀 | 실제위치 평균확률 |",
        "|---|---:|---:|---:|---:|",
    ]
    for arm in ARMS:
        lines.append(
            f"| {LABELS[arm]} | {_pct(macro[arm]['fixed_rate'])} | "
            f"{_pct(macro[arm]['operational_rate'])} | {macro[arm]['operational_cells']:.1f} | "
            f"{_pct(macro[arm]['mean_probability'])} |"
        )

    b_cells, c_cells = overall["B"]["operational_cells"], overall["C"]["operational_cells"]
    cell_saving = 1 - c_cells / b_cells
    lines += [
        "",
        "## 해석",
        "",
        f"- **동일 38셀 조건:** C는 {overall['C']['fixed_hits']}/{overall['C']['n']}, B는 "
        f"{overall['B']['fixed_hits']}/{overall['B']['n']}로 C가 "
        f"{overall['C']['fixed_hits'] - overall['B']['fixed_hits']:+d}개 시간점 차이였다. "
        f"짝지은 비교에서는 C만 맞힌 시점이 {fixed_pair['c_only']}개, "
        f"B만 맞힌 시점이 {fixed_pair['b_only']}개였다.",
        f"- **운영 80% 조건:** C는 평균 셀을 {b_cells:.1f}→{c_cells:.1f}, "
        f"즉 {_pct(cell_saving)} 줄였지만 위치 포함은 "
        f"{overall['B']['operational_hits']}/{overall['B']['n']}→"
        f"{overall['C']['operational_hits']}/{overall['C']['n']}으로 "
        f"{overall['C']['operational_hits'] - overall['B']['operational_hits']:+d}회 차이였다.",
        f"- **D1 밖:** 각 군의 자체 80% 정책에서 C는 {overall['C']['outside_operational_hits']}/"
        f"{overall['C']['outside_n']}, B는 {overall['B']['outside_operational_hits']}/"
        f"{overall['B']['outside_n']}였다.",
        f"- **B와 같은 시점별 셀 예산:** C는 {matched_c['hits']}/{matched_c['n']}, "
        f"B는 {overall['B']['operational_hits']}/{overall['B']['n']}였다. "
        "따라서 누적 80% 정책의 C 성능 저하는 개인화 확률 자체뿐 아니라 "
        "집중된 분포에서 셀을 너무 일찍 끊는 임계값의 영향도 포함한다.",
        f"- 실제 위치 평균 확률은 C {_pct(overall['C']['mean_probability'])}, "
        f"B {_pct(overall['B']['mean_probability'])}로 C가 "
        f"{overall['C']['mean_probability'] / max(overall['B']['mean_probability'], 1e-12):.2f}배였다.",
        f"- 이 결과는 {persona_count}개 합성 Persona의 기제 검증이다. 실제 치매 실종자 모집단에 대한 "
        "통계적 일반화나 발견시간 단축을 증명하지 않는다.",
    ]

    output = RESULTS / args.output
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"saved={output}")


if __name__ == "__main__":
    main()
