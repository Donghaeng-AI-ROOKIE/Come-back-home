"""0·45·90·135분 POA·알림셀·동시간대 정답위치 비교 보고서."""

from __future__ import annotations

import argparse
import copy
import html
import math
from pathlib import Path

from app.geo.roadnet import OSMnxNetwork
from experiments.personalized_alert_replay.render_persona_abc_report import (
    GRAPHML,
    RESULTS,
    _bounds,
    _load,
    MAP_H,
    MAP_W,
    render_row,
)


def _shared_bounds(row: dict):
    merged = copy.deepcopy(row)
    for arm in "ABC":
        surface = {}
        for snapshot in row["arms"][arm]["temporal"]["snapshots"]:
            for cell, probability in snapshot["surface_cells"].items():
                surface[cell] = max(surface.get(cell, 0.0), probability)
        merged["arms"][arm]["surface_cells"] = surface
    merged["truth_path"] = [row["start"], *[
        {"lat": item["lat"], "lng": item["lng"]} for item in row["truth_samples"]
    ]]
    merged["destination"] = merged["truth_path"][-1]
    return _bounds(merged)


def _row_at(row: dict, index: int) -> dict:
    minute = row["arms"]["A"]["temporal"]["snapshots"][index]["minute_after_report"]
    rendered = copy.deepcopy(row)
    rendered["scenario_id"] = f"{row['scenario_id']}-t{minute:03d}"
    rendered["truth_samples"] = [
        item for item in row["truth_samples"] if item["minute"] <= minute
    ]
    current_truth = row["arms"]["A"]["temporal"]["snapshots"][index]["truth"]
    rendered["truth_path"] = [row["start"], *[
        {"lat": item["lat"], "lng": item["lng"]} for item in rendered["truth_samples"]
    ]]
    rendered["destination"] = current_truth
    for arm in "ABC":
        snapshot = row["arms"][arm]["temporal"]["snapshots"][index]
        rendered["arms"][arm]["surface_cells"] = snapshot["surface_cells"]
        rendered["arms"][arm]["metrics"]["alert_cells"] = sorted(
            set(snapshot["d1_cells"]) | set(snapshot["d2_cells"])
        )
        rendered["arms"][arm]["metrics"]["d2_gtcr_outside_d1"] = (
            float(snapshot["d2_hit"]) if snapshot["truth_outside_d1"] else None
        )
    return rendered


