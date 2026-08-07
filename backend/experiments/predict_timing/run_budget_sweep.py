"""P2-1 — mind_call_budget 실측 스윕 (EXAONE 라이브, 김순자 시나리오).

P1-5 가 심은 계측(스테이지 타이머 + call_log.elapsed_ms)으로 budget 10→7→5→3 의
(실측 소요시간, POA 품질) 곡선을 얻는다. 품질 = budget=10 기준 POA 대비
Jensen-Shannon divergence. budget=10 을 2회 돌려 run-to-run JS(노이즈 바닥)를
먼저 재고, 축소 budget 의 JS 가 그 바닥 수준이면 "품질 손실 없음"으로 판정한다.

실행:  .venv/bin/python experiments/predict_timing/run_budget_sweep.py
전제:  EXAONE vLLM 서빙(SSH 터널, .env EXAONE_BASE_URL) + mind-v5 로드 상태.
산출:  experiments/predict_timing/results_<날짜>_budget_sweep.{json,md}
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("USE_ROADNET", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
from scipy.spatial.distance import jensenshannon

from fastapi.testclient import TestClient

from app import storage
from app.config import settings
from app.llm import exaone
from app.main import app
from app.phase2.pipeline import run_prediction

OUT_DIR = Path(__file__).parent
SEED = 42
# 측정 순서: 기준 2회(노이즈 바닥) → 축소 스윕. 워밍업은 별도 1회(버림).
RUNS = [("b10_A", 10), ("b10_B", 10), ("b7", 7), ("b5", 5), ("b3", 3)]

client = TestClient(app)


def make_case() -> str:
    """김순자 시나리오 (e2e_smoke 1·2단계와 동일 좌표·구성) — 매 런 새 케이스."""
    p = client.post("/phase0/personas", json={
        "name": "김순자", "age": 78, "type": "dementia",
        "home": {"lat": 37.6061, "lng": 127.0106},
        "attraction_points": [
            {"label": "옛집(아리랑고개)", "location": {"lat": 37.6015, "lng": 127.0088},
             "weight": 0.55},
            {"label": "정릉시장", "location": {"lat": 37.6047, "lng": 127.0121},
             "weight": 0.30}],
        "behavior_notes": ["해질녘 옛집 방향으로 걷는 습관", "중기 치매 — 시간 인식 혼란"]})
    assert p.status_code < 300, p.text
    lkp_time = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
    case = client.post("/phase1/reports", json={
        "missing_type": "dementia", "lkp": {"lat": 37.6061, "lng": 127.0106},
        "lkp_time": lkp_time, "persona_id": p.json()["id"],
        "appearance": {
            "top": "파란색 점퍼", "bottom": "회색 바지", "shoes": "흰색 운동화"
        },
        "with_document": True})
    assert case.status_code < 300, case.text
    return case.json()["id"]


def js_divergence(p: dict, q: dict) -> float:
    """두 POA(cell→prob) 의 JS divergence (base 2). 셀 합집합 위에서 계산."""
    cells = sorted(set(p) | set(q))
    pv = np.array([p.get(c, 0.0) for c in cells])
    qv = np.array([q.get(c, 0.0) for c in cells])
    d = jensenshannon(pv, qv, base=2)  # 반환값은 거리(=sqrt(JSD))
    return float(d * d)


def one_run(label: str, budget: int) -> dict:
    settings.mind_call_budget = budget
    cid = make_case()
    case = storage.cases.get(cid)
    n0 = len(exaone.call_log)
    t0 = time.perf_counter()
    result = run_prediction(case, seed=SEED, trace=True)
    wall_s = time.perf_counter() - t0
    calls = exaone.call_log[n0:]
    mind = [c for c in calls if c["kind"] == "mind"]
    prior = [c for c in calls if c["kind"] == "prior"]
    debug = storage.debug_traces.get(cid)
    timings = dict(debug.timings) if debug and debug.timings else {}
    return {
        "label": label, "budget": budget, "case_id": cid,
        "wall_s": round(wall_s, 2),
        "timings_ms": timings,
        "prior_ms": prior[0]["elapsed_ms"] if prior else None,
        "mind_calls": len(mind),
        "mind_ms_each": [c["elapsed_ms"] for c in mind],
        "mind_ms_sum": round(sum(c["elapsed_ms"] or 0 for c in mind), 1),
        "poa": dict(result.poa_combined.cells),
        "exaone_stub": exaone.is_stub,
    }


def main() -> None:
    assert not exaone.is_stub, "EXAONE 스텁 상태 — 서빙/키 확인 (실측 무의미)"
    print(f"[sweep] mind_model={settings.mind_model} base_url={settings.exaone_base_url}")

    print("[sweep] 워밍업 (도로망 콜드 로딩 제거용, 결과 버림)…")
    warm = one_run("warmup", 3)
    print(f"[sweep] 워밍업 {warm['wall_s']}s (mind {warm['mind_calls']}콜)")

    results = []
    for label, budget in RUNS:
        r = one_run(label, budget)
        results.append(r)
        print(f"[sweep] {label}: {r['wall_s']}s, mind {r['mind_calls']}콜 "
              f"{r['mind_ms_sum']:.0f}ms, prior {r['prior_ms']:.0f}ms")

    base = results[0]["poa"]  # b10_A = 품질 기준
    for r in results:
        r["js_vs_b10A"] = round(js_divergence(base, r["poa"]), 6)

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_json = OUT_DIR / f"results_{stamp}_budget_sweep.json"
    out_json.write_text(json.dumps(results, ensure_ascii=False, indent=2))

    lines = [
        "# P2-1 budget 스윕 실측 결과",
        "",
        f"- 일시: {datetime.now().isoformat(timespec='seconds')} / seed={SEED} / "
        f"mind_model={settings.mind_model}",
        "- 시나리오: 김순자(치매, 정릉) — e2e_smoke 와 동일. 매 런 새 케이스, 도로망 웜.",
        "- JS = budget=10 1회차(b10_A) 대비 Jensen-Shannon divergence(base 2). "
        "b10_B 의 JS = run-to-run 노이즈 바닥.",
        "",
        "| run | budget | wall(s) | mind 콜 | mind 합(ms) | prior(ms) | JS vs b10_A |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['label']} | {r['budget']} | {r['wall_s']} | {r['mind_calls']} "
            f"| {r['mind_ms_sum']:.0f} | {r['prior_ms']:.0f} | {r['js_vs_b10A']:.6f} |")
    lines += ["", "## 스테이지 타이머 (ms)", ""]
    keys = ["prepare_ms", "prior_ms", "roadnet_ms", "topdown_ms", "bottomup_ms",
            "statistical_ms", "combine_ms", "total_ms"]
    lines.append("| run | " + " | ".join(k.replace("_ms", "") for k in keys) + " |")
    lines.append("|---|" + "---|" * len(keys))
    for r in results:
        t = r["timings_ms"]
        lines.append(f"| {r['label']} | " +
                     " | ".join(f"{t.get(k, 0):.0f}" for k in keys) + " |")
    out_md = OUT_DIR / f"results_{stamp}_budget_sweep.md"
    out_md.write_text("\n".join(lines) + "\n")
    print(f"[sweep] 저장: {out_json.name} / {out_md.name}")


if __name__ == "__main__":
    main()
