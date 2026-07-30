"""P2-2 실험B — prior 매핑 상수 3종 민감도 점검 (LLM 호출 0회).

목적: EPSILON / LEVEL_WEIGHTS / ATTRACTION_CAP 이 sanity 지표를 실제로
움직이는 살아있는 손잡이인지, 아니면 다른 장치(재정규화·cap 포화)에 흡수되는
무효 상수인지 판별한다. 움직이지 않는 상수는 현행 유지(YAGNI — 튜닝 대상 아님).

정답 좌표가 없으므로 "최적값"은 찾지 않는다(순환논법 — README 참조). 재는 것은
민감도뿐: 상수를 스윙했을 때 (1) 가드레일 통과 후 분포(해석층)와 (2) MC POA
지표(실측층)가 seed 간 자연 변동보다 크게 움직이는가.

실행: backend/ 에서  .venv/bin/python experiments/prior_mapping/sweep_sensitivity.py
"""

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from app.geo import envlayer, h3grid, roadnet
from app.llm.exaone import _KOESTER_PARAMS
from app.phase2 import guardrail, simulation
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionEvidence, AttractionPoint, Persona, PersonaType
from app.schemas.prediction import PriorParams
from sim_testset import LKP, ATTRACTION

N_WALKERS = 300
SEEDS = [42, 43, 44]
OUT_DIR = Path(__file__).resolve().parent / "results"

# 끌림점 3개 시나리오 — cap 포화 여부와 배분 변화를 모두 볼 수 있는 최소 구성.
# B(2등)와 C(3등)는 실제 정릉 좌표 (A=옛집은 sim_testset 상수 재사용).
POINT_B = GeoPoint(lat=37.6047, lng=127.0121)   # 정릉시장
POINT_C = GeoPoint(lat=37.6089, lng=127.0172)   # 문구점


def make_persona3(ev_a: str, ev_b: str, ev_c: str) -> Persona:
    return Persona(
        id="sens-3ap", name="민감도", age=78, type=PersonaType.dementia, home=LKP,
        attraction_points=[
            AttractionPoint(label="옛집", location=ATTRACTION,
                            evidence=AttractionEvidence(ev_a)),
            AttractionPoint(label="정릉시장", location=POINT_B,
                            evidence=AttractionEvidence(ev_b)),
            AttractionPoint(label="문구점", location=POINT_C,
                            evidence=AttractionEvidence(ev_c)),
        ])


def mc_metrics(prior: PriorParams, persona: Persona, elapsed: float) -> dict:
    """seed 평균 (mean±seed범위): 1등 끌림점까지 평균거리, coverage80."""
    d_top, covs = [], []
    for seed in SEEDS:
        poa = simulation.run_monte_carlo(LKP, prior, persona, elapsed,
                                         mode="statistical", net=NET,
                                         n_walkers=N_WALKERS, seed=seed)
        d_top.append(sum(h3grid.haversine_km(ATTRACTION, h3grid.cell_center(c)) * p
                         for c, p in poa.items()))
        acc, n = 0.0, 0
        for _, p in sorted(poa.items(), key=lambda kv: kv[1], reverse=True):
            acc += p
            n += 1
            if acc >= 0.8:
                break
        covs.append(n)
    return {"d_top_km": round(statistics.mean(d_top), 3),
            "d_top_spread": round(max(d_top) - min(d_top), 3),
            "coverage80": round(statistics.mean(covs), 1),
            "cov_spread": round(max(covs) - min(covs), 1)}


def strategy_prior(probs: dict, weights: dict) -> PriorParams:
    return PriorParams(strategy_probs=probs, attraction_weights=weights,
                       radius_lognormal=_KOESTER_PARAMS[PersonaType.dementia],
                       reasoning="실험B")


# ── B-1. EPSILON — 전략 floor 가 개인화(seek_pull)를 얼마나 희석하나 ──────────
def sweep_epsilon() -> list[dict]:
    persona = make_persona3("previous_missing_found", "caregiver_report", "mention_only")
    default = {"route_following": 0.30, "direction_keeping": 0.25, "random_walk": 0.15,
               "backtracking": 0.05, "staying_put": 0.10, "landmark_seeking": 0.15}
    rows = []
    for eps in [0.005, 0.02, 0.05, 0.1]:
        old = guardrail.EPSILON
        guardrail.EPSILON = eps
        try:
            # LLM 이 개인화 극단(전부 landmark_seeking)을 낸 경우의 가드레일 통과 후 분포
            floored = guardrail.sanitize_strategy_probs({"landmark_seeking": 1.0}, default)
            p_seek = floored["landmark_seeking"]
            seek = mc_metrics(strategy_prior(floored, {"옛집": 1.0}), persona, 1.0)
            rand_probs = guardrail.sanitize_strategy_probs({"random_walk": 1.0}, default)
            rand = mc_metrics(strategy_prior(rand_probs, {"옛집": 1.0}), persona, 1.0)
        finally:
            guardrail.EPSILON = old
        rows.append({"eps": eps, "p_seek_floor후": round(p_seek, 3),
                     "d_seek": seek["d_top_km"], "d_rand": rand["d_top_km"],
                     "pull_gap_km": round(rand["d_top_km"] - seek["d_top_km"], 3),
                     "seed_spread": max(seek["d_top_spread"], rand["d_top_spread"])})
    return rows


