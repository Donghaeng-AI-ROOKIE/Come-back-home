"""마음 호출 예산 배분 — 선착순 vs 층화 효과 귀속 (재현 스크립트).

PR #130 의 헤드라인 수치가 재현되지 않아(적대검증 2026-08-06: 25.5% 를 세 검증자가
30.0 / 35.1 / 35.2% 로 재현) 조건을 코드에 박아 고정한다. 이 레포는 08-04 에 같은
사유로 알림셀 기준선을 폐기한 이력이 있다 — 조건 미상 수치는 인용 대상이 아니다.

## 세 조건 (배분 규칙만 다르고 나머지는 전부 동일)

  legacy  선착순 + 2회차 배제 + 균등 표집        = 구버전
  d1fix   선착순 + 2회차 허용 + 균등 표집        = 회차 게이트 한 줄 삭제
  strata  층화   + 2회차 허용 + 거리가중 표집    = 현행

## 두 축으로 잰다 (하나만 보면 귀속을 틀린다)

  A. 미커버율   = 실호출이 한 건도 없는 (회차 × 혼란등급) 조합에 속한 트리거 비중.
                 PR 이 헤드라인으로 쓴 축. **층 정의와 축이 겹치므로 자기충족 위험**이
                 있어 단독 인용 금지 — 반드시 B 와 함께 본다.
  B. 꼬리 결손율 = "불안" 층에 실호출이 0건인 seed 의 비율. 층화 고유 기여가 보이는 축.

⚠ LLM 스텁으로 돈다(무과금). 스텁은 층과 무관하게 같은 MindState(goal=None,
behavior="")를 반환하므로 **배달되는 마음의 내용 차이(D3)는 이 하네스로 측정할 수
없다.** 여기서 재는 것은 "어느 문맥이 실호출을 받았는가"라는 배분기의 성질뿐이고,
예측 정확도(POA)가 아니다.

실행:  cd backend && python experiments/mind_strata/run_strata.py
전제:  data/roadnet_cache 에 정릉 5km 캐시 (walk_37.6061_127.0106_5000.graphml)
산출:  experiments/mind_strata/results_strata.{json,md}
"""

import json
import os
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("USE_ROADNET", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config import settings
from app.geo.roadnet import OSMnxNetwork
from app.phase2 import simulation
from app.phase2.simulation import _LATER, _MindPool
from app.schemas.common import GeoPoint
from app.schemas.debug import SimTrace
from app.schemas.persona import AttractionPoint, Persona, PersonaType
from app.schemas.prediction import LognormalParams, PriorParams

OUT_DIR = Path(__file__).parent
# n>=12 — config.py 08-04 주석의 "seed 3개 판(오차 ±2셀)에서 두 번 잘못 읽었다" 기준.
SEEDS = list(range(42, 54))
ELAPSED_HOURS = 4.0
N_WALKERS = 500
RADIUS_M = 5000

LKP = GeoPoint(lat=37.6061, lng=127.0106)

PERSONA = Persona(
    id="strata-bench", name="김순자", age=78, type=PersonaType.dementia, home=LKP,
    attraction_points=[
        AttractionPoint(label="옛집(아리랑고개)", location=GeoPoint(lat=37.6015, lng=127.0088),
                        weight=0.55, place_type="past_residence"),
        AttractionPoint(label="정릉시장", location=GeoPoint(lat=37.6047, lng=127.0121),
                        weight=0.30, origin_slot="routine_destinations"),
    ],
    behavior_notes=["해질녘 옛집 방향으로 걷는 습관", "중기 치매 — 시간 인식 혼란"],
)

# prior 는 고정 — EXAONE 이 만드는 값이지만, 배분 규칙만 비교하려면 상수여야 한다.
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
    """선착순 배분기 — 층을 무시하고 총량만 센다. exclude_later 면 2회차를 배제(구버전)."""
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
    "legacy": (_fcfs(True), 0.0),    # 선착순 + 2회차 배제 + 균등
    "d1fix": (_fcfs(False), 0.0),    # 선착순 + 2회차 허용 + 균등
    "strata": (_ORIG_GRANT, 1.0),    # 층화 + 2회차 허용 + 거리가중
}


def _rows(trace: SimTrace) -> list[tuple[int, str, str, str]]:
    """(회차, 혼란등급, 발동사유, source) — 회차는 워커별 step 오름차순으로 복원."""
    per = defaultdict(list)
    for e in trace.mind_events:
        per[e.walker_idx].append(e)
    out = []
    for events in per.values():
        for ordinal, e in enumerate(sorted(events, key=lambda x: x.step), start=1):
            m = _REPORT_RE.search(e.trigger)
            out.append((min(ordinal, 2),
                        m.group("c") if m else "?",
                        m.group("fired") if m else "?",
                        e.source))
    return out


