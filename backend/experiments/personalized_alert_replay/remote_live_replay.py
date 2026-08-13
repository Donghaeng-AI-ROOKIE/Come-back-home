"""배포 FastAPI를 통해 실제 EXAONE+mind+도로망 파이프라인을 B/C 비교한다.

클라이언트는 GPU 키를 보유하지 않는다. 정식 배포 경로인
``https://macmini.tail67859f.ts.net:8443``의 FastAPI가 서버 내부 키로
EXAONE를 호출한다.

실행:
    .venv/bin/python -m experiments.personalized_alert_replay.remote_live_replay --pilot

안전:
- 페르소나 이름과 상황에 [실험]/[훈련] 표시.
- 예측 즉시 사건을 withdrawn 종결·삭제하고 페르소나도 privacy API로 파기.
- fallback/stub prior나 도로망 폴백은 정상 결과로 숨기지 않고 런 실패로 기록.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.geo import h3grid
from app.geo.roadnet import OSMnxNetwork
from app.phase3 import alerts
from experiments.personalized_alert_replay.truth_routes import (
    TruthScenario,
    build_scenarios,
    truth_points_after_report,
)

BASE_DEFAULT = "https://macmini.tail67859f.ts.net:8443"
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
GRAPHML = BACKEND / "data/roadnet_cache/walk_37.6061_127.0106_5000.graphml"
OUT_DIR = HERE / "results"
BUDGET_K = 19


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def request(self, method: str, path: str, body=None, timeout: float = 300.0):
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"{method} {path}: HTTP {exc.code} {detail}") from exc


def _persona_payload(s: TruthScenario, personalized: bool) -> dict:
    points = []
    notes = []
    if personalized:
        points = [{
            "label": "[실험] 반복 방문 장소",
            "location": {"lat": s.attraction.lat, "lng": s.attraction.lng},
            "weight": 1.0,
            "precision": "poi",
            "place_type": "market",
            "evidence": "caregiver_report",
            "origin_slot": "routine_destinations",
        }]
        notes = [
            "매주 같은 장소를 반복해 방문한다.",
            "길을 잃으면 멈추기보다 계속 걷는 편이다.",
            "익숙한 큰길이나 시장 방향을 선호한다.",
        ]
    return {
        "name": f"[실험] {s.scenario_id} {'C-개인화' if personalized else 'B-비개인화'}",
        "age": 78,
        "type": "dementia",
        "home": {"lat": s.start.lat, "lng": s.start.lng},
        "attraction_points": points,
        "behavior_notes": notes,
    }


def _top_k_outside(poa: dict[str, float], excluded: set[str], k: int) -> set[str]:
    ranked = sorted(poa.items(), key=lambda item: item[1], reverse=True)
    return set([cell for cell, _ in ranked if cell not in excluded][:k])


def _mean_poa(poas: list[dict[str, float]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for poa in poas:
        for cell, prob in poa.items():
            out[cell] = out.get(cell, 0.0) + prob / len(poas)
    total = sum(out.values()) or 1.0
    return {cell: prob / total for cell, prob in out.items()}


def _evaluate(s: TruthScenario, graph, poa: dict[str, float]) -> dict:
    truth = truth_points_after_report(graph, s)
    truth_cells = [(minute, h3grid.cell_of(point)) for minute, point in truth]
    d1 = set(alerts.select_reflex_cells(s.start, k=2))
    d2 = _top_k_outside(poa, d1, BUDGET_K)
    active = d1 | d2
    hits = [minute for minute, cell in truth_cells if cell in active]
    d2_hits = [minute for minute, cell in truth_cells if cell in d2]
    corridor: set[str] = set()
    for _, point in truth:
        corridor.update(h3grid.cells_within_k(point, 1))
    return {
        "d1_cells": len(d1),
        "d2_cells": len(d2),
        "unique_alert_cells": len(active),
        "gtcr60": len(hits) / len(truth_cells),
        "d2_gtcr60": len(d2_hits) / len(truth_cells),
        "any_coverage60": bool(hits),
        "ttfc_min": min(hits) if hits else None,
        "endpoint_hit": truth_cells[-1][1] in active,
        "irrelevant_d2_rate": len(d2 - corridor) / max(len(d2), 1),
        "poa_support_cells": len(poa),
        "poa_mass_in_d1": sum(poa.get(cell, 0.0) for cell in d1),
        "alert_cells": sorted(active),
    }


def _cleanup(api: Api, persona_id: str | None, case_id: str | None) -> list[str]:
    errors = []
    if case_id:
        try:
            api.request("POST", f"/privacy/cases/{case_id}/close", {"reason": "withdrawn"}, 30)
        except Exception as exc:  # cleanup must continue
            errors.append(f"close:{type(exc).__name__}:{exc}")
        try:
            api.request("DELETE", f"/privacy/cases/{case_id}", timeout=30)
        except Exception as exc:
            errors.append(f"case_delete:{type(exc).__name__}:{exc}")
    if persona_id:
        try:
            api.request("DELETE", f"/privacy/personas/{persona_id}", timeout=30)
        except Exception as exc:
            errors.append(f"persona_delete:{type(exc).__name__}:{exc}")
    return errors


def _run_arm(
    api: Api,
    graph,
    s: TruthScenario,
    personalized: bool,
    seeds: list[int],
    *,
    trace: bool = False,
) -> dict:
    persona_id = case_id = None
    result = None
    started = time.perf_counter()
    try:
        persona = api.request("POST", "/phase0/personas", _persona_payload(s, personalized))
        persona_id = persona["id"]
        # B/C의 lkp_time은 시나리오 시작 직전에 각각 만들지만, 실험 순서를
        # 시나리오마다 반전해 예열/지연 편향을 한 쪽으로 고정하지 않는다.
        # 배포 컨테이너는 UTC이고 LocalNaiveDT는 offset이 있는 입력을 컨테이너
        # 로컬 시각으로 변환한다. KST naive를 보내면 9시간 미래로 해석되어
        # elapsed_hours가 0.05(3분)로 클램프되므로 반드시 offset을 보낸다.
        lkp_time = (datetime.now(timezone.utc) - timedelta(
            minutes=s.missing_before_report_min,
        )).replace(microsecond=0).isoformat()
        case = api.request("POST", "/phase1/reports", {
            "missing_type": "dementia",
            "lkp": {"lat": s.start.lat, "lng": s.start.lng},
            "lkp_time": lkp_time,
            "persona_id": persona_id,
            "situation": "[훈련] EXAONE 개인화 실험. 실제 실종 사건 아님.",
        })
        case_id = case["id"]
        poas = []
        priors = []
        roadnet_flags = []
        trace_summaries = []
        for seed in seeds:
            endpoint = (
                f"/debug/cases/{case_id}/predict?seed={seed}"
                if trace else f"/phase2/cases/{case_id}/predict?seed={seed}"
            )
            response = api.request("POST", endpoint, timeout=300)
            if trace:
                prediction = response["result"]
                events = response.get("mind_events", [])
                source_counts: dict[str, int] = {}
                for event in events:
                    source = event.get("source", "unknown")
                    source_counts[source] = source_counts.get(source, 0) + 1
                trace_summaries.append({
                    "mind_events": len(events),
                    "mind_source_counts": source_counts,
                    "exaone_stub": response.get("exaone_stub"),
                    "timings": response.get("timings", {}),
                })
            else:
                prediction = response
            state = api.request("GET", f"/phase1/cases/{case_id}", timeout=30)
            priors.append(prediction["prior"])
            poas.append(prediction["poa_combined"]["cells"])
            roadnet_flags.append(bool(state.get("roadnet_used")))
        sources = [p.get("source") for p in priors]
        valid = all(source == "exaone" for source in sources) and all(roadnet_flags)
        mean_poa = _mean_poa(poas)
        server_lkp = datetime.fromisoformat(state["lkp_time"])
        server_sim = datetime.fromisoformat(state["last_sim_at"])
        result = {
            "valid": valid,
            "arm": "C_personalized" if personalized else "B_nonpersonalized",
            "prior_sources": sources,
            "fallback_reasons": [p.get("fallback_reason", "") for p in priors],
            "roadnet_used": roadnet_flags,
            "priors": priors,
            "trace_summaries": trace_summaries,
            "server_elapsed_hours": round(
                (server_sim - server_lkp).total_seconds() / 3600.0, 4
            ),
            "poa_mean": mean_poa,
            "metrics": _evaluate(s, graph, mean_poa),
            "elapsed_sec": round(time.perf_counter() - started, 2),
            "cleanup_errors": [],
        }
        return result
    finally:
        cleanup_errors = _cleanup(api, persona_id, case_id)
        if result is not None:
            result["cleanup_errors"] = cleanup_errors
        if cleanup_errors:
            print(f"[cleanup-warning] {s.scenario_id} {cleanup_errors}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=BASE_DEFAULT)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--per-stratum", type=int)
    parser.add_argument("--repeats", type=int)
    parser.add_argument("--scenario", help="특정 scenario_id만 재실행")
    parser.add_argument("--arms", default="BC", choices=("B", "C", "BC"))
    parser.add_argument("--trace", action="store_true", help="debug trace로 mind 실호출 확인")
    args = parser.parse_args()
    per_stratum = args.per_stratum or (2 if args.pilot else 10)
    repeats = args.repeats or (2 if args.pilot else 3)
    seeds = list(range(42, 42 + repeats))

    api = Api(args.base)
    root = api.request("GET", "/", timeout=10)
    if root.get("service") != "돌아오길 backend":
        raise SystemExit(f"잘못된 백엔드: {root}")

    net = OSMnxNetwork.from_graphml(GRAPHML)
    scenarios = build_scenarios(net.graph, per_stratum=per_stratum, fixed_start=True)
    if args.scenario:
        scenarios = [s for s in scenarios if s.scenario_id == args.scenario]
        if not scenarios:
            raise SystemExit(f"시나리오 없음: {args.scenario}")
    OUT_DIR.mkdir(exist_ok=True)
    if args.trace:
        out = OUT_DIR / f"remote_trace_{args.scenario or 'all'}.jsonl"
    elif args.scenario:
        out = OUT_DIR / f"remote_live_{args.scenario}.jsonl"
    else:
        out = OUT_DIR / ("remote_live_pilot.jsonl" if args.pilot else "remote_live.jsonl")
    with out.open("w", encoding="utf-8") as handle:
        for idx, scenario in enumerate(scenarios):
            arm_order = [(False, "B"), (True, "C")] if idx % 2 == 0 else [(True, "C"), (False, "B")]
            arm_order = [item for item in arm_order if item[1] in args.arms]
            arms = {}
            for personalized, label in arm_order:
                print(f"[{idx + 1:02d}/{len(scenarios)}] {scenario.scenario_id} {label} start")
                arms[label] = _run_arm(
                    api, net.graph, scenario, personalized, seeds, trace=args.trace,
                )
                m = arms[label]["metrics"]
                print(
                    f"[{idx + 1:02d}/{len(scenarios)}] {scenario.scenario_id} {label} "
                    f"source={arms[label]['prior_sources']} roadnet={arms[label]['roadnet_used']} "
                    f"D2_GTCR={m['d2_gtcr60']:.3f} sec={arms[label]['elapsed_sec']:.1f}"
                )
            record = {
                "scenario_id": scenario.scenario_id,
                "stratum": scenario.stratum,
                "path_length_m": round(scenario.path_length_m, 1),
                "speed_kmh": scenario.speed_kmh,
                "missing_before_report_min": scenario.missing_before_report_min,
                "start": [scenario.start.lat, scenario.start.lng],
                "attraction": [scenario.attraction.lat, scenario.attraction.lng],
                "destination": [scenario.destination.lat, scenario.destination.lng],
                "seeds": seeds,
                "arms": arms,
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
    print(f"saved={out} n={len(scenarios)} repeats={repeats}")


if __name__ == "__main__":
    main()
