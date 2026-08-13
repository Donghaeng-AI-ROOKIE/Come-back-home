"""재사용 매칭(λ) 검증 — 층별로 다른 답을 내는 대리 응답기로 (무과금).

## 왜 대리 응답기인가

LLM 스텁은 층과 무관하게 같은 MindState(goal=None, behavior="")를 반환한다
(exaone.py). 풀 엔트리 5개가 전부 같으면 **어느 것을 골라도 결과가 같으므로
"잘 골랐다"를 보일 방법이 없다** — λ 매칭은 스텁으로 검증 불가다.

대리 응답기는 프롬프트에 실제로 들어 있는 정보(gauge_report 의 발동사유·혼란등급)만
읽어 층마다 다른 답을 낸다. 실 LLM 이 아니지만 "매칭이 문맥에 맞는 답을 배달하는가"
라는 **배달 정확도**는 이것으로 정확히 잴 수 있다 — 이 질문은 답의 내용이 무엇이든
성립하기 때문이다. 답의 품질(마음 예측이 옳은가)은 별개 문제이고 여기 범위가 아니다.

## 측정

각 답에 "어느 문맥에서 나온 답인가"를 태그로 달아 두고, 소비 시점에 워커 자신의
문맥과 비교한다.
  - 배달 정확도 = 받은 답의 태그가 내 문맥과 같은 비율
  - 행동 배달   = "불안"으로 흔들린 워커가 불안 답(은신·멈춤)을 받은 비율
비교군: λ=0(구버전 균등 표집) vs λ=1.0(현행 거리가중).

실행:  cd backend && python experiments/mind_strata/run_matching.py
산출:  experiments/mind_strata/results_matching.{json,md}
"""

import json
import os
import re
import statistics as st
import sys
from collections import Counter
from pathlib import Path

