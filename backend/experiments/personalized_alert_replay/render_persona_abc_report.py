"""A/B/C 확률 셀·OSMnx 도로망·정답 궤적을 시나리오별 SVG 보고서로 렌더링."""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path

from app.geo import h3grid
from app.geo.roadnet import OSMnxNetwork
from app.schemas.common import GeoPoint

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
RESULTS = HERE / "results"
GRAPHML = BACKEND / "data/roadnet_cache/walk_37.6061_127.0106_5000.graphml"
PANEL_W, PANEL_H, GAP = 390, 520, 18
# 범례 두 줄을 패널 내부에 확보한다. 이전 단일 행 범례는 다음 패널까지
# 넘어가 직접 SVG를 열거나 캡처할 때 잘려 보였다.
MAP_X, MAP_Y, MAP_W, MAP_H = 12, 52, PANEL_W - 24, PANEL_H - 112
ARM_COLORS = {"A": (49, 130, 189), "B": (230, 85, 13), "C": (35, 139, 69)}


def _load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _point(raw: dict) -> GeoPoint:
    return GeoPoint.model_validate(raw)


def _all_points(row: dict) -> list[GeoPoint]:
    points = [_point(row["start"]), _point(row["destination"])]
    points += [_point(item) for item in row["truth_path"]]
    for arm in "ABC":
        for cell in row["arms"][arm].get("surface_cells", {}):
            points += h3grid.cell_boundary(cell)
    return points


def _bounds(row: dict) -> tuple[float, float, float, float]:
    points = _all_points(row)
    min_lat, max_lat = min(p.lat for p in points), max(p.lat for p in points)
    min_lng, max_lng = min(p.lng for p in points), max(p.lng for p in points)
    lat_pad = max((max_lat - min_lat) * 0.08, 0.001)
    lng_pad = max((max_lng - min_lng) * 0.08, 0.001)
    return min_lat - lat_pad, max_lat + lat_pad, min_lng - lng_pad, max_lng + lng_pad


def _project(point: GeoPoint, bounds) -> tuple[float, float]:
    min_lat, max_lat, min_lng, max_lng = bounds
    center_lat = (min_lat + max_lat) / 2
    center_lng = (min_lng + max_lng) / 2
    longitude_scale = math.cos(math.radians(center_lat))
    projected_width = max((max_lng - min_lng) * longitude_scale, 1e-9)
    projected_height = max(max_lat - min_lat, 1e-9)
    # One uniform geographic scale preserves H3 geometry.  Independent x/y
    # fitting made Seoul's hexagons look tall and horizontally compressed.
    scale = min(MAP_W / projected_width, MAP_H / projected_height)
    x = MAP_X + MAP_W / 2 + (point.lng - center_lng) * longitude_scale * scale
    y = MAP_Y + MAP_H / 2 - (point.lat - center_lat) * scale
    return x, y


def _poly(points: list[GeoPoint], bounds) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in (_project(point, bounds) for point in points))


def _road_svg(graph, bounds) -> str:
    min_lat, max_lat, min_lng, max_lng = bounds
    seen = set()
    paths = []
    for u, v in graph.edges():
        key = tuple(sorted((str(u), str(v))))
        if key in seen:
            continue
        seen.add(key)
        du, dv = graph.nodes[u], graph.nodes[v]
        a = GeoPoint(lat=float(du["y"]), lng=float(du["x"]))
        b = GeoPoint(lat=float(dv["y"]), lng=float(dv["x"]))
        if not (
            min_lat <= a.lat <= max_lat and min_lng <= a.lng <= max_lng
            or min_lat <= b.lat <= max_lat and min_lng <= b.lng <= max_lng
        ):
            continue
        ax, ay = _project(a, bounds)
        bx, by = _project(b, bounds)
        paths.append(f'<path d="M{ax:.1f},{ay:.1f} L{bx:.1f},{by:.1f}"/>')
    return "".join(paths)


