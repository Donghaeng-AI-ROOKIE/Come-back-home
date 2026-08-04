"""골드셋 채점 — 8개 시나리오를 N회 돌려 사람 정답표(03) 대비 성능을 집계한다.

실행(backend 에서):
  python -m experiments.chatbot_goldset.evaluate --runs 3          # 실 Mi:dm(기본)
  python -m experiments.chatbot_goldset.evaluate --stub            # 배관 확인용
  python -m experiments.chatbot_goldset.evaluate --runs 3 --scenario G_D1_kim

성능은 **수집률**로 읽는다(지오코딩 혼입 회피). 저신호 시나리오(D3·D4·P4)는
**과다추출**(골드 외 추출 = 환각)이 핵심 지표. 각 설정 N회 평균으로 Mi:dm 노이즈를 줄인다.
"""

from __future__ import annotations

import argparse
import os
import sys


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def _pct(v):
    return "  —" if v is None else f"{v * 100:3.0f}%"


def main() -> int:
    parser = argparse.ArgumentParser(description="챗봇 추출 골드셋 채점")
    parser.add_argument("--stub", action="store_true", help="스텁 모드(배관 확인)")
    parser.add_argument("--runs", type=int, default=3, help="시나리오당 반복(평균)")
    parser.add_argument("--scenario", help="특정 시나리오 id (쉼표 다중)")
    args = parser.parse_args()

    if args.stub:
        for k in ("EXAONE_API_KEY", "EXAONE_BASE_URL", "EXAONE_MODEL",
                  "MIDM_API_KEY", "MIDM_BASE_URL", "MIDM_MODEL"):
            os.environ[k] = ""
    os.environ["AXIS_SCORING_ENABLED"] = "false"

    from fastapi.testclient import TestClient
    from app.main import app
    from app.llm import midm as midm_client

    from experiments.chatbot_eval.runner import run_scenario
    from experiments.chatbot_eval.scorer import score
    from experiments.chatbot_goldset.goldset_scenarios import GOLDSET

    mode = "스텁" if midm_client.is_stub else "실 Mi:dm"
    client = TestClient(app)

    ids = ([s.strip() for s in args.scenario.split(",")] if args.scenario
           else list(GOLDSET))
    print(f"═══ 챗봇 추출 골드셋 채점 · 모드 {mode} · 시나리오 {len(ids)}개 × {args.runs}회 ═══")

    # 시나리오별 N회 평균
    per: dict[str, dict] = {}
    for sid in ids:
        sc_def = GOLDSET[sid]
        cards = []
        for _ in range(args.runs):
            tr = run_scenario(sc_def, client, verbose=False)
            cards.append(score(tr, sc_def))
        per[sid] = {
            "type": sc_def.persona_type,
            "done": _mean([1.0 if c.done else 0.0 for c in cards]),
            "collection": _mean([c.collection_recall for c in cards]),
            "evidence": _mean([c.evidence_accuracy for c in cards]),
            "axis": _mean([c.axis_coverage for c in cards]),
            "extra": _mean([float(c.extra_extractions) for c in cards]),
            "name_ok": _mean([1.0 if c.name_ok else 0.0 for c in cards]),
            "age_ok": _mean([1.0 if c.age_ok else 0.0 for c in cards]),
        }
        print(f"  · {sid:14} 완료")

    # 표
    print("\n" + "═" * 92)
    print("골드셋 성능 (시나리오별, N회 평균) — 수집률로 읽음, 과다추출=환각 지표")
    print("═" * 92)
    print(f"{'시나리오':14} {'유형':6} {'종료':>5} {'수집':>6} "
          f"{'evidence':>9} {'축':>6} {'과다추출':>7} {'이름':>5} {'나이':>5}")
    print("─" * 92)
    for sid in ids:
        p = per[sid]
        print(f"{sid:14} {'치매':6} {_pct(p['done']):>5} {_pct(p['collection']):>6} "
              f"{_pct(p['evidence']):>9} {_pct(p['axis']):>6} "
              f"{p['extra']:>7.1f} {_pct(p['name_ok']):>5} {_pct(p['age_ok']):>5}")
    print("─" * 92)

    # 집계 (전체·유형별)
    def agg(subset):
        return {
            "done": _mean([per[s]["done"] for s in subset]),
            "collection": _mean([per[s]["collection"] for s in subset]),
            "evidence": _mean([per[s]["evidence"] for s in subset]),
            "axis": _mean([per[s]["axis"] for s in subset]),
            "extra": _mean([per[s]["extra"] for s in subset]),
        }

    a = agg(ids)
    print(f"{'전체':14} {'':6} {_pct(a['done']):>5} {_pct(a['collection']):>6} "
          f"{_pct(a['evidence']):>9} {_pct(a['axis']):>6} "
          f"{a['extra']:>7.1f}")
    print("═" * 92)
    print("수집=골드 끌림점 재현율 · evidence=근거등급 정확도(수집분 기준)")
    print("축=골드 축근거 커버리지 · 과다추출=골드에 없는 추출 평균(저신호 D3/D4 는 0 이 목표)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
