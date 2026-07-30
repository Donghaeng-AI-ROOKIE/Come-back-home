"""P1-3 — tip_llm(제보 구조화) 온도 스윕.

`tip_llm_compare` 의 손라벨 70개 골드셋과 동일한 채점 기준을 재사용해, 온도만
{0.0, 0.2, 0.4} 로 바꿔 돌린다. 제보 구조화는 입력이 **한 덩어리 고정 텍스트**라
같은 시나리오를 N회 반복하면 정확도와 결정성을 한 번에 잴 수 있다.

지표:
- 균형정확도(★판정 기준) = 상/중/하 각 클래스 recall 의 평균.
  단순정확도를 쓰지 않는 이유는 4파전 문서와 같다 — 골드셋이 "중" 51% 로 편중돼
  전부 "중" 을 찍는 모델이 51% 를 공짜로 얻는다.
- 단순정확도 / 필드추출 정확도(4필드 존재유무) / 호출실패 / 평균지연
- 결정성 = 같은 제보를 N회 넣었을 때 최빈 출력 비율(1.0 = 완전 결정론)

자격증명: `settings.tip_llm_*` 가 비어 있으면 Mi:dm(`settings.midm_*`) 을 주입한다
— run_compare.py 와 같은 방식이고, 프로덕션 코드 경로(TipLLMClient.structure_tip)를
그대로 탄다. ⚠ KT 발급 endpoint 가 Mini(2.3B)인지 Base(11.5B)인지는 응답으로
확인되지 않는다(2026-07-29 확인) — 여기 최적 온도는 "이 엔드포인트 기준"이다.

실행 (backend 에서):
    .venv/Scripts/python.exe -m experiments.temp_sweep.tip_temp --runs 3
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tip_llm_compare"))

RESULTS = Path(__file__).resolve().parent / "results"
LEVELS = ("상", "중", "하")


def _canon(result: dict) -> str:
    """결정성 비교용 — 리스트 순서 차이는 같은 출력으로 본다."""
    r = dict(result)
    r["appearance_cues"] = sorted(r.get("appearance_cues") or [])
    return json.dumps(r, ensure_ascii=False, sort_keys=True)


def _balanced_accuracy(rows: list[dict]) -> tuple[float, dict[str, float]]:
    """클래스별 recall 평균. 골드에 없는 클래스는 평균에서 제외."""
    recalls: dict[str, float] = {}
    for lv in LEVELS:
        sub = [r for r in rows if r["gold_specificity"] == lv]
        if sub:
            recalls[lv] = sum(r["specificity_match"] for r in sub) / len(sub)
    return (sum(recalls.values()) / len(recalls) if recalls else 0.0), recalls


def main() -> int:
    ap = argparse.ArgumentParser(description="tip_llm 제보 구조화 온도 스윕")
    ap.add_argument("--runs", type=int, default=3, help="시나리오당 반복(정확도 평균 + 결정성)")
    ap.add_argument("--temps", default="0.0,0.2,0.4")
    args = ap.parse_args()
    temps = [float(t) for t in args.temps.split(",")]

    from app.config import settings
    from app.llm.tip_llm import TipLLMClient
    from scenarios import SCENARIOS  # type: ignore[import-not-found]

    # tip_llm 전용 자격증명이 없으면 Mi:dm endpoint 를 빌려 쓴다(run_compare.py 와 동일).
    source = "tip_llm_*"
    if not (settings.tip_llm_api_key and settings.tip_llm_base_url and settings.tip_llm_model):
        settings.tip_llm_api_key = settings.midm_api_key
        settings.tip_llm_base_url = settings.midm_base_url
        settings.tip_llm_model = settings.midm_model
        source = "midm_* (tip 전용 자격증명 없음)"

    client = TipLLMClient()
    if client.is_stub:
        print("tip_llm 스텁 모드 — 자격증명 없음. 실측 불가.")
        return 1

    print(f"═══ tip_llm 온도 스윕 · 자격증명 {source} · "
          f"시나리오 {len(SCENARIOS)}개 × 온도 {temps} × {args.runs}회 ═══")

    per_temp: dict[float, dict] = {}
    all_rows: list[dict] = []

    for temp in temps:
        settings.tip_llm_temp_structure = temp
        client.call_failures = 0
        rows: list[dict] = []
        t_start = time.perf_counter()
        for sc in SCENARIOS:
            outs, preds, lat = [], [], []
            for _ in range(args.runs):
                t0 = time.perf_counter()
                res = client.structure_tip(sc.text)
                lat.append((time.perf_counter() - t0) * 1000)
                outs.append(_canon(res))
                preds.append(res)
            mode_rate = Counter(outs).most_common(1)[0][1] / len(outs)
            # 정확도는 N회 평균 — 단일 실행은 노이즈 지배(P1-3 노트).
            rows.append({
                "id": sc.id, "category": sc.category, "note": sc.note,
                "gold_specificity": sc.gold_specificity,
                "pred_specificity": preds[0]["specificity"],
                "specificity_match": sum(p["specificity"] == sc.gold_specificity
                                         for p in preds) / len(preds),
                "location_match": sum((p["location_text"] is not None) == sc.expect_location
                                      for p in preds) / len(preds),
                "time_match": sum((p["time_kind"] != "none") == sc.expect_time
                                  for p in preds) / len(preds),
                "appearance_match": sum(bool(p["appearance_cues"]) == sc.expect_appearance
                                        for p in preds) / len(preds),
                "direction_match": sum((p["direction"] is not None) == sc.expect_direction
                                       for p in preds) / len(preds),
                "mode_rate": mode_rate,
                "elapsed_ms": sum(lat) / len(lat),
                "temp": temp,
            })
        elapsed = time.perf_counter() - t_start
        n = len(rows)
        fkeys = ["location_match", "time_match", "appearance_match", "direction_match"]
        bal, recalls = _balanced_accuracy(rows)
        per_temp[temp] = {
            "simple_accuracy": sum(r["specificity_match"] for r in rows) / n,
            "balanced_accuracy": bal,
            "recalls": recalls,
            "field_accuracy": sum(sum(r[k] for k in fkeys) for r in rows) / (n * len(fkeys)),
            "determinism": sum(r["mode_rate"] for r in rows) / n,
            "call_failures": client.call_failures,
            "avg_latency_ms": sum(r["elapsed_ms"] for r in rows) / n,
        }
        all_rows += rows
        print(f"  · T={temp} 완료 ({elapsed/60:.1f}분) — 균형정확도 {bal:.1%} "
              f"결정성 {per_temp[temp]['determinism']:.1%} 실패 {client.call_failures}")

    # 표
    print("\n" + "═" * 96)
    print(f"{'온도':>5} {'균형정확도':>11} {'단순정확도':>11} {'상recall':>9} {'중recall':>9} "
          f"{'하recall':>9} {'필드추출':>9} {'결정성':>8} {'실패':>5} {'지연ms':>8}")
    print("─" * 96)
    for temp in temps:
        s = per_temp[temp]
        r = s["recalls"]
        print(f"{temp:>5} {s['balanced_accuracy']:>10.1%} {s['simple_accuracy']:>10.1%} "
              f"{r.get('상', 0):>8.0%} {r.get('중', 0):>8.0%} {r.get('하', 0):>8.0%} "
              f"{s['field_accuracy']:>8.1%} {s['determinism']:>7.1%} "
              f"{s['call_failures']:>5} {s['avg_latency_ms']:>8.0f}")
    print("═" * 96)
    print("무작위 기준선(항상 '중') = 51.4% 단순정확도 · 균형정확도는 클래스 recall 평균")
    print("결정성 = 같은 제보 N회 중 최빈 출력 비율(1.0 = 완전 결정론)")

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"tip_temp_runs{args.runs}.json"
    out.write_text(json.dumps({"runs": args.runs, "temps": temps, "credential_source": source,
                               "summary": {str(k): v for k, v in per_temp.items()},
                               "rows": all_rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"원본 저장: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
