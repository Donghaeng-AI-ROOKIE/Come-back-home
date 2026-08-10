"""마음 호출 예산 배분 — 실 EXAONE 으로 배달 내용·POA 까지 측정 (GPU 실호출).

## 왜 이 스크립트가 따로 필요한가

`run_strata.py` 는 LLM 스텁으로 돈다. 스텁은 층과 무관하게 같은 MindState
(goal=None, status="혼란 심화")를 반환하므로, 풀 엔트리 5개가 전부 같다.
그래서 스텁 하네스가 재는 것은 **"어느 문맥이 실호출을 받았는가"라는 배분기의
성질뿐**이고, 배분 방식이 바꾼 것이 실제로 워커에게 **무엇을 배달했는가**는
원리적으로 측정할 수 없다(적대검증 2026-08-06 치명 지적 2번).

여기서는 실 EXAONE 을 붙여 그 공백을 메운다:
  - 실호출 5건이 층마다 **다른 답**을 내는가 (층화·매칭의 전제)
  - 배분 방식이 배달된 goal·confusion 분포를 바꾸는가
  - 그 차이가 POA(cov80·끌림점 질량)까지 내려오는가

## 조건 (run_strata.py 와 동일 — 배분 규칙만 다르고 나머지는 전부 고정)

  legacy  선착순 + 2회차 배제 + 균등 표집        = 구버전
  d1fix   선착순 + 2회차 허용 + 균등 표집        = 회차 게이트 한 줄 삭제
  strata  층화   + 2회차 허용 + 거리가중 표집    = 현행

prior 는 고정 상수다. EXAONE 이 만드는 값이지만 배분 규칙만 비교하려면 상수여야 한다.

## 비용

조건 3 × seed N × budget 5 = 15N 회 실호출. 호출당 약 1초.

실행:  cd backend && python experiments/mind_strata/run_strata_live.py [seed수]
전제:  EXAONE 게이트웨이 접속 가능 (맥미니 tailnet 100.73.27.46:18000)
산출:  experiments/mind_strata/results_strata_live.{json,md}
"""

import json
import os
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

# settings 는 임포트 시점에 환경변수를 읽는다 — app.* 임포트보다 먼저 세팅해야 한다.
os.environ.setdefault("USE_ROADNET", "true")
os.environ.setdefault("EXAONE_BASE_URL", "http://100.73.27.46:18000/v1")
os.environ.setdefault("EXAONE_API_KEY", "sk-local-exaone")
os.environ.setdefault("EXAONE_MODEL", "exaone-base")
os.environ.setdefault("MIND_MODEL", "exaone-mind-dem3")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config import settings
from app.geo import h3grid
from app.geo.roadnet import OSMnxNetwork
from app.llm import exaone as exaone_mod
from app.phase2 import simulation
from app.phase2.simulation import _LATER, _MindPool
from app.schemas.common import GeoPoint
from app.schemas.debug import SimTrace
from app.schemas.persona import AttractionPoint, Persona, PersonaType
from app.schemas.prediction import LognormalParams, PriorParams

OUT = Path(__file__).parent
RADIUS_M = 5000
ELAPSED_HOURS = 4.0
N_WALKERS = 500
BUDGET = 5

LKP = GeoPoint(lat=37.6061, lng=127.0106)
OLD_HOME = GeoPoint(lat=37.6015, lng=127.0088)

PERSONA = Persona(
    id="strata-live", name="김순자", age=78, type=PersonaType.dementia, home=LKP,
    attraction_points=[
        AttractionPoint(label="옛집(아리랑고개)", location=OLD_HOME,
                        weight=0.55, place_type="past_residence"),
        AttractionPoint(label="정릉시장", location=GeoPoint(lat=37.6047, lng=127.0121),
                        weight=0.30, origin_slot="routine_destinations"),
    ],
    behavior_notes=["해질녘 옛집 방향으로 걷는 습관", "중기 치매 — 시간 인식 혼란"],
)

PRIOR = PriorParams(
    strategy_probs={"route_following": 0.25, "direction_keeping": 0.15, "random_walk": 0.15,
                    "backtracking": 0.10, "staying_put": 0.10, "landmark_seeking": 0.25},
    attraction_weights={"옛집(아리랑고개)": 0.6, "정릉시장": 0.4},
    radius_lognormal=LognormalParams(mu=0.095, sigma=1.48),
    reasoning="배분 규칙 비교용 고정 prior",
)

_REPORT_RE = re.compile(r"혼란도: (?P<c>\S+),.*방금 (?P<fired>\S+) 게이지")
_ORIG_GRANT = _MindPool._grant


def _fcfs(exclude_later: bool):
    """선착순 배분기 — 층을 무시하고 총량만 센다. exclude_later 면 2회차 배제(구버전)."""
    def grant(self, key, progress):
        if exclude_later and key == _LATER:
            return False
        if getattr(self, "_fcfs_left", None) is None:
            self._fcfs_left = sum(self.quota.values())
        if self._fcfs_left > 0:
            self._fcfs_left -= 1
            return True
        return False
    return grant


CONDITIONS = {
    "legacy": (_fcfs(True), 0.0),
    "d1fix": (_fcfs(False), 0.0),
    "strata": (_ORIG_GRANT, 1.0),
}


def _cov80(poa: dict) -> int:
    cum, n = 0.0, 0
    for p in sorted(poa.values(), reverse=True):
        cum += p
        n += 1
        if cum >= 0.8:
            break
    return n


