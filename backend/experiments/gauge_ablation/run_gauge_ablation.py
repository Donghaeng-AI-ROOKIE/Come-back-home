"""P1-4 — road/env strength 노브 그리드서치 (실험 상세 설계안 [대흠] 몫).

노브 2개(config.road_preference_strength·env_response_strength, 기본 둘 다 1.0)는
소비 메커니즘이 독립이다:
  - 도로 위계 선호: 치매 한정, 갈림길 선택 확률에 지수로 (gauges.road_preference)
  - 개인 환경 반응: env_responses 보유 페르소나 한정, 사정거리 내 배수
    (gauges.env_response_weight, water 100m·나머지 60m)

따라서 1-D 스윕으로 각 노브의 효과 곡선(용량-반응)을 재고, 3×3 코너 그리드로
상식 지표(sim_testset 밴드) 회귀만 확인한다. 전부 statistical 모드(LLM 0회) +
seed 고정 + 디스크 캐시 도로망 — 비용 0, 재현 가능.

지표:
  - avoid_share  : 간선(trunk/primary) 성격 셀에 실린 확률 질량 — strength↑ 면 ↓ 기대
  - prefer_share : 이면(residential 계열) 성격 셀 질량 — strength↑ 면 ↑ 기대
  - water_share  : 물가 사정거리(수변 100m) 셀 질량 — env strength↑ 면 ↑ 기대(접근 반응)
  - dist_ratio   : 워커 이탈거리 중앙값 / Koester 중앙값(√t 스케일) — 0.2~1.5 밴드
  - 적용 범위 검증: ID 페르소나는 도로 선호 중립(치매 한정)이어야 함

실행: backend/ 에서  .venv/bin/python experiments/gauge_ablation/run_gauge_ablation.py
"""

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from app.config import settings
from app.geo import envlayer, h3grid, roadnet
from app.phase2 import simulation
from app.phase2.gauges import _ENV_RESPONSE_RANGE_M, _ROAD_PREFERENCE
from app.schemas.persona import EnvResponse, PersonaType
from sim_testset import LKP, make_persona, make_prior

N_WALKERS = 300
SEED = 42
SEEDS = [42, 43, 44]              # 스윕은 다중 seed 평균 — 단일 seed 경로 노이즈와 효과 구분
ELAPSED = 3.0                     # 거리·선택이 충분히 누적되는 중간 경과
SWEEP = [0.0, 0.5, 1.0, 1.5, 2.0]
GRID = [0.0, 1.0, 2.0]
OUT_DIR = Path(__file__).resolve().parent / "results"


# ── 셀 분류 (도로 위계 / 수변 사정거리) ──────────────────────────────

def classify_road_cells(net) -> dict[str, float]:
    """셀 → 소속 노드들의 인접 에지 선호값 평균. <0.95 기피 / >1.05 선호."""
    per_cell: dict[str, list[float]] = defaultdict(list)
    for u, v, attrs in net.graph.edges(data=True):
        hw = attrs.get("highway")
        if isinstance(hw, list):
            hw = hw[0] if hw else None
        pref = _ROAD_PREFERENCE.get(hw, 1.0)
        for n in (u, v):
            per_cell[h3grid.cell_of(net.node_location(n))].append(pref)
    return {c: statistics.mean(s) for c, s in per_cell.items()}


def water_cells(net) -> set[str]:
    """수변 사정거리(_ENV_RESPONSE_RANGE_M['water']) 안 노드가 있는 셀."""
    rng = _ENV_RESPONSE_RANGE_M["water"]
    cells: set[str] = set()
    for n in net.graph.nodes:
        env = net.env(n)
        w = env.get("water_m") if env else None
        if isinstance(w, (int, float)) and w <= rng:
            cells.add(h3grid.cell_of(net.node_location(n)))
    return cells


def share(poa: dict[str, float], cells: set[str]) -> float:
    return sum(p for c, p in poa.items() if c in cells)


def dist_ratio(poa: dict[str, float], prior, elapsed: float) -> float:
    dists: list[float] = []
    for cell, p in poa.items():
        dists += [h3grid.haversine_km(LKP, h3grid.cell_center(cell))] * round(p * N_WALKERS)
    med = statistics.median(dists) if dists else 0.0
    koester_med = math.exp(prior.radius_lognormal.mu) * max(1.0, elapsed) ** 0.5
    return med / koester_med


def run(persona, prior, elapsed=ELAPSED, seed=SEED):
    return simulation.run_monte_carlo(
        LKP, prior, persona, elapsed, mode="statistical",
        net=NET, n_walkers=N_WALKERS, seed=seed)


def mean_over_seeds(fn) -> dict[str, float]:
    """seed별 지표 dict 를 평균 — 값은 (평균, 최소, 최대)."""
    per_seed = [fn(s) for s in SEEDS]
    keys = per_seed[0].keys()
    return {k: (round(statistics.mean(d[k] for d in per_seed), 4),
                round(min(d[k] for d in per_seed), 4),
                round(max(d[k] for d in per_seed), 4)) for k in keys}


# ── 실험 ─────────────────────────────────────────────────────────────

