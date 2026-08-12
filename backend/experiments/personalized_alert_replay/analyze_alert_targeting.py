"""Phase 3 실제 발송 판정과 같은 res7·참여도 문턱으로 A/B/C를 재평가한다.

실제 Expo 전송·시민 제보를 실행한 실험이 아니다. 각 정답 위치에 해당하는
res7 셀에 등록 시민 기기 하나가 있다고 가정했을 때, 그 기기가 서버의
발송 대상 목록에 들어오는지를 측정한다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from collections import defaultdict

from app.geo import h3grid
from experiments.personalized_alert_replay.analyze_temporal import _coverage_cells

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
THRESHOLDS = {"high": 0.30, "normal": 0.45, "low": 0.60}
TARGET_RES = 7


def _load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _relative_probability_by_parent(poa: dict[str, float]) -> dict[str, float]:
    """app.phase3.alerts.relative_prob_by_parent와 같은 계산."""
    peak = max(poa.values())
    out: dict[str, float] = {}
    for cell, probability in poa.items():
        relative = min(0.95, probability / peak * 0.9)
        parent = h3grid.parent_cells([cell], TARGET_RES).pop()
        out[parent] = max(out.get(parent, 0.0), relative)
    return out


def evaluate(rows: list[dict], arm: str, level: str = "normal") -> dict:
    threshold = THRESHOLDS[level]
    eligible_truth = eligible_truth_outside = outside_n = target_regions = n = 0
    for row in rows:
        for snapshot in row["arms"][arm]["temporal"]["snapshots"]:
            poa = snapshot["surface_cells"]
            source_cells = _coverage_cells(poa)
            target_parents = h3grid.parent_cells(source_cells, TARGET_RES)
            relative = _relative_probability_by_parent(poa)
            eligible_parents = {
                parent for parent in target_parents if relative.get(parent, 0.0) >= threshold
            }
            truth_parent = h3grid.parent_cells([snapshot["truth_cell"]], TARGET_RES).pop()
            hit = truth_parent in eligible_parents
            eligible_truth += hit
            target_regions += len(eligible_parents)
            n += 1
            if snapshot["truth_outside_d1"]:
                eligible_truth_outside += hit
                outside_n += 1
    return {
        "arm": arm,
        "engagement": level,
        "truth_device_targeted": eligible_truth,
        "n": n,
        "truth_device_target_rate": eligible_truth / n,
        "outside_truth_device_targeted": eligible_truth_outside,
        "outside_n": outside_n,
        "outside_truth_device_target_rate": eligible_truth_outside / outside_n,
        "mean_target_res7_regions": target_regions / n,
        # 모든 res7 구역의 시민 수가 같다는 강한 가정 아래에서만 정밀도 대리지표.
        "equal_population_region_precision_proxy": eligible_truth / target_regions,
    }


def evaluate_equal_region_budget(
    rows: list[dict], arm: str, budget: int, target_res: int
) -> dict:
    """세 군에 동일한 수·해상도의 알림구역을 주어 위치 포함률을 비교한다.

    하나의 타깃 구역에 속한 res9 셀들의 확률질량을 합산한 뒤 상위
    ``budget``개 구역을 선택한다. 이는 특정 군의 수치를 낮추기 위한
    조정이 아니라 실제 알림구역 수를 통제하는 공정 비교다.
    """
    hits = outside_hits = outside_n = n = 0
    by_behavior: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_stratum: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in rows:
        behavior = row["truth_behavior"]
        stratum = row["stratum"]
        for snapshot in row["arms"][arm]["temporal"]["snapshots"]:
            parent_mass: dict[str, float] = defaultdict(float)
            for cell, probability in snapshot["surface_cells"].items():
                parent = h3grid.parent_cells([cell], target_res).pop()
                parent_mass[parent] += probability
            selected = {
                parent
                for parent, _ in sorted(
                    parent_mass.items(), key=lambda item: item[1], reverse=True
                )[:budget]
            }
            truth_parent = h3grid.parent_cells([snapshot["truth_cell"]], target_res).pop()
            hit = truth_parent in selected
            hits += hit
            n += 1
            by_behavior[behavior][0] += hit
            by_behavior[behavior][1] += 1
            by_stratum[stratum][0] += hit
            by_stratum[stratum][1] += 1
            if snapshot["truth_outside_d1"]:
                outside_hits += hit
                outside_n += 1
    return {
        "arm": arm,
        "target_resolution": target_res,
        "region_budget": budget,
        "truth_location_covered": hits,
        "n": n,
        "truth_location_coverage_rate": hits / n,
        "outside_truth_location_covered": outside_hits,
        "outside_n": outside_n,
        "outside_truth_location_coverage_rate": outside_hits / outside_n,
        "by_behavior": {
            key: {"hits": value[0], "n": value[1], "rate": value[0] / value[1]}
            for key, value in sorted(by_behavior.items())
        },
        "by_stratum": {
            key: {"hits": value[0], "n": value[1], "rate": value[0] / value[1]}
            for key, value in sorted(by_stratum.items())
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows = _load(RESULTS / args.input)
    result = {
        "definition": (
            "If one registered device existed in the truth res7 cell, would it pass "
            "the production geofence and engagement probability threshold?"
        ),
        "not_measured": [
            "Expo transport delivery", "real device population", "notification open",
            "citizen report", "missing-person discovery",
        ],
        "target_resolution": TARGET_RES,
        "thresholds": THRESHOLDS,
        "results": {
            level: {arm: evaluate(rows, arm, level) for arm in "ABC"}
            for level in THRESHOLDS
        },
        "equal_res7_region_budget": {
            str(budget): {
                arm: evaluate_equal_region_budget(rows, arm, budget, 7) for arm in "ABC"
            }
            for budget in (1, 2, 3)
        },
        "equal_res8_region_budget": {
            str(budget): {
                arm: evaluate_equal_region_budget(rows, arm, budget, 8) for arm in "ABC"
            }
            for budget in (5, 7, 10)
        },
    }
    output = RESULTS / args.output
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"saved={output}")


if __name__ == "__main__":
    main()
