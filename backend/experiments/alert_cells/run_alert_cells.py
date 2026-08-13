"""알림셀 수 기준선 — 경과시간별 알림 대상 칸 수를 재고 기록한다.

## 왜 이 스크립트가 있는가

기존 알림셀 실측값(0.5h 11 · 1h 22 · 2h 31 · 4h 40)은 config.py 주석 한 줄이
전부였고 **재현 스크립트가 없었다.** 2026-08-04 같은 "이전 구성"으로 다시 재니
12.3 / 14.7 / 14.7 / 15.7 이 나왔고, 차이의 원인(페르소나·prior·도로망 반경 중
무엇이 달랐는지)을 확인할 방법이 없었다. 그래서 옛 값을 폐기하고 이 스크립트가
내는 값을 새 기준선으로 삼는다 — 조건이 코드에 박혀 있으니 다음엔 대조가 된다.

## 무엇을 재는가

pipeline.run_prediction 과 같은 순서로 POA 를 만든 뒤 alerts.select_alert_cells
(누적 80% · 상한 500)를 적용해 **알림 대상 칸 수**를 센다. prior 는 고정한다 —
이 실험의 대상은 마음 소비 경로이고, prior 를 매번 LLM 으로 새로 뽑으면 그 분산이
결과에 섞인다.

네 구성으로 나눠 어느 노브가 무엇을 움직였는지 분리한다.

  A  이전 구성   behavior off · 인식 실패 off
  B  behavior만  behavior on  · 인식 실패 off
  C  혼란도만    behavior off · 인식 실패 on
  D  새 기본값   behavior on  · 인식 실패 on

## 실행

    cd backend
    MIND_MODEL=exaone-mind-dem3 python -m experiments.alert_cells.run_alert_cells

**실 EXAONE 호출이 필요하다** (구성당 60회, 총 240회). 스텁이면 마음 재해석이 전부
"혼란 심화" 폴백이 되어 behavior 가 아예 나오지 않아 측정이 무의미하므로 중단한다.
도로망은 정릉 3km 디스크 캐시를 쓴다(첫 실행은 Overpass 콜드 다운로드).
"""

import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from sim_testset import _STRATEGY_MIX, ATTRACTION, LKP

from app import llm
from app.config import settings
from app.geo import envlayer, h3grid, roadnet
from app.llm.exaone import _KOESTER_PARAMS
from app.phase2 import combine, simulation
from app.phase3 import alerts
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, Persona, PersonaType
from app.schemas.prediction import PriorParams

N_WALKERS = 500          # settings.mc_num_walkers 운영값
# seed 3개로는 결론이 안 난다. 마음 모델을 실제로 호출하므로 seed 변동 위에 LLM
# 변동(회차 간 최대 약 2셀)이 얹히고, 구성 간 차이 대부분이 그 오차 안에 묻혔다
# (2026-08-04 1차·2차 측정). seed 를 늘려 표준오차를 내린다 — seed 마다 마음 호출이
# 새로 일어나므로 seed 를 늘리는 것이 곧 LLM 변동까지 표집하는 것이다.
SEEDS = list(range(42, 54))          # 12개
ELAPSED = [0.5, 1.0, 2.0, 4.0]
MARKET = GeoPoint(lat=37.6100, lng=127.0160)   # 두 번째 끌림점
OUT_DIR = Path(__file__).resolve().parent / "results"

CONFIGS = {
    "A 이전 구성":   (False, 0.0),
    "B behavior만":  (True,  0.0),
    "C 혼란도만":    (False, 1.0),
    "D 새 기본값":   (True,  1.0),
}


def make_persona() -> Persona:
    """끌림점 2개(과거 거주지·시장) — 귀소 매핑과 목표 전환이 모두 살아 있는 구성.

    끌림점이 하나뿐이면 goal_label 전환이 사실상 무의미해지고, 과거 장소가 없으면
    behavior "귀소 시도"가 설계대로 무동작이 되어 B 구성이 반쪽만 측정된다.
    """
    return Persona(
        id="alertcells-dem-78", type=PersonaType.dementia, name="기준선", age=78,
        home=LKP,
        attraction_points=[
            AttractionPoint(label="옛집", location=ATTRACTION, weight=0.7,
                            place_type="past_residence"),
            AttractionPoint(label="시장", location=MARKET, weight=0.3,
                            place_type="market"),
        ])


def make_prior() -> PriorParams:
    return PriorParams(
        strategy_probs=_STRATEGY_MIX[PersonaType.dementia],
        attraction_weights={"옛집": 0.7, "시장": 0.3},
        radius_lognormal=_KOESTER_PARAMS[PersonaType.dementia],
        reasoning="기준선 고정 prior")


CALLS = [0]


