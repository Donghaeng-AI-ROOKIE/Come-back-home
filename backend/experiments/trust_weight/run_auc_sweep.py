"""P1-5 재설계 — genuine_scenarios.py 의 진짜/가짜 목격담으로 r(개연성:구체성 비율)을
ROC-AUC 기준으로 스윕. "정답표 정답률"이 아니라 "진짜/가짜 분리 성능"이라는 텍스트 판단이
섞이지 않은 지표를 쓴다(genuine_scenarios.py 상단 docstring 참고).

실행: backend 폴더 안에서 `python experiments/trust_weight/run_auc_sweep.py`.
Stage B(Mi:dm 실호출)는 tip_llm 이 스텁이면 자동 건너뜀.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from sklearn.metrics import roc_auc_score  # noqa: E402

from app.config import settings  # noqa: E402
from app.geo import reachability  # noqa: E402
from app.llm import tip_llm as tip_llm_client  # noqa: E402
from app.phase3.trust import SPECIFICITY_LEVELS  # noqa: E402

from genuine_scenarios import CREATED_AT, GENUINE_SCENARIOS, LKP, LKP_TIME, PERSONA  # noqa: E402

RESULTS_DIR = Path(__file__).parent / "results"
R_RANGE = [round(1.0 + 0.1 * i, 1) for i in range(21)]  # 1.0~3.0
# 하드코딩 대신 config 값 참조 — 안 그러면 r 확정치가 바뀔 때마다 "현재" 표시가 낡는다
# (2026-07-31 셀프리뷰에서 발견: r=1.6→2.3 반영 후에도 이 파일이 1.6을 "현재"로 표시하던 버그).
CURRENT_R = round(settings.trust_weight_plausibility / settings.trust_weight_specificity, 4)


def compute_p(plaus: float, level: str, r: float) -> float:
    spec_val = SPECIFICITY_LEVELS[level]
    return (plaus * r + spec_val * 1.0) / (r + 1.0)


def compute_plausibilities() -> dict[str, float]:
    """좌표 기반 실제 개연성 계산 — 텍스트 판단 없음, 순수 좌표거리."""
    result = {}
    for sc in GENUINE_SCENARIOS:
        p = reachability.plausibility(
            LKP, LKP_TIME, sc.location, PERSONA,
            seen_at=None, created_at=CREATED_AT,
        )
        result[sc.id] = p
    return result


def majority_specificity(votes: list[str]) -> str:
    counts = Counter(votes)
    top, top_n = counts.most_common(1)[0]
    return "중" if (top_n == 1 and len(counts) == 3) else top


def stage_b_grades(n_votes: int = 3) -> dict[str, str]:
    grades = {}
    total = len(GENUINE_SCENARIOS)
    for i, sc in enumerate(GENUINE_SCENARIOS, 1):
        votes = [tip_llm_client.structure_tip(sc.text)["specificity"] for _ in range(n_votes)]
        grades[sc.id] = majority_specificity(votes)
        print(f"  Stage B 호출 {i}/{total} ({sc.id}): {votes} -> {grades[sc.id]}")
    return grades


def auc_sweep(plausibilities: dict[str, float], specificity_by_id: dict[str, str]) -> list[dict]:
    labels = [1 if sc.genuine else 0 for sc in GENUINE_SCENARIOS]
    rows = []
    for r in R_RANGE:
        scores = [
            compute_p(plausibilities[sc.id], specificity_by_id[sc.id], r)
            for sc in GENUINE_SCENARIOS
        ]
        auc = roc_auc_score(labels, scores)
        rows.append({"r": r, "auc": round(auc, 4)})
    return rows


def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    plausibilities = compute_plausibilities()

    n_genuine = sum(1 for sc in GENUINE_SCENARIOS if sc.genuine)
    print(f"시나리오 {len(GENUINE_SCENARIOS)}개 (genuine={n_genuine}, fake={len(GENUINE_SCENARIOS)-n_genuine})")

    result: dict = {}

    # Stage A: gold specificity
    gold_by_id = {sc.id: sc.gold_specificity for sc in GENUINE_SCENARIOS}
    stage_a_rows = auc_sweep(plausibilities, gold_by_id)
    result["stage_a"] = {"sweep": stage_a_rows}
    best_a = max(stage_a_rows, key=lambda row: row["auc"])
    print(f"\nStage A (gold) 최고 AUC={best_a['auc']} at r={best_a['r']}")

    # Stage B: 실제 Mi:dm
    if tip_llm_client.is_stub:
        result["stage_b"] = {"skipped": True, "reason": "tip_llm.is_stub=True"}
        print("Stage B 건너뜀 (tip_llm 스텁)")
    else:
        print("\nStage B (Mi:dm 실호출) 시작...")
        grades = stage_b_grades()
        stage_b_rows = auc_sweep(plausibilities, grades)
        result["stage_b"] = {"model_grades": grades, "sweep": stage_b_rows}
        best_b = max(stage_b_rows, key=lambda row: row["auc"])
        print(f"\nStage B (Mi:dm) 최고 AUC={best_b['auc']} at r={best_b['r']}")

    out_path = RESULTS_DIR / "auc_sweep.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {out_path}")

    print("\n=== r별 AUC (Stage A) ===")
    for row in stage_a_rows:
        marker = " <-- 현재" if row["r"] == CURRENT_R else ""
        print(f"  r={row['r']}: AUC={row['auc']}{marker}")
    if not result["stage_b"].get("skipped"):
        print("\n=== r별 AUC (Stage B) ===")
        for row in result["stage_b"]["sweep"]:
            marker = " <-- 현재" if row["r"] == CURRENT_R else ""
            print(f"  r={row['r']}: AUC={row['auc']}{marker}")


if __name__ == "__main__":
    main()
