"""P2-3 축소판 — 게이지 상수 민감도 점검 (LLM 실호출 0회).

원래 P2-3(게이지 그리드서치)는 P2-2와 동일 사유로 재정의됐다: 정답 좌표가
없어 "최적 게이지"는 측정 불가(순환논법). 대신 P2-2 실험B 방법론을 게이지
상수에 적용해, 상수가 (1) 마음 발동 동역학과 (2) POA 를 실제로 움직이는
살아있는 손잡이인지만 판별한다.

대상 3종 (gauges.GaugeConfig — 전부 "잠정값 (역산 튜닝 대상)" 주석 상태):
  - theta_mind 1.1  : H·A 발동 임계 — 마음 재해석이 언제/얼마나 발동하나
  - k_h1     0.006  : 귀소 누적 속도 (집떠난시간 항)
  - theta_f   1.2   : 피로 발동 임계 — 휴식(이동 감소) 빈도

LLM 0 유지 장치: llm.exaone.reinterpret_mind 를 무변경 재해석(fake)으로
패치 — 발동 계측은 되지만 HTTP 호출은 없다. POA 는 fake 마음(상태 유지)
기준이므로 "게이지→발동→휴식/전환 시도"의 동역학 민감도만 잰다.

실행: backend/ 에서  .venv/bin/python experiments/gauge_ablation/sweep_gauge_sensitivity.py
"""

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from app import llm
from app.geo import envlayer, h3grid, roadnet
from app.phase2 import gauges as gauge_mod
from app.phase2 import guardrail, simulation
from app.schemas.persona import PersonaType
from sim_testset import LKP, make_persona, make_prior

N_WALKERS = 300
SEEDS = [42, 43, 44]
ELAPSED = 3.0
OUT_DIR = Path(__file__).resolve().parent / "results"

# ── LLM 실호출 차단: 무변경 재해석 + 발동 계수기 ─────────────────────────────
TRIGGERS = [0]


def fake_reinterpret(persona, current, gauge_report, labels,
                     prior=None, scene=None, rng=None):
    return guardrail.sanitize_mind({}, current, labels)


_orig_pool_reinterpret = simulation._MindPool.reinterpret


def counted_reinterpret(self, *a, **k):
    TRIGGERS[0] += 1
    return _orig_pool_reinterpret(self, *a, **k)


_ORIG_CONFIG_FOR = gauge_mod.config_for


def patched_config_for(**mods):
    def factory(persona):
        cfg = _ORIG_CONFIG_FOR(persona)
        for key, val in mods.items():
            setattr(cfg, key, val)
        return cfg
    return factory


def run_cell(mode: str, **cfg_mods) -> dict:
    gauge_mod.config_for = patched_config_for(**cfg_mods) if cfg_mods else _ORIG_CONFIG_FOR
    persona = make_persona(PersonaType.dementia, 78, True)
    prior = make_prior(PersonaType.dementia, True)
    trig, dist, covs = [], [], []
    try:
        for seed in SEEDS:
            TRIGGERS[0] = 0
            poa = simulation.run_monte_carlo(LKP, prior, persona, ELAPSED,
                                             mode=mode, net=NET,
                                             n_walkers=N_WALKERS, seed=seed)
            trig.append(TRIGGERS[0])
            dist.append(sum(h3grid.haversine_km(LKP, h3grid.cell_center(c)) * p
                            for c, p in poa.items()))
            acc, n = 0.0, 0
            for _, p in sorted(poa.items(), key=lambda kv: kv[1], reverse=True):
                acc += p; n += 1
                if acc >= 0.8:
                    break
            covs.append(n)
    finally:
        gauge_mod.config_for = _ORIG_CONFIG_FOR
    return {"trig_mean": round(statistics.mean(trig), 1),
            "trig_spread": max(trig) - min(trig),
            "d_km": round(statistics.mean(dist), 3),
            "d_spread": round(max(dist) - min(dist), 3),
            "coverage80": round(statistics.mean(covs), 1),
            "cov_spread": max(covs) - min(covs)}


if __name__ == "__main__":
    NET = roadnet.get_network(LKP)
    envlayer.attach(NET, LKP)
    llm.exaone.reinterpret_mind = fake_reinterpret          # LLM 실호출 차단
    simulation._MindPool.reinterpret = counted_reinterpret  # 1회차 발동 계수

    results = {}
    # theta_mind — 마음 발동 임계 (agent 모드에서만 소비)
    results["theta_mind"] = [
        {"theta_mind": v, **run_cell("agent", theta_mind=v)}
        for v in [0.9, 1.0, 1.1, 1.2, 1.3]]
    # k_h1 — 귀소 누적 속도
    results["k_h1"] = [
        {"k_h1": v, **run_cell("agent", k_h1=v)}
        for v in [0.003, 0.006, 0.012]]
    # theta_f — 피로 임계 (statistical 모드에도 켜져 있는 유일 게이지)
    results["theta_f"] = [
        {"theta_f": v, **run_cell("statistical", theta_f=v)}
        for v in [1.0, 1.2, 1.4]]

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "gauge_sensitivity.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    L = ["# P2-3 축소판 — 게이지 상수 민감도 (LLM 실호출 0회)", "",
         f"agent/statistical {N_WALKERS}워커 × seed {SEEDS} 평균, 경과 {ELAPSED}h, "
         "정릉 3km 캐시. 마음 재해석은 무변경 fake 패치(발동 계측만, HTTP 0).",
         "판정 원칙(P2-2 실험B와 동일): 지표 이동 > seed 변동(spread)이면 살아있는 손잡이.", "",
         "## theta_mind — H·A 발동 임계 (agent, 현행 1.1)", "",
         "| θ | 1회차 발동 수(300워커) | 변동 | d(km) | coverage80 |",
         "|---|---|---|---|---|"]
    for r in results["theta_mind"]:
        cur = " ◀ 현행" if r["theta_mind"] == 1.1 else ""
        L.append(f"| {r['theta_mind']}{cur} | {r['trig_mean']} | ±{r['trig_spread']} "
                 f"| {r['d_km']} (±{r['d_spread']}) | {r['coverage80']} (±{r['cov_spread']}) |")
    L += ["", "## k_h1 — 귀소 누적 속도 (agent, 현행 0.006)", "",
          "| k_h1 | 1회차 발동 수 | 변동 | d(km) | coverage80 |", "|---|---|---|---|---|"]
    for r in results["k_h1"]:
        cur = " ◀ 현행" if r["k_h1"] == 0.006 else ""
        L.append(f"| {r['k_h1']}{cur} | {r['trig_mean']} | ±{r['trig_spread']} "
                 f"| {r['d_km']} (±{r['d_spread']}) | {r['coverage80']} (±{r['cov_spread']}) |")
    L += ["", "## theta_f — 피로 임계 (statistical, 현행 1.2)", "",
          "| θ_f | d(km) | coverage80 |", "|---|---|---|"]
    for r in results["theta_f"]:
        cur = " ◀ 현행" if r["theta_f"] == 1.2 else ""
        L.append(f"| {r['theta_f']}{cur} | {r['d_km']} (±{r['d_spread']}) "
                 f"| {r['coverage80']} (±{r['cov_spread']}) |")
    md = "\n".join(L) + "\n"
    (OUT_DIR / "gauge_sensitivity.md").write_text(md, encoding="utf-8")
    print(md)
