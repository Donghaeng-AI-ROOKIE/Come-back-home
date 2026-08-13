"""P1-6 — α-pool 0.7/0.3 · topdown 0.6/0.4·σ0.3 · 전환기준 tips≥3 재검증
(실험 상세 설계안 [대흠] 몫. 선행조건 = 서영 P1-2(PR #70, 전부 도보) 머지 완료).

세 상수군을 각각 재검증한다:
  A. α-pool: combined = alpha_pool([bottom-up, statistical], [α, 1-α]).
     bu/stat 시뮬은 seed당 1회만 돌리고 α만 바꿔 결합 — α 효과를 순수 분리.
  B. topdown 0.6·ring + 0.4·bump·(ring+ε), 끌림점 σ=0.3km: 파라미터화 복제본을
     만들어 (0.6, 0.3)이 실제 topdown_poa 와 일치함을 검증한 뒤 스윕.
  C. 전환기준 tips≥3: 같은 bu/stat 쌍에서 linear vs log_linear 의 좁힘 정도를
     정량화 — "몇 건부터 좁혀도 되는가"의 위험 크기를 수치로.

statistical/agent 모드 모두 LLM 스텁(오프라인) — 비용 0, 재현 가능.

실행: backend/ 에서  .venv/bin/python experiments/pool_weights/run_pool_weights.py
"""

import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from app.geo import envlayer, h3grid, roadnet
from app.phase2 import combine, radius, simulation, topdown
from app.schemas.persona import PersonaType
from sim_testset import ATTRACTION, LKP, make_persona, make_prior

N_WALKERS = 300
SEEDS = [42, 43, 44]
ELAPSED = 3.0
ALPHAS = [0.5, 0.6, 0.7, 0.8, 0.9]          # α = bottom-up 가중 (현행 0.7)
RING_WS = [0.5, 0.6, 0.7]                    # topdown ring 가중 (현행 0.6)
SIGMAS = [0.2, 0.3, 0.5]                     # 끌림점 범프 σ km (현행 0.3)
ATTR_RADIUS_KM = 0.5                         # "끌림점 부근" 판정 반경
OUT_DIR = Path(__file__).resolve().parent / "results"


# ── 지표 ─────────────────────────────────────────────────────────────

def coverage80(poa: dict[str, float]) -> int:
    """누적 80% 질량에 필요한 최소 셀 수 — 알림 타겟 크기(greedy 80%)와 직결."""
    acc, n = 0.0, 0
    for _, p in sorted(poa.items(), key=lambda kv: kv[1], reverse=True):
        acc += p
        n += 1
        if acc >= 0.8:
            return n
    return n


def attraction_share(poa: dict[str, float]) -> float:
    """끌림점 반경 500m 셀 질량 — 개인화(목적지 성향) 신호의 보존 정도."""
    return sum(p for c, p in poa.items()
               if h3grid.haversine_km(ATTRACTION, h3grid.cell_center(c)) <= ATTR_RADIUS_KM)


def js_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    cells = set(p) | set(q)
    eps = 1e-12
    js = 0.0
    for c in cells:
        a, b = p.get(c, 0.0) + eps, q.get(c, 0.0) + eps
        m = (a + b) / 2
        js += 0.5 * (a * math.log(a / m) + b * math.log(b / m))
    return js


# ── A. α-pool 스윕 ───────────────────────────────────────────────────

def sweep_alpha(pairs) -> list[dict]:
    rows = []
    for alpha in ALPHAS:
        per_seed = []
        for bu, stat in pairs:
            comb = combine.alpha_pool([bu, stat], alphas=[alpha, 1 - alpha], mode="linear")
            base = combine.alpha_pool([bu, stat], alphas=[0.7, 0.3], mode="linear")
            per_seed.append({
                "coverage80": coverage80(comb),
                "attraction_share": attraction_share(comb),
                "js_vs_default": js_divergence(comb, base),
            })
        rows.append({
            "alpha_bu": alpha,
            "coverage80": round(statistics.mean(d["coverage80"] for d in per_seed), 1),
            "attraction_share": round(statistics.mean(d["attraction_share"] for d in per_seed), 4),
            "js_vs_default": round(statistics.mean(d["js_vs_default"] for d in per_seed), 5),
        })
    return rows


# ── B. topdown 가중·σ 스윕 (파라미터화 복제본, 원본과 일치 검증 후 사용) ──

def topdown_replica(lkp, prior, persona, elapsed, ring_w: float, sigma_bump: float):
    mu, sigma = prior.radius_lognormal.mu, prior.radius_lognormal.sigma
    median_km = math.exp(mu)
    max_km = radius.p95_km(prior.radius_lognormal, elapsed, radius.vmax_kmh(persona))
    cells = h3grid.cells_within_km(lkp, max_km)
    attractions = []
    if persona:
        for ap in persona.attraction_points:
            w = prior.attraction_weights.get(ap.label, 0.0)
            if w > 0 and ap.location:
                attractions.append((ap.location, w))
    scores = {}
    bump_w = 1.0 - ring_w
    for cell in cells:
        center = h3grid.cell_center(cell)
        d = max(h3grid.haversine_km(lkp, center), 1e-3)
        ring = math.exp(-((math.log(d) - math.log(median_km)) ** 2) / (2 * sigma ** 2)) / d
        bump = sum(w * math.exp(-(h3grid.haversine_km(center, loc) ** 2)
                                / (2 * sigma_bump ** 2))
                   for loc, w in attractions)
        scores[cell] = ring_w * ring + bump_w * bump * (ring + 1e-9)
    total = sum(scores.values())
    return {c: v / total for c, v in scores.items()} if total > 0 else scores


