"""발견율 곡선 집계 — curve.jsonl → 마크다운 표.

곡선의 축:
  x = 알림 셀 수 평균(발송 비용 대리값), y = hit율(발견율 상한)

같은 x 에서 y 를 비교하는 것이 이 실험의 목적이다. 전략마다 x 가 자유롭게
움직이므로 "커버리지 0.8 끼리" 비교하면 비용이 다른 것을 비교하게 된다.
그래서 비용 정합 비교(`_cost_matched`)를 따로 낸다 — `ours` 의 각 커버리지가
쓴 셀 수와 **같은 비용**을 `blanket`·`stat_only` 에 줬을 때의 hit율을 견준다.

실행: backend/ 에서
    python experiments/discovery_curve/analyze.py            # curve.jsonl
    python experiments/discovery_curve/analyze.py --pilot    # curve_pilot.jsonl
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent


def _load(pilot: bool, roadnet: bool = False) -> list[dict]:
    suffix = "_roadnet" if roadnet else ""
    path = OUT_DIR / (f"curve_pilot{suffix}.jsonl" if pilot else f"curve{suffix}.jsonl")
    if not path.exists():
        raise SystemExit(f"없음: {path} — run_curve.py 를 먼저 실행하십시오.")
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _agg(rows: list[dict]) -> dict[tuple, dict]:
    """(strategy, coverage, cap) → {hit율, 셀수 평균/중앙, n}."""
    buckets: dict[tuple, list[dict]] = {}
    for row in rows:
        for r in row["results"]:
            buckets.setdefault((r["strategy"], r["coverage"], r["cap"]), []).append(r)
    out: dict[tuple, dict] = {}
    for key, rs in buckets.items():
        cells = [r["cells"] for r in rs]
        out[key] = {
            "hit_rate": sum(r["hit"] for r in rs) / len(rs),
            "cells_mean": statistics.mean(cells),
            "cells_median": statistics.median(cells),
            "n": len(rs),
        }
    return out


def _cost_matched(rows: list[dict], cap: int | None) -> list[dict]:
    """비용 정합 비교 — `ours` 가 커버리지 c 에서 쓴 셀 수 k 를 그대로 다른
    전략에 준다. 즉 "같은 k 셀을 보낼 때 누가 더 맞히는가".

    타임라인마다 k 가 다르므로 타임라인 단위로 맞춘 뒤 평균한다. `blanket` 은
    확률 순위가 없어 상위 k 를 못 고르므로, 도달 반경 안에서 무작위로 k 셀을
    고른 것과 같다고 보고 **기하적 기대값**(k / 반경 내 전체 셀)으로 계산한다.
    """
    per_cov: dict[float, list[tuple[bool, float, float]]] = {}
    for row in rows:
        res = row["results"]
        blanket = next(r for r in res if r["strategy"] == "blanket")
        ours = {r["coverage"]: r for r in res if r["strategy"] == "ours" and r["cap"] == cap}
        stat_k = {r["coverage"]: r for r in res
                  if r["strategy"] == "stat_only_at_k" and r["cap"] == cap}
        for cov, our in ours.items():
            k = our["cells"]
            sk = stat_k.get(cov)
            stat_hit = float(sk["hit"]) if sk else 0.0
            blanket_exp = (k / blanket["cells"]) * blanket["hit"] if blanket["cells"] else 0.0
            per_cov.setdefault(cov, []).append((our["hit"], stat_hit, blanket_exp))
    out = []
    for cov in sorted(per_cov):
        vals = per_cov[cov]
        out.append({
            "coverage": cov,
            "ours_hit": sum(v[0] for v in vals) / len(vals),
            "stat_hit": sum(v[1] for v in vals) / len(vals),
            "blanket_hit": sum(v[2] for v in vals) / len(vals),
            "n": len(vals),
        })
    return out


def main(pilot: bool, roadnet: bool = False) -> None:
    rows = _load(pilot, roadnet)
    agg = _agg(rows)
    n_tl = len(rows)

    dists = [r["true_dist_km"] for r in rows]
    poa_cells = [r["poa_cells"] for r in rows]
    elapsed = [r["elapsed_hours"] for r in rows]
    used = [r["n_used_tips"] for r in rows]

    mode = "도로망 켬" if roadnet else "도로망 끔"
    print(f"# 발견율 곡선 — {'파일럿' if pilot else '본 실험'} 결과 ({mode})\n")
    print(f"타임라인 {n_tl}개. LLM 호출 0회.\n")
    print("## 생성된 타임라인의 성질\n")
    print("| 항목 | 중앙값 | 최소 | 최대 |")
    print("|---|---|---|---|")
    print(f"| 경과시간(h) | {statistics.median(elapsed):.2f} | {min(elapsed):.2f} | {max(elapsed):.2f} |")
    print(f"| 진짜 이탈거리(km) | {statistics.median(dists):.2f} | {min(dists):.2f} | {max(dists):.2f} |")
    print(f"| 우리 POA 셀수 | {statistics.median(poa_cells):.0f} | {min(poa_cells)} | {max(poa_cells)} |")
    print(f"| 채택된 제보 수 | {statistics.median(used):.0f} | {min(used)} | {max(used)} |")

    print("\n## 전략별 곡선 (커버리지 스윕)\n")
    for cap in (None, 500):
        cap_label = "셀 상한 없음" if cap is None else f"셀 상한 {cap}(운영 기본)"
        print(f"\n### {cap_label}\n")
        print("| 커버리지 | ours 셀수 | ours hit | stat_only 셀수 | stat_only hit |")
        print("|---|---|---|---|---|")
        covs = sorted({k[1] for k in agg if k[0] == "ours" and k[2] == cap and k[1] is not None})
        for cov in covs:
            o = agg[("ours", cov, cap)]
            s = agg[("stat_only", cov, cap)]
            print(f"| {cov:.2f} | {o['cells_mean']:.1f} | {o['hit_rate']:.1%} "
                  f"| {s['cells_mean']:.1f} | {s['hit_rate']:.1%} |")

    none = agg[("none", None, None)]
    blanket = agg[("blanket", None, None)]
    print("\n### 노브 없는 두 전략\n")
    print("| 전략 | 셀수 평균 | hit율 |")
    print("|---|---|---|")
    print(f"| 알림 없음 | {none['cells_mean']:.0f} | {none['hit_rate']:.1%} |")
    print(f"| 무차별(도달반경 전체) | {blanket['cells_mean']:.0f} | {blanket['hit_rate']:.1%} |")

    print("\n## 비용 정합 비교 (같은 셀 수를 썼다면)\n")
    print("`ours` 가 각 커버리지에서 쓴 셀 수를 다른 전략에 그대로 준 경우의 hit율.\n")
    for cap in (None, 500):
        cap_label = "셀 상한 없음" if cap is None else f"셀 상한 {cap}"
        print(f"\n### {cap_label}\n")
        print("| 커버리지 | ours 셀수 | ours hit | stat_only(동일비용) | 무차별(동일비용, 기대값) |")
        print("|---|---|---|---|---|")
        for m in _cost_matched(rows, cap):
            o = agg[("ours", m["coverage"], cap)]
            print(f"| {m['coverage']:.2f} | {o['cells_mean']:.1f} | {m['ours_hit']:.1%} "
                  f"| {m['stat_hit']:.1%} | {m['blanket_hit']:.1%} |")

    print("\n## 읽는 법\n")
    print("- hit = 종료 시점 진짜 위치 셀이 알림 셀 집합에 포함됨. **POD=1 가정이라 발견율의 상한.**")
    print("- 셀수 = 발송 비용의 대리값. h3 res 9 한 셀은 약 0.105km².")
    print("- 정답 궤적을 우리 시뮬레이터가 만들었으므로 `stat_only` 대비 `ours` 우위는")
    print("  구조적으로 과대평가된다. 곡선은 성능이 아니라 **알림 전략 효율 비교**로 인용할 것.")


if __name__ == "__main__":
    main(pilot="--pilot" in sys.argv, roadnet="--roadnet" in sys.argv)
