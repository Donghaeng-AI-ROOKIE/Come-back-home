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

# --all 로 전량 렌더링할 때 쓰는 인덱스 파일명. 시나리오 x 시점이 100장을
# 넘어가면 파일명만으로는 훑기 어려워서, 승패 표를 한 장으로 같이 남긴다.
INDEX_NAME = "INDEX.md"


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


def _write_index(rows: list[dict], minutes: list[int], out_dir: Path) -> Path:
    """시나리오 x 시점 승패를 한 표로 남긴다 (파일이 100장을 넘어가므로)."""
    lines = [
        "# 전량 렌더링 인덱스",
        "",
        f"시나리오 {len(rows)}개 x 시점 {len(minutes)}개 = {len(rows) * len(minutes)}장.",
        ("각 SVG는 A/B/C 3패널이다. 검정 점선 = D1(실종지점 k-ring 2, 세 군 공통), "
         "검정 실선 = 그 군이 예측으로 고른 알림 셀(D1 제외분), 빨간 선 = 정답 이동 "
         "경로, 파란 원 = 실종 지점, 빨간 마름모 = 정답 목적지, 색면 = POA 확률."),
        "",
        "| 시나리오 | 층 | 행동 | " + " | ".join(f"{m}분" for m in minutes) + " |",
        "|---|---|---|" + "---|" * len(minutes),
    ]
    for row in sorted(rows, key=lambda r: r["scenario_id"]):
        cells = []
        for minute in minutes:
            snaps = row["arms"]["A"]["temporal"]["snapshots"]
            idx = next((i for i, s in enumerate(snaps)
                        if s["minute_after_report"] == minute), None)
            if idx is None:
                cells.append("-")
                continue
            marks = "".join(
                arm if row["arms"][arm]["temporal"]["snapshots"][idx]["hit"] else "·"
                for arm in "ABC"
            )
            cells.append(marks)
        lines.append(
            f"| {row['scenario_id']} | {row['stratum']} | "
            f"{BEHAVIOR_LABELS[row['truth_behavior']]} | " + " | ".join(cells) + " |"
        )
    lines += [
        "",
        "표기: 적중한 군의 알파벳만 표시하고 실패는 `·`. 예) `A·C` = A 성공, B 실패, C 성공.",
        "",
        ("적중은 '정답 위치가 그 군의 알림 셀(D1 + 예측 19셀) 안에 있었는가'이며, "
         "실제 푸시 전달·열람·제보·발견을 뜻하지 않는다."),
    ]
    path = out_dir / INDEX_NAME
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument(
        "--all", action="store_true",
        help="SELECTIONS 대신 모든 시나리오 x 모든 시점을 렌더링하고 INDEX.md 를 만든다",
    )
    args = parser.parse_args()

    rows = _load(RESULTS / args.input)
    by_id = {row["scenario_id"]: row for row in rows}
    graph = OSMnxNetwork.from_graphml(GRAPHML).graph
    out_dir = RESULTS / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.all:
        minutes = sorted({
            snapshot["minute_after_report"]
            for row in rows
            for snapshot in row["arms"]["A"]["temporal"]["snapshots"]
        })
        count = 0
        for row in sorted(rows, key=lambda r: r["scenario_id"]):
            available = {s["minute_after_report"]
                         for s in row["arms"]["A"]["temporal"]["snapshots"]}
            for minute in minutes:
                if minute not in available:
                    continue
                render_selected(row, minute, graph, out_dir)
                count += 1
        index = _write_index(rows, minutes, out_dir)
        print(f"{count}장 렌더링 · 인덱스 {index}")
        return

    for minute, scenario_id in SELECTIONS:
        path = render_selected(by_id[scenario_id], minute, graph, out_dir)
        print(path)


if __name__ == "__main__":
    main()
