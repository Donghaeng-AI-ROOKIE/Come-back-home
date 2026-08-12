"""Mi:dm 온보딩 Persona를 쓴 EXAONE E2E A/B/C 재생을 시나리오 단위로 집계한다."""

from __future__ import annotations

import argparse
import json
import random
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
STRATA = ("consistent", "neutral", "counter")


def _load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _paired_ci(values: list[float], *, seed: int = 20260812) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    rng = random.Random(seed)
    means = sorted(
        statistics.mean(rng.choice(values) for _ in values)
        for _ in range(10_000)
    )
    return means[250], means[9749]


def _valid(row: dict) -> bool:
    return all(row["arms"].get(arm, {}).get("valid") for arm in "ABC")


def _metric(row: dict, arm: str, key: str):
    return row["arms"][arm]["metrics"][key]


def _primary_rows(rows: list[dict]) -> list[dict]:
    return [row for row in rows if _valid(row)
            and _metric(row, "A", "d2_gtcr_outside_d1") is not None]


def _summary_row(rows: list[dict]) -> tuple[list[str], dict]:
    values = {
        arm: [_metric(row, arm, "d2_gtcr_outside_d1") for row in rows]
        for arm in "ABC"
    }
    cb = [c - b for b, c in zip(values["B"], values["C"], strict=True)]
    ca = [c - a for a, c in zip(values["A"], values["C"], strict=True)]
    cb_lo, cb_hi = _paired_ci(cb)
    ca_lo, ca_hi = _paired_ci(ca)
    means = {arm: _mean(values[arm]) for arm in "ABC"}
    cells = [
        str(len(rows)), _fmt(means["A"]), _fmt(means["B"]), _fmt(means["C"]),
        _fmt(_mean(cb)), f"[{_fmt(cb_lo)}, {_fmt(cb_hi)}]",
        _fmt(_mean(ca)), f"[{_fmt(ca_lo)}, {_fmt(ca_hi)}]",
    ]
    return cells, {"means": means, "cb": cb, "ca": ca}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="persona_abc_live_30_r1.jsonl")
    parser.add_argument("--output", default="persona_abc_live_30_r1.md")
    args = parser.parse_args()
    rows = _load(RESULTS / args.input)

    invalid = [
        (row["scenario_id"], arm, row["arms"][arm].get("fallback_reasons", []))
        for row in rows for arm in "ABC" if not row["arms"].get(arm, {}).get("valid")
    ]
    cleanup_errors = [
        (row["scenario_id"], arm, row["arms"][arm]["cleanup_errors"])
        for row in rows for arm in "ABC" if row["arms"][arm].get("cleanup_errors")
    ]
    budget_errors = [
        (row["scenario_id"], arm)
        for row in rows for arm in "ABC"
        if any(_metric(row, arm, key) != expected for key, expected in (
            ("d1_cells", 19), ("d2_cells", 19), ("unique_alert_cells", 38),
        ))
    ]
    primary = _primary_rows(rows)
    axis_nonempty = sum(bool(row["arms"]["C"].get("axis_scores")) for row in rows)
    c_prior_with_attraction = sum(
        bool(row["arms"]["C"].get("prior_summaries", [{}])[0].get("attraction_weights"))
        for row in rows if row["arms"]["C"].get("valid")
    )

    lines = [
        "# EXAONE E2E 12슬롯 개인화 알림 A/B/C 라이브 재생",
        "",
        f"- 설계: {len(rows)}건 = 10명 × 일관·중립·반대 3층",
        "- 알림 예산: A/B/C 모두 D1 19셀 + D2 19셀 = 38셀",
        "- 정답: Phase 2와 분리된 OSM 최단경로 + 고정 보행속도, 5분 간격 13시점",
        "- 예측: 배포 FastAPI → GPU EXAONE → 도로망 MC, seed 42 1회",
        f"- 유효: {sum(_valid(row) for row in rows)}/{len(rows)}건; 예산 위반 {len(budget_errors)}건; 파기 오류 {len(cleanup_errors)}건",
        f"- C군 EXAONE prior에 등록장소 반영: {c_prior_with_attraction}/{sum(row['arms']['C'].get('valid', False) for row in rows)}건",
        f"- 숫자 축점(axis_scores) 반영: {axis_nonempty}/{len(rows)}건 — 배포 플래그 off; 12슬롯 노트·장소는 EXAONE 프롬프트에 사용",
        "",
        "## 주지표 — D1 밖 정답 시점의 D2 포함률",
        "",
        "| 층 | n | A 거리 | B EXAONE 비개인화 | C EXAONE 개인화 | C−B | 95% CI | C−A | 95% CI |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    summaries = {}
    for stratum in (*STRATA, "all"):
        subset = primary if stratum == "all" else [row for row in primary if row["stratum"] == stratum]
        cells, summary = _summary_row(subset)
        summaries[stratum] = summary
        lines.append(f"| {stratum} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "## 전체 활성구역 GTCR@60 — D1∪D2 보조지표",
        "",
        "| 층 | n | A | B | C | C−B |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    valid_rows = [row for row in rows if _valid(row)]
    for stratum in (*STRATA, "all"):
        subset = valid_rows if stratum == "all" else [row for row in valid_rows if row["stratum"] == stratum]
        means = {arm: _mean([_metric(row, arm, "gtcr60") for row in subset]) for arm in "ABC"}
        lines.append(
            f"| {stratum} | {len(subset)} | {_fmt(means['A'])} | {_fmt(means['B'])} | "
            f"{_fmt(means['C'])} | {_fmt(means['C'] - means['B'])} |"
        )

    lines += [
        "",
        "## 시나리오별 주지표",
        "",
        "| 시나리오 | 층 | D1 밖 시점 | A | B | C | C−B |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        if not _valid(row):
            lines.append(f"| {row['scenario_id']} | {row['stratum']} | — | — | — | 무효 | — |")
            continue
        outside = _metric(row, "A", "outside_d1_truth_steps")
        lines.append(
            f"| {row['scenario_id']} | {row['stratum']} | {outside} | "
            f"{_fmt(_metric(row, 'A', 'd2_gtcr_outside_d1'))} | "
            f"{_fmt(_metric(row, 'B', 'd2_gtcr_outside_d1'))} | "
            f"{_fmt(_metric(row, 'C', 'd2_gtcr_outside_d1'))} | "
            f"{_fmt((_metric(row, 'C', 'd2_gtcr_outside_d1') or 0) - (_metric(row, 'B', 'd2_gtcr_outside_d1') or 0))} |"
        )

    lines += ["", "## 품질 예외", ""]
    if invalid:
        for scenario, arm, reasons in invalid:
            lines.append(f"- `{scenario}` {arm}: 성능 집계 제외 — `{reasons}`")
    else:
        lines.append("- 없음")
    lines += [
        "",
        "## 해석 제한",
        "",
        "- 실제 발견률이 아니라 정답 위치가 알림 셀에 든 **발견 기회의 상한**이다.",
        "- 실제 치매 실종 궤적이 아닌 합성 페르소나·OSM 규칙 궤적의 메커니즘 실험이다.",
        "- 1시드 탐색 결과라 확증 근거가 아니다. CI는 시나리오 표본의 불확실성만 나타낸다.",
        "- 배포의 axis scoring 플래그가 꺼져 있어, 이 결과는 12슬롯 문맥·장소 개인화이지 숫자 6축 가드레일까지 켠 완전판이 아니다.",
    ]

    out = RESULTS / args.output
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"saved={out} valid={len(valid_rows)}/{len(rows)} primary={len(primary)}")


if __name__ == "__main__":
    main()
