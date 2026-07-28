"""페르소나 뱅크 축 점수 백필 — 완전한 운영형 입력([특성] 블록)을 위한 보강.

뱅크 생성 시점에는 axis_scoring_enabled=False(기본)라 축이 미채점이었다.
persona.axis_evidence(인터뷰 수집 quote)는 살아 있으므로 운영과 동일한
score_axes_for(B-P1, 축당 3회 다수결)로 채점해 뱅크 JSON 에 되써 넣는다.

BEFORE/AFTER 측정 모두 이 백필된 동일 뱅크를 쓰므로 비교 조건은 오염되지 않는다.

실행: cd backend && .venv/bin/python -m experiments.mind_probe.backfill_axis
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

RESULTS = Path(__file__).parent / "results"


def main() -> None:
    from app.llm.exaone import ExaoneClient
    from app.phase0.axis_scoring import score_axes_for
    from app.schemas.persona import Persona

    path = RESULTS / "persona_bank.json"
    bank = json.loads(path.read_text(encoding="utf-8"))
    client = ExaoneClient()

    for key, item in bank.items():
        if not (item.get("ok") and item.get("persona")):
            continue
        p = Persona.model_validate(item["persona"])
        if p.axis_scores:
            print(f"[axis-backfill] {key}: 이미 채점됨({len(p.axis_scores)}축) — 건너뜀")
            continue
        scores, meta = score_axes_for(p, client=client)
        item["persona"]["axis_scores"] = scores
        item["axis_backfill_meta"] = {k: v for k, v in (meta or {}).items()
                                      if not isinstance(v, (bytes,))}
        print(f"[axis-backfill] {key}: {len(scores)}축 채점 — "
              + " ".join(f"{a.split('_')[0]}:{s}" for a, s in list(scores.items())[:4]))

    path.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[axis-backfill] 저장: {path}")


if __name__ == "__main__":
    main()
