"""개인화인가 라벨 과적합인가 — 진술 × 라벨 교차 프로브 (GPU 실호출).

## 왜

`probe_persona_sensitivity.py`(2026-08-06)에서 네 페르소나 중 **A(옛집지향)만**
"끌림점 접근"을 냈고(12/15) B·C·D 는 0/15 에 goal 도 전부 None 이었다.
네 페르소나 모두 끌림점 2개를 동일한 구조로 받았으므로 구조 차이가 아니다.

A 의 라벨은 데모 케이스 그대로(`옛집(아리랑고개)`·`정릉시장`)다. 운영 백본
`exaone-mind-dem3` 가 김순자·정릉 데이터로 튜닝됐다면, 모델이 **그 라벨을 외운**
것일 수 있다. 그렇다면 "개인화가 된다"가 아니라 "데모에만 된다"이고, 제안서의
개인화 주장이 무너진다.

## 방법

보호자 진술(behavior_notes)과 장소 라벨을 2×2 로 교차한다. 게이지·장면·가중치는
전부 고정이므로 변하는 것은 이 둘뿐이다.

    A진술+A라벨 (기준)   A진술+C라벨 (라벨만 교체)
    C진술+A라벨 (진술만)  C진술+C라벨 (기준)

판정:
  - 끌림점 접근·goal 선택이 **라벨**을 따라가면 → 라벨 과적합. 개인화 주장 철회 대상.
  - **진술**을 따라가면 → 진짜 개인화. A/B/C/D 차이는 진술 내용 탓.
  - 둘 다 아니면 → 상호작용. 원인 재탐색.

실행: cd backend && EXAONE_BASE_URL=... EXAONE_API_KEY=... MIND_MODEL=exaone-mind-dem3 \
      python experiments/mind_strata/probe_label_overfit.py
산출: experiments/mind_strata/results_label_overfit.{json,md}
"""

import json
import os
import random
import sys
from collections import Counter
from pathlib import Path

os.environ.setdefault("EXAONE_BASE_URL", "http://100.73.27.46:18000/v1")
os.environ.setdefault("EXAONE_API_KEY", "sk-local-exaone")
os.environ.setdefault("EXAONE_MODEL", "exaone-base")
os.environ.setdefault("MIND_MODEL", "exaone-mind-dem3")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import llm
from app.config import settings
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, Persona, PersonaType
from app.schemas.prediction import LognormalParams, MindState, PriorParams

OUT_DIR = Path(__file__).parent
REPEATS = int(os.environ.get("PROBE_REPEATS", "15"))
LKP = GeoPoint(lat=37.6061, lng=127.0106)

# 게이지·장면 고정 — persona_sensitivity 와 같은 문맥이라 결과를 직접 비교할 수 있다.
GAUGE = ("집을 나선 지 70분 경과. 피로도: 중간, 혼란도: 중간, 귀소 충동: 높음, "
         "불안: 낮음. 방금 귀소 게이지가 임계를 넘었다.")
SCENE = "주변에 좁은 골목과 낮은 주택이 보인다."

NOTES = {
    "A진술(옛집지향)": ["해질녘 옛집 방향으로 걷는 습관", "중기 치매 — 시간 인식 혼란"],
    "C진술(시장단골)": ["매일 아침 시장에 가서 사람들과 이야기한다",
                    "길을 잘 알고 혼자 멀리까지 다닌다"],
}
# 좌표·가중치·place_type 은 동일하게 두고 **문자열만** 바꾼다 — 라벨 자체의 효과를 본다.
LABELS = {
    "A라벨(데모)": [("옛집(아리랑고개)", "past_residence"), ("정릉시장", "")],
    "C라벨(비데모)": [("망원시장", ""), ("경로당", "")],
}
_LOCS = [(37.6015, 127.0088, 0.55), (37.6047, 127.0121, 0.30)]

# 모델 3종 비교 — 과적합의 출처가 LoRA 인지 백본 능력인지 가른다.
#   exaone-base       튜닝 안 한 원본. 데모 라벨을 외웠을 리 없다.
#   exaone-mind-dem3  운영 백본(치매 단독 튜닝).
#   exaone-mind-v5    치매+발달 혼합 시절 튜닝(08-03 스코프 변경 전).
# guided JSON 디코딩이 세 모델에 동일하게 걸리므로 출력 구조는 공정하게 비교된다.
MODELS = ["exaone-base", "exaone-mind-dem3", "exaone-mind-v5"]


def _persona(notes: list[str], labels: list[tuple]) -> Persona:
    return Persona(
        id="xover", name="테스트", age=78, type=PersonaType.dementia, home=LKP,
        attraction_points=[
            AttractionPoint(label=lb, location=GeoPoint(lat=la, lng=ln),
                            weight=w, place_type=pt)
            for (lb, pt), (la, ln, w) in zip(labels, _LOCS)],
        behavior_notes=notes)


def main() -> None:
    if llm.exaone.is_stub:
        raise SystemExit("스텁 모드 — 실호출 전용 프로브다. EXAONE_* 환경변수를 확인하라.")
    print(f"모델 mind={settings.mind_model} / repeats={REPEATS}\n")

    rng = random.Random(42)
    results: dict[str, dict[str, list[dict]]] = {}
    for model in MODELS:
        settings.mind_model = model
        print(f"\n{'=' * 68}\n모델 {model}\n{'=' * 68}")
        results[model] = {}
        for nk, notes in NOTES.items():
            for lk, labels in LABELS.items():
                persona = _persona(notes, labels)
                names = [ap.label for ap in persona.attraction_points]
                prior = PriorParams(
                    strategy_probs={"route_following": 0.25, "direction_keeping": 0.15,
                                    "random_walk": 0.15, "backtracking": 0.10,
                                    "staying_put": 0.10, "landmark_seeking": 0.25},
                    attraction_weights={names[0]: 0.6, names[1]: 0.4},
                    radius_lognormal=LognormalParams(mu=0.095, sigma=1.48),
                    reasoning="교차 프로브 고정 prior")
                rows = []
                for _ in range(REPEATS):
                    mind, goal = llm.exaone.reinterpret_mind(
                        persona, MindState(), GAUGE, names, prior, SCENE, rng=rng)
                    rows.append({"status": mind.status, "confusion": mind.confusion,
                                 "behavior": mind.behavior, "goal": goal})
                key = f"{nk} × {lk}"
                results[model][key] = rows
                goals = Counter(r["goal"] or "(없음)" for r in rows)
                beh = Counter(r["behavior"] or "(없음)" for r in rows)
                picked = sum(1 for r in rows if r["goal"])
                # 진술 정합: "시장 단골" 진술이면 그 라벨셋의 시장을 골라야 한다.
                # 두 라벨셋 모두 시장을 하나씩 갖고 있어 조건이 대칭이다.
                fit = ""
                if nk.startswith("C진술"):
                    want = next((n for n in names if "시장" in n), None)
                    hit = sum(1 for r in rows if r["goal"] == want)
                    fit = f"  진술정합({want}) {hit}/{REPEATS}"
                print(f"{key}")
                print(f"   goal선택 {picked}/{REPEATS}{fit}")
                print(f"   goal {dict(goals)}")
                print(f"   behavior {dict(beh)}")

    (OUT_DIR / "results_label_overfit.json").write_text(
        json.dumps({"gauge": GAUGE, "scene": SCENE, "repeats": REPEATS,
                    "models": MODELS, "raw": results},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장: {OUT_DIR / 'results_label_overfit.json'}")


if __name__ == "__main__":
    main()
