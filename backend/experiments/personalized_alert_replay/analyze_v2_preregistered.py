"""v2 사전등록 분석 — PREREGISTRATION_V2.md 의 지표만 계산한다.

주 지표
  1. 집중도: 각 시점 POA 상위 3셀 누적 확률질량 (C > B, 부호검정)
  2. 동일예산 적중률: 상위 N셀 선택 시 정답 포함 (N=5,10,15,20,25,30, McNemar)

평가 구간은 전체 시점이다. D1 안팎으로 나누지 않는다.
다중비교: 주 지표 2개에 Bonferroni 보정 α=0.025.

    python -m experiments.personalized_alert_replay.analyze_v2_preregistered \
        --input persona_abc_v2_r1.jsonl --output V2_RESULTS.md
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from math import comb
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"

TOP_K = 3                      # 집중도 주 판정 k (사전등록)
TOP_K_REPORT = (1, 3, 5, 10)   # 함께 보고할 k
BUDGETS = (5, 10, 15, 20, 25, 30)
ALPHA = 0.025                  # Bonferroni 보정 (주 지표 2개)
NONINFERIORITY_MARGIN = 0.05   # H2: C >= B - 5%p


def binom_two_sided(k: int, n: int) -> float:
    """이항 정확검정 양측 p값 (p=0.5)."""
    if n == 0:
        return 1.0
    probs = [comb(n, i) * 0.5**n for i in range(n + 1)]
    return min(1.0, sum(p for p in probs if p <= probs[k] * (1 + 1e-9)))


def top_mass(cells: dict[str, float], k: int) -> float:
    return sum(sorted(cells.values(), reverse=True)[:k])


def top_cells(cells: dict[str, float], n: int) -> set[str]:
    return {c for c, _ in sorted(cells.items(), key=lambda kv: kv[1], reverse=True)[:n]}


def load(path: Path) -> list[dict]:
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [r for r in rows if all(r["arms"].get(a, {}).get("valid") for a in "BC")]


def paired_snapshots(rows: list[dict]) -> list[dict]:
    """같은 시나리오·같은 시점의 A/B/C 를 한 레코드로 묶는다."""
    out = []
    for row in rows:
        counts = {a: len(row["arms"][a]["temporal"]["snapshots"]) for a in "ABC"
                  if row["arms"].get(a, {}).get("temporal")}
        n = min(counts.values())
        for i in range(n):
            rec = {
                "scenario_id": row["scenario_id"],
                "stratum": row["stratum"],
                "behavior": row["truth_behavior"],
            }
            for a in "ABC":
                arm = row["arms"].get(a) or {}
                if not arm.get("temporal"):
                    continue
                s = arm["temporal"]["snapshots"][i]
                rec[a] = {"cells": s["surface_cells"], "truth": s["truth_cell"]}
            rec["minute"] = row["arms"]["B"]["temporal"]["snapshots"][i]["minute_after_report"]
            out.append(rec)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    rows = load(RESULTS / args.input)
    snaps = paired_snapshots(rows)
    lines: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        lines.append(s)

    emit("# v2 사전등록 분석 결과")
    emit()
    emit(f"입력: `{args.input}` — 유효 시나리오 {len(rows)}개, 대응 시점 {len(snaps)}개")
    emit()
    emit("사전등록: `PREREGISTRATION_V2.md`. 평가 구간은 전체 시점이며 D1 안팎으로 "
         "나누지 않는다. 주 지표 2개에 Bonferroni 보정(α=0.025)을 적용한다.")
    emit()

    # ── 주 지표 1: 집중도 ────────────────────────────────────────────
    emit("## 주 지표 1 — 확률 집중도 (H1)")
    emit()
    emit("각 시점 POA에서 상위 k셀이 차지하는 확률질량. 적중 여부와 무관한 예측 특성이다.")
    emit()
    emit("| k | B 평균 | C 평균 | C 승 | B 승 | p (부호검정) | 판정 |")
    emit("|---:|---:|---:|---:|---:|---:|---|")
    h1_pass = False
    for k in TOP_K_REPORT:
        b = [top_mass(s["B"]["cells"], k) for s in snaps]
        c = [top_mass(s["C"]["cells"], k) for s in snaps]
        win = sum(1 for x, y in zip(c, b) if x > y)
        lose = sum(1 for x, y in zip(c, b) if x < y)
        p = binom_two_sided(win, win + lose)
        primary = " **(주판정)**" if k == TOP_K else ""
        verdict = ("C 우위" if p < ALPHA and win > lose else "유의하지 않음")
        if k == TOP_K:
            h1_pass = p < ALPHA and win > lose
        emit(f"| {k}{primary} | {statistics.mean(b):.4f} | {statistics.mean(c):.4f} | "
             f"{win} | {lose} | {p:.3g} | {verdict} |")
    emit()

    # 층·행동별 일관성 (보고용, 판정에는 미사용)
    emit("### 층·행동유형별 집중도 (k=3, 기술 통계 — 주 판정에는 쓰지 않음)")
    emit()
    for key in ("stratum", "behavior"):
        emit(f"| {key} | B | C | C 우위 |")
        emit("|---|---:|---:|---|")
        g: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for s in snaps:
            g[s[key]].append((top_mass(s["B"]["cells"], TOP_K),
                              top_mass(s["C"]["cells"], TOP_K)))
        for name, v in sorted(g.items()):
            mb = statistics.mean(x[0] for x in v)
            mc = statistics.mean(x[1] for x in v)
            emit(f"| {name} | {mb:.4f} | {mc:.4f} | {'예' if mc > mb else '아니오'} |")
        emit()

    # ── 주 지표 2: 동일예산 적중률 ──────────────────────────────────
    emit("## 주 지표 2 — 동일 셀 예산에서의 적중률 (H2 비열등)")
    emit()
    emit(f"상위 N셀을 알림 구역으로 선택했을 때 정답 셀이 포함된 비율. "
         f"비열등 기준은 C ≥ B − {NONINFERIORITY_MARGIN*100:.0f}%p.")
    emit()
    emit("| N | A 참조 | B | C | C−B | C만맞힘 | B만맞힘 | p (McNemar) | 비열등 |")
    emit("|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    h2_pass = True
    for n in BUDGETS:
        rates, hits = {}, {}
        for a in "ABC":
            hs = [s[a]["truth"] in top_cells(s[a]["cells"], n) for s in snaps if a in s]
            hits[a] = hs
            rates[a] = sum(hs) / len(hs) if hs else 0.0
        only_c = sum(1 for x, y in zip(hits["C"], hits["B"]) if x and not y)
        only_b = sum(1 for x, y in zip(hits["C"], hits["B"]) if y and not x)
        p = binom_two_sided(only_c, only_c + only_b)
        diff = rates["C"] - rates["B"]
        ok = diff >= -NONINFERIORITY_MARGIN
        h2_pass = h2_pass and ok
        emit(f"| {n} | {rates['A']*100:.1f}% | {rates['B']*100:.1f}% | {rates['C']*100:.1f}% | "
             f"{diff*100:+.1f}%p | {only_c} | {only_b} | {p:.3g} | {'충족' if ok else '**위반**'} |")
    emit()

    # ── 부 지표 ────────────────────────────────────────────────────
    emit("## 부 지표")
    emit()
    emit("| 항목 | A | B | C |")
    emit("|---|---:|---:|---:|")
    for label, fn in (
        ("예측면 지지 셀 수 (평균)", lambda s, a: len(s[a]["cells"])),
        ("정답 셀 확률 (평균)", lambda s, a: s[a]["cells"].get(s[a]["truth"], 0.0)),
    ):
        vals = {a: statistics.mean(fn(s, a) for s in snaps if a in s) for a in "ABC"}
        emit(f"| {label} | {vals['A']:.4f} | {vals['B']:.4f} | {vals['C']:.4f} |")
    emit()

    # ── 판정 ───────────────────────────────────────────────────────
    emit("## 사전등록 판정")
    emit()
    emit(f"- H1 (집중도 C>B, k={TOP_K}, α={ALPHA}): **{'성립' if h1_pass else '기각'}**")
    emit(f"- H2 (전 예산 구간 비열등): **{'충족' if h2_pass else '위반'}**")
    emit()
    if h1_pass and h2_pass:
        emit("→ **성공.** 개인화는 정확도 손실 없이 확률질량을 좁은 영역에 집중시킨다.")
    elif h1_pass:
        emit("→ **부분 성공.** 예측을 좁히지만 정확도 비열등은 미확인. "
             "성능 주장에는 쓰지 않는다.")
    else:
        emit("→ **실패.** 제안서에서 개인화 성능 주장을 빼고 구현 사실로만 기술한다.")
    emit()
    emit("측정하지 않은 것: 실제 푸시 전달, 알림 열람, 시민 제보 전환, 실제 실종자 "
         "궤적, 발견 성공.")

    if args.output:
        out = RESULTS / args.output
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n저장됨: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
