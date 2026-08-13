"""P1-6(감쇠계수 k) + P1-5(가중치 r, Stage A/B) 스윕 실행기.

노션 설계(2026-07-30) "절차" 4단계를 그대로 코드로 옮긴다:
  1. P1-6 먼저 — k ∈ {0.5,1.0,2.0} 감쇠 곡선.
  2. P1-5 Stage A — gold 구체성 등급으로 r(1.0~3.0, 0.1 간격) 스윕.
  3. P1-5 Stage B — 실제 Mi:dm structure_tip() 등급(시나리오당 3회 다수결)으로 동일 스윕.
  4. A vs B 비교는 analyze.py 가 담당(이 파일은 원시 결과를 JSON 으로만 남긴다).

실행: backend 폴더 안에서 `python experiments/trust_weight/run_sweep.py`.
Stage B 는 tip_llm 이 스텁이면(터널 안 열림 등) 자동으로 건너뛰고 그 사실을 결과에 남긴다.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

# Windows 콘솔(cp949)로 리다이렉트하면 —·⚠ 같은 문자에서 UnicodeEncodeError 남 → 강제 UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/ 를 import 루트로

from app.geo.reachability import decay_factor
from app.llm import tip_llm as tip_llm_client  # 싱글턴 인스턴스(app/llm/__init__.py)
from app.phase3 import poa_update
from app.phase3.trust import SPECIFICITY_LEVELS

from scenarios import SCENARIOS, TrustScenario
from scenarios_70 import SCENARIOS_70

RESULTS_DIR = Path(__file__).parent / "results"

# ── P1-6: k 스윕 ──────────────────────────────────────────────────────
K_VALUES = [0.5, 1.0, 2.0]
D_RATIOS = [1.2, 2.0, 3.0]  # d/d_max — "살짝 초과"·"2배"·"3배"


def sweep_k() -> list[dict]:
    """d_max=1 로 고정하고 d=ratio 로 두면 decay_factor 결과가 ratio 에만 의존한다
    (식이 (d-d_max)/d_max 형태라 절대 거리가 아니라 비율만 보면 됨)."""
    rows = []
    for ratio in D_RATIOS:
        row = {"d_over_dmax": ratio}
        for k in K_VALUES:
            row[f"k={k}"] = round(decay_factor(d=ratio, d_max=1.0, k=k), 4)
        rows.append(row)
    return rows


# ── P1-5: r 스윕 ──────────────────────────────────────────────────────
R_RANGE = [round(1.0 + 0.1 * i, 1) for i in range(21)]  # 1.0 ~ 3.0, 0.1 간격


def compute_p(plausibility: float, specificity_level: str, r: float) -> float:
    """trust.score_tip() 과 같은 가중평균 식(재정규화)을 r=w1/w2 로 재현.
    w1=r, w2=1.0 로 둬도 결과는 동일 — 절대값이 아니라 비율만 영향을 준다(설계 문서 명시).
    """
    spec_val = SPECIFICITY_LEVELS[specificity_level]
    w1, w2 = r, 1.0
    return (plausibility * w1 + spec_val * w2) / (w1 + w2)


def sweep_r(scenarios: list[TrustScenario], specificity_by_id: dict[str, str]) -> list[dict]:
    """시나리오별 r-스윕. specificity_by_id 로 Stage A(gold)/Stage B(모델) 를 전환."""
    rows = []
    for r in R_RANGE:
        row: dict = {"r": r}
        for sc in scenarios:
            level = specificity_by_id[sc.id]
            p = compute_p(sc.plausibility, level, r)
            decision = poa_update.classify_tip(p, sc.has_location_time)
            row[sc.id] = {"p": round(p, 4), "decision": decision.value}
        rows.append(row)
    return rows


def check_sanity(sweep_rows: list[dict], scenarios: list[TrustScenario]) -> dict:
    """expected_decision 있는 시나리오가 전체 r 범위에서 안 바뀌는지 확인.
    draft=False(자동파생·확정) 시나리오만 대상 — draft=True(Claude 초안)는 원래 r 에 따라
    갈릴 수 있는 경계 케이스라 '안 바뀜'을 기대하지 않는다(accuracy_by_r 로 별도 채점)."""
    sanity = [sc for sc in scenarios if sc.expected_decision is not None and not sc.draft]
    report = {}
    for sc in sanity:
        decisions = {row["r"]: row[sc.id]["decision"] for row in sweep_rows}
        mismatches = {r: d for r, d in decisions.items() if d != sc.expected_decision.value}
        report[sc.id] = {
            "expected": sc.expected_decision.value,
            "held_for_all_r": not mismatches,
            "mismatches": mismatches,
        }
    return report


def accuracy_by_r(sweep_rows: list[dict], scenarios: list[TrustScenario]) -> list[dict]:
    """선정기준 ①: r 별 '정답률' — expected_decision 있는 시나리오 전체(sanity+draft) 대상.
    draft 초안은 서영 검토 전이라 이 정확도가 최종 근거는 아니고, r 후보를 좁히는 참고용."""
    graded = [sc for sc in scenarios if sc.expected_decision is not None]
    if not graded:
        return []
    rows = []
    for row in sweep_rows:
        correct = sum(1 for sc in graded if row[sc.id]["decision"] == sc.expected_decision.value)
        rows.append({"r": row["r"], "accuracy": round(correct / len(graded), 4), "n": len(graded)})
    return rows


# ── Stage B: 실제 Mi:dm 호출(시나리오당 3회 다수결) ──────────────────────
def majority_specificity(votes: list[str]) -> tuple[str, bool]:
    """다수결. 3표가 전부 다르면(3-way tie) 실전 관례상 '중'으로 폴백하고 tie=True 로 표시."""
    counts = Counter(votes)
    top, top_n = counts.most_common(1)[0]
    tie = top_n == 1 and len(counts) == 3
    return ("중", True) if tie else (top, False)


def stage_b_grades(scenarios: list[TrustScenario], n_votes: int = 3, label: str = "") -> dict:
    """시나리오당 1회만 모델 호출 세트(3표) — r 스윕과 무관하니 여기서 캐싱."""
    grades = {}
    total = len(scenarios)
    for i, sc in enumerate(scenarios, 1):
        votes = [tip_llm_client.structure_tip(sc.text)["specificity"] for _ in range(n_votes)]
        level, tie = majority_specificity(votes)
        grades[sc.id] = {"votes": votes, "majority": level, "tie": tie}
        if total > 10:  # 70개셋처럼 오래 걸릴 때만 진행상황 표시
            print(f"  [{label}] Stage B 호출 {i}/{total} ({sc.id})")
    return grades


def run_experiment(scenarios: list[TrustScenario], label: str) -> dict:
    result: dict = {}

    gold_by_id = {sc.id: sc.gold_specificity for sc in scenarios}
    stage_a_rows = sweep_r(scenarios, gold_by_id)
    result["stage_a"] = {
        "sweep": stage_a_rows,
        "sanity": check_sanity(stage_a_rows, scenarios),
        "accuracy_by_r": accuracy_by_r(stage_a_rows, scenarios),
    }

    if tip_llm_client.is_stub:
        result["stage_b"] = {"skipped": True, "reason": "tip_llm.is_stub=True — 터널/서버 확인 필요"}
    else:
        grades = stage_b_grades(scenarios, label=label)
        model_by_id = {sid: g["majority"] for sid, g in grades.items()}
        stage_b_rows = sweep_r(scenarios, model_by_id)
        result["stage_b"] = {
            "model_grades": grades,
            "sweep": stage_b_rows,
            "sanity": check_sanity(stage_b_rows, scenarios),
            "accuracy_by_r": accuracy_by_r(stage_b_rows, scenarios),
        }
    return result


def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    result: dict = {"p1_6_decay_sweep": sweep_k()}

    print("=== core (5개, 손으로 고른 sanity+경계) ===")
    result["core_5"] = run_experiment(SCENARIOS, "core_5")

    print("=== full (70개, 4파전 재활용 — sanity 65 자동파생 + 경계 5 Claude초안) ===")
    result["full_70"] = run_experiment(SCENARIOS_70, "full_70")

    out_path = RESULTS_DIR / "trust_weight_sweep.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장 완료: {out_path}")

    print("\n=== P1-6 감쇠 곡선 (d/d_max별 k) ===")
    for row in result["p1_6_decay_sweep"]:
        print(row)

    for label in ("core_5", "full_70"):
        sub = result[label]
        print(f"\n=== [{label}] Stage A sanity ===")
        for sid, rep in sub["stage_a"]["sanity"].items():
            print(f"{sid}: expected={rep['expected']} held_for_all_r={rep['held_for_all_r']}")
        if not sub["stage_b"].get("skipped"):
            print(f"=== [{label}] Stage B sanity ===")
            for sid, rep in sub["stage_b"]["sanity"].items():
                print(f"{sid}: expected={rep['expected']} held_for_all_r={rep['held_for_all_r']}")
        else:
            print(f"[{label}] Stage B 건너뜀: {sub['stage_b']['reason']}")


if __name__ == "__main__":
    main()
