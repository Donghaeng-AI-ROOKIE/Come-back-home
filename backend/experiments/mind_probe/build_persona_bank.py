"""페르소나 뱅크 생성 — 대화 세트를 실 Phase 0 추출(Mi:dm)에 통과시켜 저장.

실행 (backend 에서, .env 의 Mi:dm 실키 필요):
  .venv/bin/python -m experiments.mind_probe.build_persona_bank
  .venv/bin/python -m experiments.mind_probe.build_persona_bank --scenario MB_dem_bal

산출: experiments/mind_probe/results/persona_bank.json
  { scenario_id: {"persona": {...}, "turns": n, "degraded": bool} }

좌표 정밀도는 뱅크 목적(마음 입력 생성)에 영향 없음 — 마음 입력은 라벨·근거·
노트만 쓴다. 지오코딩 폴백(gazetteer)이어도 그대로 저장한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

RESULTS = Path(__file__).parent / "results"


def main(only: str | None) -> None:
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.main import app
    from experiments.chatbot_eval.runner import run_scenario
    from experiments.mind_probe.bank_scenarios import BANK_SCENARIOS

    if not (settings.midm_api_key and settings.midm_model):
        sys.exit("[bank] Mi:dm 키/모델 미설정 — 실추출 불가. .env 확인.")

    client = TestClient(app)
    out: dict[str, dict] = {}
    scenarios = [s for s in BANK_SCENARIOS if not only or s.id == only]
    for sc in scenarios:
        print(f"[bank] {sc.id} ({sc.title}) …")
        t = run_scenario(sc, client, max_turns=40)
        persona = t.persona
        ok = t.done and persona is not None
        print(f"       done={t.done} turns={len(t.turns)} "
              f"attractions={len((persona or {}).get('attraction_points', []))} "
              f"notes={len((persona or {}).get('behavior_notes', []))} "
              f"degraded={t.llm_degraded}")
        out[sc.id] = {"ok": ok, "persona": persona, "turns": len(t.turns),
                      "degraded": t.llm_degraded,
                      "questions": t.assistant_questions,
                      "dialogue": t.turns}

    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / "persona_bank.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if (path.exists() and only) else {}
    existing.update(out)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=1), encoding="utf-8")
    n_ok = sum(1 for v in out.values() if v["ok"])
    print(f"[bank] 저장 {path} — 성공 {n_ok}/{len(out)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default=None)
    main(ap.parse_args().scenario)
