"""수집률 0% 시나리오 진단 — 무엇을 기대했고 무엇을 뽑았나.

P1-3 온도 스윕에서 G_D3_choi·G_P2_seoyeon 이 온도와 무관하게 항상 수집 0% 였다.
온도 문제가 아니므로 원인을 따로 본다: 챗봇이 그 슬롯을 **묻기는 했는지**,
보호자 답변을 받고도 **추출을 못 한 건지**를 구분해야 처방이 갈린다.

실행: .venv/Scripts/python.exe -m experiments.temp_sweep.diagnose_zero
"""

from __future__ import annotations

import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

TARGETS = ["G_D3_choi", "G_P2_seoyeon"]


def main() -> int:
    os.environ["AXIS_SCORING_ENABLED"] = "false"

    from fastapi.testclient import TestClient
    from app.main import app
    from experiments.chatbot_eval.runner import run_scenario
    from experiments.chatbot_eval.scorer import score
    from experiments.chatbot_goldset.goldset_scenarios import GOLDSET

    client = TestClient(app)

    for sid in TARGETS:
        sc = GOLDSET[sid]
        tr = run_scenario(sc, client, verbose=False)
        card = score(tr, sc)
        print("=" * 78)
        print(f"{sid} — {sc.title}")
        print(f"기대 끌림점 {sc.expected.attraction_labels} · 기대 선호 {sc.expected.preferred_labels}")
        print(f"수집률 {card.collection_recall} · 선호 {card.preferred_recall} "
              f"· 과다추출 {card.extra_extractions}")
        print("-" * 78)
        print("[챗봇이 수집한 장소(좌표화 이전 draft)]")
        for a in (tr.draft_attractions or []):
            print(f"  · {a.get('label')!r}  evidence={a.get('evidence')}  raw={a.get('raw_text')!r}")
        print("[최종 페르소나 반영분]")
        for a in ((tr.persona or {}).get("attraction_points") or []):
            print(f"  · {a.get('label')!r}")
        print("[선호대상]")
        print(f"  {card.details.get('preferred_got')}")
        print("[골드 외 추출]")
        print(f"  {card.details.get('extra')}")
        print("[챗봇이 던진 질문]")
        for q in tr.assistant_questions:
            print(f"  Q: {q}")
        print("[보호자 발화 — 실제로 전달된 것]")
        for m in (tr.messages if hasattr(tr, "messages") else []):
            if m.get("role") == "user":
                print(f"  A: {m.get('text')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
