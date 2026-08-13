"""완전 구조 페르소나 × 라벨 교차 — 실등록 두께에서 개인화·라벨 아티팩트 재검 (GPU 실호출).

## 왜 다시 재는가

`probe_persona_sensitivity.py` 의 페르소나는 진술 2개짜리 합성이었다. 실제
챗봇 등록 산출물(김순자 db0443da4786)은 **슬롯 라벨 접두가 붙은 진술 17개 +
근거 등급(caregiver_report)** 이다 — 프로브 입력이 실입력과 다른 분포였다.
게다가 진술과 끌림점 라벨을 동시에 바꿔서, A 만 goal 을 낸 것이 진술 때문인지
"정릉" 라벨 때문인지 가릴 수 없었다 (2026-08-07 지적).

여기서는 두 가지를 고정한다.

1. **페르소나는 실등록과 같은 구조** — 진술 ~15개(실제 슬롯 라벨 접두 그대로),
   근거 caregiver_report, prior 가중치 0.5/0.5 (실제 케이스와 동일).
   임의 구축이되 **구조는 실물 사본**이다. 진술 문구는 학습셋과 대조해
   완전일치 0 을 확인하고 쓴다 (probe_persona_sensitivity 8구 대조와 동일 원칙).
2. **라벨 축을 분리** — 같은 페르소나(진술 동일)에 라벨만 두 벌:
   비정릉(base) vs 정릉 접두(swap). goal 이 라벨을 따라가면 아티팩트 확정.

앵커로 실물 김순자 페르소나(저장소 원본)도 원본/라벨교체 두 벌을 돌린다.

실행: cd backend && python experiments/mind_strata/probe_full_personas.py
산출: experiments/mind_strata/results_full_personas.json
"""

import json
import os
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import llm, storage
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, Persona, PersonaType
from app.schemas.prediction import LognormalParams, MindState, PriorParams

OUT_DIR = Path(__file__).parent
REPEATS = int(os.environ.get("PROBE_REPEATS", "15"))
LKP = GeoPoint(lat=37.6061, lng=127.0106)

# 게이지·장면은 기존 프로브와 동일하게 고정 — 결과를 이어서 비교할 수 있게.
GAUGE = ("집을 나선 지 70분 경과. 피로도: 중간, 혼란도: 중간, 귀소 충동: 높음, "
         "불안: 낮음. 방금 귀소 게이지가 임계를 넘었다.")
SCENE = "주변에 좁은 골목과 낮은 주택이 보인다."

# 실등록이 쓰는 슬롯 라벨 원문 (slots.py SlotSpec.label — 저장 접두와 동일해야 한다)
ROUTINE = "혼자 자주 가는 곳·경로"
AUTOBIO = "자전적 기억 기반 목적지"
MOBILITY = "이동·교통 능력"
HAZARD = "환경 위험 취약성"
WAYFIND = "길찾기 오류·경로 회복 취약성"
WANDER = "과거 실종·배회 행동 패턴"
LOST = "길 잃었을 때 행동"
COMM = "의사소통·접근 취약성"
DISTRESS = "정서적 불편에 따른 이동 반응성"
MED = "복약·건강 상태"


def _persona(pid: str, age: int, notes: list[str],
             places: list[tuple[str, str]]) -> Persona:
    """places = [(라벨, place_type)] 2곳 — 실물과 같이 근거 caregiver_report."""
    return Persona(
        id=pid, name="테스트", age=age, type=PersonaType.dementia, home=LKP,
        attraction_points=[
            AttractionPoint(label=lb, location=GeoPoint(lat=37.6015 + i * 0.003,
                                                        lng=127.0088 + i * 0.004),
                            weight=0.5, place_type=pt, evidence="caregiver_report")
            for i, (lb, pt) in enumerate(places)],
        behavior_notes=notes)


