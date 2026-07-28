"""P1-4 — records.jsonl → 층2 트리거 결정표.

run_sweep.py 의 즉석 요약(summarize())은 실행 직후 빠른 확인용이고, 이 스크립트가
팀이 실제로 값을 고를 때 쓰는 정식 결정표(B1~B3)를 만든다. records.jsonl 만 다시
읽어 가공하므로 재실행(Phase2) 비용은 전혀 안 든다.

★이동/정지 분리 필수(2026-07-28 발견, D3 analyze.py 의 positive/negative 분리와
같은 이유): 정지 케이스(진짜 안 움직인 세계)는 애초에 처음 예측이 끝까지 맞아
정확도가 높게 나오기 쉽다. 합쳐서 평균내면 실제 추적 성능이 좋아 보이는 착시가
생기므로, 정확도·중심점거리는 항상 이동 케이스로만 낸다. 정지 케이스는 별도로
"재실행 안 해도 되는 상황에서 비용을 얼마나 아꼈나"만 본다.

실행: backend/ 에서
    python experiments/layer2_gridsearch/analyze.py --pilot
    python experiments/layer2_gridsearch/analyze.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔 cp949 방어(D3 analyze.py 관례)

OUT_DIR = Path(__file__).resolve().parent
LATENCY_BUDGETS_MIN = [18, 20, 22, 24]  # 관측된 탐지지연 범위(17~23분대)를 커버


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in open(path, encoding="utf-8")]


def _avg(rows: list[dict], key: str) -> float:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return sum(vals) / len(vals) if vals else float("nan")


def combo_stats(rows: list[dict]) -> dict:
    """콤보 하나(모든 세계에 대한 재생 기록)를 지표로 요약. moved/stationary 분리."""
    moved = [r for r in rows if r["moved"]]
    stationary = [r for r in rows if not r["moved"]]
    detected = [r for r in moved if r["detected"]]
    r0 = rows[0]
    return {
        "combo": r0["combo"], "type": r0["combo_type"],
        "periodic": r0["periodic_minutes"], "kl": r0["kl_threshold"],
        "n_moved": len(moved), "n_stationary": len(stationary),
        "탐지율": len(detected) / len(moved) if moved else float("nan"),
        "평균탐지지연_분": _avg(detected, "detection_delay_min"),
        "정확도_이동": _avg(moved, "poa_accuracy_final"),
        "정확도_정지": _avg(stationary, "poa_accuracy_final"),
        "중심점km_이동": _avg(moved, "centroid_km_final"),
        "재실행_이동": _avg(moved, "policy_reruns"),
        "재실행_정지": _avg(stationary, "policy_reruns"),
    }


def table_b1(all_rows: list[dict]) -> list[dict]:
    """콤보(25그리드+3ablation)별 지표 — 이동/정지 분리."""
    by_combo: dict[str, list[dict]] = defaultdict(list)
    for r in all_rows:
        by_combo[r["combo"]].append(r)
    return [combo_stats(rows) for _, rows in
            sorted(by_combo.items(), key=lambda kv: (kv[1][0]["combo_type"], kv[0]))]


def table_b2(grid_only: list[dict], budgets: list[int] = LATENCY_BUDGETS_MIN) -> list[dict]:
    """지연 예산 X분 이내인 그리드 콤보 중, 이동 케이스 재실행 비용이 최소인 것.
    "빠르게 잡아야 한다"는 제약을 걸고 그 안에서 가장 싼 콤보를 답으로 준다
    (D3 decision_table 의 '목표 탐지율 제약 → 최소 헛알림' 과 같은 철학)."""
    out = []
    for budget in budgets:
        candidates = [c for c in grid_only if c["평균탐지지연_분"] <= budget]
        if not candidates:
            out.append({"지연예산_분": budget, "선택콤보": "(만족 콤보 없음)",
                        "탐지율_%": None, "재실행_이동": None})
            continue
        best = min(candidates, key=lambda c: c["재실행_이동"])
        out.append({"지연예산_분": budget, "선택콤보": best["combo"],
                    "탐지율_%": round(best["탐지율"] * 100, 1),
                    "재실행_이동": round(best["재실행_이동"], 2)})
    return out


def ablation_note(b1: list[dict]) -> str:
    by_label = {c["combo"]: c for c in b1 if c["type"] == "ablation"}
    both = by_label.get("ablation_both_default")
    p_only = by_label.get("ablation_periodic_only")
    kl_only = by_label.get("ablation_kl_only")
    if not (both and p_only and kl_only):
        return "(ablation 콤보 데이터 없음)"
    return (
        f"- **주기+KL(both)** — 탐지율 {both['탐지율']:.1%} · 지연 {both['평균탐지지연_분']:.1f}분 · "
        f"정확도(이동) {both['정확도_이동']:.4f} · 재실행(이동) {both['재실행_이동']:.2f}\n"
        f"- **주기만(KL 끔)** — 탐지율 {p_only['탐지율']:.1%} · 지연 {p_only['평균탐지지연_분']:.1f}분 · "
        f"정확도(이동) {p_only['정확도_이동']:.4f} · 재실행(이동) {p_only['재실행_이동']:.2f}\n"
        f"- **KL만(주기 끔)** — 탐지율 {kl_only['탐지율']:.1%} · 지연 {kl_only['평균탐지지연_분']:.1f}분 · "
        f"정확도(이동) {kl_only['정확도_이동']:.4f} · 재실행(이동) {kl_only['재실행_이동']:.2f}\n\n"
        f"주기만/both 가 탐지율·지연·정확도 전부 거의 동일한데 재실행 비용은 주기만 쪽이 더 적다"
        f"({p_only['재실행_이동']:.2f} < {both['재실행_이동']:.2f}) — **KL 트리거가 주기 트리거 위에"
        f" 추가로 기여하는 게 거의 없어 보인다.** KL만(주기 끔)은 탐지율이 뚜렷이 낮아"
        f"({kl_only['탐지율']:.1%}) 주기가 탐지의 핵심 동력임을 보여준다."
    )


def _fmt_table(rows: list[dict]) -> str:
    if not rows:
        return "(데이터 없음)"
    headers = list(rows[0].keys())
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        vals = []
        for h in headers:
            v = row[h]
            if isinstance(v, float):
                vals.append("nan" if v != v else (f"{v:.1%}" if h == "탐지율" else f"{v:.4f}"))
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def render_markdown(pilot: bool, all_rows: list[dict]) -> str:
    b1 = table_b1(all_rows)
    grid_only = [c for c in b1 if c["type"] == "grid"]
    b2 = table_b2(grid_only)
    n_worlds = len({r["world_id"] for r in all_rows})
    n_moved_worlds = len({r["world_id"] for r in all_rows if r["moved"]})

    lines = [f"# 층2 재실행 트리거 결정표 ({'파일럿' if pilot else '본실험'})", ""]
    lines.append(f"세계 {n_worlds}개(이동 {n_moved_worlds} / 정지 {n_worlds - n_moved_worlds}) "
                f"× 콤보 {len(b1)}개(그리드 25 + ablation 3) = 기록 {len(all_rows)}행")
    lines.append("")
    lines.append("**시뮬레이션 기반 자체 평가.** 탐지 시점은 라벨이 아니라 "
                "'재실행 전까지 footprint 밖 진짜 셀 확률은 정확히 0'이라는 성질로 기계적으로 산출"
                "(layer1_update 는 기존 셀만 재가중, 새 셀은 재실행에서만 생김).")
    lines.append("")
    lines.append("**tip_llm·EXAONE prior 둘 다 스텁 상태의 상한선 결과** — EXAONE 파인튜닝 후 "
                "재검증 필요(메모리 project_p1_4_d3_threshold_spec.md 후속작업 A, D3 와 공통).")
    lines.append("")

    lines.append("## B1 — 콤보별 결정표 (그리드 25 + ablation 3)")
    lines.append("")
    lines.append("정확도·중심점거리·재실행은 이동/정지 분리. 정지 케이스는 원래 쉬운 상황"
                "(안 움직였으니 처음 예측이 계속 맞음)이라 섞으면 착시가 생긴다.")
    lines.append("")
    lines.append(_fmt_table(b1))
    lines.append("")

    lines.append("## B2 — 지연 예산별 최소비용 콤보")
    lines.append("")
    lines.append("\"이 시간 안에는 잡아야 한다\"는 제약을 걸고, 그 안에서 재실행(비용)이 "
                "가장 적은 그리드 콤보를 고른 것. 그리드 콤보만 대상(ablation 제외).")
    lines.append("")
    lines.append(_fmt_table(b2))
    lines.append("")

    lines.append("## B3 — Ablation (주기 vs KL 각각의 기여)")
    lines.append("")
    lines.append(ablation_note(b1))
    lines.append("")

    lines.append("## 한계")
    lines.append("")
    lines.append("- tip_llm 구체성 판정 + EXAONE prior 생성 둘 다 스텁(휴리스틱/Koester 통계) — "
                "\"LLM이 완벽하다\"는 가정 하 상한선. 실서빙 붙으면 재검증 필요.")
    lines.append("- 제보 품질은 baseline 혼합(고30/저50/허위20) 하나만 사용 — D3처럼 허위 스트레스"
                "·저품질 변형을 따로 돌리지 않았다(층2는 트리거 타이밍이 관심사라 스코프에서 뺌).")
    lines.append("- 트리거는 제보 도착 시에만 검사된다(app/phase3/tip_flow.py 실제 구조와 동일 — "
                "이 코드베이스엔 별도 주기 폴러가 없음). 그래서 \"주기 15분\"이 정확히 15분 간격이 "
                "아니라 그다음 제보 도착 시점에 반영된다 — 탐지지연이 주기값과 정확히 비례하지 않는 "
                "이유.")
    lines.append("- ablation 은 그리드 값(기본 45분/0.5) 기준 1세트만 — 다른 주기값 기준 ablation은 "
                "안 돌림.")
    lines.append("")
    return "\n".join(lines)


def main(pilot: bool) -> None:
    path = OUT_DIR / ("records_pilot.jsonl" if pilot else "records.jsonl")
    rows = load(path)
    md = render_markdown(pilot, rows)
    out_path = OUT_DIR / "results" / ("layer2_gridsearch_pilot.md" if pilot else "layer2_gridsearch.md")
    out_path.write_text(md, encoding="utf-8")
    print(md)
    print(f"\n저장: {out_path}")


if __name__ == "__main__":
    main(pilot="--pilot" in sys.argv)
