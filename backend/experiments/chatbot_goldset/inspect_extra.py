"""과다추출 내용 확인 — LLM 이 골드에 없는 무엇을 더 뽑았는지 원문 그대로 찍는다.

실행:  python -m experiments.chatbot_goldset.inspect_extra [id...] [--runs N]
기본: G_D1_kim G_D2_lee G_D3_choi, 각 2회. 실 Mi:dm(키 있으면).
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    runs = 2
    args = [a for a in sys.argv[1:]]
    if "--runs" in args:
        i = args.index("--runs")
        runs = int(args[i + 1])
        del args[i:i + 2]
    ids = args or ["G_D1_kim", "G_D2_lee", "G_D3_choi"]

    os.environ["AXIS_SCORING_ENABLED"] = "false"
    from fastapi.testclient import TestClient
    from app.main import app
    from app.llm import midm as midm_client

    from experiments.chatbot_eval.runner import run_scenario
    from experiments.chatbot_eval.scorer import score
    from experiments.chatbot_goldset.goldset_scenarios import GOLDSET

    print(f"═══ 과다추출 내용 확인 · 모드 {'스텁' if midm_client.is_stub else '실 Mi:dm'} ═══")
    client = TestClient(app)
    for sid in ids:
        sc_def = GOLDSET[sid]
        exp = sc_def.expected
        print("\n" + "═" * 72)
        print(f"▶ {sid} — {sc_def.title}")
        print(f"  골드 끌림점: {exp.attraction_labels or '없음'}")
        print(f"  골드 축: {exp.axis_fields}")
        for r in range(runs):
            tr = run_scenario(sc_def, client, verbose=False)
            sc = score(tr, sc_def)
            draft = [(a.get("label"), a.get("evidence"), a.get("area_text") or "지역없음")
                     for a in (tr.draft_attractions or [])]
            axes = sorted((tr.persona or {}).get("axis_evidence", {}).keys())
            extra = sc.details.get("extra", {})
            print(f"\n  [run {r+1}] 과다추출={sc.extra_extractions}")
            print(f"    수집 끌림점(라벨·evidence·지역): {draft or '—'}")
            print(f"    수집 축: {axes}")
            print(f"    ⚠ 골드 외 → 끌림점:{extra.get('끌림점') or '—'} · "
                  f"선호:{extra.get('선호') or '—'} · 축:{extra.get('축') or '—'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