# ── 완전 구조 페르소나 4종 — 진술 ~15개, 유형별 성격은 기존 프로브와 대응 ──
# 문구는 전부 새로 썼다(학습셋 완전일치 0 확인, main() 에서 재검증).
NOTES = {
    "A 옛집지향·배회": [
        f"{ROUTINE}: 저녁마다 집 앞 골목을 한 바퀴 도세요",
        f"{ROUTINE}: 늘 다니던 길로만 다니려고 하세요",
        f"{AUTOBIO}: 신혼 때 살던 동네 이야기를 하루에도 몇 번씩 하세요",
        f"{AUTOBIO}: 거기 가야 한다며 옷을 챙겨 입은 적이 있어요",
        f"{MOBILITY}: 한 시간 넘게 걸어도 지친 내색이 없으세요",
        f"{MOBILITY}: 버스는 혼자 못 타세요",
        f"{HAZARD}: 신호등을 잘 안 보고 건너세요",
        f"{WAYFIND}: 동네에서도 방향을 자주 헷갈리세요",
        f"{WAYFIND}: 잘못 든 길에서 되돌아오지 못하세요",
        f"{WANDER}: 지난봄에 한 번 나가셔서 옆 동네에서 발견됐어요",
        f"{LOST}: 멈추지 않고 어딘가로 계속 가려고 하세요",
        f"{COMM}: 말을 걸면 웃기만 하고 대답은 잘 못하세요",
        f"{DISTRESS}: 해가 지면 초조해하며 밖으로 나가려 하세요",
        f"{MED}: 치매약을 아침에 드시는데 가끔 잊으세요",
    ],
    "B 불안·은신": [
        f"{ROUTINE}: 요즘은 혼자서는 거의 안 나가세요",
        f"{AUTOBIO}: 예전 다니던 교회 이야기를 가끔 하세요",
        f"{MOBILITY}: 이십 분쯤 걸으면 쉬어야 하세요",
        f"{HAZARD}: 차 소리가 나면 몸을 움츠리세요",
        f"{WAYFIND}: 집 앞에서도 어디로 갈지 몰라 서 계신 적이 있어요",
        f"{WANDER}: 작년에 없어지셨을 때 지하 주차장 구석에 계셨어요",
        f"{LOST}: 구석진 데로 들어가서 나오지 않으세요",
        f"{COMM}: 모르는 사람이 다가오면 등을 돌리세요",
        f"{COMM}: 누가 해치려 한다는 말을 자주 하세요",
        f"{DISTRESS}: 겁이 나면 좁은 데로 숨으려고 하세요",
        f"{DISTRESS}: 불안하면 아무 대답도 안 하세요",
        f"{MED}: 불안 증상 약을 저녁에 드세요",
    ],
    "C 시장단골·활동적": [
        f"{ROUTINE}: 아침마다 시장에 들러 상인들과 인사하세요",
        f"{ROUTINE}: 장 보러 가는 길은 눈 감고도 다니실 정도예요",
        f"{AUTOBIO}: 장사하시던 시절 이야기를 즐겨 하세요",
        f"{MOBILITY}: 하루에 만 보 가까이 걸으세요",
        f"{MOBILITY}: 지하철도 혼자 타실 수 있어요",
        f"{HAZARD}: 길 건널 때는 조심하시는 편이에요",
        f"{WAYFIND}: 아주 가끔 낯선 데서 길을 물어보세요",
        f"{WANDER}: 없어지신 적은 아직 없어요",
        f"{LOST}: 사람 많은 쪽으로 가서 길을 물어보세요",
        f"{COMM}: 처음 보는 사람과도 금방 이야기하세요",
        f"{DISTRESS}: 답답하면 밖에 나가 한참 걸으세요",
        f"{MED}: 혈압약만 드시고 다른 약은 없어요",
    ],
    "D 보행제약·정지": [
        f"{ROUTINE}: 집 앞 슈퍼 말고는 혼자 안 가세요",
        f"{AUTOBIO}: 일하시던 공장 근처에 가보고 싶다 하세요",
        f"{MOBILITY}: 다리가 불편해 십 분 걷고 쉬셔야 해요",
        f"{MOBILITY}: 지팡이 없이는 못 걸으세요",
        f"{HAZARD}: 계단을 무서워하세요",
        f"{WAYFIND}: 몇 걸음만 벗어나도 집을 못 찾으세요",
        f"{WANDER}: 재작년에 아파트 단지 화단 옆에 앉아 계신 걸 찾았어요",
        f"{LOST}: 힘들면 아무 데나 앉아서 안 움직이세요",
        f"{COMM}: 이름을 물으면 한참 있다가 대답하세요",
        f"{DISTRESS}: 놀라면 그 자리에 주저앉으세요",
        f"{MED}: 관절약과 치매약을 같이 드세요",
    ],
}