def _surface_svg(arm: str, result: dict, bounds) -> str:
    surface = result.get("surface_cells", {})
    if not surface:
        return ""
    peak = max(surface.values()) or 1.0
    r, g, b = ARM_COLORS[arm]
    polygons = []
    for cell, probability in sorted(surface.items(), key=lambda item: item[1]):
        intensity = math.sqrt(max(probability, 0.0) / peak)
        opacity = 0.08 + 0.62 * intensity
        polygons.append(
            f'<polygon points="{_poly(h3grid.cell_boundary(cell), bounds)}" '
            f'fill="rgb({r},{g},{b})" fill-opacity="{opacity:.3f}" stroke="none"/>'
        )
    return "".join(polygons)


def _alert_svg(arm: str, row: dict, result: dict, bounds) -> str:
    d1 = set(h3grid.cells_within_k(_point(row["start"]), 2))
    active = set(result["metrics"]["alert_cells"])
    d2 = active - d1
    out = []
    for cell in d1:
        out.append(
            f'<polygon points="{_poly(h3grid.cell_boundary(cell), bounds)}" '
            'fill="none" stroke="#111827" stroke-width="1.35" '
            'stroke-dasharray="4 3" stroke-linejoin="round"/>'
        )
    for cell in d2:
        out.append(
            f'<polygon points="{_poly(h3grid.cell_boundary(cell), bounds)}" '
            'fill="none" stroke="#111827" stroke-width="2.15" '
            'stroke-linejoin="round"/>'
        )
    return "".join(out)


def _truth_svg(row: dict, bounds) -> str:
    path = [_point(item) for item in row["truth_path"]]
    samples = [_point(item) for item in row["truth_samples"]]
    start, destination = _point(row["start"]), _point(row["destination"])
    sx, sy = _project(start, bounds)
    dx, dy = _project(destination, bounds)
    line = _poly(path, bounds)
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.1" fill="#dc2626"/>'
        for x, y in (_project(point, bounds) for point in samples)
    )
    return (
        f'<polyline points="{line}" fill="none" stroke="#dc2626" stroke-width="3" '
        f'stroke-linecap="round" stroke-linejoin="round"/>{dots}'
        f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="6" fill="#2563eb" stroke="white" stroke-width="2"/>'
        f'<path d="M{dx:.1f},{dy - 7:.1f} L{dx + 7:.1f},{dy:.1f} '
        f'L{dx:.1f},{dy + 7:.1f} L{dx - 7:.1f},{dy:.1f} Z" fill="#dc2626" '
        'stroke="white" stroke-width="2"/>'
    )


def _panel(arm: str, row: dict, bounds) -> str:
    result = row["arms"][arm]
    metrics = result["metrics"]
    labels = {"A": "A 거리 기준", "B": "B EXAONE 비개인화", "C": "C EXAONE 개인화"}
    status = "유효" if result.get("valid") else "무효(폴백)"
    primary = metrics.get("d2_gtcr_outside_d1")
    primary_text = "평가 불필요" if primary is None else f"D2 외부커버 {primary * 100:.1f}%"
    return (
        '<rect x="0" y="0" width="390" height="520" rx="14" fill="#fff" stroke="#d8dee9"/>'
        f'<text x="18" y="28" font-size="18" font-weight="700" fill="#111827">{labels[arm]}</text>'
        f'<text x="372" y="28" text-anchor="end" font-size="12" fill="#64748b">{status} · {primary_text}</text>'
        '<g clip-path="url(#map-clip)"><use href="#roads"/>'
        f'{_surface_svg(arm, result, bounds)}'
        f'{_alert_svg(arm, row, result, bounds)}'
        f'{_truth_svg(row, bounds)}</g>'
        '<text x="18" y="484" font-size="10.5" fill="#475569">'
        '● 시작 · ━ 정답 이동 · ◆ 현재 실제 위치</text>'
        '<text x="18" y="503" font-size="10.5" fill="#475569">'
        '검정 점선 D1 · 검정 실선 알림 후보 셀</text>'
    )


