"""P1-7 — 사람 정답표 기반 점수 vs LLM judge 점수의 상관 측정.

절차 (시나리오 8개 × 차원 3개, judge 입력 2방식 통제 비교):
  1. 골드셋 시나리오를 실 Mi:dm 으로 끝까지 굴린다 (runner, 서버 불필요)
  2. 정답 기반 점수 = scorer 의 내용 3지표 (사람 정답표 03 의 기계 전사 대비)
  3. judge 점수 — 같은 전사에 대해 입력 2방식으로 각각 채점:
       v1(names) = 축 이름 목록만 (최초 설계 — axis r=0.33 실측)
       v2(texts) = 축 근거 원문 포함 (그 낮은 r 이 입력 설계 탓인지 검증)
  4. 피어슨 r — 차원×방식별 + 전체 풀. 도입 기준 r≥0.7

실행 (backend/, .env 에 MIDM_* 실키 필요 — 스텁이면 중단):
  PYTHONUTF8=1 .venv/bin/python -m experiments.chatbot_eval.run_judge_corr
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app import llm
from app.main import app
from experiments.chatbot_eval.judge import judge_scenario
from experiments.chatbot_eval.runner import run_scenario
from experiments.chatbot_eval.scorer import score
from experiments.chatbot_goldset.goldset_scenarios import GOLDSET

OUT_DIR = Path(__file__).resolve().parent / "results"

# ScoreCard 내용 지표 ↔ judge 차원
DIMS = [("collection", "collection_recall"),
        ("evidence", "evidence_accuracy"),
        ("axis", "axis_coverage")]

# judge 입력 방식 — 같은 전사에 둘 다 적용해 인터뷰 비결정성을 통제
VARIANTS = [("names", False),   # 축 이름 목록만
            ("texts", True)]    # 축 근거 원문 포함


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    try:
        return statistics.correlation(xs, ys)
    except statistics.StatisticsError:   # 상수열(분산 0)이면 정의 불가
        return None


def main() -> int:
    if llm.midm.is_stub:
        print("Mi:dm 이 스텁입니다 — .env 에 MIDM_API_KEY/MIDM_BASE_URL/MIDM_MODEL 을 "
              "채우고 Friendli 엔드포인트를 켠 뒤 실행하세요.")
        return 1

    client = TestClient(app)
    rows = []
    for sid, sc_def in GOLDSET.items():
        print(f"[run] {sid} …", flush=True)
        tr = run_scenario(sc_def, client)
        card = score(tr, sc_def)
        row = {"scenario": sid}
        parse_fail = False
        for vname, flag in VARIANTS:
            j = judge_scenario(sc_def, tr, include_axis_texts=flag)
            if j is None:
                print(f"  judge({vname}) 파싱 실패 — {sid} 제외")
                parse_fail = True
                break
            for jd, _sd in DIMS:
                row[f"judge_{vname}_{jd}"] = j[jd]
            row[f"judge_{vname}_reasoning"] = j["reasoning"]
        if parse_fail:
            continue
        for jd, sd in DIMS:
            row[f"truth_{jd}"] = getattr(card, sd)
        rows.append(row)

    # 상관 — 방식×차원별 + 방식별 전체 풀 (정답 지표가 None 인 쌍은 제외)
    corr: dict[str, float | None] = {}
    n_pairs: dict[str, int] = {}
    for vname, _flag in VARIANTS:
        all_t: list[float] = []
        all_j: list[float] = []
        for jd, _sd in DIMS:
            ts = [r[f"truth_{jd}"] for r in rows if r[f"truth_{jd}"] is not None]
            js = [r[f"judge_{vname}_{jd}"] for r in rows if r[f"truth_{jd}"] is not None]
            corr[f"{vname}_{jd}"] = pearson(ts, js)
            n_pairs[jd] = len(ts)
            all_t += ts
            all_j += js
        corr[f"{vname}_pooled"] = pearson(all_t, all_j)
        n_pairs["pooled"] = len(all_t)

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "judge_corr.json").write_text(
        json.dumps({"rows": rows, "pearson": corr, "n_pairs": n_pairs},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")

    def fmt(key: str) -> str:
        r_val = corr[key]
        return "—" if r_val is None else f"{r_val:.3f}"

    lines = ["# P1-7 사람 정답 기반 점수 vs LLM judge 상관 — 입력 2방식 통제 비교", "",
             f"시나리오 {len(rows)}/8 채점 성공 · 같은 전사에 judge 입력만 변경 · "
             "도입 기준 r≥0.7", "",
             "| 차원 | v1 축이름만 | v2 근거원문 | 데이터쌍 |", "|---|---|---|---|"]
    for jd, _sd in DIMS:
        lines.append(f"| {jd} | {fmt(f'names_{jd}')} | {fmt(f'texts_{jd}')} "
                     f"| {n_pairs[jd]} |")
    lines.append(f"| **전체 풀** | **{fmt('names_pooled')}** | **{fmt('texts_pooled')}** "
                 f"| {n_pairs['pooled']} |")
    lines += ["", "한계: (1) n=6~8 파일럿 규모 — 95% CI 가 넓어 높은 r 만 해석 가능, "
              "낮은 r 은 '판정 불가'로 읽을 것. (2) judge = Mi:dm(추출과 동일 모델) — "
              "자기 출력 자기 평가(self-bias). (3) 전체 풀은 시나리오당 3쌍 비독립."]
    md = "\n".join(lines) + "\n"
    (OUT_DIR / "judge_corr.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
