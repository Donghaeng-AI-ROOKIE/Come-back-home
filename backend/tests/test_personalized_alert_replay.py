import ast
from pathlib import Path

from app.geo.roadnet import OSMnxNetwork
from experiments.personalized_alert_replay.truth_routes import (
    STRATA,
    build_scenarios,
    truth_points_after_report,
)


FIXTURE = Path(__file__).parent / "fixtures/jeongneung_walk_800m.graphml"


def test_truth_generator_does_not_import_phase2():
    source = (Path(__file__).parents[1]
              / "experiments/personalized_alert_replay/truth_routes.py").read_text()
    tree = ast.parse(source)
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any(name == "app.phase2" or name.startswith("app.phase2.")
                   for name in imported)


def test_truth_scenarios_are_balanced_and_deterministic():
    net = OSMnxNetwork.from_graphml(FIXTURE)
    first = build_scenarios(net.graph, per_stratum=1, seed=7)
    second = build_scenarios(net.graph, per_stratum=1, seed=7)
    assert [s.scenario_id for s in first] == [s.scenario_id for s in second]
    assert {s.stratum for s in first} == set(STRATA)
    assert all(800 <= s.path_length_m <= 2400 for s in first)


def test_truth_timeline_has_thirteen_ordered_samples():
    net = OSMnxNetwork.from_graphml(FIXTURE)
    scenario = build_scenarios(net.graph, per_stratum=1, seed=11)[0]
    points = truth_points_after_report(net.graph, scenario)
    assert [minute for minute, _ in points] == list(range(0, 61, 5))