def run_one(net, seed: int, condition: str) -> dict:
    grant, lam = CONDITIONS[condition]
    _MindPool._grant = grant
    old_lam, old_budget = settings.mind_pool_match_strength, settings.mind_call_budget
    settings.mind_pool_match_strength, settings.mind_call_budget = lam, BUDGET
    try:
        trace = SimTrace(max_paths=0)
        poa = simulation.run_monte_carlo(LKP, PRIOR, PERSONA, ELAPSED_HOURS, mode="agent",
                                         net=net, n_walkers=N_WALKERS, seed=seed, trace=trace)
    finally:
        _MindPool._grant = _ORIG_GRANT
        settings.mind_pool_match_strength = old_lam
        settings.mind_call_budget = old_budget

    # 회차 복원 (워커별 step 오름차순)
    per = defaultdict(list)
    for e in trace.mind_events:
        per[e.walker_idx].append(e)
    rows = []
    for events in per.values():
        for ordinal, e in enumerate(sorted(events, key=lambda x: x.step), start=1):
            m = _REPORT_RE.search(e.trigger)
            rows.append({"ord": min(ordinal, 2),
                         "c": m.group("c") if m else "?",
                         "fired": m.group("fired") if m else "?",
                         "src": e.source, "goal": e.goal, "conf": e.confusion,
                         "status": e.status, "beh": e.behavior})
    real = [r for r in rows if r["src"] in ("exaone", "stub")]
    covered = {(r["ord"], r["c"]) for r in real}
    near = sum(p for c, p in poa.items()
               if h3grid.haversine_km(h3grid.cell_center(c), OLD_HOME) < 0.3)
    return {
        "triggers": len(rows), "real_calls": len(real),
        "uncovered_pct": sum(1 for r in rows if (r["ord"], r["c"]) not in covered)
                         / max(1, len(rows)) * 100,
        "anxiety_zero": not any(r["fired"] == "불안" for r in real),
        "second_share_pct": sum(1 for r in real if r["ord"] >= 2) / max(1, len(real)) * 100,
        # ── 실 EXAONE 이라야 의미가 생기는 축 ──
        "real_answers": [{"층": f"{r['fired']}·{r['c']}·{r['ord']}회차",
                          "goal": r["goal"], "conf": r["conf"], "status": r["status"]}
                         for r in real],
        "uniq_answers": len({(r["goal"], round(r["conf"], 2), r["status"]) for r in real}),
        "goal_delivered_pct": sum(1 for r in rows if r["goal"]) / max(1, len(rows)) * 100,
        "conf_mean": st.fmean([r["conf"] for r in rows]) if rows else 0.0,
        # ── behavior 채널 — POA 를 가장 크게 움직이는 경로 (2026-08-06 실측) ──
        # 배달된 것(전체 트리거)과 실호출이 만든 것(풀 원본)을 나눠 본다:
        # 배분 규칙이 바꾸는 것은 풀 구성이고, 워커가 실제로 받는 것은 배달분이다.
        "beh_delivered": dict(Counter(r["beh"] or "(없음)" for r in rows)),
        "beh_pool": dict(Counter(r["beh"] or "(없음)" for r in real)),
        "cov80": _cov80(poa), "near_oldhome_pct": near * 100,
        "poa": poa,
    }


def main() -> None:
    n_seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    seeds = list(range(42, 42 + n_seeds))
    print(f"EXAONE {settings.exaone_base_url} / mind={settings.mind_model} "
          f"/ stub={exaone_mod.is_stub}")
    if exaone_mod.is_stub:
        sys.exit("EXAONE 스텁 모드 — 게이트웨이 설정을 확인하라 (실호출 실험 중단)")
    net = OSMnxNetwork()
    net.load(LKP, RADIUS_M)

    out = {}
    for cond in CONDITIONS:
        runs = [run_one(net, s, cond) for s in seeds]
        for r in runs:
            r.pop("poa", None)
        out[cond] = runs
        agg = {k: st.fmean([r[k] for r in runs])
               for k in ("uncovered_pct", "second_share_pct", "uniq_answers",
                         "goal_delivered_pct", "conf_mean", "cov80", "near_oldhome_pct")}
        agg["anxiety_zero_pct"] = sum(r["anxiety_zero"] for r in runs) / len(runs) * 100
        print(f"\n[{cond}] n={len(seeds)}")
        print(f"  미커버 {agg['uncovered_pct']:.1f}%  불안결손 {agg['anxiety_zero_pct']:.0f}%  "
              f"2회차실호출 {agg['second_share_pct']:.0f}%")
        print(f"  풀 고유답 {agg['uniq_answers']:.2f}/5  goal배달 {agg['goal_delivered_pct']:.1f}%  "
              f"혼란평균 {agg['conf_mean']:.3f}")
        print(f"  cov80 {agg['cov80']:.1f}셀  옛집300m {agg['near_oldhome_pct']:.1f}%")
        for tag, field in (("배달", "beh_delivered"), ("풀원본", "beh_pool")):
            tot: Counter = Counter()
            for r in runs:
                tot.update(r[field])
            n = sum(tot.values()) or 1
            share = "  ".join(f"{k} {v/n*100:.0f}%"
                              for k, v in sorted(tot.items(), key=lambda x: -x[1]))
            print(f"  behavior {tag}: {share}")
            agg[field] = {k: v / n * 100 for k, v in tot.items()}
        out[cond + "_agg"] = agg

    (OUT / "results_strata_live.json").write_text(
        json.dumps({"seeds": seeds, "elapsed_h": ELAPSED_HOURS, "walkers": N_WALKERS,
                    "budget": BUDGET, "mind_model": settings.mind_model, "result": out},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT / 'results_strata_live.json'}")


if __name__ == "__main__":
    main()
