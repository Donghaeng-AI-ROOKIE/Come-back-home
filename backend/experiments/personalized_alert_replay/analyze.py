"""개인화 알림 독립 궤적 replay 결과를 짝지어 집계한다."""

from __future__ import annotations

import argparse
import json
import random
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _ci(values: list[float], seed: int = 20260810) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    rng = random.Random(seed)
    means = []
    for _ in range(5000):
        sample = [rng.choice(values) for _ in values]
        means.append(statistics.mean(sample))
    means.sort()
    return means[int(0.025 * len(means))], means[int(0.975 * len(means))]


def _fmt(v: float) -> str:
    return f"{v * 100:.1f}%"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    inp = HERE / "results" / ("pilot.jsonl" if args.pilot else "replay.jsonl")
    rows = [json.loads(line) for line in inp.read_text(encoding="utf-8").splitlines() if line]

    lines = [
        "# 독립 OSM 궤적 개인화 알림 replay",
        "",
        f"- 시나리오: {len(rows)}건 (일치·중립·불일치 균등)",
        "- 알림 예산: D1 19셀 공통 + D2 19셀 고정",
        "- 예측: 도로망 MC 500워커 × 시드 12개 평균",
        "- 정답: Phase 2를 쓰지 않는 NetworkX 최단경로 + 고정속도",
        "",
        "## 주지표 — D2 GTCR@60 (개인화 알림 19셀의 위치 포함비율)",
        "",
        "| 층 | n | B 비개인화 | C 개인화 | C−B | 95% bootstrap CI |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for stratum in ("consistent", "neutral", "counter", "all"):
        subset = rows if stratum == "all" else [r for r in rows if r["stratum"] == stratum]
        b = [r["arms"]["B"]["d2_gtcr60"] for r in subset]
        c = [r["arms"]["C"]["d2_gtcr60"] for r in subset]
        diffs = [cv - bv for bv, cv in zip(b, c)]
        lo, hi = _ci(diffs)
        lines.append(
            f"| {stratum} | {len(subset)} | {_fmt(statistics.mean(b))} | "
            f"{_fmt(statistics.mean(c))} | {_fmt(statistics.mean(diffs))} | "
            f"[{_fmt(lo)}, {_fmt(hi)}] |"
        )

    lines += [
        "",
        "## 전체 활성 구역 GTCR@60 (D1∪D2, 보조)",
        "",
        "| 층 | B 비개인화 | C 개인화 | C−B |",
        "|---|---:|---:|---:|",
    ]
    for stratum in ("consistent", "neutral", "counter", "all"):
        subset = rows if stratum == "all" else [r for r in rows if r["stratum"] == stratum]
        b = statistics.mean(r["arms"]["B"]["gtcr60"] for r in subset)
        c = statistics.mean(r["arms"]["C"]["gtcr60"] for r in subset)
        lines.append(f"| {stratum} | {_fmt(b)} | {_fmt(c)} | {_fmt(c - b)} |")

    lines += [
        "",
        "## 보조지표",
        "",
        "| 층 | Any coverage B | Any coverage C | Endpoint B | Endpoint C | 무관 D2 B | 무관 D2 C |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for stratum in ("consistent", "neutral", "counter", "all"):
        subset = rows if stratum == "all" else [r for r in rows if r["stratum"] == stratum]

        def mean(arm: str, key: str) -> float:
            return statistics.mean(float(r["arms"][arm][key]) for r in subset)

        lines.append(
            f"| {stratum} | {_fmt(mean('B', 'any_coverage60'))} | "
            f"{_fmt(mean('C', 'any_coverage60'))} | {_fmt(mean('B', 'endpoint_hit'))} | "
            f"{_fmt(mean('C', 'endpoint_hit'))} | {_fmt(mean('B', 'irrelevant_d2_rate'))} | "
            f"{_fmt(mean('C', 'irrelevant_d2_rate'))} |"
        )

    all_diffs = [r["arms"]["C"]["d2_gtcr60"] - r["arms"]["B"]["d2_gtcr60"] for r in rows]
    lines += [
        "",
        "## 해석 제한",
        "",
        "- 이 결과는 실제 발견률이 아니라 **위치가 알림 구역에 포함된 기회**다.",
        "- 정답은 실제 치매 실종 궤적이 아니라 예측기와 분리된 지도 규칙 궤적이다.",
        "- C는 사전등록 장소 하나만 켠 장소 개인화 ablation이며, 전체 페르소나 성능을 대표하지 않는다.",
        "- 일치/중립/불일치를 균등 합산한 all 수치는 실제 발생 비율을 모르므로 주장 근거로 쓰지 않는다.",
        f"- 균등 혼합에서의 탐색적 평균 차이는 {_fmt(statistics.mean(all_diffs))}다.",
        "",
        "## 재현",
        "",
        "```bash",
        ".venv/bin/python -m experiments.personalized_alert_replay.run_replay --pilot",
        ".venv/bin/python -m experiments.personalized_alert_replay.analyze --pilot",
        "```",
    ]
    out = HERE / "results" / ("pilot.md" if args.pilot else "replay.md")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"saved={out}")


if __name__ == "__main__":
    main()
