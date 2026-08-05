"""실 EXAONE 이 층마다 다른 답을 주는가 — 층화·매칭의 전제 검증 (GPU 실호출).

## 왜 이 프로브가 필요한가

층화 배분과 거리가중 재사용(λ)은 **"층이 다르면 답도 다르다"**를 전제한다.
그 전제가 거짓이면 — 모델이 문맥과 무관하게 같은 답을 낸다면 — 어느 층에
호출을 쓰든, 어느 엔트리를 골라 재사용하든 결과가 같아 두 장치 모두 무의미하다.

스텁으로는 이 전제를 검증할 수 없다(스텁은 정의상 상수 응답). 대리 응답기
(run_matching.py)는 전제를 **가정**하고 배달 정확도만 잰다. 여기서 전제 자체를 잰다.

⚠ 반대 방향의 선행 관측이 있다: 07-29 프로브(236B·혼합 스코프)에서 goal 59/59,
status 59/59 가 단일값이었고 confusion 만 조건에 반응했다. 그 리포트는 운영 백본
(7.8B, mind-dem3, 치매 단독)에서 재측정이 필요하다고 표기돼 있다 — 이 스크립트가
그 재측정이다.

## 방법

`Gauges.report` 가 만드는 문자열 형식 그대로 6개 층 문맥을 합성하고, 층마다
REPEATS 회 실호출한다. 프롬프트·모델·계약은 운영 경로와 동일(reinterpret_mind).

판정:
  - behavior/goal 이 층에 따라 갈리면 → 전제 성립, 층화·매칭에 실질이 있다
  - 전 층이 같은 답이면 → 전제 실패. 층화는 호출 문맥만 고르게 할 뿐 배달 내용은
    바뀌지 않으므로, λ 매칭의 기대효과를 0 으로 봐야 한다

실행: cd backend && EXAONE_API_KEY=... EXAONE_BASE_URL=... EXAONE_MODEL=... \
      MIND_MODEL=exaone-mind-dem3 python experiments/mind_strata/probe_real_strata.py
산출: experiments/mind_strata/results_real_probe.{json,md}
"""

import json
import os
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import llm
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, Persona, PersonaType
from app.schemas.prediction import LognormalParams, MindState, PriorParams

OUT_DIR = Path(__file__).parent
REPEATS = int(os.environ.get("PROBE_REPEATS", "5"))

LKP = GeoPoint(lat=37.6061, lng=127.0106)
OLD_HOME = "옛집(아리랑고개)"

PERSONA = Persona(
    id="real-probe", name="김순자", age=78, type=PersonaType.dementia, home=LKP,
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
    radius_lognormal=LognormalParams(mu=0.095, sigma=1.48), reasoning="프로브")

LABELS = [OLD_HOME, "정릉시장"]
SCENE = "주변에 좁은 골목과 낮은 주택이 보인다."


def report(elapsed_min: int, f: str, c: str, h: str, a: str, reason: str) -> str:
    """Gauges.report 와 동일한 문자열 형식 (gauges.py)."""
    return (f"집을 나선 지 {elapsed_min}분 경과. "
            f"피로도: {f}, 혼란도: {c}, 귀소 충동: {h}, 불안: {a}. "
            f"방금 {reason} 게이지가 임계를 넘었다.")


# 6개 층 문맥 — 실제 시뮬레이션에서 관측된 조합을 대표값으로 합성
CONTEXTS = {
    "귀소·낮음": report(35, "낮음", "낮음", "중간", "낮음", "귀소"),
    "귀소·중간": report(70, "중간", "중간", "높음", "낮음", "귀소"),
    "귀소·높음": report(130, "높음", "높음", "높음", "중간", "귀소"),
    "불안·낮음": report(35, "낮음", "낮음", "낮음", "중간", "불안"),
    "불안·중간": report(70, "중간", "중간", "중간", "높음", "불안"),
    "불안·높음": report(130, "높음", "높음", "높음", "높음", "불안"),
}


def main() -> None:
    if llm.exaone.is_stub:
        raise SystemExit(
            "스텁 모드 — 이 프로브는 실호출 전용이다. EXAONE_API_KEY / EXAONE_BASE_URL /\n"
            "EXAONE_MODEL 을 설정하고 다시 실행하라 (게이트웨이: 맥미니 tailnet).")

    rng = random.Random(42)
    results = {}
    print(f"모델: mind={os.environ.get('MIND_MODEL') or '(EXAONE_MODEL 상속)'}  "
          f"층 {len(CONTEXTS)} × {REPEATS}회 = {len(CONTEXTS) * REPEATS} 콜\n")
    print(f"{'층':<12} {'behavior 분포':<44} {'goal':<22} {'confusion'}")
    for name, gauge_report in CONTEXTS.items():
        rows = []
        for _ in range(REPEATS):
            mind, goal = llm.exaone.reinterpret_mind(
                PERSONA, MindState(), gauge_report, LABELS, PRIOR, SCENE, rng=rng)
            rows.append({"status": mind.status, "confusion": mind.confusion,
                         "behavior": mind.behavior, "goal": goal})
        results[name] = rows
        beh = Counter(r["behavior"] or "(없음)" for r in rows)
        goals = Counter(r["goal"] or "(없음)" for r in rows)
        confs = sorted({round(r["confusion"], 2) for r in rows})
        print(f"{name:<12} {dict(beh)!s:<44} {dict(goals)!s:<22} {confs}")

    # 판정 — 층 사이에서 갈리는 채널이 있는가
    def spread(field):
        per = {k: Counter(r[field] or "(없음)" for r in v).most_common(1)[0][0]
               for k, v in results.items()}
        return len(set(per.values())), per

    print()
    verdict = {}
    for field in ("behavior", "goal", "status"):
        n, per = spread(field)
        verdict[field] = {"distinct_across_strata": n, "per_stratum_mode": per}
        print(f"{field:<10} 층별 최빈값 종류 = {n}/{len(CONTEXTS)}"
              f"  {'→ 층에 따라 갈림' if n > 1 else '→ 전 층 동일 (층화 무의미)'}")
    confs = {k: sorted({round(r['confusion'], 2) for r in v}) for k, v in results.items()}
    verdict["confusion_per_stratum"] = confs
    print(f"{'confusion':<10} 층별 값 {confs}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "results_real_probe.json").write_text(
        json.dumps({"raw": results, "verdict": verdict}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\n저장: {OUT_DIR}/results_real_probe.json")


if __name__ == "__main__":
    main()