def sweep_topdown(persona, prior) -> tuple[float, list[dict]]:
    original = topdown.topdown_poa(LKP, prior, persona, ELAPSED)
    replica = topdown_replica(LKP, prior, persona, ELAPSED, 0.6, 0.3)
    max_diff = max(abs(original.get(c, 0.0) - replica.get(c, 0.0))
                   for c in set(original) | set(replica))
    rows = []
    for ring_w in RING_WS:
        for sig in SIGMAS:
            poa = topdown_replica(LKP, prior, persona, ELAPSED, ring_w, sig)
            rows.append({
                "ring_w": ring_w, "sigma_km": sig,
                "coverage80": coverage80(poa),
                "attraction_share": round(attraction_share(poa), 4),
                "peak_prob": round(max(poa.values()), 4),
            })
    return max_diff, rows


# ── C. 전환기준 — linear vs log_linear 좁힘 정량화 ──────────────────

def mode_contrast(pairs) -> dict:
    lin, log = [], []
    for bu, stat in pairs:
        lin.append(coverage80(combine.alpha_pool([bu, stat], [0.7, 0.3], mode="linear")))
        log.append(coverage80(combine.alpha_pool([bu, stat], [0.7, 0.3], mode="log_linear")))
    lin_m, log_m = statistics.mean(lin), statistics.mean(log)
    return {"coverage80_linear": round(lin_m, 1), "coverage80_log_linear": round(log_m, 1),
            "shrink_pct": round((1 - log_m / lin_m) * 100, 1)}


def to_md(alpha_rows, td_diff, td_rows, contrast) -> str:
    lines = ["# P1-6 α-pool·topdown 가중·전환기준 재검증 결과", "",
             f"조건: 치매 78세+끌림점, 경과 {ELAPSED}h, bu=agent(스텁)/stat {N_WALKERS}워커, "
             f"seed {SEEDS} 평균, 정릉 3km 캐시 도로망", "",
             "## A. α-pool 스윕 (α = bottom-up 가중, 현행 0.7)", "",
             "| α_bu | coverage80(셀) | 끌림점 질량 | JS vs 현행 |", "|---|---|---|---|"]
    for r in alpha_rows:
        lines.append(f"| {r['alpha_bu']} | {r['coverage80']} | {r['attraction_share']} "
                     f"| {r['js_vs_default']} |")
    lines += ["", f"## B. topdown 스윕 (복제본 검증: 현행 파라미터 재현 최대오차 {td_diff:.2e})",
              "", "| ring_w | σ(km) | coverage80 | 끌림점 질량 | 최대 셀 확률 |", "|---|---|---|---|---|"]
    for r in td_rows:
        star = " ◀ 현행" if r["ring_w"] == 0.6 and r["sigma_km"] == 0.3 else ""
        lines.append(f"| {r['ring_w']} | {r['sigma_km']} | {r['coverage80']} "
                     f"| {r['attraction_share']} | {r['peak_prob']}{star} |")
    lines += ["", "## C. 전환기준 (linear→log_linear 좁힘 크기)", "",
              f"- coverage80: linear {contrast['coverage80_linear']}셀 → "
              f"log_linear {contrast['coverage80_log_linear']}셀 "
              f"(**{contrast['shrink_pct']}% 축소**)",
              "- 이 축소가 '전 분포가 동의하는 곳만 남기기'의 크기 — 제보 1~2건 단계에서",
              "  발동하면 오제보 1건이 수색 범위를 이만큼 잘라낸다. ≥3 유지 근거.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    net = roadnet.get_network(LKP)
    envlayer.attach(net, LKP)
    persona = make_persona(PersonaType.dementia, 78, True)
    prior = make_prior(PersonaType.dementia, True)

    pairs = []
    for seed in SEEDS:
        bu = simulation.run_monte_carlo(LKP, prior, persona, ELAPSED, mode="agent",
                                        net=net, n_walkers=N_WALKERS, seed=seed)
        stat = simulation.run_monte_carlo(LKP, prior, persona, ELAPSED, mode="statistical",
                                          net=net, n_walkers=N_WALKERS, seed=seed)
        pairs.append((bu, stat))

    alpha_rows = sweep_alpha(pairs)
    td_diff, td_rows = sweep_topdown(persona, prior)
    contrast = mode_contrast(pairs)

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "pool_weights.json").write_text(
        json.dumps({"alpha": alpha_rows, "topdown_replica_max_diff": td_diff,
                    "topdown": td_rows, "mode_contrast": contrast},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    md = to_md(alpha_rows, td_diff, td_rows, contrast)
    (OUT_DIR / "pool_weights.md").write_text(md, encoding="utf-8")
    print(md)
