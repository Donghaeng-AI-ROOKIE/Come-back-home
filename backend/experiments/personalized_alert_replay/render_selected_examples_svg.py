"""제안서용 시간별 대표 사례를 확대된 독립 SVG로 내보낸다."""

from __future__ import annotations

import argparse
import html
from pathlib import Path

from app.geo.roadnet import OSMnxNetwork
from experiments.personalized_alert_replay.render_persona_abc_report import (
    GAP,
    GRAPHML,
    MAP_H,
    MAP_W,
    MAP_X,
    MAP_Y,
    PANEL_W,
    RESULTS,
    _load,
    _panel,
    _road_svg,
)
from experiments.personalized_alert_replay.render_temporal_report import (
    _focused_bounds,
    _row_at,
)


BEHAVIOR_LABELS = {
    "stay": "정지형",
    "move": "지속 이동형",
    "backtrack": "왕복·순환형",
    "hide": "정지 후 재이동·은폐형",
}

SELECTIONS = (
    (0, "SP10-neutral"),
    (45, "SP10-neutral"),
    (90, "SP04-consistent"),
    (135, "SP05-consistent"),
)


def _verdict(row: dict, index: int) -> tuple[str, str]:
    parts = []
    filename_parts = []
    for arm in "ABC":
        hit = bool(row["arms"][arm]["temporal"]["snapshots"][index]["hit"])
        label = "성공" if hit else "실패"
        parts.append(f"{arm} {label}")
        filename_parts.append(f"{arm}{label}")
    return " · ".join(parts), "_".join(filename_parts)


def render_selected(row: dict, minute: int, graph, out_dir: Path) -> Path:
    snapshots = row["arms"]["A"]["temporal"]["snapshots"]
    index = next(
        idx for idx, snapshot in enumerate(snapshots)
        if snapshot["minute_after_report"] == minute
    )
    rendered = _row_at(row, index)
    bounds = _focused_bounds(rendered)
    roads = _road_svg(graph, bounds)
    verdict, filename_verdict = _verdict(row, index)
    behavior = BEHAVIOR_LABELS[row["truth_behavior"]]

    total_w = PANEL_W * 3 + GAP * 2
    header_h = 105
    footer_h = 30
    content_h = 520
    total_h = header_h + content_h + footer_h
    panels = []
    for panel_index, arm in enumerate("ABC"):
        x = panel_index * (PANEL_W + GAP)
        panels.append(
            f'<g transform="translate({x},{header_h})">{_panel(arm, rendered, bounds)}</g>'
        )

    title = f"{minute}분 · {row['scenario_id']} · {behavior}"
    footer = (
        f"{row['scenario_id']} | {row['stratum']} | "
        f"{row['design'].get('home_provider') or ''} | "
        f"{row['design'].get('home_match') or ''}"
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="{total_h}" '
        f'viewBox="0 0 {total_w} {total_h}" role="img" '
        f'aria-label="{html.escape(title)} · {html.escape(verdict)}">'
        '<style>text{font-family:"Apple SD Gothic Neo","Noto Sans KR",sans-serif}</style>'
        f'<rect width="{total_w}" height="{total_h}" rx="18" fill="#fff"/>'
        f'<text x="22" y="40" font-size="25" font-weight="800" fill="#111827">'
        f'{html.escape(title)}</text>'
        f'<text x="22" y="76" font-size="17" font-weight="750" fill="#111827">'
        f'{html.escape(verdict)}</text>'
        f'<defs><clipPath id="map-clip"><rect x="{MAP_X}" y="{MAP_Y}" '
        f'width="{MAP_W}" height="{MAP_H}"/></clipPath>'
        f'<g id="roads" fill="none" stroke="#d7dce2" stroke-width="0.75">{roads}</g></defs>'
        + "".join(panels)
        + f'<text x="0" y="{total_h - 7}" font-size="13" font-weight="600" '
        f'fill="#334155">{html.escape(footer)}</text></svg>'
    )

    safe_behavior = behavior.replace("·", "-").replace(" ", "_")
    filename = (
        f"{minute:03d}분_{row['scenario_id']}_{safe_behavior}_{filename_verdict}.svg"
    )
    path = out_dir / filename
    path.write_text(svg, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    rows = _load(RESULTS / args.input)
    by_id = {row["scenario_id"]: row for row in rows}
    graph = OSMnxNetwork.from_graphml(GRAPHML).graph
    out_dir = RESULTS / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    for minute, scenario_id in SELECTIONS:
        path = render_selected(by_id[scenario_id], minute, graph, out_dir)
        print(path)


if __name__ == "__main__":
    main()