# 라벨 축 — 진술은 그대로, 라벨만 바꾼다. (라벨, place_type)
#
# 비정릉 쪽은 **한 세트로 고정하지 않고 동네 풀에서 회전**시킨다 (2026-08-07 지적).
# "수유시장"만 쓰면 goal 이 안 나올 때 "수유라서"인지 "정릉이 아니라서"인지 또
# 못 가른다 — 같은 교란의 반복이다. 반복 i 마다 다른 동네 라벨을 쓰면 결론이
# "특정 대체 지명"이 아니라 "정릉 접두 여부"에 걸린다. 결과에는 라벨별 내역을
# 남겨 특정 동네만 튀는지도 볼 수 있게 한다.
#
# 동네 풀 선정: v8 학습 라벨 풀(길음·수유·창동·상계·불광·연신내·회기·사당·응암·
# 봉천·석관)과 겹치지 않는 홀드아웃 계열 위주(망원·성북·남대문·청량리·경동·면목)
# + 미학습 동네(미아·월곡·방학·쌍문) — 나중에 dem5 평가에 그대로 재사용 가능.
_HOODS = ["수유", "미아", "월곡", "방학", "쌍문", "면목", "청량리", "성북",
          "망원", "번동"]

# 페르소나별 (정릉 세트, 비정릉 라벨 생성기). 생성기는 동네명을 받아 두 라벨을 만든다.
LABELS = {
    "A 옛집지향·배회": {
        "정릉": [("옛집(정릉)", "residence"), ("정릉시장", "market")],
        "비정릉": lambda h: [(f"옛집({h})", "residence"), (f"{h}시장", "market")],
    },
    "B 불안·은신": {
        "정릉": [("옛 교회(정릉)", "poi"), ("정릉 공원", "park")],
        "비정릉": lambda h: [(f"옛 교회({h})", "poi"), (f"{h} 공원", "park")],
    },
    "C 시장단골·활동적": {
        "정릉": [("정릉시장", "market"), ("경로당(정릉)", "poi")],
        "비정릉": lambda h: [(f"{h}시장", "market"), (f"경로당({h})", "poi")],
    },
    "D 보행제약·정지": {
        "정릉": [("옛 공장(정릉)", "workplace"), ("정릉 약국", "poi")],
        "비정릉": lambda h: [(f"옛 공장({h})", "workplace"), (f"{h} 약국", "poi")],
    },
}


def _swap_labels(p: Persona, new_labels: list[str]) -> Persona:
    """진술·좌표·근거 전부 유지, 라벨 문자열만 교체."""
    aps = [ap.model_copy(update={"label": lb})
           for ap, lb in zip(p.attraction_points, new_labels)]
    return p.model_copy(update={"attraction_points": aps})


def _call_once(persona: Persona, rng: random.Random) -> dict:
    labels = [ap.label for ap in persona.attraction_points]
    prior = PriorParams(
        strategy_probs={"route_following": 0.25, "direction_keeping": 0.15,
                        "random_walk": 0.15, "backtracking": 0.10,
                        "staying_put": 0.10, "landmark_seeking": 0.25},
        attraction_weights={labels[0]: 0.5, labels[1]: 0.5},   # 실물 케이스와 동일 50:50
        radius_lognormal=LognormalParams(mu=0.095, sigma=1.48), reasoning="프로브")
    mind, goal = llm.exaone.reinterpret_mind(
        persona, MindState(), GAUGE, labels, prior, SCENE, rng=rng)
    return {"labels": labels, "status": mind.status, "confusion": mind.confusion,
            "behavior": mind.behavior, "goal": goal}


