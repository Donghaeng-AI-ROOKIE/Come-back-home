"""P2-2 실험A — EXAONE prior 반경 μ 보정폭 폭주 임계 (LLM 호출 0회).

guardrail.RADIUS_MU_ADJUST 는 LLM 의 반경 등급(상/중/하)을 μ±0.4 로 매핑한다
(중앙값 ×1.49 / ×0.67). 이 실험은 "±0.4 가 왜 상한인가"를 실측으로 뒷받침한다:
μ 보정폭을 ±0.8 까지 쓸어 어느 폭부터 분포가 폭주(상식 밴드 이탈·알림 타겟
폭발·과잉 확신)하는지 잰다. LLM 정답이 없어도 가능한 부분 — 등급 매핑 자체의
최적화(실험 B)는 EXAONE 서빙 후 골드셋으로.

지표 (statistical 300워커, seed {42,43,44} 평균, 경과 3h, 정릉 3km 캐시):
  - median_ratio : 이론 중앙값 배율 e^dμ (참조)
  - dist_ratio   : 워커 이탈거리 중앙값 / 원 Koester 중앙값 — sim_testset 밴드 0.2~1.5
  - coverage80   : 누적 80% 셀 수 — 알림 타겟 크기 (폭주 = 급증, 과잉 확신 = 급감)
  - roadnet_radius : P1-3 동적 반경이 이 μ 로 계산될 때의 로딩 반경(부하 상호작용)

실행: backend/ 에서  .venv/bin/python experiments/prior_mapping/run_mu_adjust.py
"""

import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from app.geo import envlayer, h3grid, roadnet
from app.phase2 import radius, simulation
from app.schemas.persona import PersonaType
from app.schemas.prediction import LognormalParams
from sim_testset import LKP, make_persona, make_prior

N_WALKERS = 300
SEEDS = [42, 43, 44]
ELAPSED = 3.0
DMU = [-0.8, -0.6, -0.4, -0.2, 0.0, 0.2, 0.4, 0.6, 0.8]
BAND = (0.2, 1.5)                 # sim_testset dist_ratio 상식 밴드
OUT_DIR = Path(__file__).resolve().parent / "results"


def coverage80(poa: dict[str, float]) -> int:
    acc, n = 0.0, 0
    for _, p in sorted(poa.items(), key=lambda kv: kv[1], reverse=True):
        acc += p
        n += 1
        if acc >= 0.8:
            return n
    return n


def walker_median_km(poa: dict[str, float]) -> float:
    dists: list[float] = []
    for cell, p in poa.items():
        dists += [h3grid.haversine_km(LKP, h3grid.cell_center(cell))] * round(p * N_WALKERS)
    return statistics.median(dists) if dists else 0.0


if __name__ == "__main__":
    net = roadnet.get_network(LKP)
    envlayer.attach(net, LKP)
    persona = make_persona(PersonaType.dementia, 78, True)
    base_prior = make_prior(PersonaType.dementia, True)
    base = base_prior.radius_lognormal
    koester_median = math.exp(base.mu)

    rows = []
    for dmu in DMU:
        params = LognormalParams(mu=base.mu + dmu, sigma=base.sigma)
        prior = base_prior.model_copy(update={"radius_lognormal": params})
        ratios, covs = [], []
        for seed in SEEDS:
            poa = simulation.run_monte_carlo(LKP, prior, persona, ELAPSED,
                                             mode="statistical", net=net,
                                             n_walkers=N_WALKERS, seed=seed)
            ratios.append(walker_median_km(poa) / koester_median)
            covs.append(coverage80(poa))
        ratio_m = statistics.mean(ratios)
        rows.append({
            "dmu": dmu,
            "median_ratio_theory": round(math.exp(dmu), 2),
            "dist_ratio": round(ratio_m, 3),
            "in_band": BAND[0] <= ratio_m <= BAND[1],
            "coverage80": round(statistics.mean(covs), 1),
            "roadnet_radius_m": radius.roadnet_radius_m(params, ELAPSED, radius.vmax_kmh(persona)),
        })

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "mu_adjust.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# P2-2 실험A — 반경 μ 보정폭 폭주 임계", "",
             f"조건: 치매+끌림점, statistical {N_WALKERS}워커, seed {SEEDS} 평균, "
             f"경과 {ELAPSED}h, 정릉 3km 캐시 (LLM 0회). 현행 가드레일 = ±0.4", "",
             "| dμ | 중앙값 배율(이론) | dist_ratio | 밴드(0.2~1.5) | coverage80(셀) | 동적 로딩 반경 |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        mark = " ◀ 가드레일" if abs(abs(r["dmu"]) - 0.4) < 1e-9 else ""
        lines.append(f"| {r['dmu']:+.1f} | ×{r['median_ratio_theory']} | {r['dist_ratio']} "
                     f"| {'O' if r['in_band'] else '**X**'} | {r['coverage80']} "
                     f"| {r['roadnet_radius_m']}m{mark} |")
    md = "\n".join(lines) + "\n"
    (OUT_DIR / "mu_adjust.md").write_text(md, encoding="utf-8")
    print(md)
