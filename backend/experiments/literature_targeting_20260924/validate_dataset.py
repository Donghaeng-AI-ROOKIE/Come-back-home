"""Check truth integrity, graph feasibility and input separation without prediction."""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import h3

from build_dataset import (BACKEND, HERE, SITES, TIMES, digest, distance,
                           load_graph, location, path_length, point_at_distance, write_json)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(folder):
    read = lambda name: json.loads((folder / name).read_text(encoding="utf-8"))
    manifest = read("manifest.json")
    for name, expected in manifest["files"].items():
        require(digest(folder / name) == expected, f"Hash changed: {name}")
    require(digest(HERE / "build_dataset.py") == manifest["generator_sha256"], "Generator changed")
    require(digest(HERE / "PROTOCOL.md") == manifest["protocol_sha256"], "Protocol changed")
    require(digest(HERE / "SOURCES.md") == manifest["sources_sha256"], "Sources changed")
    seen_scenarios, seen_profiles, results = set(), set(), {}
    descriptions = ["# 시나리오 검토 예시", "", "개발용 6명의 사례다. 평가용 결과는 모델 설정 선택에 사용하지 않는다.",
                    "실제 환자 또는 실제 거주지가 아닌 도로망 위 합성 인물·사건이다.", ""]
    for split, spec in SITES.items():
        inputs, truth = read(f"{split}_inputs.json"), read(f"{split}_truth.json")
        im = {r["scenario_id"]: r for r in inputs}
        tm = {r["scenario_id"]: r for r in truth}
        require(len(im) == len(tm) == 18 and im.keys() == tm.keys(), "Missing/duplicate scenarios")
        require(not seen_scenarios.intersection(im), "Cross-split scenario overlap")
        seen_scenarios.update(im)
        profiles = {r["profile_id"] for r in inputs}
        require(len(profiles) == 6 and not seen_profiles.intersection(profiles), "Profile split leakage")
        seen_profiles.update(profiles)
        graph_path = BACKEND / "data/roadnet_cache" / spec[0]
        require(digest(graph_path) == manifest["graphs"][split]["sha256"], "Road graph changed")
        graph = load_graph(graph_path)
        per_profile = defaultdict(list)
        boundary_counts = Counter()
        arrived = Counter()
        endpoint_cells = defaultdict(set)
        for sid, case in im.items():
            t = tm[sid]
            require(case["B"]["common"] == case["C"]["common"], "B/C common data mismatch")
            require(case["B"]["personal"] is None, "B received personal history")
            require(set(case) == {"scenario_id", "profile_id", "split", "graph_file", "minutes_after_report", "B", "C"}, "Unexpected model input field")
            require(set(case["B"]) == set(case["C"]) == {"common", "personal"}, "Unexpected arm field")
            require(set(case["C"]["personal"]) == {"profile_id", "age", "type", "home", "routine_destination", "routine_route", "caregiver_notes", "place_semantics"}, "Unexpected profile field")
            require(set(case["B"]["common"]) == {"age", "type", "home", "last_seen", "minutes_before_report", "transport", "scene"}, "Unexpected common field")
            require(t["profile_id"] == case["profile_id"] and t["split"] == split, "Metadata mismatch")
            require(case["minutes_after_report"] == list(TIMES), "Wrong requested times")
            require([p["minute_after_report"] for p in t["points"]] == list(TIMES), "Wrong truth times")
            path = t["path_nodes"]
            require(all(graph.has_edge(u, v) for u, v in zip(path, path[1:])), "Off-road path")
            require(abs(path_length(graph, path) - t["path_length_m"]) < 1e-8, "Length mismatch")
            require(location(graph, path[0]) == case["B"]["common"]["last_seen"], "Start mismatch")
            personal = case["C"]["personal"]
            if t["condition"] == "routine_related":
                require([location(graph, n) for n in path] == personal["routine_route"], "Routine mismatch")
            elif t["condition"] == "route_departure":
                require(t["branch_node"] in path, "Missing branch")
                require([location(graph, n) for n in path] != personal["routine_route"], "No route departure")
            elif t["condition"] == "unrelated_direction":
                require(distance(location(graph, path[-1]), personal["routine_destination"]) >= 1000, "Control destination too close")
            else:
                raise ValueError("Unknown condition")
            for p in t["points"]:
                meters = min(t["path_length_m"], t["speed_kmh_assumption"] * 1000 * (p["minute_after_report"] + 10) / 60)
                actual = point_at_distance(graph, path, meters)
                require(distance(actual, p) < 1e-6, "Time/coordinate mismatch")
                require(abs(meters - p["distance_walked_m"]) < 1e-8, "Speed mismatch")
                require(p["arrived"] == (meters == t["path_length_m"]), "Arrival flag mismatch")
                arrived[t["condition"]] += int(p["arrived"])
                for res in (7, 8, 9):
                    cell = h3.latlng_to_cell(p["lat"], p["lng"], res)
                    require(p[f"res{res}"] == cell, "H3 mismatch")
                    if res < 9:
                        boundary_counts[str(res)] += int(cell != h3.cell_to_parent(p["res9"], res))
            endpoint_cells[t["profile_id"]].add(t["points"][-1]["res8"])
            per_profile[t["profile_id"]].append((case, t))
        for pid, rows in per_profile.items():
            require({t["condition"] for _, t in rows} == {"routine_related", "route_departure", "unrelated_direction"}, "Incomplete conditions")
            require(all(c["C"]["personal"] == rows[0][0]["C"]["personal"] for c, _ in rows), "Profile changed by truth condition")
            require(all(c["B"] == rows[0][0]["B"] for c, _ in rows), "Common input changed by truth condition")
            if split == "development":
                c = rows[0][0]
                descriptions.extend([f"## {pid}", "", f"나이 {c['B']['common']['age']}세. 합성 치매 유형. 개인화에는 사전 산책 경로와 등록 목적지를 제공한다.",
                                     f"마지막 목격 좌표: {c['B']['common']['last_seen']}. 신고까지 10분.",
                                     f"사전등록 목적지: {c['C']['personal']['routine_destination']}. 실제 공원/거주지로 확인한 지점이 아니다.", "",
                                     "| 조건 | 정답 경로 길이 m | 이탈 분기 노드 | 신고 후 30분 정답 좌표 |", "|---|---:|---|---|"])
                for _, t in rows:
                    p = t["points"][2]
                    descriptions.append(f"| {t['condition']} | {t['path_length_m']:.1f} | {t['branch_node']} | {p['lat']:.6f}, {p['lng']:.6f} |")
                descriptions.append("")
        results[split] = {"profiles": len(profiles), "scenarios": len(im), "paired_timepoints": len(im) * len(TIMES),
                          "arrived_timepoints_by_condition": dict(arrived), "direct_vs_parent_cell_mismatches": dict(boundary_counts),
                          "distinct_endpoint_res8_by_profile": {p: len(c) for p, c in endpoint_cells.items()}}
    write_json(HERE / "VALIDATION.json", {"status": "passed", "dataset_manifest_sha256": digest(folder / "manifest.json"),
               "checks": ["frozen hashes", "no split overlap", "B/C common input equality", "same profile across conditions",
                          "strict input field whitelist", "road edges and geometry", "time and speed", "direct H3 truth"],
               "results": results, "model_predictions_run": False, "push_calls": 0})
    (HERE / "SCENARIO_REVIEW.md").write_text("\n".join(descriptions), encoding="utf-8")
    print(json.dumps({"status": "passed", "results": results}, ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, default=HERE / "dataset_v1")
    validate(p.parse_args().dataset)
