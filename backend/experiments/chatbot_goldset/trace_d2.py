"""D2 가드 누수 추적 — '마포구 신수동'(되묻기 주소)이 별개 끌림점으로 새는 지점을 찾는다.

턴마다 세션 상태(prev_target_key·pending_area_label·draft_attractions)를 찍어,
어느 턴/상태에서 신수동이 draft 에 추가되는지 본다. 되묻기 턴이면 가드가 있어야
정상, 다른 턴이면 Mi:dm 재추출(이전 턴 장소 되뱉기) 누수다.

실행:  python -m experiments.chatbot_goldset.trace_d2   (실 Mi:dm 필요)
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    os.environ["AXIS_SCORING_ENABLED"] = "false"
    from fastapi.testclient import TestClient
    from app.main import app

    from experiments.chatbot_eval.responder import is_summary_gate, respond
    from experiments.chatbot_goldset.goldset_scenarios import GOLDSET

    sc = GOLDSET["G_D2_lee"]
    client = TestClient(app)

    def dump(tag, session):
        drafts = [(a.get("label"), a.get("area_text") or "∅", a.get("evidence"))
                  for a in session.get("draft_attractions", [])]
        print(f"  [{tag}] prev={session.get('prev_target_key')} "
              f"pending_area={session.get('pending_area_label')!r} "
              f"await_confirm={session.get('awaiting_confirmation')}")
        print(f"        draft_attractions={drafts}")

    s = client.post("/phase0/interviews", json={
        "guardian_name": sc.guardian_name, "persona_type": None}).json()
    sid = s["id"]
    corrections = list(sc.corrections) + [sc.affirm]
    cidx = 0
    prev_drafts = []
    for turn in range(40):
        if s.get("done"):
            break
        q = next((m["text"] for m in reversed(s["messages"]) if m["role"] == "assistant"), None)
        if q is None:
            break
        a = corrections[min(cidx, len(corrections)-1)] if is_summary_gate(q) else respond(q, sc)
        if is_summary_gate(q):
            cidx += 1
        print(f"\n턴{turn}  🤖 {q[:70]}")
        print(f"       🧑 {a}")
        s = client.post(f"/phase0/interviews/{sid}/answers", json={"text": a}).json()
        dump(f"턴{turn} 후", s)
        # 이번 턴에 새로 생긴 draft 라벨 강조
        cur = [x.get("label") for x in s.get("draft_attractions", [])]
        new = [x for x in cur if x not in prev_drafts]
        if new:
            print(f"        ▶ 새 끌림점 추가: {new}")
            if "신수동" in " ".join(new):
                print("        ★★★ 신수동 누수 발생! 위 pending_area/prev 상태 확인 ★★★")
        prev_drafts = cur
    return 0


if __name__ == "__main__":
    sys.exit(main())
