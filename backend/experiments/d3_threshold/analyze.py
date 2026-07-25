"""P1-4 — timelines.jsonl → D3 임계값 결정표.

목적함수: 탐지율 ≥ 목표(제약) + 그 안에서 헛알림(negative 오발동) 최소.
total_new_mass 는 시나리오당 스칼라 1개라 임계 스윕은 그리드서치가 아니라
포지티브 분포의 분위수 하나 뽑는 정렬 연산으로 붕괴한다(메모리 설계 문서 참고).

놓침은 "임계 탓"(mass>0인데 문턱 미달)과 "정보부족 탓"(reruns=0 → mass 항상 0,
어떤 임계로도 못 잡음 — layer1_update 는 기존 셀만 갱신, 새 셀은 재실행에서만
생긴다)으로 분리 집계한다.

실행: backend/ 에서
    python experiments/d3_threshold/analyze.py --pilot
    python experiments/d3_threshold/analyze.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔 cp949 가 ∉ 등 특수문자를 못 씀

OUT_DIR = Path(__file__).resolve().parent
TARGET_RATES = [0.99, 0.98, 0.97, 0.96, 0.95]


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in open(path, encoding="utf-8")]


def _quantile(sorted_vals: list[float], q: float) -> float:
    """q=0이면 최솟값. sorted_vals 는 이미 오름차순."""
    if not sorted_vals:
        return 0.0
    idx = max(0, min(len(sorted_vals) - 1, round(q * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


def decision_table(rows: list[dict]) -> list[dict]:
    """목표 탐지율별 mass_thr·js_thr·헛알림수·놓침 분해."""
    pos = [r for r in rows if r["positive"]]
    neg = [r for r in rows if not r["positive"]]
    pos_mass_sorted = sorted(r["total_new_mass"] for r in pos)
    n_pos = len(pos)

    # 도달 최대 — 정보부족(reruns=0, mass 항상 0)인 positive 는 어떤 임계로도 못 잡으므로
    # 그 비율만큼이 이론적 탐지율 상한이다.
    info_scarce_pos = sum(1 for r in pos if r["reruns"] == 0)
    ceiling_rate = (n_pos - info_scarce_pos) / n_pos if n_pos else 0.0

    out = []
    targets = [round(ceiling_rate, 4)] + [t for t in TARGET_RATES if t <= ceiling_rate + 1e-9]
    # 도달 불가능한 목표(천장 초과)도 참고용으로 한 줄 남긴다(달성 불가 표시)
    infeasible = [t for t in TARGET_RATES if t > ceiling_rate + 1e-9]

    seen = set()
    for target in targets:
        if target in seen:
            continue
        seen.add(target)
        miss_quantile = max(0.0, 1.0 - target)
        mass_thr = _quantile(pos_mass_sorted, miss_quantile)
        detected_pos = [r for r in pos if r["total_new_mass"] >= mass_thr]
        missed_pos = [r for r in pos if r["total_new_mass"] < mass_thr]
        miss_info_scarce = sum(1 for r in missed_pos if r["reruns"] == 0)
        miss_threshold = len(missed_pos) - miss_info_scarce
        false_alarms = [r for r in neg if r["total_new_mass"] >= mass_thr]

        # js_thr — mass 로 발동 판정된(=detected_pos) 케이스를 하나도 안 거르는 최댓값
        js_thr = min((r["js"] for r in detected_pos), default=0.0)

        out.append({
            "목표탐지율": f"{target:.1%}" + (" (도달최대)" if target == round(ceiling_rate, 4) else ""),
            "mass_thr": round(mass_thr, 4),
            "js_thr": round(js_thr, 4),
            "실제탐지율": round(len(detected_pos) / n_pos, 4) if n_pos else 0.0,
            "헛알림수": len(false_alarms),
            "헛알림율": round(len(false_alarms) / len(neg), 4) if neg else 0.0,
            "놓침_임계탓": miss_threshold,
            "놓침_정보부족": miss_info_scarce,
        })
    return out, infeasible, ceiling_rate


def robustness_by_mix(all_rows: list[dict]) -> dict:
    """mix_name(허위비율 스트레스·저품질변형)별 결정표 — 강건성 확인용."""
    mixes = sorted({r["mix_name"] for r in all_rows})
    return {mix: decision_table([r for r in all_rows if r["mix_name"] == mix])
            for mix in mixes}


def render_markdown(pilot: bool, all_rows: list[dict]) -> str:
    lines = [f"# D3 임계값 결정표 ({'파일럿' if pilot else '본 실험'})", ""]
    lines.append(f"타임라인 {len(all_rows)}개 "
                f"(positive={sum(r['positive'] for r in all_rows)}, "
                f"negative={sum(not r['positive'] for r in all_rows)})")
    lines.append("")
    lines.append("**시뮬레이션 기반 자체 평가.** 정답은 사람 라벨이 아니라 "
                "'진짜 위치 셀 ∉ last_alert footprint'(집합 차, POA와 독립)로 기계적으로 산출.")
    lines.append("")

    for mix, (table, infeasible, ceiling) in robustness_by_mix(all_rows).items():
        lines.append(f"## {mix} (도달 가능 탐지율 천장: {ceiling:.1%})")
        lines.append("")
        if not table:
            lines.append("(데이터 없음)")
            lines.append("")
            continue
        headers = list(table[0].keys())
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|" + "---|" * len(headers))
        for row in table:
            lines.append("| " + " | ".join(str(row[h]) for h in headers) + " |")
        if infeasible:
            lines.append("")
            lines.append(f"도달 불가능한 목표(천장 초과): {', '.join(f'{t:.0%}' for t in infeasible)} "
                        f"— 정보부족(제보가 POA를 못 움직임) 비중이 그만큼 있다는 뜻.")
        lines.append("")
    return "\n".join(lines)


def main(pilot: bool) -> None:
    path = OUT_DIR / ("timelines_pilot.jsonl" if pilot else "timelines.jsonl")
    rows = load(path)
    md = render_markdown(pilot, rows)
    out_path = OUT_DIR / "results" / ("d3_threshold_pilot.md" if pilot else "d3_threshold.md")
    out_path.write_text(md, encoding="utf-8")
    print(md)
    print(f"\n저장: {out_path}")


if __name__ == "__main__":
    main(pilot="--pilot" in sys.argv)