def render_row(row: dict, graph, out_dir: Path, *, bounds=None) -> Path:
    bounds = bounds or _bounds(row)
    roads = _road_svg(graph, bounds)
    total_w = PANEL_W * 3 + GAP * 2
    panels = []
    for index, arm in enumerate("ABC"):
        x = index * (PANEL_W + GAP)
        panels.append(f'<g transform="translate({x},0)">{_panel(arm, row, bounds)}</g>')
    title = html.escape(
        f"{row['scenario_id']} | {row['stratum']} | {row['design'].get('home_provider')} | "
        f"{row['design'].get('home_match') or ''}"
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="560" '
        f'viewBox="0 0 {total_w} 560" role="img" aria-label="{title}">'
        '<style>text{font-family:"AppleGothic","Arial Unicode MS",sans-serif}</style>'
        f'<defs><clipPath id="map-clip"><rect x="{MAP_X}" y="{MAP_Y}" '
        f'width="{MAP_W}" height="{MAP_H}"/></clipPath>'
        f'<g id="roads" fill="none" stroke="#d7dce2" stroke-width="0.75">{roads}</g></defs>'
        f'<text x="0" y="552" font-size="13" font-weight="600" fill="#334155">{title}</text>'
        + "".join(panels) + "</svg>"
    )
    path = out_dir / f"{row['scenario_id']}.svg"
    path.write_text(svg, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", default="persona_abc_map_report")
    args = parser.parse_args()
    rows = _load(RESULTS / args.input)
    report_dir = RESULTS / args.out_dir
    map_dir = report_dir / "maps"
    map_dir.mkdir(parents=True, exist_ok=True)
    graph = OSMnxNetwork.from_graphml(GRAPHML).graph
    cards = []
    for index, row in enumerate(rows, start=1):
        path = render_row(row, graph, map_dir)
        cards.append(
            '<section class="card">'
            f'<h2>{html.escape(row["scenario_id"])} <small>{html.escape(row["stratum"])}</small></h2>'
            f'<p>{html.escape(row["design"].get("home_match") or "")} · '
            f'{row["path_length_m"]:.0f}m · {row["speed_kmh"]:.1f}km/h</p>'
            f'<a href="maps/{path.name}"><img loading="lazy" src="maps/{path.name}" '
            f'alt="{html.escape(row["scenario_id"])} A/B/C 확률지도"/></a></section>'
        )
        print(f"[{index}/{len(rows)}] {path.name}", flush=True)
    document = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>A/B/C 확률지도 보고서</title>
<style>body{margin:0;background:#f4f6f8;color:#111827;font-family:-apple-system,BlinkMacSystemFont,"Noto Sans KR",sans-serif}
main{max-width:1280px;margin:auto;padding:28px}.intro,.card{background:white;border:1px solid #dde3ea;border-radius:18px;padding:22px;margin-bottom:22px;box-shadow:0 3px 14px #0f172a0d}
h1{margin:0 0 10px}h2{margin:0}small,p{color:#64748b}.card img{width:100%;height:auto;display:block;margin-top:12px;border-radius:10px;background:#fff}</style></head><body><main>
<section class="intro"><h1>EXAONE E2E 개인화 알림 A/B/C 확률지도</h1>
<p>Mi:dm은 온보딩 대화와 12슬롯 Persona 저장에만 사용했고, B·C군의 경로 예측과 확률표면 생성은 모두 EXAONE E2E로 수행했다.</p>
<p>OSMnx 도로망 위에 예측 표면, 동일 예산 D1 19셀+D2 19셀, 독립 OSM 정답 궤적을 겹쳐 표시했다. 이 지도는 실제 발견률이 아니라 합성 재생 결과이다.</p></section>
""" + "\n".join(cards) + "</main></body></html>"
    report = report_dir / "index.html"
    report.write_text(document, encoding="utf-8")
    print(f"saved={report} maps={len(rows)}")


if __name__ == "__main__":
    main()