os.environ.setdefault("USE_ROADNET", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import llm
from app.config import settings
from app.geo.roadnet import OSMnxNetwork
from app.phase2 import simulation
from app.schemas.common import GeoPoint
from app.schemas.debug import SimTrace
from app.schemas.persona import AttractionPoint, Persona, PersonaType
from app.schemas.prediction import LognormalParams, MindState, PriorParams

OUT_DIR = Path(__file__).parent
SEEDS = list(range(42, 54))
ELAPSED_HOURS = 4.0
N_WALKERS = 500
RADIUS_M = 5000

LKP = GeoPoint(lat=37.6061, lng=127.0106)
OLD_HOME = "옛집(아리랑고개)"

PERSONA = Persona(
    id="matching-bench", name="김순자", age=78, type=PersonaType.dementia, home=LKP,
    attraction_points=[
        AttractionPoint(label=OLD_HOME, location=GeoPoint(lat=37.6015, lng=127.0088),
                        weight=0.55, place_type="past_residence"),
        AttractionPoint(label="정릉시장", location=GeoPoint(lat=37.6047, lng=127.0121),
                        weight=0.30, origin_slot="routine_destinations"),
    ],
    behavior_notes=["해질녘 옛집 방향으로 걷는 습관", "중기 치매 — 시간 인식 혼란"],
)

PRIOR = PriorParams(
    strategy_probs={"route_following": 0.25, "direction_keeping": 0.15, "random_walk": 0.15,
                    "backtracking": 0.10, "staying_put": 0.10, "landmark_seeking": 0.25},
    attraction_weights={OLD_HOME: 0.6, "정릉시장": 0.4},
    radius_lognormal=LognormalParams(mu=0.095, sigma=1.48),
    reasoning="매칭 검증용 고정 prior",
)

_REPORT_RE = re.compile(r"혼란도: (?P<c>\S+),.*방금 (?P<fired>\S+) 게이지")

# 대리 응답 표 — 프롬프트에 실제로 있는 (사유, 혼란등급)에만 의존한다.
# behavior 는 guardrail 의 닫힌 4종. 값 자체가 "옳은 마음"이라는 주장은 하지 않는다 —
# 층마다 **구별 가능하기만** 하면 배달 정확도를 잴 수 있다.
_PROXY = {
    ("귀소", "낮음"): ("끌림점 접근", OLD_HOME, 0.35),
    ("귀소", "중간"): ("귀소 시도", None, 0.60),
    ("귀소", "높음"): ("귀소 시도", None, 0.85),
    ("불안", "낮음"): ("계속 배회", None, 0.35),
    ("불안", "중간"): ("계속 배회", None, 0.60),
    ("불안", "높음"): ("은신·멈춤", None, 0.85),
}


def _ctx(gauge_report: str) -> tuple[str, str]:
    m = _REPORT_RE.search(gauge_report)
    return (m.group("fired"), m.group("c")) if m else ("?", "?")


def _proxy_reinterpret(persona, current, gauge_report, labels,
                       prior=None, scene=None, rng=None):
    """층별로 다른 답. status 에 출처 문맥을 태그로 박아 배달 추적을 가능하게 한다."""
    key = _ctx(gauge_report)
    behavior, goal, confusion = _PROXY.get(key, ("계속 배회", None, 0.5))
    if goal is not None and goal not in labels:
        goal = None
    return (MindState(status=f"TAG|{key[0]}|{key[1]}", confusion=confusion,
                      behavior=behavior, changed=True), goal)


def run_one(net, seed: int, lam: float) -> dict:
    old_lam = settings.mind_pool_match_strength
    settings.mind_pool_match_strength = lam
    try:
        trace = SimTrace(max_paths=0)
        poa = simulation.run_monte_carlo(LKP, PRIOR, PERSONA, ELAPSED_HOURS, mode="agent",
                                         net=net, n_walkers=N_WALKERS, seed=seed, trace=trace)
    finally:
        settings.mind_pool_match_strength = old_lam

    reused = [e for e in trace.mind_events if e.source == "pool"]
    exact = near = 0
    anx_total = anx_got_anx = 0
    for e in reused:
        mine = _ctx(e.trigger)
        parts = e.status.split("|")
        theirs = (parts[1], parts[2]) if len(parts) == 3 else ("?", "?")
        exact += mine == theirs
        near += mine[0] == theirs[0]            # 최소한 발동 사유는 맞았는가
        if mine[0] == "불안":
            anx_total += 1
            anx_got_anx += theirs[0] == "불안"
    n = max(1, len(reused))
    return {
        "reused": len(reused),
        "exact_pct": exact / n * 100,
        "reason_pct": near / n * 100,
        "anx_match_pct": anx_got_anx / max(1, anx_total) * 100,
        "anx_total": anx_total,
        "behavior_mix": Counter(e.status for e in reused),
        "poa": poa,
    }


def js_divergence(p: dict, q: dict) -> float:
    import math
    cells = set(p) | set(q)
    m = {c: 0.5 * (p.get(c, 0.0) + q.get(c, 0.0)) for c in cells}

    def kl(a):
        return sum(a.get(c, 0.0) * math.log2(a[c] / m[c]) for c in cells if a.get(c, 0.0) > 0)
    return 0.5 * kl(p) + 0.5 * kl(q)


def main() -> None:
    print(f"도로망 로딩 (정릉 {RADIUS_M}m 캐시)…")
    net = OSMnxNetwork()
    net.load(LKP, RADIUS_M)

    orig = llm.exaone.reinterpret_mind
    llm.exaone.reinterpret_mind = _proxy_reinterpret
    try:
        runs = {lam: [run_one(net, s, lam) for s in SEEDS] for lam in (0.0, 1.0)}
    finally:
        llm.exaone.reinterpret_mind = orig

    out = {}
    print(f"\n{'λ':>4} {'재사용':>7} {'정확일치':>9} {'사유일치':>9} {'불안→불안':>10}")
    for lam, rs in runs.items():
        out[f"lam{lam}"] = {
            k: {"mean": st.mean(r[k] for r in rs),
                "se": st.stdev([r[k] for r in rs]) / len(rs) ** 0.5}
            for k in ("exact_pct", "reason_pct", "anx_match_pct")
        }
        out[f"lam{lam}"]["reused_mean"] = st.mean(r["reused"] for r in rs)
        o = out[f"lam{lam}"]
        print(f"{lam:>4} {o['reused_mean']:>7.0f} "
              f"{o['exact_pct']['mean']:>7.1f}%±{o['exact_pct']['se']:.1f} "
              f"{o['reason_pct']['mean']:>7.1f}%±{o['reason_pct']['se']:.1f} "
              f"{o['anx_match_pct']['mean']:>8.1f}%±{o['anx_match_pct']['se']:.1f}")

    # POA 영향 — 처리 효과가 같은 조건 seed 노이즈를 넘는가 (PR #103 판정 방식)
    treat = [js_divergence(a["poa"], b["poa"]) for a, b in zip(runs[0.0], runs[1.0])]
    noise = [js_divergence(rs[i]["poa"], rs[i + 1]["poa"])
             for rs in runs.values() for i in range(len(rs) - 1)]
    out["poa"] = {"treatment_js_mean": st.mean(treat),
                  "treatment_js_se": st.stdev(treat) / len(treat) ** 0.5,
                  "seed_noise_js_mean": st.mean(noise),
                  "seed_noise_js_se": st.stdev(noise) / len(noise) ** 0.5}
    print(f"\nPOA 처리효과 JS {out['poa']['treatment_js_mean']:.4f}"
          f" ± {out['poa']['treatment_js_se']:.4f}"
          f"  vs  seed 노이즈 {out['poa']['seed_noise_js_mean']:.4f}"
          f" ± {out['poa']['seed_noise_js_se']:.4f}")
    verdict = ("노이즈 초과 — 출력에 반영됨"
               if out["poa"]["treatment_js_mean"] >
               out["poa"]["seed_noise_js_mean"] + 2 * out["poa"]["seed_noise_js_se"]
               else "노이즈 이하 — 출력 수준 효과 미검출")
    out["poa"]["verdict"] = verdict
    print(f"판정: {verdict}")

    (OUT_DIR / "results_matching.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT_DIR}/results_matching.json")


if __name__ == "__main__":
    main()