# ── B-2. LEVEL_WEIGHTS — 등급비를 바꾸면 끌림점 배분이 실제로 변하나 ─────────
def sweep_level_weights() -> list[dict]:
    persona = make_persona3("caregiver_report", "caregiver_report", "caregiver_report")
    mix = {"route_following": 0.25, "direction_keeping": 0.15, "random_walk": 0.10,
           "backtracking": 0.05, "staying_put": 0.05, "landmark_seeking": 0.40}
    raw_levels = {"옛집": "상", "정릉시장": "중", "문구점": "하"}
    rows = []
    for name, lw in [("3:2:1(현행)", {"상": 3.0, "중": 2.0, "하": 1.0}),
                     ("4:2:1", {"상": 4.0, "중": 2.0, "하": 1.0}),
                     ("5:2:1", {"상": 5.0, "중": 2.0, "하": 1.0})]:
        old = guardrail.LEVEL_WEIGHTS
        guardrail.LEVEL_WEIGHTS = lw
        try:
            w = guardrail.sanitize_attraction_levels(raw_levels, persona)
            m = mc_metrics(strategy_prior(mix, w), persona, 3.0)
        finally:
            guardrail.LEVEL_WEIGHTS = old
        rows.append({"ratio": name,
                     "w_배분": {k: round(v, 3) for k, v in w.items()},
                     "w_top": round(max(w.values()), 3), **m})
    return rows


# ── B-3. ATTRACTION_CAP — 독식 상한이 POA 집중도를 실제로 조절하나 ───────────
def sweep_cap() -> list[dict]:
    # 1등이 발견이력+상 (uncapped 0.75) — cap 이 실제로 걸리는 구성
    persona = make_persona3("previous_missing_found", "caregiver_report", "mention_only")
    mix = {"route_following": 0.25, "direction_keeping": 0.15, "random_walk": 0.10,
           "backtracking": 0.05, "staying_put": 0.05, "landmark_seeking": 0.40}
    raw_levels = {"옛집": "상", "정릉시장": "중", "문구점": "하"}
    rows = []
    for cap in [0.4, 0.5, 0.6, 0.7, 0.8]:
        old = guardrail.ATTRACTION_CAP
        guardrail.ATTRACTION_CAP = cap
        try:
            w = guardrail.sanitize_attraction_levels(raw_levels, persona)
            m = mc_metrics(strategy_prior(mix, w), persona, 3.0)
        finally:
            guardrail.ATTRACTION_CAP = old
        rows.append({"cap": cap, "w_top": round(max(w.values()), 3),
                     "w_배분": {k: round(v, 3) for k, v in w.items()}, **m})
    return rows


if __name__ == "__main__":
    NET = roadnet.get_network(LKP)
    envlayer.attach(NET, LKP)
    results = {"epsilon": sweep_epsilon(),
               "level_weights": sweep_level_weights(),
               "attraction_cap": sweep_cap()}

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "sensitivity.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    L = ["# P2-2 실험B — 상수 민감도 점검 (LLM 0회)", "",
         f"statistical {N_WALKERS}워커 × seed {SEEDS} 평균, 정릉 3km 캐시, 끌림점 3개.",
         "판정 원칙: 지표 이동이 seed 간 변동(spread)보다 크면 '살아있는 손잡이'.", "",
         "## B-1. EPSILON (전략 floor) — 극단 개인화(전부 landmark_seeking) 희석도", "",
         "| ε | floor 후 P(seek) | d_seek(km) | d_rand(km) | pull 격차 | seed 변동 |",
         "|---|---|---|---|---|---|"]
    for r in results["epsilon"]:
        L.append(f"| {r['eps']} | {r['p_seek_floor후']} | {r['d_seek']} | {r['d_rand']} "
                 f"| {r['pull_gap_km']} | {r['seed_spread']} |")
    L += ["", "## B-2. LEVEL_WEIGHTS (등급비) — 상/중/하 3끌림점 배분", "",
          "| 비율 | w(옛집/시장/문구점) | w_top | d_top(km) | coverage80 | seed 변동(d/cov) |",
          "|---|---|---|---|---|---|"]
    for r in results["level_weights"]:
        w = r["w_배분"]
        L.append(f"| {r['ratio']} | {w['옛집']}/{w['정릉시장']}/{w['문구점']} | {r['w_top']} "
                 f"| {r['d_top_km']} | {r['coverage80']} | {r['d_top_spread']}/{r['cov_spread']} |")
    L += ["", "## B-3. ATTRACTION_CAP (독식 상한) — 발견이력 1등의 상한 스윙", "",
          "| cap | w_top | w(옛집/시장/문구점) | d_top(km) | coverage80 | seed 변동(d/cov) |",
          "|---|---|---|---|---|---|"]
    for r in results["attraction_cap"]:
        w = r["w_배분"]
        L.append(f"| {r['cap']} | {r['w_top']} | {w['옛집']}/{w['정릉시장']}/{w['문구점']} "
                 f"| {r['d_top_km']} | {r['coverage80']} | {r['d_top_spread']}/{r['cov_spread']} |")
    md = "\n".join(L) + "\n"
    (OUT_DIR / "sensitivity.md").write_text(md, encoding="utf-8")
    print(md)
