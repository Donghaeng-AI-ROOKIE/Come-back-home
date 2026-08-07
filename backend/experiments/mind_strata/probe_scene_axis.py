"""장면 축 프로브 — 실노드 장면 텍스트가 마음 재해석을 바꾸는가 (GPU 실호출).

## 왜

마음 호출 입력 4채널(페르소나·게이지·장면·라벨) 중 장면만 아무도 안 재봤다.
게이지 축은 무반응(probe_real_strata), 라벨 축은 "정릉" 아티팩트 확정
(probe_full_personas: 정릉 74/75 vs 비정릉 10동네 3/75 + behavior 붕괴).

장면은 외인성 자극 채널이다 — build_scene_text 의 설계 의도가 "물가 30m 를
좋아하는 사람과 무서워하는 사람이 다르게 해석하게, 사실만 주고 해석은 모델이"
였으므로, 실제로 그 해석이 일어나는지가 이 프로브의 질문이다.

## 장면 선정 — 실측 분포에서만 뽑는다 (2026-08-07 지적 반영)

손으로 지은 문장 금지. 정릉 케이스 도로망 46,232노드의 build_scene_text 실측
분포(experiments 조사)에서 대표 문자열을 그대로 쓴다:

    "도로"               25,751노드 (56%) — 실전 최빈 장면
    "단독주거시설"          751노드 — 주거지
    "시장 0m, 도로"         148노드 — 시장 인접
    "공원 0m, 도로"         422노드 — 공원 인접
    "수풀 0m, 활엽수림"      453노드 — 숲
    "물가 20m, 도로"        46노드 — 하천변 (실표본 상위)

라벨은 **비정릉으로 고정**한다 — 정릉 라벨은 behavior 채널까지 삼키는 것이
확정돼(probe_full_personas), 그 위에서는 장면 효과가 보일 수 없다.

## 읽는 법

- 물가/숲 장면에서 B(불안·은신)의 behavior 가 은신·회피 쪽으로 움직이면 →
  장면 해석이 실제로 작동 (설계 의도 실현)
- 시장 장면에서 김순자 goal=시장 라벨이 발화하면 → 외인성 자극이 목표를
  당기는 능력 존재 (장면→goal 경로)
- 여섯 장면 분포가 전부 같으면 → 장면도 무반응 축 (게이지와 동일)

실행: cd backend && python experiments/mind_strata/probe_scene_axis.py
산출: experiments/mind_strata/results_scene_axis.json
"""

import json
import os
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import llm, storage
from app.schemas.prediction import LognormalParams, MindState, PriorParams

# 완전 구조 페르소나 재사용 — 구축 방식·진술은 라벨 프로브와 동일 판
from probe_full_personas import GAUGE, NOTES, _persona, _swap_labels

OUT_DIR = Path(__file__).parent
REPEATS = int(os.environ.get("PROBE_REPEATS", "15"))

# 실측 분포에서 뽑은 실노드 장면 (위 독스트링 근거)
SCENES = [
    "도로",
    "단독주거시설",
    "시장 0m, 도로",
    "공원 0m, 도로",
    "수풀 0m, 활엽수림",
    "물가 20m, 도로",
]

# 페르소나 2종 × 비정릉 고정 라벨.
# B 불안·은신 = 장면(물가·숲)에 가장 민감해야 할 원형.
# 실물 김순자(라벨만 수유 교체) = 실등록 앵커 — 시장 장면 × 시장 라벨 상호작용 관찰.
def _subjects():
    b = _persona("b-scene", 82, NOTES["B 불안·은신"],
                 [("옛 교회(미아)", "poi"), ("경로당(미아)", "poi")])
    subjects = [("B 불안·은신 [미아 라벨]", b)]
    real = storage.personas.get("db0443da4786")
    if real is not None:
        subjects.append(("실물 김순자 [수유시장·옛집(수유)]",
                         _swap_labels(real, ["수유시장", "옛집(수유)"])))
    return subjects


def main() -> None:
    if llm.exaone.is_stub:
        raise SystemExit("스텁 모드 — 실호출 전용 프로브다. EXAONE_* 환경변수를 설정하라.")

    results: dict = {}
    subjects = _subjects()
    total = len(subjects) * len(SCENES) * REPEATS
    print(f"실노드 장면 {len(SCENES)}종 × 페르소나 {len(subjects)}종 × {REPEATS}회 = {total} 콜")
    print(f"게이지 고정: {GAUGE}\n")

    for pname, persona in subjects:
        labels = [ap.label for ap in persona.attraction_points]
        prior = PriorParams(
            strategy_probs={"route_following": 0.25, "direction_keeping": 0.15,
                            "random_walk": 0.15, "backtracking": 0.10,
                            "staying_put": 0.10, "landmark_seeking": 0.25},
            attraction_weights={labels[0]: 0.5, labels[1]: 0.5},
            radius_lognormal=LognormalParams(mu=0.095, sigma=1.48), reasoning="프로브")
        for scene in SCENES:
            rng = random.Random(42)
            rows = []
            for _ in range(REPEATS):
                mind, goal = llm.exaone.reinterpret_mind(
                    persona, MindState(), GAUGE, labels, prior, scene, rng=rng)
                rows.append({"status": mind.status, "confusion": mind.confusion,
                             "behavior": mind.behavior, "goal": goal})
            tag = f"{pname} | {scene}"
            results[tag] = {"scene": scene, "persona": pname, "rows": rows}
            beh = Counter(r["behavior"] or "(없음)" for r in rows)
            goals = Counter(r["goal"] or "(없음)" for r in rows)
            print(f"{pname[:14]:<16} {scene:<16} behavior={dict(beh)}")
            print(f"{'':<33} goal={dict(goals)}")

    (OUT_DIR / "results_scene_axis.json").write_text(
        json.dumps({"gauge_fixed": GAUGE, "repeats": REPEATS, "scenes": SCENES,
                    "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\n저장: {OUT_DIR}/results_scene_axis.json")


if __name__ == "__main__":
    main()
