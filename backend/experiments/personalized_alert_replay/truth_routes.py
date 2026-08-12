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
BEHAVIOR_TYPES = ("stay", "move", "backtrack", "hide")


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
    return point_at_distance(graph, scenario, target_m)


def point_at_distance(graph, scenario: TruthScenario, target_m: float) -> GeoPoint:
    """정답 OSM 경로에서 누적 보행거리 target_m 지점의 위치."""
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


def temporal_truth_point(
    graph,
    scenario: TruthScenario,
    *,
    minute_after_report: int,
    final_minute_after_report: int,
    behavior: str = "move",
) -> GeoPoint:
    """Persona 이동 반경 경로를 시간축 실험 구간에 맞춰 재생.

    계속 보행 속도를 165분 내내 강제하면 Persona의 이동 능력과 모순된다.
    대신 기존에 독립 생성한 OSM 경로를 실종 시점부터 마지막 관측
    시점까지 이동·휴식한 것으로 재생한다. 따라서 네 시점의 위치는
    달라지지만 총 이동거리는 Persona 시나리오의 사전 밴드를 벗어나지 않는다.
    """
    total = scenario.missing_before_report_min + final_minute_after_report
    elapsed = scenario.missing_before_report_min + minute_after_report
    progress = min(max(elapsed / max(total, 1), 0.0), 1.0)
    fraction = behavior_path_fraction(progress, behavior)
    return point_at_distance(graph, scenario, scenario.path_length_m * fraction)


def behavior_path_fraction(progress: float, behavior: str) -> float:
    """행동 유형별 독립 정답 궤적에서 원경로상의 위치 비율을 반환한다.

    EXAONE/Phase 2 출력은 사용하지 않는다. 같은 OSM 최단경로를 기반으로
    시간 진행 형태만 사전에 고정해, 이동·정지·왕복·은폐 후 체류를 구분한다.

    - move: 전체 경로를 끝까지 진행
    - stay: 전체 경로의 80%까지 비교적 일찍 이동한 뒤 체류
    - hide: 이동 후 잠시 정지했다가 다시 이동해 은폐 장소에 체류
    - backtrack: 경로의 절반까지 갔다가 같은 길을 되돌아옴

    backtrack의 총 보행거리는 원경로 길이와 같아 Persona 이동 밴드를
    초과하지 않는다.
    """
    if behavior not in BEHAVIOR_TYPES:
        raise ValueError(f"알 수 없는 행동 유형: {behavior}")
    progress = min(max(progress, 0.0), 1.0)
    if behavior == "move":
        return progress
    if behavior == "backtrack":
        return progress if progress <= 0.5 else 1.0 - progress
    if behavior == "stay":
        return min(progress / 0.40, 1.0) * 0.80
    # hide: 초기 이동 → 일시 정지 → 재이동 → 은폐 장소 체류.
    # 30분 후 신고, 0·45·90·135분 평가에서는 대략 다음처럼 보인다.
    #   0분: 이동 중 / 45분: 정지 지점 도착 / 90분: 같은 곳에 머묾
    #   135분: 다시 이동해 최종 은폐 지점 도착
    # 모든 은폐형·방향층에 같은 사전 규칙을 적용한다.
    pause_start, pause_end = 0.45, 0.75
    pause_fraction, final_fraction = 0.55, 0.80
    if progress <= pause_start:
        return progress / pause_start * pause_fraction
    if progress <= pause_end:
        return pause_fraction
    resumed = (progress - pause_end) / (1.0 - pause_end)
    return pause_fraction + resumed * (final_fraction - pause_fraction)


def behavior_truth_distance_m(scenario: TruthScenario, behavior: str) -> float:
    """마지막 관측까지의 총 보행거리(왕복 누적 포함)."""
    if behavior == "move":
        return scenario.path_length_m
    if behavior == "backtrack":
        return scenario.path_length_m
    if behavior in {"stay", "hide"}:
        return scenario.path_length_m * 0.80
    raise ValueError(f"알 수 없는 행동 유형: {behavior}")


def truth_points_after_report(
    graph, scenario: TruthScenario, *, window_min: int = 60, step_min: int = 5,
) -> list[tuple[int, GeoPoint]]:
    return [
        (minute, point_at_minutes(
            graph, scenario, scenario.missing_before_report_min + minute,
        ))
        for minute in range(0, window_min + 1, step_min)
    ]
