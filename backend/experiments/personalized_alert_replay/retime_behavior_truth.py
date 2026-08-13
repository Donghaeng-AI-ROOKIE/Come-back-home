"""기존 EXAONE 확률지도를 유지하고 독립 정답 시간규칙만 다시 매칭한다.

정답경로는 예측 입력이 아니므로 행동 시간규칙을 바꿀 때 GPU 추론을
반복할 필요가 없다. 원본 JSONL을 보존한 채 새 파일을 만들고, 해당 행동
유형의 truth_samples와 A/B/C temporal 적중지표만 재계산한다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.geo import h3grid
from app.geo.roadnet import OSMnxNetwork
from app.schemas.common import GeoPoint
from experiments.personalized_alert_replay.render_persona_abc_report import GRAPHML, RESULTS
from experiments.personalized_alert_replay.truth_routes import (
    TruthScenario,
    behavior_truth_distance_m,
    temporal_truth_point,
)


def _node_index(graph) -> dict[tuple[float, float], object]:
    return {
        (round(float(data["y"]), 7), round(float(data["x"]), 7)): node
        for node, data in graph.nodes(data=True)
    }


def _path_nodes(graph, index: dict, path: list[dict]) -> tuple:
    nodes = []
    for raw in path:
        key = (round(raw["lat"], 7), round(raw["lng"], 7))
        node = index.get(key)
        if node is None:
            point = GeoPoint.model_validate(raw)
            node = min(
                graph.nodes,
                key=lambda candidate: h3grid.haversine_km(
                    point,
                    GeoPoint(
                        lat=float(graph.nodes[candidate]["y"]),
                        lng=float(graph.nodes[candidate]["x"]),
                    ),
                ),
            )
        if not nodes or nodes[-1] != node:
            nodes.append(node)
    return tuple(nodes)


def _scenario(row: dict, graph, index: dict) -> TruthScenario:
    nodes = _path_nodes(graph, index, row["truth_path"])
    start = GeoPoint.model_validate(row["start"])
    destination = GeoPoint.model_validate(row["truth_path"][-1])
    return TruthScenario(
        scenario_id=row["scenario_id"],
        stratum=row["stratum"],
        start_node=nodes[0],
        attraction_node=nodes[0],
        destination_node=nodes[-1],
        start=start,
        attraction=start,
        destination=destination,
        path_nodes=nodes,
        path_length_m=float(row["path_length_m"]),
        speed_kmh=float(row["speed_kmh"]),
        missing_before_report_min=int(row["missing_before_report_min"]),
    )


def _retime_temporal(temporal: dict, scenario: TruthScenario, graph, behavior: str) -> None:
    snapshots = temporal["snapshots"]
    final_minute = max(item["minute_after_report"] for item in snapshots)
    for snapshot in snapshots:
        truth = temporal_truth_point(
            graph,
            scenario,
            minute_after_report=snapshot["minute_after_report"],
            final_minute_after_report=final_minute,
            behavior=behavior,
        )
        truth_cell = h3grid.cell_of(truth)
        d1 = set(snapshot["d1_cells"])
        d2 = set(snapshot["d2_cells"])
        snapshot.update({
            "truth": truth.model_dump(),
            "truth_cell": truth_cell,
            "truth_probability": snapshot["surface_cells"].get(truth_cell, 0.0),
            "truth_outside_d1": truth_cell not in d1,
            "hit": truth_cell in d1 | d2,
            "d2_hit": truth_cell in d2,
        })

    outside = [item for item in snapshots if item["truth_outside_d1"]]
    hits = [item for item in snapshots if item["hit"]]
    d2_hits = [item for item in outside if item["d2_hit"]]
    jaccards = [
        item["d2_jaccard_vs_previous"] for item in snapshots
        if item["d2_jaccard_vs_previous"] is not None
    ]
    all_cells = {
        cell for item in snapshots for cell in (*item["d1_cells"], *item["d2_cells"])
    }
    temporal.update({
        "time_matched_hit_rate": len(hits) / len(snapshots),
        "time_matched_d2_hit_rate_outside_d1": (
            len(d2_hits) / len(outside) if outside else None
        ),
        "outside_d1_steps": len(outside),
        "first_hit_min": min((item["minute_after_report"] for item in hits), default=None),
        "mean_truth_probability": sum(
            item["truth_probability"] for item in snapshots
        ) / len(snapshots),
        "mean_d2_jaccard_vs_previous": sum(jaccards) / len(jaccards) if jaccards else None,
        "unique_alert_cells_over_time": len(all_cells),
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--behavior", default="hide")
    args = parser.parse_args()

    graph = OSMnxNetwork.from_graphml(GRAPHML).graph
    index = _node_index(graph)
    rows = [
        json.loads(line) for line in (RESULTS / args.input).read_text(encoding="utf-8").splitlines()
        if line
    ]
    changed = 0
    for row in rows:
        if row["truth_behavior"] != args.behavior:
            continue
        scenario = _scenario(row, graph, index)
        final_minute = max(
            item["minute_after_report"]
            for item in row["arms"]["A"]["temporal"]["snapshots"]
        )
        row["truth_samples"] = [
            {
                "minute": minute,
                **temporal_truth_point(
                    graph,
                    scenario,
                    minute_after_report=minute,
                    final_minute_after_report=final_minute,
                    behavior=args.behavior,
                ).model_dump(),
            }
            for minute in range(0, final_minute + 1, 5)
        ]
        row["destination"] = row["truth_samples"][-1]
        row["design"].update({
            "truth_generation": "move_pause_resume_then_low_degree_hide",
            "temporal_truth_version": "pause_resume_v1",
            "truth_travel_distance_m": round(
                behavior_truth_distance_m(scenario, args.behavior), 1
            ),
        })
        for arm in "ABC":
            _retime_temporal(row["arms"][arm]["temporal"], scenario, graph, args.behavior)
        changed += 1

    destination = RESULTS / args.output
    destination.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(f"saved={destination} rows={len(rows)} retimed={changed}")


if __name__ == "__main__":
    main()