def run_one(net, seed: int, condition: str, budget: int) -> dict:
    grant, lam = CONDITIONS[condition]
    _MindPool._grant = grant
    old_lam, old_budget = settings.mind_pool_match_strength, settings.mind_call_budget
    settings.mind_pool_match_strength, settings.mind_call_budget = lam, budget
    try:
        trace = SimTrace(max_paths=0)
        simulation.run_monte_carlo(LKP, PRIOR, PERSONA, ELAPSED_HOURS, mode="agent",
                                   net=net, n_walkers=N_WALKERS, seed=seed, trace=trace)
    finally:
        _MindPool._grant = _ORIG_GRANT
        settings.mind_pool_match_strength = old_lam
        settings.mind_call_budget = old_budget

    rows = _rows(trace)
    real = [r for r in rows if r[3] in ("exaone", "stub")]
    covered = {(o, c) for o, c, _, _ in real}
    return {
        "triggers": len(rows),
        "real_calls": len(real),
        # A. 미커버율 — 실호출이 한 건도 없는 (회차·혼란) 조합에 속한 트리거 비중
        "uncovered_pct": sum(1 for o, c, _, _ in rows if (o, c) not in covered) / len(rows) * 100,
        # B. 꼬리 결손 — "불안" 층에 실호출이 0건인가
        "anxiety_zero": not any(f == "불안" for _, _, f, _ in real),
        # 참고: 실호출 중 2회차 비중 (D1 제거가 실제로 먹었는가)
        "second_share_pct": sum(1 for o, _, _, _ in real if o >= 2) / max(1, len(real)) * 100,
    }


def main() -> None:
    print(f"도로망 로딩 (정릉 {RADIUS_M}m 캐시)…")
    net = OSMnxNetwork()
    net.load(LKP, RADIUS_M)

    results = {}
    for budget in (3, 5):
        for cond in CONDITIONS:
            runs = [run_one(net, s, cond, budget) for s in SEEDS]
            unc = [r["uncovered_pct"] for r in runs]
            results[f"{cond}_b{budget}"] = {
                "budget": budget, "condition": cond, "seeds": SEEDS,
                "uncovered_mean": st.mean(unc),
                "uncovered_se": st.stdev(unc) / len(unc) ** 0.5,
                "uncovered_per_seed": [round(u, 1) for u in unc],
                "anxiety_zero_pct": sum(r["anxiety_zero"] for r in runs) / len(runs) * 100,
                "second_share_mean": st.mean(r["second_share_pct"] for r in runs),
                "real_calls_mean": st.mean(r["real_calls"] for r in runs),
            }
            r = results[f"{cond}_b{budget}"]
            print(f"  b{budget} {cond:<7} 미커버 {r['uncovered_mean']:5.1f}% ±{r['uncovered_se']:.1f}"
                  f" | 불안 결손 seed {r['anxiety_zero_pct']:5.1f}%"
                  f" | 실호출 중 2회차 {r['second_share_mean']:5.1f}%")

    (OUT_DIR / "results_strata.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 마음 호출 예산 배분 — 효과 귀속 실측",
        "",
        (f"조건: 정릉 {RADIUS_M}m 도로망 · 워커 {N_WALKERS} · 경과 {ELAPSED_HOURS}h "
         f"· seed {SEEDS[0]}~{SEEDS[-1]} (n={len(SEEDS)}) · LLM 스텁"),
        "",
        "| 예산 | 배분 | 미커버율(평균±SE) | 불안 층 결손 seed | 실호출 중 2회차 |",
        "|---|---|---|---|---|",
    ]
    for r in results.values():
        lines.append(f"| {r['budget']} | {r['condition']} | "
                     f"{r['uncovered_mean']:.1f}% ± {r['uncovered_se']:.1f} | "
                     f"{r['anxiety_zero_pct']:.0f}% | {r['second_share_mean']:.0f}% |")
    lines += [
        "",
        "## 읽는 법",
        "",
        "- **미커버율**은 층 정의와 축이 겹쳐 자기충족 위험이 있다. 단독 인용 금지.",
        "- **불안 층 결손**이 층화 고유 기여가 보이는 축이다 — d1fix 는 여기서 legacy 보다",
        "  악화한다(2회차가 예산 경쟁에 들어와 희소 층을 밀어낸다).",
        "- 전부 배분기의 성질이지 **예측 정확도(POA)가 아니다.** 스텁이라 배달되는 마음이",
        "  상수이므로 D3(문맥 매칭)의 효과는 이 하네스로 측정할 수 없다.",
    ]
    (OUT_DIR / "results_strata.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n저장: {OUT_DIR}/results_strata.json, .md")


if __name__ == "__main__":
    main()
