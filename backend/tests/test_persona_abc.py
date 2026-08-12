import json
import math

import networkx as nx

from app.geo import h3grid
from app.schemas.common import GeoPoint
from experiments.personalized_alert_replay.build_persona_bank import load_profiles
from experiments.personalized_alert_replay.remote_persona_abc import (
    MANIFEST,
    _run_a,
    build_persona_scenarios,
)
from experiments.personalized_alert_replay.truth_routes import (
    TruthScenario,
    behavior_path_fraction,
    behavior_truth_distance_m,
    temporal_truth_point,
)


def _point(origin_lat: float, origin_lng: float, bearing: float, distance_km: float):
    dlat = distance_km / 111.32 * math.cos(bearing)
    dlng = distance_km / (111.32 * math.cos(math.radians(origin_lat))) * math.sin(bearing)
    return origin_lat + dlat, origin_lng + dlng


def _three_direction_graph():
    graph = nx.MultiDiGraph()
    lat, lng = 37.6, 127.0
    graph.add_node(0, y=lat, x=lng)
    for node, bearing in enumerate((0.0, math.pi / 2, math.pi), start=1):
        y, x = _point(lat, lng, bearing, 0.4)
        graph.add_node(node, y=y, x=x)
        graph.add_edge(0, node, length=400.0)
    return graph


def test_manifest_matches_all_ten_authored_profiles():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest_ids = {row["profile_id"] for row in manifest["personas"]}
    assert manifest_ids == {profile.profile_id for profile in load_profiles()}
    assert len({row["persona_id"] for row in manifest["personas"]}) == 10


def test_persona_scenarios_are_independently_direction_stratified():
    graph = _three_direction_graph()
    persona = {
        "home": {"lat": 37.6, "lng": 127.0},
        "attraction_points": [{
            "label": "north",
            "weight": 1.0,
            "location": {"lat": 37.61, "lng": 127.0},
        }],
    }
    scenarios = build_persona_scenarios(graph, "SP01", persona, 0.1)
    angles = {scenario.stratum: design["actual_angle_diff_deg"]
              for scenario, design in scenarios}
    assert angles["consistent"] < 5
    assert 85 < angles["neutral"] < 95
    assert angles["counter"] > 175
    assert all(250 <= scenario.path_length_m <= 500 for scenario, _ in scenarios)


def test_arm_a_uses_exactly_the_same_19_plus_19_cell_budget():
    graph = _three_direction_graph()
    persona = {
        "home": {"lat": 37.6, "lng": 127.0},
        "attraction_points": [{
            "label": "north",
            "weight": 1.0,
            "location": {"lat": 37.61, "lng": 127.0},
        }],
    }
    scenario, _ = build_persona_scenarios(graph, "SP01", persona, 0.1)[0]
    result = _run_a(graph, scenario)
    metrics = result["metrics"]
    assert metrics["d1_cells"] == 19
    assert metrics["d2_cells"] == 19
    assert metrics["unique_alert_cells"] == 38
    assert len(set(metrics["alert_cells"])) == 38
    assert h3grid.cell_of(scenario.start) in metrics["alert_cells"]
    assert "d2_gtcr_outside_d1" in metrics


def test_temporal_evaluation_matches_each_map_to_same_minute_truth():
    graph = _three_direction_graph()
    persona = {
        "home": {"lat": 37.6, "lng": 127.0},
        "attraction_points": [{
            "label": "north",
            "weight": 1.0,
            "location": {"lat": 37.61, "lng": 127.0},
        }],
    }
    scenario, _ = build_persona_scenarios(graph, "SP01", persona, 0.1)[0]
    result = _run_a(graph, scenario, [0, 15, 30, 45, 60])
    temporal = result["temporal"]
    assert [item["minute_after_report"] for item in temporal["snapshots"]] == [
        0, 15, 30, 45, 60,
    ]
    assert all(len(item["d1_cells"]) == 19 for item in temporal["snapshots"])
    assert all(len(item["d2_cells"]) == 19 for item in temporal["snapshots"])
    assert temporal["unique_alert_cells_over_time"] == 38


def test_temporal_truth_route_uses_distinct_progress_points_without_overextension():
    graph = nx.MultiDiGraph()
    lat, lng = 37.6, 127.0
    for node in range(101):
        y, x = _point(lat, lng, math.pi / 2, node * 0.1)
        graph.add_node(node, y=y, x=x)
        if node:
            graph.add_edge(node - 1, node, length=100.0)
            graph.add_edge(node, node - 1, length=100.0)
    destination_node = 55
    scenario = TruthScenario(
        scenario_id="temporal-chain",
        stratum="consistent",
        start_node=0,
        attraction_node=4,
        destination_node=destination_node,
        start=GeoPoint(lat=lat, lng=lng),
        attraction=GeoPoint(lat=graph.nodes[4]["y"], lng=graph.nodes[4]["x"]),
        destination=GeoPoint(
            lat=graph.nodes[destination_node]["y"],
            lng=graph.nodes[destination_node]["x"],
        ),
        path_nodes=tuple(range(destination_node + 1)),
        path_length_m=5_500.0,
        speed_kmh=2.0,
        missing_before_report_min=30,
    )
    points = [
        temporal_truth_point(
            graph,
            scenario,
            minute_after_report=minute,
            final_minute_after_report=135,
        )
        for minute in (0, 45, 90, 135)
    ]
    assert len({h3grid.cell_of(point) for point in points}) == 4
    assert points[-1] == scenario.destination


def test_behavior_truth_patterns_are_distinct_and_bounded():
    checkpoints = (0.0, 0.25, 0.5, 0.75, 1.0)
    move = [behavior_path_fraction(value, "move") for value in checkpoints]
    stay = [behavior_path_fraction(value, "stay") for value in checkpoints]
    hide = [behavior_path_fraction(value, "hide") for value in checkpoints]
    backtrack = [behavior_path_fraction(value, "backtrack") for value in checkpoints]

    assert move == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert stay[-3:] == [0.8, 0.8, 0.8]
    assert hide == [0.0, 0.3055555555555556, 0.55, 0.55, 0.8]
    assert backtrack == [0.0, 0.25, 0.5, 0.25, 0.0]
    assert all(0.0 <= value <= 1.0 for values in (move, stay, hide, backtrack) for value in values)


def test_hide_truth_moves_pauses_then_resumes_at_experiment_times():
    # missing_before_report=30, final=135일 때의 정규화 진행률.
    progress = [30 / 165, 75 / 165, 120 / 165, 165 / 165]
    fractions = [behavior_path_fraction(value, "hide") for value in progress]

    assert fractions[0] < fractions[1]
    assert fractions[1] == fractions[2]
    assert fractions[2] < fractions[3]


def test_behavior_truth_total_walk_does_not_exceed_scenario_band():
    graph = _three_direction_graph()
    persona = {
        "home": {"lat": 37.6, "lng": 127.0},
        "attraction_points": [{
            "label": "north",
            "weight": 1.0,
            "location": {"lat": 37.61, "lng": 127.0},
        }],
    }
    scenario, _ = build_persona_scenarios(graph, "SP01", persona, 0.1)[0]
    for behavior in ("stay", "move", "backtrack", "hide"):
        assert behavior_truth_distance_m(scenario, behavior) <= scenario.path_length_m