def measures(poa: dict[str, float], cells: list[str]) -> dict:
    """한 예측에서 뽑는 지표들.

    알림 셀 수 하나로는 부족하다는 것이 실측으로 드러났다 — 끌림점 위치가 고정이라
    시간이 지나 반경이 넓어져도 질량이 계속 거기 모여서, 셀 수가 시간에 둔감하다.
    그래서 "지도가 얼마나 뾰족한가"와 "질량이 얼마나 멀리 갔나"를 함께 본다.

    - cells   : 알림 대상 칸 수 (누적 80% · 상한 500)
    - top1    : 최고 칸 확률. 수색 우선순위가 서는가
    - top3    : 상위 3칸 누적
    - flat    : top1 / 알림 셀 확률 중앙값. 1 에 가까우면 평평(우선순위 없음)
    - mean_km : 확률가중 평균 이탈거리. 질량이 LKP 에서 얼마나 멀리 갔나
    """
    ps = sorted((poa[c] for c in cells), reverse=True)
    med = statistics.median(ps) if ps else 0.0
    return {
        "cells": len(cells),
        "top1": ps[0] if ps else 0.0,
        "top3": sum(ps[:3]),
        "flat": (ps[0] / med) if med > 0 else 0.0,
        "mean_km": sum(h3grid.haversine_km(LKP, h3grid.cell_center(c)) * p
                       for c, p in poa.items()),
    }


def agg(vals: list[float]) -> dict:
    """평균과 표준오차. n 이 작을 때 평균만 보면 없는 차이를 있다고 읽는다."""
    n = len(vals)
    m = statistics.mean(vals)
    se = (statistics.stdev(vals) / math.sqrt(n)) if n > 1 else 0.0
    return {"mean": round(m, 3), "se": round(se, 3), "n": n}


def main() -> None:
    if llm.exaone.is_stub:
        raise SystemExit("EXAONE 스텁 모드 — 실호출 없이는 측정 의미 없음")
    orig_chat = type(llm.exaone).chat

    def counted_chat(self, *a, **k):
        CALLS[0] += 1
        return orig_chat(self, *a, **k)

    type(llm.exaone).chat = counted_chat

    net = roadnet.get_network(LKP)
    envlayer.attach(net, LKP)
    print(f"[net] nodes={len(net.graph.nodes)}  mind_model={settings.mind_model}")

    persona, prior = make_persona(), make_prior()
    # statistical 은 두 노브의 영향을 받지 않으므로 (elapsed, seed) 당 1회만 돌려 재사용
    stat_cache: dict[tuple, dict] = {}
    rows = []

    KEYS = ["cells", "top1", "top3", "flat", "mean_km"]
    for name, (behav, miss) in CONFIGS.items():
        settings.mind_behavior_enabled = behav
        settings.confusion_miss_strength = miss
        per_elapsed = {}
        for el in ELAPSED:
            samples = {k: [] for k in KEYS}
            for seed in SEEDS:
                key = (el, seed)
                if key not in stat_cache:
                    stat_cache[key] = simulation.run_monte_carlo(
                        LKP, prior, persona, el, mode="statistical", net=net,
                        n_walkers=N_WALKERS, seed=seed)
                bu = simulation.run_monte_carlo(
                    LKP, prior, persona, el, mode="agent", net=net,
                    n_walkers=N_WALKERS, seed=seed)
                pooled = combine.alpha_pool([bu, stat_cache[key]],
                                            alphas=[0.7, 0.3], mode="linear")
                m = measures(pooled, alerts.select_alert_cells(pooled))
                for k in KEYS:
                    samples[k].append(m[k])
            per_elapsed[str(el)] = {k: agg(samples[k]) for k in KEYS}
            c, t1 = per_elapsed[str(el)]["cells"], per_elapsed[str(el)]["top1"]
            print(f"{name:14s} {el:>4}h  셀 {c['mean']:5.1f}±{c['se']:.2f}  "
                  f"top1 {t1['mean'] * 100:4.1f}%±{t1['se'] * 100:.1f}  "
                  f"(누적 호출 {CALLS[0]})")
        rows.append({"config": name, "behavior": behav, "miss": miss,
                     "by_elapsed": per_elapsed})

    print(f"\n=== {N_WALKERS}워커 × seed {len(SEEDS)}개, 정릉 3km, 실 EXAONE "
          f"({settings.mind_model}) · 평균±표준오차 ===")
    for k, label, fmt in [("cells", "알림 셀 수", "{:.1f}"),
                          ("top1", "최고 칸 확률(%)", "{:.1f}"),
                          ("flat", "평탄도 top1/중앙값", "{:.1f}"),
                          ("mean_km", "평균 이탈거리(km)", "{:.2f}")]:
        print(f"\n[{label}]")
        print(f"{'구성':16s}" + "".join(f"{e:>13}h" for e in ELAPSED))
        for r in rows:
            cells = []
            for e in ELAPSED:
                a = r["by_elapsed"][str(e)][k]
                mul = 100 if k == "top1" else 1
                cells.append(f"{fmt.format(a['mean'] * mul)}±{a['se'] * mul:.2f}".rjust(14))
            print(f"{r['config']:16s}" + "".join(cells))
    print(f"\n총 EXAONE 호출 {CALLS[0]}회")

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "alert_cells.json").write_text(
        json.dumps({"rows": rows, "exaone_calls": CALLS[0], "n_walkers": N_WALKERS,
                    "seeds": SEEDS, "elapsed": ELAPSED,
                    "mind_model": settings.mind_model},
                   ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
