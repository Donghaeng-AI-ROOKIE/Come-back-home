"""라벨 1개 교체 분리 프로브 — 데모/비데모 goal 비대칭의 원인 문자열 특정 (GPU 실호출).

## 왜

교차 프로브(probe_label_overfit.py, 2026-08-07)에서 goal 선택이 라벨 쌍을 따라갔다:
데모 쌍(옛집(아리랑고개)+정릉시장) 11~15/15, 비데모 쌍(망원시장+경로당) 0~2/15.
"LoRA 라벨 암기" 가설은 **기각됐다** — 학습 데이터·claims·candidates 전 단계에서
데모 지명이 0행이다(외울 수 없는 것은 외울 수 없다). 그러면 비대칭의 원인은
쌍을 이루는 문자열 자체 또는 조합에 있다.

두 쌍은 문자열 2개가 통째로 다르므로, 한 개씩 바꿔 4셀로 분리한다:

    정릉시장 + 옛집(아리랑고개)   기준(데모 쌍)      — 종전 15/15
    망원시장 + 경로당            기준(비데모 쌍)    — 종전 0~1/15
    정릉시장 + 경로당            시장만 데모
    망원시장 + 옛집(아리랑고개)   파트너만 데모

판정 (진술 = "매일 아침 시장에 간다" 고정, 시장 라벨이 진술 정합 목표):
  - 정릉시장 쪽 2셀만 높으면 → "정릉시장" 문자열 자체가 원인
  - 옛집 쪽 2셀만 높으면    → 파트너 옛집(아리랑고개)가 goal 선택을 유발
  - 데모 문자열 포함 3셀 전부 높으면 → 데모 문자열 아무거나 있으면 발화
  - 기준 데모 쌍만 높으면   → 조합 효과

실행: cd backend && python experiments/mind_strata/probe_label_swap.py
산출: experiments/mind_strata/results_label_swap.json
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

# 게이지·장면·진술 = 교차 프로브와 동일 고정 — 셀 간 비교 가능성 유지.
GAUGE = ("집을 나선 지 70분 경과. 피로도: 중간, 혼란도: 중간, 귀소 충동: 높음, "
         "불안: 낮음. 방금 귀소 게이지가 임계를 넘었다.")
SCENE = "주변에 좁은 골목과 낮은 주택이 보인다."
NOTES = ["매일 아침 시장에 가서 사람들과 이야기한다", "길을 잘 알고 혼자 멀리까지 다닌다"]

# (시장 라벨, 파트너 라벨, 파트너 place_type) — 좌표·가중치는 전 셀 동일.
#
# 통제 3셀(하단): 분리 결과 원인 문자열이 "정릉시장"으로 특정된 뒤, 그것이
# 데모 고유 현상인지 "장소명 일반"인지 가른다. 가설 = 튜닝은 goal 선택 **정책**만
# 가르쳤고(원본 base 는 어떤 라벨에도 0~1/15) 어떤 문자열이 근거 문턱을 넘는지는
# 베이스 사전지식이 정한다. 가설이 맞으면 유명 시장명은 정릉시장처럼 선택되고,
# 틀리면(정릉시장만 선택) 데모 의존이 남아 별도 원인 탐색이 필요하다.
#   남대문시장       — 전국구 유명 실존 시장 (학습 코퍼스 밖)
#   청량리 경동시장  — 실존 + 골드셋 어휘 (학습 코퍼스 밖, build_dataset 제외목록)
#   재래시장         — 학습 코퍼스의 goal 버킷 어휘 그대로 (일반명사)
CELLS = {
    "정릉시장 + 옛집(아리랑고개) [데모쌍]": ("정릉시장", "옛집(아리랑고개)", "past_residence"),
    "망원시장 + 경로당 [비데모쌍]": ("망원시장", "경로당", ""),
    "정릉시장 + 경로당 [시장만 데모]": ("정릉시장", "경로당", ""),
    "망원시장 + 옛집(아리랑고개) [파트너만 데모]": ("망원시장", "옛집(아리랑고개)", "past_residence"),
    "남대문시장 + 경로당 [유명 실존]": ("남대문시장", "경로당", ""),
    "청량리 경동시장 + 경로당 [골드셋 어휘]": ("청량리 경동시장", "경로당", ""),
    "재래시장 + 경로당 [학습 어휘]": ("재래시장", "경로당", ""),
    # 분해 3셀 — 통제 결과 "정릉시장"만 이상 반응(14~15/15 vs 0~4/15)으로 나온 뒤,
    # 그 반응이 "정릉" 접두에서 오는지, 정확한 문자열 형태에서 오는지 가른다.
    "정릉 시장(공백) + 경로당 [형태 변형]": ("정릉 시장", "경로당", ""),
    "성북시장 + 경로당 [인접 지명]": ("성북시장", "경로당", ""),
    "정릉슈퍼 + 경로당 [접두만 유지]": ("정릉슈퍼", "경로당", ""),
}
_LOCS = [(37.6047, 127.0121, 0.30), (37.6015, 127.0088, 0.55)]   # 시장, 파트너 순


def main() -> None:
    if llm.exaone.is_stub:
        raise SystemExit("스텁 모드 — 실호출 전용 프로브다. EXAONE_* 환경변수를 확인하라.")
    print(f"모델 mind={settings.mind_model} / repeats={REPEATS}\n")

    rng = random.Random(42)
    results: dict[str, list[dict]] = {}
    for cell, (market, partner, ptype) in CELLS.items():
        persona = Persona(
            id="swap", name="테스트", age=78, type=PersonaType.dementia, home=LKP,
            attraction_points=[
                AttractionPoint(label=market, location=GeoPoint(lat=_LOCS[0][0], lng=_LOCS[0][1]),
                                weight=_LOCS[0][2]),
                AttractionPoint(label=partner, location=GeoPoint(lat=_LOCS[1][0], lng=_LOCS[1][1]),
                                weight=_LOCS[1][2], place_type=ptype),
            ],
            behavior_notes=NOTES)
        names = [ap.label for ap in persona.attraction_points]
        prior = PriorParams(
            strategy_probs={"route_following": 0.25, "direction_keeping": 0.15,
                            "random_walk": 0.15, "backtracking": 0.10,
                            "staying_put": 0.10, "landmark_seeking": 0.25},
            attraction_weights={market: 0.4, partner: 0.6},
            radius_lognormal=LognormalParams(mu=0.095, sigma=1.48),
            reasoning="라벨 교체 프로브 고정 prior")
        rows = []
        for _ in range(REPEATS):
            mind, goal = llm.exaone.reinterpret_mind(
                persona, MindState(), GAUGE, names, prior, SCENE, rng=rng)
            rows.append({"status": mind.status, "confusion": mind.confusion,
                         "behavior": mind.behavior, "goal": goal})
        results[cell] = rows
        goals = Counter(r["goal"] or "(없음)" for r in rows)
        beh = Counter(r["behavior"] or "(없음)" for r in rows)
        picked = sum(1 for r in rows if r["goal"])
        market_hit = sum(1 for r in rows if r["goal"] == market)
        print(f"{cell}")
        print(f"   goal선택 {picked}/{REPEATS}  진술정합({market}) {market_hit}/{REPEATS}")
        print(f"   goal {dict(goals)}")
        print(f"   behavior {dict(beh)}")

    (OUT_DIR / "results_label_swap.json").write_text(
        json.dumps({"gauge": GAUGE, "scene": SCENE, "notes": NOTES, "repeats": REPEATS,
                    "mind_model": settings.mind_model, "raw": results},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장: {OUT_DIR / 'results_label_swap.json'}")


if __name__ == "__main__":
    main()
