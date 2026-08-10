"""독립 OSM 궤적에서 비개인화(B) 대 장소 개인화(C) 알림을 비교한다.

실행(백엔드 루트):
    .venv/bin/python -m experiments.personalized_alert_replay.run_replay --pilot

정답 궤적은 truth_routes.py가 NetworkX 최단경로로 만들고, 예측은
Phase 2의 도로망 MC를 쓴다. 두 경로는 도로망만 공유하며 Koester 표본·게이지·
6전략 난수는 정답 생성에 쓰지 않는다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from app.geo import h3grid
from app.geo.roadnet import OSMnxNetwork
from app.llm.exaone import _KOESTER_PARAMS
from app.phase2 import simulation
from app.phase3 import alerts
from app.schemas.persona import AttractionPoint, Persona, PersonaType
from app.schemas.prediction import PriorParams
from experiments.personalized_alert_replay.truth_routes import (
    STRATA,
    TruthScenario,
    build_scenarios,
    truth_points_after_report,
)
from sim_testset import _STRATEGY_MIX

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
GRAPHML = BACKEND / "data/roadnet_cache/walk_37.6061_127.0106_5000.graphml"
OUT_DIR = HERE / "results"
# 상위 19셀은 MC 순위 노이즈에 민감하다. alert_cells 기준선과 동일하게
# 500워커×12시드로 맞춘다. 3시드 초안은 안정화 전 결과로 폐기한다.
PREDICTION_SEEDS = tuple(range(42, 54))
N_WALKERS = 500
BUDGET_K = 19


def _persona(s: TruthScenario, personalized: bool) -> Persona:
    points = []
    if personalized:
        points = [AttractionPoint(
            label="사전등록 장소",
            location=s.attraction,
            weight=1.0,
            place_type="market",
            origin_slot="routine_destinations",
        )]
    return Persona(
        id=f"{s.scenario_id}-{'C' if personalized else 'B'}",
        type=PersonaType.dementia,
        name="실험 페르소나",
        age=78,
        home=s.start,
        attraction_points=points,
    )


def _prior(personalized: bool) -> PriorParams:
    return PriorParams(
        strategy_probs=dict(_STRATEGY_MIX[PersonaType.dementia]),
        attraction_weights={"사전등록 장소": 1.0} if personalized else {},
        radius_lognormal=_KOESTER_PARAMS[PersonaType.dementia],
        reasoning="실험 고정 prior — 장소 개인화만 ablation",
        source="stub",
    )


def _mean_poa(poas: list[dict[str, float]]) -> dict[str, float]:
    acc: dict[str, float] = {}
    for poa in poas:
        for cell, p in poa.items():
            acc[cell] = acc.get(cell, 0.0) + p / len(poas)
    total = sum(acc.values()) or 1.0
    return {c: p / total for c, p in acc.items()}


def _top_k_outside(poa: dict[str, float], excluded: set[str], k: int) -> list[str]:
    ranked = sorted(poa.items(), key=lambda item: item[1], reverse=True)
    return [cell for cell, _ in ranked if cell not in excluded][:k]


def _run_arm(net, scenario: TruthScenario, personalized: bool, truth) -> dict:
    persona = _persona(scenario, personalized)
    prior = _prior(personalized)
    elapsed_h = max(scenario.missing_before_report_min / 60.0, 0.05)
    poa = _mean_poa([
        simulation.run_monte_carlo(
            scenario.start,
            prior,
            persona,
            elapsed_h,
            mode="statistical",
            net=net,
            n_walkers=N_WALKERS,
            seed=seed,
        )
        for seed in PREDICTION_SEEDS
    ])
    d1 = set(alerts.select_reflex_cells(scenario.start, k=2))
    d2 = set(_top_k_outside(poa, d1, BUDGET_K))
    active = d1 | d2
    truth_cells = [(minute, h3grid.cell_of(point)) for minute, point in truth]
    hits = [minute for minute, cell in truth_cells if cell in active]
    d2_hits = [minute for minute, cell in truth_cells if cell in d2]
    # 5분마다 찍은 점 셀만으로 경로를 정의하면 샘플 사이 진행 구간을
    # 모두 무관 알림으로 오판한다. 시점별 위치의 1-ring을 경로 corridor로 쓴다.
    route_cells: set[str] = set()
    for _, point in truth:
        route_cells.update(h3grid.cells_within_k(point, 1))
    return {
        "arm": "C_personalized" if personalized else "B_nonpersonalized",
        "d1_cells": len(d1),
        "d2_cells": len(d2),
        "unique_alert_cells": len(active),
        "gtcr60": len(hits) / len(truth_cells),
        "d2_gtcr60": len(d2_hits) / len(truth_cells),
        "any_coverage60": bool(hits),
        "ttfc_min": min(hits) if hits else None,
        "endpoint_hit": truth_cells[-1][1] in active,
        "irrelevant_d2_rate": len(d2 - route_cells) / max(len(d2), 1),
        "top_mass": sum(poa.get(c, 0.0) for c in d2),
        "alert_cells": sorted(active),
    }


def _scenario_record(net, s: TruthScenario) -> dict:
    truth = truth_points_after_report(net.graph, s)
    return {
        "scenario_id": s.scenario_id,
        "stratum": s.stratum,
        "path_length_m": round(s.path_length_m, 1),
        "speed_kmh": s.speed_kmh,
        "missing_before_report_min": s.missing_before_report_min,
        "start": [s.start.lat, s.start.lng],
        "attraction": [s.attraction.lat, s.attraction.lng],
        "destination": [s.destination.lat, s.destination.lng],
        "truth": [
            {"minute": minute, "lat": point.lat, "lng": point.lng,
             "cell": h3grid.cell_of(point)}
            for minute, point in truth
        ],
        "arms": {
            "B": _run_arm(net, s, False, truth),
            "C": _run_arm(net, s, True, truth),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--per-stratum", type=int)
    args = parser.parse_args()
    per_stratum = args.per_stratum or (10 if args.pilot else 40)

    net = OSMnxNetwork.from_graphml(GRAPHML)
    scenarios = build_scenarios(net.graph, per_stratum=per_stratum)
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / ("pilot.jsonl" if args.pilot else "replay.jsonl")
    with out.open("w", encoding="utf-8") as f:
        for idx, scenario in enumerate(scenarios, start=1):
            record = _scenario_record(net, scenario)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            b, c = record["arms"]["B"], record["arms"]["C"]
            print(
                f"[{idx:03d}/{len(scenarios)}] {scenario.scenario_id:14s} "
                f"GTCR B={b['gtcr60']:.3f} C={c['gtcr60']:.3f} "
                f"Δ={c['gtcr60'] - b['gtcr60']:+.3f}"
            )
    print(f"saved={out} strata={STRATA} n={len(scenarios)}")


if __name__ == "__main__":
    main()
