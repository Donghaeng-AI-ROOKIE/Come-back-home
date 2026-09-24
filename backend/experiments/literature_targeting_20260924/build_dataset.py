"""Literature-informed synthetic truth; no predictor imports or service calls."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

import h3
import networkx as nx
from shapely import wkt
from shapely.geometry import LineString

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
SEED = 20260924
TIMES = (0, 15, 30, 60)  # after report; LKP is 10 minutes before report
SITES = {
    "development": ("walk_37.6061_127.0106_3000.graphml", 37.6061, 127.0106),
    "evaluation": ("walk_37.5511_126.9410_3000.graphml", 37.5511, 126.9410),
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def location(g, node):
    return {"lat": float(g.nodes[node]["y"]), "lng": float(g.nodes[node]["x"])}


def distance(a, b):
    lat = math.radians((a["lat"] + b["lat"]) / 2)
    return 111195 * math.hypot(a["lat"] - b["lat"], (a["lng"] - b["lng"]) * math.cos(lat))


def load_graph(path):
    raw = nx.read_graphml(path)
    # Preserve directed edges and select the shortest parallel walking edge.
    g = nx.DiGraph()
    g.add_nodes_from(raw.nodes(data=True))
    for u, v, data in raw.edges(data=True):
        length = float(data["length"])
        if length <= 0 or not math.isfinite(length):
            raise ValueError("Invalid road length")
        if not g.has_edge(u, v) or length < g[u][v]["length"]:
            g.add_edge(u, v, **{**data, "length": length})
    return g


def path_length(g, path):
    return sum(g[u][v]["length"] for u, v in zip(path, path[1:]))


def point_at_distance(g, path, meters):
    """Interpolate along saved OSM edge geometry, not node-to-node shortcuts."""
    for u, v in zip(path, path[1:]):
        edge = g[u][v]
        if meters <= edge["length"]:
            a, b = location(g, u), location(g, v)
            geom = wkt.loads(edge["geometry"]) if edge.get("geometry") else LineString(
                [(a["lng"], a["lat"]), (b["lng"], b["lat"])])
            coords = list(geom.coords)
            if distance(a, {"lat": coords[-1][1], "lng": coords[-1][0]}) < distance(
                    a, {"lat": coords[0][1], "lng": coords[0][0]}):
                geom = LineString(coords[::-1])
            p = geom.interpolate(max(0, meters) / edge["length"], normalized=True)
            return {"lat": p.y, "lng": p.x}
        meters -= edge["length"]
    return location(g, path[-1])


def diverged_path(g, routine, rng):
    # First usable off-route branch at 35-70% of the familiar path. This is a
    # design rule, not an empirically estimated dementia transition probability.
    total = path_length(g, routine)
    walked = 0.0
    for i, node in enumerate(routine[:-1]):
        if .35 * total <= walked <= .70 * total:
            candidates = sorted(n for n in g.successors(node) if n not in routine)
            rng.shuffle(candidates)
            for nxt in candidates:
                branch = [node, nxt]
                excluded = set(routine) | {nxt}
                while path_length(g, branch) < 900:
                    choices = sorted(n for n in g.successors(branch[-1]) if n not in excluded)
                    if not choices:
                        break
                    chosen = rng.choice(choices)
                    branch.append(chosen)
                    excluded.add(chosen)
                if path_length(g, branch) >= 300:
                    return routine[:i] + branch, node
        walked += g[node][routine[i + 1]]["length"]
    return None


def make_site(split, spec, seed, count=6):
    filename, lat, lng = spec
    graph_path = BACKEND / "data/roadnet_cache" / filename
    g = load_graph(graph_path)
    rng = random.Random(seed)
    starts = sorted(n for n in g if distance(location(g, n), {"lat": lat, "lng": lng}) < 800)
    rng.shuffle(starts)
    profiles, cases, truth, rejected = [], [], [], 0
    for start in starts:
        if len(profiles) == count:
            break
        if any(distance(location(g, start), p["home"]) < 150 for p in profiles):
            continue
        lengths, paths = nx.single_source_dijkstra(g, start, cutoff=2200, weight="length")
        destinations = sorted(n for n, d in lengths.items() if 1000 <= d <= 1800)
        rng.shuffle(destinations)
        accepted = None
        for goal in destinations[:40]:
            routine = paths[goal]
            deviation = diverged_path(g, routine, rng)
            alternatives = [n for n in destinations if distance(location(g, n), location(g, goal)) >= 1000]
            if deviation and alternatives:
                accepted = routine, deviation, paths[rng.choice(alternatives)]
                break
        if accepted is None:
            rejected += 1
            continue
        index = len(profiles)
        pid = f"{split[:3]}-P{index + 1:02}"
        routine, (deviation, branch), other = accepted
        speed = (1.5, 2.0, 2.5)[index % 3]
        profile = {
            "profile_id": pid, "age": 72 + index * 2, "type": "dementia",
            "home": location(g, start),
            "routine_destination": location(g, routine[-1]),
            "routine_route": [location(g, n) for n in routine],
            "caregiver_notes": ["평소 사전등록한 익숙한 산책 경로를 이용한다.",
                                "등록 장소는 과거 생활 이력이며 이번 사건의 목적지는 확인되지 않았다."],
            "place_semantics": "synthetic routine waypoint; not a verified real park or home",
        }
        profiles.append(profile)
        for condition, path, branch_node in (
            ("routine_related", routine, None),
            ("route_departure", deviation, branch),
            ("unrelated_direction", other, None),
        ):
            # Opaque identifiers: conditions cannot leak through scenario names.
            sid = hashlib.sha256(f"{seed}:{pid}:{condition}".encode()).hexdigest()[:16]
            common = {"age": profile["age"], "type": "dementia", "home": profile["home"],
                      "last_seen": profile["home"], "minutes_before_report": 10,
                      "transport": "walking", "scene": "혼자 외출한 뒤 현재 위치가 확인되지 않는다."}
            cases.append({"scenario_id": sid, "profile_id": pid, "split": split,
                          "graph_file": filename, "minutes_after_report": list(TIMES),
                          "B": {"common": common, "personal": None},
                          "C": {"common": common, "personal": profile}})
            route_m = path_length(g, path)
            points = []
            for minute in TIMES:
                meters = speed * 1000 * (minute + 10) / 60
                point = point_at_distance(g, path, min(meters, route_m))
                points.append({"minute_after_report": minute, **point,
                               "arrived": meters >= route_m,
                               "distance_walked_m": min(meters, route_m),
                               "res7": h3.latlng_to_cell(point["lat"], point["lng"], 7),
                               "res8": h3.latlng_to_cell(point["lat"], point["lng"], 8),
                               "res9": h3.latlng_to_cell(point["lat"], point["lng"], 9)})
            truth.append({"scenario_id": sid, "profile_id": pid, "split": split,
                          "condition": condition, "path_nodes": path, "path_length_m": route_m,
                          "speed_kmh_assumption": speed, "branch_node": branch_node,
                          "after_arrival_assumption": "remain at synthetic endpoint",
                          "points": points})
    if len(profiles) != count:
        raise RuntimeError(f"Only {len(profiles)} profiles in {split}; do not silently shrink sample")
    return cases, truth, {"graph": filename, "sha256": digest(graph_path),
                          "geometry_rejections": rejected, "profiles": len(profiles)}


def build(output):
    if output.exists():
        raise FileExistsError("Dataset is frozen: choose a new output directory")
    output.mkdir(parents=True)
    all_truth, graphs, counts = [], {}, {}
    for i, (split, spec) in enumerate(SITES.items()):
        cases, truth, graph = make_site(split, spec, SEED + i)
        write_json(output / f"{split}_inputs.json", cases)
        write_json(output / f"{split}_truth.json", truth)
        all_truth.extend(truth)
        graphs[split] = graph
        counts[split] = {"profiles": 6, "scenarios": len(cases), "paired_timepoints": len(cases) * len(TIMES)}
    rows = ["# 합성 시나리오 목록", "", "정답과 조건을 포함한 검토 문서다. 예측 모델에 전달하지 않는다.", "",
            "| 분할 | 인물 | 시나리오 ID | 조건 | 경로 m | 가정 속도 km/h | 도착 후 시점 수 |",
            "|---|---|---|---|---:|---:|---:|"]
    for r in all_truth:
        rows.append(f"| {r['split']} | {r['profile_id']} | {r['scenario_id']} | {r['condition']} | {r['path_length_m']:.1f} | {r['speed_kmh_assumption']} | {sum(p['arrived'] for p in r['points'])} |")
    (output / "SCENARIOS.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    manifest = {"status": "truth_frozen_predictions_not_run", "seed": SEED,
                "generator_sha256": digest(__file__), "graphs": graphs, "counts": counts,
                "protocol_sha256": digest(HERE / "PROTOCOL.md"),
                "sources_sha256": digest(HERE / "SOURCES.md"),
                "files": {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()},
                "selection": "road geometry only; no model output or H3 outcome selection",
                "condition_prevalence": "equal design allocation; not real-world prevalence"}
    write_json(output / "manifest.json", manifest)
    print(json.dumps(counts))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=HERE / "dataset_v1")
    build(parser.parse_args().output)
