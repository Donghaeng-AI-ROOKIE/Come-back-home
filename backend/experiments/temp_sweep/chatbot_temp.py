"""P1-3 — Mi:dm 온보딩 챗봇 온도 스윕 (추출 · 정정 · 질문 작문).

한 번의 인터뷰 실행이 두 계열 지표를 **동시에** 낸다 — 그래서 온도 조합마다
골드셋을 돌리면 추출 성능과 작문 성능을 같은 실행에서 읽을 수 있다.
  · 추출계(midm_temp_extract / _correction): 수집률 · evidence 정확도 ·
    과다추출(환각) · 축 커버리지 · 정정 반영
  · 작문계(midm_temp_phrase): 질문 수 · 중복질문 · 전제질문/부정조건(가드 패턴 누출)

조합 폭발을 피하려고 **한 번에 한 축만**(OFAT) 움직인다. 3×3 전수는 9배가 되는데,
두 계열이 서로 다른 프롬프트·다른 호출이라 교호작용을 기대할 근거가 약하다.

⚠ 실행 시간: 설정 하나당 8시나리오 × runs 회 인터뷰(턴마다 Mi:dm 2콜)라
설정당 수 분이 걸린다. 설정 수 × runs 를 늘리기 전에 --scenario 로 먼저 재보라.

실행 (backend 에서):
    # 1차 — 추출 온도만 움직임(작문은 현행 0.4 고정)
    .venv/Scripts/python.exe -m experiments.temp_sweep.chatbot_temp \
        --extract-temps 0.0,0.2,0.4 --phrase-temps 0.4 --runs 3
    # 2차 — 작문 온도만 움직임(추출은 1차 최적값 고정)
    .venv/Scripts/python.exe -m experiments.temp_sweep.chatbot_temp \
        --extract-temps 0.0 --phrase-temps 0.0,0.2 --runs 3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

RESULTS = Path(__file__).resolve().parent / "results"


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def _pct(v):
    return "  —" if v is None else f"{v * 100:3.0f}%"


def main() -> int:
    ap = argparse.ArgumentParser(description="Mi:dm 챗봇 온도 스윕")
    ap.add_argument("--extract-temps", default="0.0,0.2,0.4",
                    help="추출·정정 온도 (두 호출을 같이 움직인다 — 둘 다 구조화 목적)")
    ap.add_argument("--phrase-temps", default="0.4", help="질문 작문 온도")
    ap.add_argument("--runs", type=int, default=3, help="시나리오당 반복(평균)")
    ap.add_argument("--scenario", help="특정 시나리오 id (쉼표 다중) — 시간 재보기용")
    ap.add_argument("--tag", default="", help="결과 파일 접미사")
    args = ap.parse_args()

    ex_temps = [float(t) for t in args.extract_temps.split(",")]
    ph_temps = [float(t) for t in args.phrase_temps.split(",")]

    os.environ["AXIS_SCORING_ENABLED"] = "false"   # 축 채점은 EXAONE 경로 — P1-3 범위 밖

    from fastapi.testclient import TestClient
    from app.config import settings
    from app.main import app
    from app.llm import midm as midm_client

    from experiments.chatbot_eval.runner import run_scenario
    from experiments.chatbot_eval.scorer import score
    from experiments.chatbot_goldset.goldset_scenarios import GOLDSET

    if midm_client.is_stub:
        print("Mi:dm 스텁 모드 — .env 의 MIDM_* 확인 필요. 실측 불가.")
        return 1

    client = TestClient(app)
    ids = ([s.strip() for s in args.scenario.split(",")] if args.scenario else list(GOLDSET))
    configs = [(e, p) for e in ex_temps for p in ph_temps]

    print(f"═══ 챗봇 온도 스윕 · 설정 {len(configs)}개 × 시나리오 {len(ids)}개 × {args.runs}회 ═══")
    print(f"    추출·정정 {ex_temps} × 작문 {ph_temps}")

    summary: dict[str, dict] = {}
    per_scenario: dict[str, dict] = {}

    for ex_t, ph_t in configs:
        settings.midm_temp_extract = ex_t
        settings.midm_temp_correction = ex_t
        settings.midm_temp_phrase = ph_t
        label = f"ex{ex_t}/ph{ph_t}"
        t0 = time.perf_counter()

        cards_by_sid: dict[str, list] = {}
        for sid in ids:
            sc_def = GOLDSET[sid]
            cards = [score(run_scenario(sc_def, client, verbose=False), sc_def)
                     for _ in range(args.runs)]
            cards_by_sid[sid] = cards

        flat = [c for cs in cards_by_sid.values() for c in cs]
        summary[label] = {
            "extract_temp": ex_t, "phrase_temp": ph_t,
            # 추출계
            "collection": _mean([c.collection_recall for c in flat]),
            "preferred": _mean([c.preferred_recall for c in flat]),
            "evidence": _mean([c.evidence_accuracy for c in flat]),
            "axis": _mean([c.axis_coverage for c in flat]),
            "extra": _mean([float(c.extra_extractions) for c in flat]),
            "name_ok": _mean([1.0 if c.name_ok else 0.0 for c in flat]),
            "age_ok": _mean([1.0 if c.age_ok else 0.0 for c in flat]),
            # 정정계 (해당 시나리오만 — None 은 평균에서 빠진다)
            "absent_ok": _mean([None if c.absent_ok is None else float(c.absent_ok) for c in flat]),
            "area_ok": _mean([None if c.area_ok is None else float(c.area_ok) for c in flat]),
            "home_ok": _mean([None if c.home_ok is None else float(c.home_ok) for c in flat]),
            # 작문계
            "questions": _mean([float(c.n_questions) for c in flat]),
            "dups": _mean([float(c.duplicate_questions) for c in flat]),
            "presumptive": _mean([float(c.presumptive_q) for c in flat]),
            "neg_conditional": _mean([float(c.neg_conditional_q) for c in flat]),
            # 배관
            "done": _mean([1.0 if c.done else 0.0 for c in flat]),
            "degraded": _mean([1.0 if c.llm_degraded else 0.0 for c in flat]),
            "elapsed_min": (time.perf_counter() - t0) / 60,
        }
        per_scenario[label] = {
            sid: {"collection": _mean([c.collection_recall for c in cs]),
                  "evidence": _mean([c.evidence_accuracy for c in cs]),
                  "extra": _mean([float(c.extra_extractions) for c in cs]),
                  "dups": _mean([float(c.duplicate_questions) for c in cs])}
            for sid, cs in cards_by_sid.items()
        }
        s = summary[label]
        print(f"  · {label:14} 완료 ({s['elapsed_min']:.1f}분) — 수집 {_pct(s['collection'])} "
              f"evidence {_pct(s['evidence'])} 과다추출 {s['extra']:.1f} 중복 {s['dups']:.1f}")

    # ── 표 ────────────────────────────────────────────────────────────
    print("\n" + "═" * 104)
    print("[추출계]")
    print(f"{'설정':14} {'수집':>6} {'선호':>6} {'evidence':>9} {'축':>6} {'과다추출':>8} "
          f"{'이름':>5} {'나이':>5} {'삭제반영':>8} {'지역정정':>8} {'원점':>6}")
    print("─" * 104)
    for label, s in summary.items():
        print(f"{label:14} {_pct(s['collection']):>6} {_pct(s['preferred']):>6} "
              f"{_pct(s['evidence']):>9} {_pct(s['axis']):>6} {s['extra']:>8.2f} "
              f"{_pct(s['name_ok']):>5} {_pct(s['age_ok']):>5} {_pct(s['absent_ok']):>8} "
              f"{_pct(s['area_ok']):>8} {_pct(s['home_ok']):>6}")
    print("\n[작문계 · 배관]")
    print(f"{'설정':14} {'질문수':>7} {'중복질문':>8} {'전제질문':>8} {'부정조건':>8} "
          f"{'종료':>6} {'LLM열화':>8}")
    print("─" * 104)
    for label, s in summary.items():
        print(f"{label:14} {s['questions']:>7.1f} {s['dups']:>8.2f} {s['presumptive']:>8.2f} "
              f"{s['neg_conditional']:>8.2f} {_pct(s['done']):>6} {_pct(s['degraded']):>8}")
    print("═" * 104)
    print("수집=골드 끌림점 재현율 · 과다추출=골드 외 추출(환각, 낮을수록 좋음)")
    print("전제질문/부정조건=가드가 막는 패턴이 질문에 샌 횟수(낮을수록 좋음)")

    RESULTS.mkdir(exist_ok=True)
    tag = args.tag or f"ex{'_'.join(map(str, ex_temps))}_ph{'_'.join(map(str, ph_temps))}"
    out = RESULTS / f"chatbot_temp_{tag}_runs{args.runs}.json"
    out.write_text(json.dumps({"runs": args.runs, "scenarios": ids,
                               "summary": summary, "per_scenario": per_scenario},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"원본 저장: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
