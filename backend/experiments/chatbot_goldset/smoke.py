"""골드셋 대화가 하네스를 끝까지 구동하는지 스모크.

expected 가 비어 있어 내용 지표는 0/—. 여기서 보는 것: 페르소나 도달·종료,
슬롯이 실제로 질문되고 수집되는가, responder 가 대본으로 답을 매칭하는가.

실행(backend 에서):  python -m experiments.chatbot_goldset.smoke [시나리오id...]
기본은 D1(표준)·D4(판정불가) 두 개. 스텁 강제(LLM 키 빈값).
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    for key in ("EXAONE_API_KEY", "EXAONE_BASE_URL", "EXAONE_MODEL",
                "MIDM_API_KEY", "MIDM_BASE_URL", "MIDM_MODEL"):
        os.environ[key] = ""
    os.environ["AXIS_SCORING_ENABLED"] = "false"

    from fastapi.testclient import TestClient
    from app.main import app

    from experiments.chatbot_eval.runner import run_scenario
    from experiments.chatbot_eval.scorer import format_card, score
    from experiments.chatbot_goldset.goldset_scenarios import GOLDSET

    ids = sys.argv[1:] or ["G_D1_kim", "G_D4_park"]
    client = TestClient(app)
    print("═══ 골드셋 스모크 (스텁) ═══")
    for sid in ids:
        sc_def = GOLDSET.get(sid)
        if sc_def is None:
            print(f"없는 시나리오: {sid} (있는 것: {list(GOLDSET)})")
            continue
        print("\n" + "─" * 72)
        print(f"▶ {sc_def.id} — {sc_def.title}")
        print("─" * 72)
        tr = run_scenario(sc_def, client, verbose=True)
        if tr.stopped_reason and tr.stopped_reason != "done":
            print(f"  ⓘ 종료 사유: {tr.stopped_reason}")
        print("\n" + format_card(score(tr, sc_def)))
        print(f"  수집 끌림점(draft): {[a.get('label') for a in tr.draft_attractions]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