def _focused_bounds(row: dict) -> tuple[float, float, float, float]:
    """시작점부터 현재 실제 위치까지를 동일 축척으로 확대한다.

    낮은 확률의 원거리 표면 셀이 전체 지도 배율을 결정하지 않도록 정답
    이동 구간만 사용한다. H3가 찌그러지지 않도록 패널 종횡비에 맞춰
    짧은 축을 늘린다.
    """
    points = [row["start"], row["destination"], *row["truth_path"]]
    min_lat = min(point["lat"] for point in points)
    max_lat = max(point["lat"] for point in points)
    min_lng = min(point["lng"] for point in points)
    max_lng = max(point["lng"] for point in points)
    center_lat = (min_lat + max_lat) / 2
    center_lng = (min_lng + max_lng) / 2
    longitude_scale = math.cos(math.radians(center_lat))
    width = max((max_lng - min_lng) * longitude_scale, 0.0045)
    height = max(max_lat - min_lat, 0.0045)
    width *= 1.32
    height *= 1.32
    target_ratio = MAP_W / MAP_H
    if width / height < target_ratio:
        width = height * target_ratio
    else:
        height = width / target_ratio
    half_lng = width / longitude_scale / 2
    half_lat = height / 2
    return (
        center_lat - half_lat,
        center_lat + half_lat,
        center_lng - half_lng,
        center_lng + half_lng,
    )


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", default="persona_abc_temporal_report")
    parser.add_argument(
        "--focus-scenario", default="",
        help="시작점-현재위치 중심으로 확대할 scenario_id(쉼표 구분)",
    )
    parser.add_argument(
        "--focus-from-minute", type=int, default=45,
        help="확대를 시작할 신고 후 시점(분)",
    )
    args = parser.parse_args()
    focus_scenarios = {
        value.strip() for value in args.focus_scenario.split(",") if value.strip()
    }
    rows = _load(RESULTS / args.input)
    report_dir = RESULTS / args.out_dir
    map_dir = report_dir / "maps"
    map_dir.mkdir(parents=True, exist_ok=True)
    graph = OSMnxNetwork.from_graphml(GRAPHML).graph
    sections = []
    for row in rows:
        bounds = _shared_bounds(row)
        timeline = []
        snapshots = row["arms"]["A"]["temporal"]["snapshots"]
        for index, snapshot in enumerate(snapshots):
            minute = snapshot["minute_after_report"]
            rendered = _row_at(row, index)
            map_bounds = bounds
            if row["scenario_id"] in focus_scenarios and minute >= args.focus_from_minute:
                map_bounds = _focused_bounds(rendered)
            path = render_row(rendered, graph, map_dir, bounds=map_bounds)
            zoom_class = (
                " focused"
                if row["scenario_id"] in focus_scenarios
                and minute >= args.focus_from_minute
                else ""
            )
            hits = " / ".join(
                f"{arm} {'●' if row['arms'][arm]['temporal']['snapshots'][index]['hit'] else '×'}"
                for arm in "ABC"
            )
            probs = " / ".join(
                f"{arm} {_pct(row['arms'][arm]['temporal']['snapshots'][index]['truth_probability'])}"
                for arm in "ABC"
            )
            timeline.append(
                f'<article class="time{zoom_class}">'
                f'<h3>신고 +{minute}분 <span>{hits}</span></h3>'
                f'<p>실제 위치 확률: {probs}</p>'
                f'<a href="maps/{path.name}"><img loading="lazy" src="maps/{path.name}" '
                f'alt="{html.escape(row["scenario_id"])} +{minute}분 A/B/C"/></a></article>'
            )
        summary = " / ".join(
            f"{arm} {_pct(row['arms'][arm]['temporal']['time_matched_hit_rate'])}"
            for arm in "ABC"
        )
        mass = " / ".join(
            f"{arm} {_pct(row['arms'][arm]['temporal']['mean_truth_probability'])}"
            for arm in "ABC"
        )
        sections.append(
            '<section class="scenario">'
            f'<h2>{html.escape(row["scenario_id"])}</h2>'
            f'<p>{row["path_length_m"]:.0f}m OSM 도보궤적 · 시간매칭 적중률 {summary}'
            f'<br/>동시간대 실제위치 평균확률 {mass}</p>'
            + "".join(timeline) + "</section>"
        )
    document = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>EXAONE 시간축 A/B/C</title>
<style>body{margin:0;background:#f3f5f8;color:#111827;font-family:-apple-system,BlinkMacSystemFont,"Noto Sans KR",sans-serif}
main{max-width:1280px;margin:auto;padding:28px}.intro,.scenario,.time{background:#fff;border:1px solid #dfe4ea;border-radius:18px;padding:22px;margin-bottom:24px;box-shadow:0 3px 14px #0f172a0d}
.time{box-shadow:none;margin-top:18px}h1,h2,h3{margin:0 0 10px}h3 span{float:right;color:#475569;font-size:15px}p{color:#64748b;line-height:1.65}.time img{display:block;width:100%;height:auto;border-radius:12px}.time.focused img{width:100%;max-width:none}</style></head><body><main>
<section class="intro"><h1>EXAONE E2E 시간축 확률지도·알림셀 매칭</h1>
<p>A=거리 기준, B=EXAONE 비개인화, C=EXAONE Persona 개인화. 신고 후 0·45·90·135분에 각각 다시 계산한 POA에서 동일 예산 D1 19셀+D2 19셀을 선택하고, 같은 시간대 OSM 정답 위치와 1:1로 매칭했다. 실제 푸시 도달률이 아니라 알림 기회 상한이다.</p></section>
""" + "".join(sections) + "</main></body></html>"
    report = report_dir / "index.html"
    report.write_text(document, encoding="utf-8")
    print(f"saved={report} scenarios={len(rows)} maps={len(rows) * 4}")


if __name__ == "__main__":
    main()
