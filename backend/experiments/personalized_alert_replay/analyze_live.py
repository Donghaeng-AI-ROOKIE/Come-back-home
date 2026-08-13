"""공식 배포 경로의 EXAONE B/C 파일럿을 정직하게 집계한다."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def _load(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _fmt(value: float) -> str:
    return f"{value * 100:.1f}%"


def _tv(a: dict[str, float], b: dict[str, float]) -> float:
    return 0.5 * sum(abs(a.get(cell, 0.0) - b.get(cell, 0.0)) for cell in set(a) | set(b))


def main() -> None:
    rows = _load(RESULTS / "remote_live_pilot.jsonl")

    # 첫 파일럿에서 fallback이 1회 난 counter-00은 동일 설정 재실행본으로
    # 시나리오 전체(B/C)를 교체한다. arm 하나만 골라 바꾸면 결과 선택 편향이다.
    replacement = RESULTS / "remote_live_counter-00.jsonl"
    if replacement.exists():
        replacement_row = _load(replacement)[0]
        if all(replacement_row["arms"][arm]["valid"] for arm in "BC"):
            rows = [
                replacement_row if row["scenario_id"] == "counter-00" else row
                for row in rows
            ]

    prior_calls = sum(len(row["arms"][arm]["prior_sources"]) for row in rows for arm in "BC")
    exaone_calls = sum(
        source == "exaone"
        for row in rows for arm in "BC" for source in row["arms"][arm]["prior_sources"]
    )
    roadnet_runs = sum(
        bool(flag)
        for row in rows for arm in "BC" for flag in row["arms"][arm]["roadnet_used"]
    )
    attraction_runs = sum(
        bool(prior.get("attraction_weights"))
        for row in rows for prior in row["arms"]["C"]["priors"]
    )
    c_prior_runs = sum(len(row["arms"]["C"]["priors"]) for row in rows)

    trace_rows = _load(RESULTS / "remote_trace_neutral-00.jsonl")
    trace = trace_rows[0]["arms"]["C"]["trace_summaries"][0]

    lines = [
        "# 공식 배포 EXAONE 개인화 알림 라이브 파일럿",
        "",
        "- 경로: `:8443 FastAPI → tailnet GPU gateway` (클라이언트 인증 없음)",
        f"- 유효 prior: EXAONE {exaone_calls}/{prior_calls}회, 도로망 {roadnet_runs}/{prior_calls}회",
        f"- C 끌림점 반영: {attraction_runs}/{c_prior_runs}회",
        f"- trace 1회: mind 이벤트 {trace['mind_events']}건 = EXAONE 실호출 "
        f"{trace['mind_source_counts'].get('exaone', 0)}건 + 풀 재표집 "
        f"{trace['mind_source_counts'].get('pool', 0)}건; `exaone_stub={str(trace['exaone_stub']).lower()}`",
        "- 정답: Phase 2와 분리된 NetworkX 최단경로 + 고정속도, 6건(층당 2건)",
        "",
        "## 사례별 결과",
        "",
        "| 사례 | 층 | 경과 | D2 GTCR B | D2 GTCR C | C−B | 무관 D2 B | 무관 D2 C | POA TV |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        b, c = row["arms"]["B"], row["arms"]["C"]
        bm, cm = b["metrics"], c["metrics"]
        lines.append(
            f"| {row['scenario_id']} | {row['stratum']} | {b['server_elapsed_hours'] * 60:.0f}분 | "
            f"{_fmt(bm['d2_gtcr60'])} | {_fmt(cm['d2_gtcr60'])} | "
            f"{_fmt(cm['d2_gtcr60'] - bm['d2_gtcr60'])} | "
            f"{_fmt(bm['irrelevant_d2_rate'])} | {_fmt(cm['irrelevant_d2_rate'])} | "
            f"{_tv(b['poa_mean'], c['poa_mean']):.3f} |"
        )

    lines += [
        "",
        "## 층별 탐색 평균",
        "",
        "| 층 | n | D2 GTCR B | D2 GTCR C | C−B | 무관 D2 B | 무관 D2 C |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for stratum in ("consistent", "neutral", "counter", "all"):
        subset = rows if stratum == "all" else [r for r in rows if r["stratum"] == stratum]

        def mean(arm: str, key: str) -> float:
            return statistics.mean(r["arms"][arm]["metrics"][key] for r in subset)

        b_gtcr, c_gtcr = mean("B", "d2_gtcr60"), mean("C", "d2_gtcr60")
        lines.append(
            f"| {stratum} | {len(subset)} | {_fmt(b_gtcr)} | {_fmt(c_gtcr)} | "
            f"{_fmt(c_gtcr - b_gtcr)} | {_fmt(mean('B', 'irrelevant_d2_rate'))} | "
            f"{_fmt(mean('C', 'irrelevant_d2_rate'))} |"
        )

    lines += [
        "",
        "## 판정",
        "",
        "- 라이브 파일럿은 **GPU·EXAONE·페르소나·도로망 경로가 실제 작동함**을 입증한다.",
        "- n=2/층에서는 개인화 성능 우위를 입증하지 못했다. 일치 층도 두 사례 중 하나만 포함됐고 B/C 포함률은 같았다.",
        "- 반대 층의 한 사례에서는 B 100%, C 0%였다. 생활사가 현재 이동과 어긋나면 개인화가 오히려 잘못된 지역에 알림을 집중할 수 있다.",
        "- 따라서 제안서에는 고정-prior 30건의 메커니즘 결과와 이 라이브 작동성 결과를 분리하고, 라이브 결과를 발견률 향상 근거로 쓰지 않는다.",
        "- 최초 라이브 파일은 KST naive 시각을 UTC 컨테이너에 보내 경과 3분으로 클램프된 하네스 오류가 있어 `remote_live_pilot_invalid_time.jsonl`로 격리했다.",
    ]

    out = RESULTS / "remote_live_pilot.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"saved={out}")


if __name__ == "__main__":
    main()
