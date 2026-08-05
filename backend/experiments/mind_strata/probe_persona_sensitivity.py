"""마음 모델이 **무엇에** 반응하는가 — 개인화 축 vs 상태 축 (GPU 실호출).

## 배경

`probe_real_strata.py` 에서 게이지 문맥(층)을 바꿔도 답이 거의 안 갈렸다
(6개 층 전부 behavior 최빈값 "끌림점 접근", 90콜). 이때 두 해석이 가능하다:

  (a) 모델이 입력에 둔감하다 = 튜닝 문제
  (b) 모델은 **개인화 축**에는 반응하는데 **상태 축**에만 약하다

이 프로브가 둘을 가른다. 게이지 문맥을 **고정**하고 페르소나만 바꾼다.
페르소나로 갈리면 (b) — 모델은 정상이고, 층화·매칭이 딛고 선 축이 다른 것이다.

## 결과 (2026-08-06, exaone-mind-dem3, 각 15회 = 60콜 — results_persona_probe.json)

  페르소나            behavior                                  goal
  A 옛집지향·배회      끌림점 접근 12 / 귀소 시도 3                정릉시장 11 · 옛집 1 · 없음 3
  B 불안·의심·은신     귀소 시도 14 / 은신·멈춤 1                  없음 15
  C 시장단골·활동적    귀소 시도 8 / 계속 배회 6 / 은신·멈춤 1      없음 15
  D 보행제약·주저앉음  귀소 시도 15/15 (결정적)                    없음 15

⚠ temperature=0.3 이라 run-to-run 으로 분포가 흔들린다(직전 실행에서 B 는
귀소 9 / 배회 3 / 끌림 2 / 은신 1 이었다). 인용할 것은 **개별 칸이 아니라
"페르소나에 따라 분포가 갈린다"는 사실과 극단 대비(A 끌림점 접근 우세 + 목적지
지목 vs D 귀소 시도 15/15 + 목적지 없음)** 다. 칸 단위 수치를 쓰려면 반복을 늘려라.

**판정 (b).** 모델은 개인차에 강하게 반응한다. 같은 상황·같은 치매 유형인데
보호자가 알려준 습관에 따라 예측이 갈린다 — 제품의 핵심 주장(개인별 마음 추론)의
직접 근거다. 2026-08-03 골드셋 무효화(치매+발달 혼합이라 재현 불가) 이후 실 모델로
확보한 첫 개인화 증거이기도 하다.

따라서 층화·재사용 매칭이 POA 에 안 나타나는 것은 모델 품질 문제가 아니라
**그 장치들이 모델의 신호가 약한 축(상태 축)에서 동작하기 때문**이다.

## 후속 (미실행)

아키텍처 전제는 "심리 상태가 바뀔 때만 EXAONE 호출" 이다 — 시간에 따라 마음이
변한다는 전제. 실측은 그 전제가 아직 실현되지 않았음을 보인다. 프롬프트에서
게이지 문장이 페르소나·장소 목록에 묻히는지 확인하는 것이 다음 단계다.

실행: cd backend && EXAONE_API_KEY=... EXAONE_BASE_URL=... EXAONE_MODEL=... \
      MIND_MODEL=exaone-mind-dem3 python experiments/mind_strata/probe_persona_sensitivity.py
산출: experiments/mind_strata/results_persona_probe.json
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
REPEATS = int(os.environ.get("PROBE_REPEATS", "15"))
LKP = GeoPoint(lat=37.6061, lng=127.0106)

# 게이지 문맥 고정 — 이것만 상수로 두고 페르소나를 바꾼다 (Gauges.report 형식 그대로)
GAUGE = ("집을 나선 지 70분 경과. 피로도: 중간, 혼란도: 중간, 귀소 충동: 높음, "
         "불안: 낮음. 방금 귀소 게이지가 임계를 넘었다.")
SCENE = "주변에 좁은 골목과 낮은 주택이 보인다."


def _persona(pid: str, age: int, notes: list[str], places: list[tuple]) -> Persona:
    return Persona(
        id=pid, name="테스트", age=age, type=PersonaType.dementia, home=LKP,
        attraction_points=[
            AttractionPoint(label=lb, location=GeoPoint(lat=la, lng=ln),
                            weight=w, place_type=pt)
            for lb, la, ln, w, pt in places],
        behavior_notes=notes)


# 네 페르소나는 나이·유형은 비슷하게 두고 **보호자 진술만** 크게 다르게 했다.
# 개인화가 어디서 오는지(진술 → 예측)를 분리해 보기 위해서다.
CASES = {
    "A 옛집지향·배회": _persona(
        "a", 78, ["해질녘 옛집 방향으로 걷는 습관", "중기 치매 — 시간 인식 혼란"],
        [("옛집(아리랑고개)", 37.6015, 127.0088, 0.55, "past_residence"),
         ("정릉시장", 37.6047, 127.0121, 0.30, "")]),
    "B 불안·은신": _persona(
        "b", 82, ["누가 쫓아온다고 하면 사람 없는 골목이나 건물 안쪽으로 숨는다",
                  "낯선 사람이 말을 걸면 도망간다"],
        [("옛 교회", 37.6015, 127.0088, 0.55, "past_residence"),
         ("동네 공원", 37.6047, 127.0121, 0.30, "")]),
    "C 시장단골·활동적": _persona(
        "c", 71, ["매일 아침 시장에 가서 사람들과 이야기한다",
                  "길을 잘 알고 혼자 멀리까지 다닌다"],
        [("망원시장", 37.6015, 127.0088, 0.55, ""),
         ("경로당", 37.6047, 127.0121, 0.30, "")]),
    "D 보행제약·정지": _persona(
        "d", 88, ["무릎이 아파 오래 못 걷고 자주 앉아 쉰다",
                  "길을 잃으면 그 자리에 주저앉아 움직이지 않는다"],
        [("옛 직장", 37.6015, 127.0088, 0.55, "workplace"),
         ("약국", 37.6047, 127.0121, 0.30, "")]),
}


def main() -> None:
    if llm.exaone.is_stub:
        raise SystemExit("스텁 모드 — 실호출 전용 프로브다. EXAONE_* 환경변수를 설정하라.")

    rng = random.Random(42)
    results = {}
    print(f"게이지 문맥 고정, 페르소나만 변경 — 각 {REPEATS}회 = {len(CASES) * REPEATS} 콜\n")
    print(f"{'페르소나':<18} {'behavior 분포':<46} {'goal 분포'}")
    for name, persona in CASES.items():
        labels = [ap.label for ap in persona.attraction_points]
        prior = PriorParams(
            strategy_probs={"route_following": 0.25, "direction_keeping": 0.15,
                            "random_walk": 0.15, "backtracking": 0.10,
                            "staying_put": 0.10, "landmark_seeking": 0.25},
            attraction_weights={labels[0]: 0.6, labels[1]: 0.4},
            radius_lognormal=LognormalParams(mu=0.095, sigma=1.48), reasoning="프로브")
        rows = []
        for _ in range(REPEATS):
            mind, goal = llm.exaone.reinterpret_mind(
                persona, MindState(), GAUGE, labels, prior, SCENE, rng=rng)
            rows.append({"status": mind.status, "confusion": mind.confusion,
                         "behavior": mind.behavior, "goal": goal})
        results[name] = rows
        beh = Counter(r["behavior"] or "(없음)" for r in rows)
        goals = Counter(r["goal"] or "(없음)" for r in rows)
        print(f"{name:<18} {dict(beh)!s:<46} {dict(goals)}")

    modes = {k: Counter(r["behavior"] or "(없음)" for r in v).most_common(1)[0][0]
             for k, v in results.items()}
    distinct = len(set(modes.values()))
    print(f"\nbehavior 최빈값 종류 = {distinct}/{len(CASES)}"
          f"  → {'개인화 축에 반응함 (모델 정상)' if distinct > 1 else '개인화 축에도 무반응'}")

    (OUT_DIR / "results_persona_probe.json").write_text(
        json.dumps({"gauge_fixed": GAUGE, "repeats": REPEATS, "raw": results,
                    "behavior_mode_per_persona": modes, "distinct_modes": distinct},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {OUT_DIR}/results_persona_probe.json")


if __name__ == "__main__":
    main()
