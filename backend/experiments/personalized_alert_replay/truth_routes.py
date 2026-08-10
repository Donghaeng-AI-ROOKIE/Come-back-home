"""Phase 2와 분리된 OSM 정답 궤적 생성기.

이 모듈은 ``app.phase2``를 import하지 않는다. 예측기의 Koester 표본,
6전략 보행, 게이지를 정답 생성에 재사용하면 개인화 성능이 구조적으로
낙관되므로, NetworkX 최단경로와 고정 보행속도만으로 시점별 정답을 만든다.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import networkx as nx

from app.geo import h3grid
from app.schemas.common import GeoPoint


STRATA = ("consistent", "neutral", "counter")


@dataclass(frozen=True)
class TruthScenario:
    scenario_id: str
    stratum: str
    start_node: int
    attraction_node: int
    destination_node: int
    start: GeoPoint
    attraction: GeoPoint
    destination: GeoPoint
    path_nodes: tuple[int, ...]
    path_length_m: float
    speed_kmh: float
    missing_before_report_min: int


def _loc(graph, node: int) -> GeoPoint:
    data = graph.nodes[node]
    return GeoPoint(lat=float(data["y"]), lng=float(data["x"]))


def _bearing(a: GeoPoint, b: GeoPoint) -> float:
    dlat = b.lat - a.lat
    dlng = (b.lng - a.lng) * math.cos(math.radians(a.lat))
    return math.atan2(dlng, dlat)


def _angle_diff(a: float, b: float) -> float:
    return abs((a - b + math.pi) % (2 * math.pi) - math.pi)


def _edge_length_m(graph, u: int, v: int) -> float:
    data = graph.get_edge_data(u, v)
    if not data:
        return 30.0
    attrs = data[next(iter(data))]
    return float(attrs.get("length", 30.0))


def _choose_pair(
    graph,
    start: int,
    candidates: list[int],
    stratum: str,
    rng: random.Random,
) -> tuple[int, int] | None:
    """끌림점과 정답 목적지를 고른다.

    consistent: 두 지점이 80~300m 내외로 가깝다.
    neutral: 출발지 기준 방위가 60도 이상 다르다.
    counter: 출발지 기준 방위가 140도 이상 반대다.
    """
    s = _loc(graph, start)
    shuffled = list(candidates)
    rng.shuffle(shuffled)
    for attraction in shuffled[:180]:
        a = _loc(graph, attraction)
        ba = _bearing(s, a)
        dests = list(candidates)
        rng.shuffle(dests)
        for destination in dests[:240]:
            if destination == attraction:
                continue
            d = _loc(graph, destination)
            gap_km = h3grid.haversine_km(a, d)
            diff = _angle_diff(ba, _bearing(s, d))
            if stratum == "consistent" and 0.08 <= gap_km <= 0.30:
                return attraction, destination
            if stratum == "neutral" and gap_km >= 0.70 and math.radians(60) <= diff <= math.radians(120):
                return attraction, destination
            if stratum == "counter" and gap_km >= 1.00 and diff >= math.radians(140):
                return attraction, destination
    return None


def build_scenarios(
    graph,
    *,
    per_stratum: int,
    seed: int = 20260810,
    center: GeoPoint = GeoPoint(lat=37.6061, lng=127.0106),
    fixed_start: bool = False,
) -> list[TruthScenario]:
    """각 층별로 동일한 수의 독립 도보 궤적을 생성한다."""
    rng = random.Random(seed)
    if fixed_start:
        inner = [min(graph.nodes, key=lambda n: h3grid.haversine_km(center, _loc(graph, n)))]
    else:
        inner = [
            n for n in graph.nodes
            if h3grid.haversine_km(center, _loc(graph, n)) <= 1.2
        ]
    if not inner:
        raise RuntimeError("시작 노드 후보가 없음")

    scenarios: list[TruthScenario] = []
    used: set[tuple[int, int, int]] = set()
    for stratum in STRATA:
        attempts = 0
        while sum(s.stratum == stratum for s in scenarios) < per_stratum:
            attempts += 1
            if attempts > 600:
                raise RuntimeError(f"{stratum} 시나리오 생성 실패")
            start = rng.choice(inner)
            lengths = nx.single_source_dijkstra_path_length(
                graph, start, cutoff=2400.0, weight="length"
            )
            candidates = [n for n, meters in lengths.items() if 800.0 <= meters <= 2200.0]
            if len(candidates) < 20:
                continue
            pair = _choose_pair(graph, start, candidates, stratum, rng)
            if pair is None:
                continue
            attraction, destination = pair
            key = (start, attraction, destination)
            if key in used:
                continue
            try:
                path = nx.shortest_path(graph, start, destination, weight="length")
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
            path_m = sum(_edge_length_m(graph, u, v) for u, v in zip(path, path[1:]))
            if not 800.0 <= path_m <= 2400.0:
                continue
            used.add(key)
            idx = sum(s.stratum == stratum for s in scenarios)
            scenarios.append(TruthScenario(
                scenario_id=f"{stratum}-{idx:02d}",
                stratum=stratum,
                start_node=int(start),
                attraction_node=int(attraction),
                destination_node=int(destination),
                start=_loc(graph, start),
                attraction=_loc(graph, attraction),
                destination=_loc(graph, destination),
                path_nodes=tuple(int(n) for n in path),
                path_length_m=path_m,
                speed_kmh=rng.choice((2.0, 2.5, 3.0)),
                missing_before_report_min=rng.choice((15, 30, 45)),
            ))
    return scenarios


def point_at_minutes(graph, scenario: TruthScenario, minutes_since_missing: float) -> GeoPoint:
    """고정 속도로 최단경로를 이동한 시점의 위치. 도착 후는 머문다."""
    target_m = scenario.speed_kmh * 1000.0 * max(0.0, minutes_since_missing) / 60.0
    if target_m <= 0:
        return scenario.start
    walked = 0.0
    nodes = scenario.path_nodes
    for u, v in zip(nodes, nodes[1:]):
        edge_m = _edge_length_m(graph, u, v)
        if walked + edge_m >= target_m:
            frac = (target_m - walked) / max(edge_m, 1e-9)
            a, b = _loc(graph, u), _loc(graph, v)
            return GeoPoint(
                lat=a.lat + (b.lat - a.lat) * frac,
                lng=a.lng + (b.lng - a.lng) * frac,
            )
        walked += edge_m
    return scenario.destination


def truth_points_after_report(
    graph, scenario: TruthScenario, *, window_min: int = 60, step_min: int = 5,
) -> list[tuple[int, GeoPoint]]:
    return [
        (minute, point_at_minutes(
            graph, scenario, scenario.missing_before_report_min + minute,
        ))
        for minute in range(0, window_min + 1, step_min)
    ]
