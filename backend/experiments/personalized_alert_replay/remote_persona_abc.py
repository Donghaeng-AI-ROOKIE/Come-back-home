"""Mi:dm 온보딩으로 저장한 12슬롯 Persona를 EXAONE E2E 예측에 사용하는 A/B/C 실험.

A: EXAONE 없이 LKP에서 가까운 D2 19셀
B: 나이·유형·집만 있는 비개인화 EXAONE+MC
C: Mi:dm이 온보딩에서 12슬롯을 추출해 저장한 원본 Persona+EXAONE+MC

세 군 모두 D1 19셀 + D2 19셀 = 38셀을 쓴다. 정답 궤적은 Phase 2
전략·게이지·몬테카를로를 재사용하지 않고 OSM 최단경로로만 만든다.

배포 API는 신고 접수 시 D1 로직을 타지만, 이 스크립트는 Phase 3
POA 알림 엔드포인트를 호출하지 않고 각 실험 사건을 즉시 철회·파기한다.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
import urllib.error
import urllib.request
import socket
from datetime import datetime, timedelta, timezone
from itertools import pairwise
from pathlib import Path

import networkx as nx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.geo import h3grid
from app.geo.roadnet import OSMnxNetwork
from app.schemas.common import GeoPoint
from experiments.personalized_alert_replay.build_persona_bank import load_profiles
from experiments.personalized_alert_replay.truth_routes import (
    TruthScenario,
    behavior_truth_distance_m,
    temporal_truth_point,
    truth_points_after_report,
)

BASE_DEFAULT = "https://macmini.tail67859f.ts.net:8443"
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
GRAPHML = BACKEND / "data/roadnet_cache/walk_37.6061_127.0106_5000.graphml"
MANIFEST = HERE / "persona_bank_manifest.json"
OUT_DIR = HERE / "results"
BUDGET_K = 19
STRATA = ("consistent", "neutral", "counter")

# 대본의 이동능력 수준은 정답 방향이 아니라 신체적으로 가능한 경로 길이와
# 속도 상한만 제어한다. 방향은 독립적으로 일관/중립/반대를 배정한다.
MOBILITY_BANDS = {
    0.1: (250.0, 500.0, 1.5),
    0.3: (450.0, 900.0, 2.0),
    0.5: (700.0, 1400.0, 2.5),
    0.7: (1000.0, 2000.0, 3.0),
    0.9: (1400.0, 2600.0, 3.5),
}
TARGET_ANGLES = {"consistent": 0.0, "neutral": math.pi / 2, "counter": math.pi}


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def request(self, method: str, path: str, body=None, timeout: float = 300.0):
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        attempts = 3 if method in {"GET", "DELETE"} else 1
        for attempt in range(attempts):
            request = urllib.request.Request(
                self.base + path,
                data=data,
                method=method,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    raw = response.read().decode("utf-8")
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                retryable = exc.code in {502, 503, 504} and attempt + 1 < attempts
                if not retryable:
                    raise RuntimeError(
                        f"{method} {path}: HTTP {exc.code} {detail}"
                    ) from exc
            except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
                if attempt + 1 >= attempts:
                    raise RuntimeError(f"{method} {path}: {exc}") from exc
            time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"{method} {path}: retry exhausted")


def _mean_poa(poas: list[dict[str, float]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for poa in poas:
        for cell, probability in poa.items():
            out[cell] = out.get(cell, 0.0) + probability / len(poas)
    total = sum(out.values()) or 1.0
    return {cell: probability / total for cell, probability in out.items()}


def _bearing(a: GeoPoint, b: GeoPoint) -> float:
    dlat = b.lat - a.lat
    dlng = (b.lng - a.lng) * math.cos(math.radians(a.lat))
    return math.atan2(dlng, dlat)


def _angle_diff(a: float, b: float) -> float:
    return abs((a - b + math.pi) % (2 * math.pi) - math.pi)


def _loc(graph, node) -> GeoPoint:
    data = graph.nodes[node]
    return GeoPoint(lat=float(data["y"]), lng=float(data["x"]))


def _edge_length_m(graph, u, v) -> float:
    data = graph.get_edge_data(u, v)
    if not data:
        return 30.0
    return float(data[next(iter(data))].get("length", 30.0))


def _manifest() -> dict[str, str]:
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {row["profile_id"]: row["persona_id"] for row in raw["personas"]}


def _home_anchors(path: str) -> tuple[str, dict[str, dict]]:
    if not path:
        return "persona_saved_home", {}
    anchor_path = Path(path).expanduser().resolve()
    raw = json.loads(anchor_path.read_text(encoding="utf-8"))
    return raw.get("provider", "unknown"), {
        row["profile_id"]: row for row in raw["homes"]
    }


def _primary_reference(persona: dict) -> tuple[GeoPoint, str]:
    home = GeoPoint.model_validate(persona["home"])
    points = persona.get("attraction_points", [])
    if points:
        # evidence weight가 같으면 온보딩에서 먼저 추출된 장소를 고정 사용.
        best = max(enumerate(points), key=lambda item: (item[1].get("weight", 0), -item[0]))[1]
        return GeoPoint.model_validate(best["location"]), f"persona:{best['label']}"
    # 장소가 추출되지 않은 SP04도 버리지 않고 음성 대조군으로 남긴다.
    # 이 기준방향은 C군에 전달되지 않으므로 개인화에 유리한 정보 누출이 아니다.
    return h3grid.move(home, math.pi / 4, 1.0), "fallback:no_extracted_attraction"


def build_persona_scenarios(
    graph,
    profile_id: str,
    persona: dict,
    mobility: float,
    behavior: str = "move",
) -> list[tuple[TruthScenario, dict]]:
    home = GeoPoint.model_validate(persona["home"])
    reference, reference_source = _primary_reference(persona)
    start = min(graph.nodes, key=lambda node: h3grid.haversine_km(home, _loc(graph, node)))
    start_point = _loc(graph, start)
    ref_bearing = _bearing(start_point, reference)
    low_m, high_m, speed = MOBILITY_BANDS[mobility]
    lengths = nx.single_source_dijkstra_path_length(graph, start, cutoff=high_m, weight="length")
    candidates = [(node, meters) for node, meters in lengths.items() if low_m <= meters <= high_m]
    if not candidates:
        raise RuntimeError(f"{profile_id}: mobility={mobility} 경로 후보 없음")

    rng = random.Random(f"persona-abc-{profile_id}")
    rng.shuffle(candidates)
    out = []
    used = set()
    midpoint = (low_m + high_m) / 2
    for stratum in STRATA:
        target = TARGET_ANGLES[stratum]
        ranked = sorted(
            candidates,
            key=lambda item: (
                abs(_angle_diff(ref_bearing, _bearing(start_point, _loc(graph, item[0]))) - target),
                abs(item[1] - midpoint),
            ),
        )
        if behavior == "hide":
            # 은폐형 정답은 EXAONE 출력과 무관하게 OSM 연결 차수가 낮은
            # 후보를 우선한다. 방향층과 이동 밴드 조건은 그대로 유지한다.
            shortlist = [item for item in ranked if item[0] not in used][:40]
            destination, _ = min(
                shortlist,
                key=lambda item: (graph.degree(item[0]), ranked.index(item)),
            )
        else:
            destination, _ = next(item for item in ranked if item[0] not in used)
        used.add(destination)
        path = nx.shortest_path(graph, start, destination, weight="length")
        path_m = sum(_edge_length_m(graph, u, v) for u, v in pairwise(path))
        dest_point = _loc(graph, destination)
        actual_diff = math.degrees(_angle_diff(ref_bearing, _bearing(start_point, dest_point)))
        scenario = TruthScenario(
            scenario_id=f"{profile_id}-{stratum}",
            stratum=stratum,
            start_node=start,
            attraction_node=start,
            destination_node=destination,
            start=start_point,
            attraction=reference,
            destination=dest_point,
            path_nodes=tuple(path),
            path_length_m=path_m,
            speed_kmh=speed,
            missing_before_report_min=30,
        )
        out.append((scenario, {
            "reference_source": reference_source,
            "reference": reference.model_dump(),
            "actual_angle_diff_deg": round(actual_diff, 1),
            "mobility_target": mobility,
            "mobility_band_m": [low_m, high_m],
            "truth_behavior": behavior,
            "truth_generation": {
                "stay": "early_progress_then_dwell",
                "move": "continuous_progress",
                "backtrack": "out_and_return_same_osm_path",
                "hide": "move_pause_resume_then_low_degree_hide",
            }[behavior],
        }))
    return out


def _nearest_d2(start: GeoPoint) -> set[str]:
    d1 = set(h3grid.cells_within_k(start, 2))
    pool = set(h3grid.cells_within_k(start, 5)) - d1
    ranked = sorted(
        pool,
        key=lambda cell: (h3grid.haversine_km(start, h3grid.cell_center(cell)), cell),
    )
    return set(ranked[:BUDGET_K])


def _evaluate_cells(scenario: TruthScenario, graph, d2: set[str], *, poa: dict[str, float] | None = None) -> dict:
    truth = truth_points_after_report(graph, scenario)
    truth_cells = [(minute, h3grid.cell_of(point)) for minute, point in truth]
    d1 = set(h3grid.cells_within_k(scenario.start, 2))
    active = d1 | d2
    hits = [minute for minute, cell in truth_cells if cell in active]
    d2_hits = [minute for minute, cell in truth_cells if cell in d2]
    outside_d1 = [(minute, cell) for minute, cell in truth_cells if cell not in d1]
    d2_outside_hits = [minute for minute, cell in outside_d1 if cell in d2]
    corridor: set[str] = set()
    for _, point in truth:
        corridor.update(h3grid.cells_within_k(point, 1))
    return {
        "d1_cells": len(d1),
        "d2_cells": len(d2),
        "unique_alert_cells": len(active),
        "gtcr60": len(hits) / len(truth_cells),
        "d2_gtcr60": len(d2_hits) / len(truth_cells),
        # D1이 이미 덮는 저이동성 케이스의 천장효과를 제거한 핵심 지표.
        # 분모가 0이면 개인화 D2가 필요 없던 시나리오라 None으로 남긴다.
        "outside_d1_truth_steps": len(outside_d1),
        "d2_gtcr_outside_d1": (
            len(d2_outside_hits) / len(outside_d1) if outside_d1 else None
        ),
        "incremental_any_coverage": bool(d2_outside_hits),
        "any_coverage60": bool(hits),
        "ttfc_min": min(hits) if hits else None,
        "endpoint_hit": truth_cells[-1][1] in active,
        "irrelevant_d2_rate": len(d2 - corridor) / max(len(d2), 1),
        "poa_support_cells": len(poa or {}),
        "poa_mass_in_d1": sum((poa or {}).get(cell, 0.0) for cell in d1),
        "alert_cells": sorted(active),
    }


def _select_poa_d2(poa: dict[str, float], d1: set[str]) -> set[str]:
    return set([cell for cell, _ in sorted(poa.items(), key=lambda item: item[1], reverse=True)
                if cell not in d1][:BUDGET_K])


def _evaluate_temporal(
    graph,
    scenario: TruthScenario,
    surfaces: list[tuple[int, float, dict[str, float]]],
    behavior: str = "move",
) -> dict:
    """t분 POA의 알림셀을 바로 그 t분 정답 위치와 1:1 매칭."""
    d1 = set(h3grid.cells_within_k(scenario.start, 2))
    previous_d2: set[str] | None = None
    union_cells = set(d1)
    snapshots = []
    final_minute = max((minute for minute, _, _ in surfaces), default=0)
    for minute, elapsed_hours, poa in surfaces:
        truth = temporal_truth_point(
            graph,
            scenario,
            minute_after_report=minute,
            final_minute_after_report=final_minute,
            behavior=behavior,
        )
        truth_cell = h3grid.cell_of(truth)
        d2 = _select_poa_d2(poa, d1)
        active = d1 | d2
        overlap = None
        if previous_d2 is not None:
            overlap = len(previous_d2 & d2) / max(len(previous_d2 | d2), 1)
        snapshots.append({
            "minute_after_report": minute,
            "elapsed_hours_since_missing": elapsed_hours,
            "truth": truth.model_dump(),
            "truth_cell": truth_cell,
            "truth_probability": poa.get(truth_cell, 0.0),
            "truth_outside_d1": truth_cell not in d1,
            "hit": truth_cell in active,
            "d2_hit": truth_cell in d2,
            "d2_jaccard_vs_previous": overlap,
            "d1_cells": sorted(d1),
            "d2_cells": sorted(d2),
            "surface_cells": poa,
        })
        union_cells.update(d2)
        previous_d2 = d2
    outside = [item for item in snapshots if item["truth_outside_d1"]]
    hits = [item for item in snapshots if item["hit"]]
    d2_hits = [item for item in outside if item["d2_hit"]]
    jaccards = [item["d2_jaccard_vs_previous"] for item in snapshots
                if item["d2_jaccard_vs_previous"] is not None]
    return {
        "time_matched_hit_rate": len(hits) / max(len(snapshots), 1),
        "time_matched_d2_hit_rate_outside_d1": (
            len(d2_hits) / len(outside) if outside else None
        ),
        "outside_d1_steps": len(outside),
        "first_hit_min": min((item["minute_after_report"] for item in hits), default=None),
        "mean_truth_probability": (
            sum(item["truth_probability"] for item in snapshots) / max(len(snapshots), 1)
        ),
        "mean_d2_jaccard_vs_previous": (
            sum(jaccards) / len(jaccards) if jaccards else None
        ),
        "unique_alert_cells_over_time": len(union_cells),
        "snapshots": snapshots,
    }


def _fetch_temporal_surfaces(
    api: Api,
    case_id: str,
    scenario: TruthScenario,
    minutes: list[int],
) -> tuple[list[tuple[int, float, dict[str, float]]], list[str]]:
    surfaces = []
    sources = []
    for minute in minutes:
        elapsed = round((scenario.missing_before_report_min + minute) / 60.0, 6)
        response = api.request(
            "GET",
            f"/phase3/cases/{case_id}/poa?top=2000&elapsed_hours={elapsed:g}",
            timeout=300,
        )
        cells = {item["cell"]: float(item["prob"]) for item in response["top_cells"]}
        if len(cells) != response["total_cells"]:
            raise RuntimeError(
                f"시간 POA 잘림: {len(cells)}/{response['total_cells']} cells"
            )
        surfaces.append((minute, elapsed, cells))
        sources.append(response.get("prior_source", "unknown"))
    return surfaces, sources


def _close_case(api: Api, case_id: str | None) -> list[str]:
    if not case_id:
        return []
    errors = []
    for method, path, body in (
        ("POST", f"/privacy/cases/{case_id}/close", {"reason": "withdrawn"}),
        ("DELETE", f"/privacy/cases/{case_id}", None),
    ):
        try:
            api.request(method, path, body, 30)
        except Exception as exc:  # noqa: BLE001 -- 파기는 다음 단계까지 계속해야 함
            errors.append(f"{method}:{type(exc).__name__}:{exc}")
    return errors


def _delete_persona(api: Api, persona_id: str | None) -> list[str]:
    if not persona_id:
        return []
    try:
        api.request("DELETE", f"/privacy/personas/{persona_id}", timeout=30)
        return []
    except Exception as exc:  # noqa: BLE001 -- 사건 파기 오류와 함께 기록
        return [f"persona_delete:{type(exc).__name__}:{exc}"]


def _run_ai_arm(api: Api, graph, scenario: TruthScenario, persona: dict, persona_id: str,
                arm: str, seeds: list[int], temporal_minutes: list[int],
                truth_behavior: str = "move") -> dict:
    case_id = temp_persona_id = None
    started = time.perf_counter()
    result = None
    try:
        if arm == "B":
            created = api.request("POST", "/phase0/personas", {
                "name": f"[합성실험] {persona['name']} B",
                "age": persona["age"],
                "type": "dementia",
                "home": persona["home"],
                "attraction_points": [],
                "behavior_notes": [],
            })
            active_persona_id = temp_persona_id = created["id"]
        else:
            active_persona_id = persona_id

        lkp_time = (datetime.now(timezone.utc) - timedelta(
            minutes=scenario.missing_before_report_min,
        )).replace(microsecond=0).isoformat()
        case = api.request("POST", "/phase1/reports", {
            "missing_type": "dementia",
            "lkp": scenario.start.model_dump(),
            "lkp_time": lkp_time,
            "persona_id": active_persona_id,
            "situation": "[합성실험/즉시철회] 실제 실종 사건이 아님.",
        })
        case_id = case["id"]
        poas, sources, roadnet_flags, priors = [], [], [], []
        for seed in seeds:
            prediction = api.request("POST", f"/phase2/cases/{case_id}/predict?seed={seed}", timeout=300)
            state = api.request("GET", f"/phase1/cases/{case_id}", timeout=30)
            prior = prediction["prior"]
            priors.append(prior)
            sources.append(prior.get("source"))
            roadnet_flags.append(bool(state.get("roadnet_used")))
            poas.append(prediction["poa_combined"]["cells"])
        mean_poa = _mean_poa(poas)
        d1 = set(h3grid.cells_within_k(scenario.start, 2))
        d2 = _select_poa_d2(mean_poa, d1)
        scored = api.request("GET", f"/phase0/personas/{active_persona_id}", timeout=30)
        temporal = None
        temporal_sources: list[str] = []
        if temporal_minutes:
            temporal_surfaces, temporal_sources = _fetch_temporal_surfaces(
                api, case_id, scenario, temporal_minutes,
            )
            temporal = _evaluate_temporal(
                graph, scenario, temporal_surfaces, behavior=truth_behavior,
            )
        result = {
            "valid": (
                all(source == "exaone" for source in sources + temporal_sources)
                and all(roadnet_flags)
            ),
            "arm": "B_exaone_generic" if arm == "B" else "C_exaone_personalized",
            "prior_sources": sources,
            "fallback_reasons": [prior.get("fallback_reason", "") for prior in priors],
            "prior_summaries": [{
                "strategy_probs": prior.get("strategy_probs", {}),
                "attraction_weights": prior.get("attraction_weights", {}),
                "radius_lognormal": prior.get("radius_lognormal", {}),
                "reasoning": prior.get("reasoning", ""),
            } for prior in priors],
            "roadnet_used": roadnet_flags,
            "persona_input": {
                "attraction_points": len(scored.get("attraction_points", [])),
                "behavior_notes": len(scored.get("behavior_notes", [])),
                "axis_evidence_fields": len(scored.get("axis_evidence", {})),
                "completed_tiers": scored.get("completed_tiers", []),
            },
            "axis_scores": scored.get("axis_scores", {}),
            "behavior_tendency": scored.get("behavior_tendency"),
            "surface_cells": mean_poa,
            "metrics": _evaluate_cells(scenario, graph, d2, poa=mean_poa),
            "temporal": temporal,
            "elapsed_sec": round(time.perf_counter() - started, 2),
            "cleanup_errors": [],
        }
        return result
    finally:
        errors = _close_case(api, case_id) + _delete_persona(api, temp_persona_id)
        if result is not None:
            result["cleanup_errors"] = errors
        if errors:
            print(f"[cleanup-warning] {scenario.scenario_id} {arm} {errors}", flush=True)


def _run_a(
    graph,
    scenario: TruthScenario,
    temporal_minutes: list[int] | None = None,
    truth_behavior: str = "move",
) -> dict:
    temporal_minutes = temporal_minutes or []
    d2 = _nearest_d2(scenario.start)
    d1 = set(h3grid.cells_within_k(scenario.start, 2))
    raw = {
        cell: math.exp(-h3grid.haversine_km(scenario.start, h3grid.cell_center(cell)) / 0.35)
        for cell in d1 | d2
    }
    total = sum(raw.values()) or 1.0
    surface = {cell: value / total for cell, value in raw.items()}
    temporal = None
    if temporal_minutes:
        temporal = _evaluate_temporal(
            graph,
            scenario,
            [
                (
                    minute,
                    round((scenario.missing_before_report_min + minute) / 60.0, 6),
                    surface,
                )
                for minute in temporal_minutes
            ],
            behavior=truth_behavior,
        )
    return {
        "valid": True,
        "arm": "A_distance_only",
        "surface_cells": surface,
        "metrics": _evaluate_cells(scenario, graph, d2),
        "temporal": temporal,
        "elapsed_sec": 0.0,
        "cleanup_errors": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=BASE_DEFAULT)
    parser.add_argument("--profiles", default="", help="쉼표 구분 SP01,SP02")
    parser.add_argument(
        "--scenarios", default="",
        help="쉼표 구분 정확한 scenario_id; 비우면 profiles×strata 전부",
    )
    parser.add_argument("--strata", default=",".join(STRATA), help="consistent,neutral,counter")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--temporal-minutes", default="",
        help="신고 후 시간매칭 POA 분 목록(예: 0,15,30,45,60). 사용 시 repeats=1",
    )
    parser.add_argument("--out", default="persona_abc.jsonl")
    parser.add_argument(
        "--resume", action="store_true",
        help="기존 JSONL의 scenario_id는 건너뛰고 성공 행을 append",
    )
    parser.add_argument(
        "--design-only", action="store_true",
        help="원격 페르소나는 GET만 하고 신고·예측 없이 정답궤적+A군만 생성",
    )
    parser.add_argument(
        "--home-anchors", default="",
        help="resolve_home_anchors가 만든 Kakao/OSM 시작좌표 JSON",
    )
    parser.add_argument(
        "--patch-persona-homes", action="store_true",
        help="합성 운영 Persona의 오지오코딩 home을 anchor로 교정",
    )
    parser.add_argument(
        "--behavior-aware-truth", action="store_true",
        help="프로필의 stay/move/backtrack/hide 유형에 맞춘 독립 시간축 정답 사용",
    )
    args = parser.parse_args()

    try:
        temporal_minutes = sorted({
            int(item.strip()) for item in args.temporal_minutes.split(",") if item.strip()
        })
    except ValueError as exc:
        raise SystemExit("--temporal-minutes는 음이 아닌 정수 목록이어야 합니다.") from exc
    if any(minute < 0 for minute in temporal_minutes):
        raise SystemExit("--temporal-minutes는 0 이상이어야 합니다.")
    if temporal_minutes and args.repeats != 1:
        raise SystemExit("시간매칭 실험은 prior를 하나로 고정하기 위해 --repeats 1이 필수입니다.")

    selected = {item.strip() for item in args.profiles.split(",") if item.strip()}
    selected_scenarios = {item.strip() for item in args.scenarios.split(",") if item.strip()}
    strata = {item.strip() for item in args.strata.split(",") if item.strip()}
    if not strata <= set(STRATA):
        raise SystemExit(f"알 수 없는 strata: {sorted(strata - set(STRATA))}")
    manifest = _manifest()
    home_provider, home_anchors = _home_anchors(args.home_anchors)
    if home_anchors and not args.patch_persona_homes:
        raise SystemExit(
            "--home-anchors를 C군에도 적용하려면 --patch-persona-homes가 필요합니다."
        )
    profiles = [profile for profile in load_profiles() if not selected or profile.profile_id in selected]
    if selected - {profile.profile_id for profile in profiles}:
        raise SystemExit(f"없는 profiles: {sorted(selected - {p.profile_id for p in profiles})}")

    api = Api(args.base)
    root = api.request("GET", "/", timeout=10)
    if root.get("service") != "돌아오길 backend":
        raise SystemExit(f"잘못된 백엔드: {root}")
    net = OSMnxNetwork.from_graphml(GRAPHML)
    seeds = list(range(42, 42 + args.repeats))
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / args.out
    existing_rows = []
    if args.resume and out.exists():
        existing_rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()
                         if line.strip()]
    existing_ids = {row["scenario_id"] for row in existing_rows}
    completed = len(existing_rows)
    mode = "a" if args.resume else "w"
    with out.open(mode, encoding="utf-8") as handle:
        for profile in profiles:
            persona_id = manifest[profile.profile_id]
            persona = api.request("GET", f"/phase0/personas/{persona_id}", timeout=30)
            home_meta = home_anchors.get(profile.profile_id)
            if home_meta:
                corrected_home = home_meta["home"]
                if persona["home"] != corrected_home:
                    persona = api.request(
                        "PATCH", f"/phase0/personas/{persona_id}",
                        {"home": corrected_home}, 30,
                    )
            scenarios = build_persona_scenarios(
                net.graph, profile.profile_id, persona,
                profile.target_levels["mobility_transport_capacity"],
                profile.expected_behavior_tendency if args.behavior_aware_truth else "move",
            )
            for scenario, design in scenarios:
                if scenario.stratum not in strata:
                    continue
                if selected_scenarios and scenario.scenario_id not in selected_scenarios:
                    continue
                if scenario.scenario_id in existing_ids:
                    print(f"[{scenario.scenario_id}] resume skip", flush=True)
                    continue
                if temporal_minutes:
                    truth_behavior = (
                        profile.expected_behavior_tendency
                        if args.behavior_aware_truth else "move"
                    )
                    design = {
                        **design,
                        "temporal_truth_retimed": True,
                        "temporal_path_length_m": round(scenario.path_length_m, 1),
                        "truth_travel_distance_m": round(
                            behavior_truth_distance_m(scenario, truth_behavior), 1,
                        ),
                        "temporal_minutes": temporal_minutes,
                    }
                else:
                    truth_behavior = "move"
                print(f"[{profile.profile_id}] {scenario.stratum} A/B/C start", flush=True)
                arms = {"A": _run_a(
                    net.graph, scenario, temporal_minutes, truth_behavior,
                )}
                if not args.design_only:
                    # 예열 편향을 한 군에 고정하지 않도록 시나리오마다 순서를 반전.
                    order = ("B", "C") if completed % 2 == 0 else ("C", "B")
                    for arm in order:
                        arms[arm] = _run_ai_arm(
                            api, net.graph, scenario, persona, persona_id, arm, seeds,
                            temporal_minutes, truth_behavior,
                        )
                        metrics = arms[arm]["metrics"]
                        print(
                            f"  {arm} valid={arms[arm]['valid']} "
                            f"D2_GTCR={metrics['d2_gtcr60']:.3f} sec={arms[arm]['elapsed_sec']:.1f}",
                            flush=True,
                        )
                        if arms[arm]["temporal"]:
                            temporal = arms[arm]["temporal"]
                            print(
                                f"    temporal_hit={temporal['time_matched_hit_rate']:.3f} "
                                f"temporal_D2={temporal['time_matched_d2_hit_rate_outside_d1']}",
                                flush=True,
                            )
                truth_samples = (
                    [
                        {
                            "minute": minute,
                            **temporal_truth_point(
                                net.graph,
                                scenario,
                                minute_after_report=minute,
                                final_minute_after_report=max(temporal_minutes),
                                behavior=truth_behavior,
                            ).model_dump(),
                        }
                        for minute in range(0, max(temporal_minutes) + 1, 5)
                    ]
                    if temporal_minutes else [
                        {"minute": minute, **point.model_dump()}
                        for minute, point in truth_points_after_report(net.graph, scenario)
                    ]
                )
                record = {
                    "profile_id": profile.profile_id,
                    "profile_name": profile.synthetic_name,
                    "behavior_archetype": profile.behavior_archetype,
                    "truth_behavior": truth_behavior,
                    "persona_id": persona_id,
                    "scenario_id": scenario.scenario_id,
                    "stratum": scenario.stratum,
                    "path_length_m": round(scenario.path_length_m, 1),
                    "speed_kmh": scenario.speed_kmh,
                    "missing_before_report_min": scenario.missing_before_report_min,
                    "start": scenario.start.model_dump(),
                    "destination": (
                        truth_samples[-1] if truth_samples else scenario.destination.model_dump()
                    ),
                    "truth_path": [_loc(net.graph, node).model_dump()
                                   for node in scenario.path_nodes],
                    "truth_samples": truth_samples,
                    "design": {
                        **design,
                        "home_provider": home_provider,
                        "home_match": home_meta.get("matched") if home_meta else None,
                    },
                    "seeds": seeds,
                    "arms": arms,
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                completed += 1
    print(f"saved={out} scenarios={completed} repeats={args.repeats}", flush=True)


if __name__ == "__main__":
    main()