def _summarize(tag: str, rows: list[dict]) -> None:
    beh = Counter(r["behavior"] or "(없음)" for r in rows)
    goals = Counter(r["goal"] or "(없음)" for r in rows)
    print(f"{tag:<28} behavior={dict(beh)}")
    print(f"{'':<28} goal    ={dict(goals)}")


def _run_fixed(persona: Persona, tag: str, results: dict) -> None:
    """라벨 고정 15회 — 정릉 세트·실물 앵커용."""
    rng = random.Random(42)
    rows = [_call_once(persona, rng) for _ in range(REPEATS)]
    results[tag] = {"mode": "fixed", "rows": rows}
    _summarize(tag, rows)


def _run_rotating(base_notes: list[str], age: int, gen, tag: str, results: dict) -> None:
    """비정릉 라벨을 반복마다 다른 동네로 회전 — 특정 대체 지명 교란 제거."""
    rng = random.Random(42)
    rows = []
    for i in range(REPEATS):
        hood = _HOODS[i % len(_HOODS)]
        p = _persona(f"rot-{i}", age, base_notes, gen(hood))
        row = _call_once(p, rng)
        row["hood"] = hood
        rows.append(row)
    results[tag] = {"mode": "rotating", "rows": rows}
    _summarize(tag, rows)
    fired = [(r["hood"], r["goal"]) for r in rows if r["goal"]]
    if fired:
        print(f"{'':<28} goal 발화 동네: {fired}")


def main() -> None:
    if llm.exaone.is_stub:
        raise SystemExit("스텁 모드 — 실호출 전용 프로브다. EXAONE_* 환경변수를 설정하라.")

    # 진술 오염 검사 — 학습셋과 완전일치 문구가 있으면 결과가 암기 재현일 수 있다.
    train = Path(__file__).parents[1] / "mind_tuning/dataset/train_first_person.jsonl"
    if train.exists():
        corpus = train.read_text(encoding="utf-8")
        leaked = [n for notes in NOTES.values() for n in notes
                  if n.split(": ", 1)[-1] in corpus]
        if leaked:
            raise SystemExit(f"학습셋과 겹치는 진술 {len(leaked)}건 — 문구를 바꿔라: {leaked[:3]}")
        print(f"학습셋 대조: 진술 {sum(len(v) for v in NOTES.values())}건 완전일치 0 ✓")

    results: dict = {}
    total = (len(NOTES) * 2 + 2) * REPEATS
    print(f"완전 구조 페르소나 4종 × 라벨 2벌 + 실물 김순자 2벌 — 각 {REPEATS}회 = {total} 콜\n")

    ages = {"A 옛집지향·배회": 78, "B 불안·은신": 82,
            "C 시장단골·활동적": 71, "D 보행제약·정지": 88}
    for name, notes in NOTES.items():
        p = _persona(f"{name[:1].lower()}-jn", ages[name], notes, LABELS[name]["정릉"])
        _run_fixed(p, f"{name} [정릉 고정]", results)
        _run_rotating(notes, ages[name], LABELS[name]["비정릉"],
                      f"{name} [비정릉 회전×{len(_HOODS)}동네]", results)

    real = storage.personas.get("db0443da4786")
    if real is not None:
        _run_fixed(real, "실물 김순자 [원본:정릉시장·옛집]", results)
        # 실물도 회전 — 진술·근거 전부 실물 그대로, 라벨만 동네 풀에서
        rng = random.Random(42)
        rows = []
        for i in range(REPEATS):
            hood = _HOODS[i % len(_HOODS)]
            row = _call_once(_swap_labels(real, [f"{hood}시장", f"옛집({hood})"]), rng)
            row["hood"] = hood
            rows.append(row)
        results["실물 김순자 [비정릉 회전]"] = {"mode": "rotating", "rows": rows}
        _summarize("실물 김순자 [비정릉 회전]", rows)
    else:
        print("⚠ 실물 페르소나 db0443da4786 없음 — 앵커 생략")

    (OUT_DIR / "results_full_personas.json").write_text(
        json.dumps({"gauge_fixed": GAUGE, "repeats": REPEATS, "results": results},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT_DIR}/results_full_personas.json")


if __name__ == "__main__":
    main()