def sweep_road() -> list[dict]:
    """road_preference_strength 1-D 스윕 — 치매(적용, 다중 seed) vs ID(중립 검증)."""
    rows = []
    for ptype, label in [(PersonaType.dementia, "치매"),
                         (PersonaType.intellectual_disability, "ID")]:
        persona = make_persona(ptype, 78 if ptype == PersonaType.dementia else 14, True)
        prior = make_prior(ptype, True)
        for s in SWEEP:
            settings.road_preference_strength = s

            def metrics(seed):
                poa = run(persona, prior, seed=seed)
                return {"avoid_share": share(poa, AVOID_CELLS),
                        "prefer_share": share(poa, PREFER_CELLS),
                        "dist_ratio": dist_ratio(poa, prior, ELAPSED)}

            agg = mean_over_seeds(metrics)
            rows.append({"persona": label, "strength": s, **agg})
    settings.road_preference_strength = 1.0
    return rows


def sweep_env() -> list[dict]:
    """env_response_strength 1-D 스윕 — 수변 접근 반응 페르소나 (다중 seed)."""
    persona = make_persona(PersonaType.dementia, 78, True)
    persona.env_responses = [EnvResponse(feature="water", direction="접근", strength=0.9)]
    prior = make_prior(PersonaType.dementia, True)
    rows = []
    for s in SWEEP:
        settings.env_response_strength = s

        def metrics(seed):
            poa = run(persona, prior, seed=seed)
            return {"water_share": share(poa, WATER_CELLS),
                    "dist_ratio": dist_ratio(poa, prior, ELAPSED)}

        rows.append({"strength": s, **mean_over_seeds(metrics)})
    settings.env_response_strength = 1.0
    return rows


def sanity_grid() -> list[dict]:
    """3×3 그리드에서 상식 지표(밴드·단조성) 회귀 확인 — 치매 시나리오."""
    persona = make_persona(PersonaType.dementia, 78, True)
    persona.env_responses = [EnvResponse(feature="water", direction="접근", strength=0.9)]
    prior = make_prior(PersonaType.dementia, True)
    rows = []
    for rs in GRID:
        for es in GRID:
            settings.road_preference_strength = rs
            settings.env_response_strength = es
            means, ok_band = [], True
            for elapsed in [1.0, 3.0, 6.0]:
                poa = run(persona, prior, elapsed)
                means.append(sum(h3grid.haversine_km(LKP, h3grid.cell_center(c)) * p
                                 for c, p in poa.items()))
                if elapsed == 1.0:
                    ok_band = 0.2 <= dist_ratio(poa, prior, elapsed) <= 1.5
            monotonic = means == sorted(means)
            rows.append({"road": rs, "env": es, "monotonic": monotonic,
                         "band_1h": ok_band,
                         "mean_km_1h": round(means[0], 3), "mean_km_6h": round(means[2], 3)})
    settings.road_preference_strength = 1.0
    settings.env_response_strength = 1.0
    return rows


def _fmt(v) -> str:
    m, lo, hi = v
    return f"{m} ({lo}~{hi})"


def to_md(road, env, grid) -> str:
    lines = ["# P1-4 road/env strength 그리드서치 결과",
             "",
             f"조건: statistical {N_WALKERS}워커, 스윕 seed={SEEDS} 평균(최소~최대), "
             f"경과 {ELAPSED}h, 정릉 3km 캐시 도로망 (LLM 호출 0회)",
             "",
             "## 1. road_preference_strength 스윕 (치매=적용 / ID=중립 검증)",
             "", "| 페르소나 | strength | 기피셀 질량 | 선호셀 질량 | dist_ratio |", "|---|---|---|---|---|"]
    for r in road:
        lines.append(f"| {r['persona']} | {r['strength']} | {_fmt(r['avoid_share'])} "
                     f"| {_fmt(r['prefer_share'])} | {_fmt(r['dist_ratio'])} |")
    lines += ["", "## 2. env_response_strength 스윕 (수변 접근 0.9)",
              "", "| strength | 수변셀 질량 | dist_ratio |", "|---|---|---|"]
    for r in env:
        lines.append(f"| {r['strength']} | {_fmt(r['water_share'])} | {_fmt(r['dist_ratio'])} |")
    lines += ["", "## 3. 3×3 상식 지표 회귀 (road × env)",
              "", "| road | env | 단조성 | 1h 밴드 | 1h 평균km | 6h 평균km |", "|---|---|---|---|---|---|"]
    for r in grid:
        lines.append(f"| {r['road']} | {r['env']} | {'O' if r['monotonic'] else 'X'} "
                     f"| {'O' if r['band_1h'] else 'X'} | {r['mean_km_1h']} | {r['mean_km_6h']} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    NET = roadnet.get_network(LKP)
    envlayer.attach(NET, LKP)
    road_scores = classify_road_cells(NET)
    AVOID_CELLS = {c for c, s in road_scores.items() if s < 0.95}
    PREFER_CELLS = {c for c, s in road_scores.items() if s > 1.05}
    WATER_CELLS = water_cells(NET)
    print(f"셀 분류: 기피 {len(AVOID_CELLS)} / 선호 {len(PREFER_CELLS)} / 수변 {len(WATER_CELLS)}")

    road = sweep_road()
    env = sweep_env()
    grid = sanity_grid()

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "gauge_ablation.json").write_text(
        json.dumps({"road": road, "env": env, "grid": grid}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    md = to_md(road, env, grid)
    (OUT_DIR / "gauge_ablation.md").write_text(md, encoding="utf-8")
    print(md)
