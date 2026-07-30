"""run_sweep.py 결과(results/trust_weight_sweep.json)를 사람이 읽을 표로 정리.

최적 r 선정기준(노션 설계 2026-07-30) 순서대로 출력한다:
  1. 경계 케이스 판정 정답률이 가장 높은 r (accuracy_by_r — full_70 이 draft 라벨 포함
     진짜 표본, core_5 는 소규모 참고용).
  2. sanity 케이스(자동파생 65개 + core_5 의 손으로 고른 3개)가 전체 r 범위에서 안 바뀌는지.
  3. Stage A vs Stage B 비교 — 벌어지면 "r 확정 전 프롬프트/모델부터" 라는 결론.
  4. 함정: 판정이 3단계 계단이라 곡선이 평평할 수 있음 — 평평하면 "현행유지 정당"이 결론.

full_70 의 accuracy_by_r 은 5개 draft(Claude 초안, 서영 미검토) 시나리오를 포함한다 —
서영이 draft 를 수정하면 이 수치도 바뀐다는 점 주의(최종 근거 아니라 예비 참고용).

실행: backend 폴더 안에서 `python experiments/trust_weight/analyze.py`
(run_sweep.py 를 먼저 실행해 results/trust_weight_sweep.json 이 있어야 함).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/ — scenarios_70.py 의 app.* import 용
sys.path.insert(0, str(Path(__file__).parent))

from app.config import settings  # noqa: E402 — 하드코딩 대신 실제 config 값 참조(안 그러면 r 바뀔 때마다 낡음)

RESULTS_PATH = Path(__file__).parent / "results" / "trust_weight_sweep.json"
CURRENT_R = round(settings.trust_weight_plausibility / settings.trust_weight_specificity, 4)


def flip_points(sweep: list[dict], scenario_id: str) -> list[dict]:
    flips = []
    prev = None
    for row in sweep:
        decision = row[scenario_id]["decision"]
        if decision != prev:
            flips.append({"r": row["r"], "decision": decision, "p": row[scenario_id]["p"]})
            prev = decision
    return flips


def print_accuracy_peak(stage: dict, stage_name: str) -> None:
    acc = stage.get("accuracy_by_r") or []
    if not acc:
        print(f"  ({stage_name}: 채점 대상 시나리오 없음)")
        return
    best = max(acc, key=lambda row: row["accuracy"])
    at_current = next((row for row in acc if row["r"] == CURRENT_R), None)
    peak_rs = [row["r"] for row in acc if row["accuracy"] == best["accuracy"]]
    flat = len(peak_rs) > 3
    print(f"  {stage_name}: 최고 정답률={best['accuracy']:.1%} (n={best['n']}), "
          f"r={peak_rs if not flat else f'{peak_rs[0]}~{peak_rs[-1]} 등 {len(peak_rs)}개 동률'}")
    if at_current:
        print(f"    현재 r={CURRENT_R} 정답률: {at_current['accuracy']:.1%}")
    if flat:
        print("    ⚠ 봉우리가 평평함 — '최적 r 못 찾음'이 아니라 'r 에 둔감 = 현행 유지도 정당'일 수 있음")


def print_stage(name: str, stage: dict, boundary_ids: list[str]) -> None:
    print(f"\n--- {name} ---")
    if stage.get("skipped"):
        print(f"(건너뜀: {stage['reason']})")
        return

    if boundary_ids:
        print("경계 케이스 flip point:")
        for sid in boundary_ids:
            fp = flip_points(stage["sweep"], sid)
            print(f"  {sid}:")
            for f in fp:
                print(f"    r={f['r']:.1f} → {f['decision']} (p={f['p']})")
            if len(fp) == 1:
                print("    (r 1.0~3.0 전 구간에서 판정 안 바뀜 — 이 시나리오는 r 에 둔감)")

    print("sanity 유지 여부(자동파생/확정 셋만):")
    for sid, rep in stage["sanity"].items():
        status = "OK" if rep["held_for_all_r"] else f"깨짐! {rep['mismatches']}"
        print(f"  {sid}: expected={rep['expected']} → {status}")

    print("경계케이스 판정 정답률(선정기준 ①):")
    print_accuracy_peak(stage, name)


def compare_stage_a_b(stage_a: dict, stage_b: dict, boundary_ids: list[str]) -> None:
    print("--- Stage A vs Stage B 비교 (선정기준 ④: A≈B 여야 r 채택 가능) ---")
    if stage_b.get("skipped"):
        print("(Stage B 없음 — 비교 불가)")
        return
    for sid in boundary_ids:
        fp_a = flip_points(stage_a["sweep"], sid)
        fp_b = flip_points(stage_b["sweep"], sid)
        ra = fp_a[1]["r"] if len(fp_a) > 1 else None
        rb = fp_b[1]["r"] if len(fp_b) > 1 else None
        print(f"  {sid}: Stage A flip r={ra}, Stage B flip r={rb}", end="")
        if ra is not None and rb is not None:
            print(f" (차이 {abs(ra - rb):.1f})")
        else:
            print(" (한쪽 이상 flip 없음 — 비교 불가)")

    acc_a = {row["r"]: row["accuracy"] for row in stage_a.get("accuracy_by_r", [])}
    acc_b = {row["r"]: row["accuracy"] for row in stage_b.get("accuracy_by_r", [])}
    max_gap = max((abs(acc_a[r] - acc_b[r]) for r in acc_a if r in acc_b), default=None)
    if max_gap is not None:
        print(f"  정답률 곡선 최대 차이(A-B): {max_gap:.1%}"
              + ("  ⚠ 꽤 벌어짐 — 모델 오차가 판정에 영향" if max_gap > 0.1 else "  (거의 일치)"))


def draft_summary(scenarios_module) -> None:
    drafts = [sc for sc in scenarios_module.SCENARIOS_70 if sc.draft]
    if not drafts:
        return
    print(f"\n--- ⚠ 서영 검토 필요: Claude 초안 판정 {len(drafts)}개 (scenarios_70.py) ---")
    for sc in drafts:
        print(f"  [{sc.id}] {sc.expected_decision.value} — {sc.note}")
        print(f"    원문: {sc.text}")


def main() -> None:
    if not RESULTS_PATH.exists():
        print(f"결과 파일 없음: {RESULTS_PATH} — 먼저 run_sweep.py 를 실행하세요.")
        sys.exit(1)

    data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))

    print("=== P1-6 감쇠 곡선 (d/d_max × k) ===")
    for row in data["p1_6_decay_sweep"]:
        print(row)

    import scenarios_70  # noqa: E402

    print("\n\n########## core_5 (손으로 고른 sanity 3 + 경계 2) ##########")
    core_boundary = ["t03_boundary_a", "t04_boundary_b"]
    print_stage("Stage A (gold)", data["core_5"]["stage_a"], core_boundary)
    print_stage("Stage B (Mi:dm)", data["core_5"]["stage_b"], core_boundary)
    compare_stage_a_b(data["core_5"]["stage_a"], data["core_5"]["stage_b"], core_boundary)

    print("\n\n########## full_70 (4파전 재활용, v4 정답표 기준) ##########")
    # ★수정: v1 시절 하드코딩 id(["s11","c06","o06","m01","n06"])가 v4 재설계 후 안 맞아서
    # (개연성 난수 재배정으로 매 실행 경계 멤버십이 바뀜) 동적으로 뽑도록 변경.
    # "재검토표시"(★, 서영이 명시적으로 판단 내린 케이스)만 flip point 상세 출력 — 나머지
    # 패턴기본 다수(수십개)까지 전부 찍으면 콘솔이 안 읽혀서 핵심만.
    full_boundary = [sc.id for sc in scenarios_70.SCENARIOS_70 if sc.draft and "★" in sc.note]
    print(f"(★표시 재검토 케이스 {len(full_boundary)}개만 flip point 상세 출력: {full_boundary})")
    print_stage("Stage A (gold)", data["full_70"]["stage_a"], full_boundary)
    print_stage("Stage B (Mi:dm)", data["full_70"]["stage_b"], full_boundary)
    compare_stage_a_b(data["full_70"]["stage_a"], data["full_70"]["stage_b"], full_boundary)

    draft_summary(scenarios_70)

    print(
        "\n참고: flip point 가 아예 없으면(1개짜리 리스트) 그 시나리오는 r 1.0~3.0 범위 안에서 "
        "둔감하다는 뜻 — '최적 r 못 찾음'이 아니라 '판정이 r 에 안 흔들림 = 현행 유지도 정당'이 "
        "결론이 될 수 있다(설계 문서 함정 (1))."
    )


if __name__ == "__main__":
    main()
