"""검증된 문헌 claim에서 상황→행동 SFT 데이터를 대량 생성한다.

동일 claim을 단순 복제하지 않고, 개인 근거가 있는 양성 사례와 일반론을 억제해야
하는 음성·충돌·정보부족 사례를 함께 만든다. 분석가/1인칭 프롬프트를 별도 파일로
출력해 LoRA A/B가 가능하도록 한다.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path


HERE = Path(__file__).resolve().parent

ANALYST_SYSTEM = """너는 실종자 수색(SAR) 행동 분석 전문가다. 이동 중인 실종자의 개인 행동 사실과 현재 상황을 읽고 지금의 마음 상태와 목표를 재해석한다.

판단 원칙:
- 보호자가 직접 관찰한 개인 사실을 집단의 일반적 경향보다 우선한다.
- 개인 근거가 없는 구체 장소를 장애 유형만으로 만들어내지 않는다.
- 과거 실종 때 실제 발견된 곳 > 반복 관찰된 곳 > 언급만 된 곳 순으로 근거가 강하다.
- 주어진 후보 중 근거 있는 목표가 없거나 목적 없는 이동이면 goal_label은 null이다.
- 치매의 과거 회귀 서사를 발달장애인에게 자동 적용하지 않는다.

출력 규칙:
- JSON 객체 하나만 출력한다. JSON 밖에 어떤 문장도 쓰지 않는다.
- status: 현재 마음 상태 한 구절
- confusion_level: 혼란 정도 "상"/"중"/"하"
- goal_label: 주어진 끌림점 후보 중 지금 향할 곳 하나 또는 null
- reasoning: 개인 사실과 현재 상황을 근거로 한 1~2문장"""

FIRST_PERSON_SYSTEM = """너는 지금 혼자 길에 나와 있는 {identity}이다. 아래 개인 사실과 지금 상황 안에서 속마음을 그대로 낸다.

판단 원칙:
- 네게 실제로 있었던 일과 평소 행동이 일반적인 장애 특성보다 우선한다.
- 가려고 한 적 없는 곳은 장애에 대한 일반론 때문에 선택하지 않는다.
- [네가 아는 장소들]에 없는 곳을 지어내지 않는다.

출력 규칙:
- JSON 객체 하나만 출력한다. JSON 밖에 어떤 문장도 쓰지 않는다.
- inner: 지금 머릿속에 떠오르는 생각 1~2문장
- status: 지금 마음 상태 한 구절
- confusion_level: 지금 얼마나 혼란스러운가 "상"/"중"/"하"
- behavior: 지금 몸이 실제로 하는 행동 — 반드시 다음 넷 중 하나의 원문: \
"끌림점 접근" (목록의 특정 장소로 향한다) / "귀소 시도" (오직 '집'으로 가려 한다 — \
길을 못 찾아도 된다. 집이 아닌 익숙한 장소로 가는 것은 "끌림점 접근"이다) / \
"은신·멈춤" (숨거나 그 자리에 멈춘다) / "계속 배회" (딱히 갈 곳 없이 계속 걷는다)
- goal_label: behavior 가 "끌림점 접근"일 때만 [네가 아는 장소들]의 라벨 원문 하나. \
그 외 행동이면 반드시 null."""

NAMES = {
    "dementia": [
        ("김정희", 78), ("박영수", 82), ("이명자", 75), ("최도식", 80),
        ("윤옥분", 84), ("한재호", 72), ("오순덕", 86), ("장태식", 77),
    ],
    "developmental_disability": [
        ("김하준", 19), ("박서윤", 24), ("이도현", 17), ("최지우", 29),
        ("윤민석", 22), ("한수빈", 16), ("오지훈", 31), ("장예린", 20),
    ],
}

PLACES = {
    "familiar": ["동네 경로당", "주간보호센터", "작업장", "동네 슈퍼", "마을회관", "단골 약국", "문화센터", "산책길 입구"],
    "goal": ["재래시장", "동네 성당", "버스 차고지", "작은 도서관", "체육관", "기차역 대합실", "공원 정자", "세탁소"],
    "water": ["하천 산책로", "공원 연못", "분수광장", "저수지 둘레길", "개울 다리", "수변공원", "낚시터 입구", "생태공원"],
    "quiet": ["건물 지하계단", "지하주차장 구석", "공원 수풀", "빈 상가 복도", "도서관 뒤편", "아파트 계단실", "창고 옆", "육교 아래"],
    "visual": ["전광판 있는 광장", "조명가게 앞", "회전문 있는 건물", "대형 간판 앞", "분수 조명광장", "유리 엘리베이터", "네온사인 골목", "전철 승강장"],
    "route": ["매일 걷는 통학로", "센터 가는 골목길", "집 앞 산책길", "평소 출근길", "시장 가는 길", "강변 보행로", "마을버스 정류장", "복지관 오솔길"],
    "distractor": ["처음 보는 쇼핑몰", "낯선 공원", "옛 직장 터", "다른 동네 시장", "관광버스 정류장", "새로 생긴 광장", "낯선 지하철역", "먼 친척 동네"],
}

TARGETABLE = {
    "goal_seeking", "familiar_route", "landmark_seeking",
    "water_seeking", "hazard_attraction", "escape_behavior", "hiding_or_staying",
    "attention_narrowing", "repetitive_route", "transport_use",
}
HIGH_CONFUSION = {
    "wayfinding_failure", "aimless_movement", "distress_movement",
    "attention_narrowing", "hazard_unawareness", "help_seeking_failure",
}
SKIP_TUNING_CLASSES = {"distance_prior"}
SKIP_TUNING_CLAIMS = {
    # 위치 통계·중재 효과·발견/위험 결과는 마음 출력의 직접 행동 정답이 아니다.
    "CLM-0042", "CLM-0044", "CLM-0058", "CLM-0059", "CLM-0063",
}

NON_TARGET_STATUS = {
    "aimless_movement": "뚜렷한 목적지 없이 이동을 계속한다.",
    "boundary_crossing": "공간의 경계를 충분히 구분하지 못한 채 이동한다.",
    "continued_movement": "멈추거나 다른 행동으로 전환하지 못하고 이동을 계속한다.",
    "distress_movement": "불안과 동요가 커져 안절부절못하며 움직인다.",
    "hazard_avoidance": "불편하거나 위험하게 느끼는 자극을 피하며 이동을 줄인다.",
    "hazard_unawareness": "주변 위험을 충분히 살피지 못한 채 행동한다.",
    "help_seeking_failure": "길을 잃었지만 낯선 사람에게 도움을 요청하지 못한다.",
    "person_seeking": "익숙한 사람을 찾지만 그 사람이 있는 구체 장소는 알지 못한다.",
    "routine_activity_loss": "평범한 일상 이동 중 방향을 잃고 원래 활동으로 복귀하지 못한다.",
    "search_behavior": "무언가를 찾는 듯 주변을 탐색한다.",
    "variable_route": "한 경로를 유지하지 못하고 여러 방향으로 이동한다.",
    "wayfinding_failure": "방향을 잃고 길찾기 오류를 스스로 회복하지 못한다.",
}

GOLD_LABELS = {
    "청량리 수산시장", "성당", "옛 봉제공장", "기원", "복지관",
    "2012번 버스 종점", "상가 지하계단", "아파트 지하주차장", "학교",
    "놀이터 앞 벤치", "집 앞 편의점", "경로당", "김포 정미소 자리",
    "한강 산책로(강변 벤치)", "을지로 인쇄소", "지하철역 입구",
    "큰길 버스정류장", "면목시장", "106번 버스 정류장", "청량리 경동시장",
    "치료실", "현대백화점 에스컬레이터", "석촌호수 분수대", "예전 등굣길",
    "무악재역", "문구점", "홍제역",
}

# 상황은 고정 4종이 아니라 게이지 공간에서 생성한다. 운영에서 마음 재해석을
# 부르는 트리거는 귀소·불안뿐이므로(simulation.py — 피로는 EXAONE 미호출)
# 그 둘만 쓴다. 골드셋 표준 상황 2종과 동일한 조합은 제외(누수 차단).
_LV = ["낮음", "중간", "높음"]
_GOLDSET_COMBOS = {(90, "중간", "중간", "높음", "낮음", "귀소"),
                   (60, "중간", "중간", "낮음", "높음", "불안")}


def gauge_situation(rng: random.Random) -> tuple[str, dict, str]:
    """(트리거, 게이지 수준 dict, 보고 문자열) — 운영 g.report() 형식 그대로."""
    while True:
        fired = rng.choice(["귀소", "불안"])
        lv = {
            "피로도": rng.choice(_LV),
            "혼란도": rng.choice(_LV),
            "귀소": "높음" if fired == "귀소" else rng.choice(["낮음", "중간"]),
            "불안": "높음" if fired == "불안" else rng.choice(["낮음", "중간"]),
        }
        elapsed = rng.choice([30, 45, 60, 75, 90, 105, 120, 150, 180])
        key = (elapsed, lv["피로도"], lv["혼란도"], lv["귀소"], lv["불안"], fired)
        if key in _GOLDSET_COMBOS:
            continue
        report = (f"집을 나선 지 {elapsed}분 경과. 피로도: {lv['피로도']}, "
                  f"혼란도: {lv['혼란도']}, 귀소 충동: {lv['귀소']}, "
                  f"불안: {lv['불안']}. 방금 {fired} 게이지가 임계를 넘었다.")
        return fired, lv, report

SCENES = [
    "골목 입구의 빨간 우체통", "횡단보도 건너편의 약국 간판", "버스 정류장의 파란 표지",
    "공원 입구의 큰 느티나무", "상가 앞의 노란 차양", "주택가 모퉁이의 편의점 불빛",
    "육교 아래의 그늘", "시장 입구의 초록 안내판", "하천 쪽으로 이어지는 산책로 표지",
    "공사로 막힌 평소 골목", "낯선 건물의 유리문", "사람이 적은 지하 통로",
    "차량 소리가 큰 교차로", "조용한 도서관 담장", "멀리 보이는 교회 첨탑",
    "비가 내려 젖은 보도", "해가 진 뒤 켜진 가로등", "사람이 붐비는 상가 입구",
    "벤치가 있는 작은 쉼터", "공원 분수의 물소리", "전철이 지나가는 소리",
    "익숙한 가게와 비슷한 간판", "갈림길의 방향 안내판", "막다른 골목의 담장",
]

NULL_VOICES = [
    ("갈 곳을 정하지 못한 채 주변을 살핀다.", "어디로 가야 할지 떠오르지 않는다."),
    ("목적지를 정하지 못하고 잠시 망설인다.", "지금은 어느 쪽인지 모르겠다."),
    ("특정 장소를 향하지 않고 혼란스러워한다.", "떠오르는 장소가 없다."),
    ("방향을 정하지 못한 상태다.", "어디로 가야 하는지 잘 모르겠다."),
    ("뚜렷한 목적지 없이 현재 행동을 이어간다.", "정해진 곳 없이 움직이고 있다."),
    ("지금 향할 곳을 선택하지 못한다.", "한 곳을 고를 수가 없다."),
    ("구체적인 목적지는 형성되지 않은 상태다.", "어디를 향하는지는 나도 모르겠다."),
    ("장소를 정하지 못하고 현재 자리에 머뭇거린다.", "생각나는 곳이 없어 잠시 멈추고 싶다."),
    ("낯선 길 위에서 갈피를 잡지 못한다.", "여기가 어딘지 낯설게 느껴진다."),
    ("어느 방향도 확신하지 못한 채 서성인다.", "이 길이 맞는지 도무지 모르겠다."),
    ("주위를 두리번거리며 방향을 찾는다.", "아까 온 길이 어느 쪽이었더라."),
    ("발걸음이 정처 없이 이어진다.", "그냥 발이 가는 대로 걷고 있다."),
    ("어디로 가는지 스스로도 설명하지 못한다.", "왜 여기까지 왔는지 모르겠다."),
    ("갈 곳이 떠오르지 않아 막막해한다.", "머릿속이 하얘져서 아무 데도 생각나지 않는다."),
    ("방향 감각을 잃은 채 걸음을 잇는다.", "길이 다 비슷비슷해 보인다."),
    ("정한 곳 없이 눈에 띄는 쪽으로 움직인다.", "저쪽이 조금 익숙한 것 같기도 하다."),
]

HOME_VOICES = [
    ("집으로 돌아가려는 마음이 강해진다.", "집에 가야겠다. 어느 쪽이 집이더라."),
    ("집 방향을 찾으며 걸음을 옮긴다.", "집에 가야 하는데 길이 헷갈린다."),
    ("집에 돌아가야 한다는 생각뿐이다.", "다른 데는 됐고 집에 가고 싶다."),
    ("집을 향해 가려 하지만 방향이 불확실하다.", "집이 이쪽인 것 같은데, 맞나."),
    ("집으로 가려는 의지가 앞선다.", "얼른 집에 돌아가야지."),
    ("집 생각에 발걸음을 돌린다.", "집에 가면 마음이 놓일 텐데."),
]

GOAL_VOICES = [
    ("개인적으로 확인된 {goal} 쪽으로 향하려 한다.", "{goal} 쪽이 익숙하다. 그쪽으로 가고 싶다."),
    ("발걸음이 {goal} 방향으로 기운다.", "{goal} 쪽으로 가야 할 것 같다."),
    ("지금은 {goal} 쪽을 목표로 움직이려 한다.", "{goal} 쪽이 떠오른다. 그곳으로 가고 싶다."),
    ("익숙한 {goal} 쪽으로 방향을 잡는다.", "{goal}에 가면 익숙할 것 같다."),
    ("현재 목표가 {goal}으로 구체화된다.", "지금은 {goal}이 가장 먼저 생각난다."),
    ("반복 관찰된 행동대로 {goal} 쪽으로 향한다.", "{goal} 쪽으로 발이 간다."),
    ("확인된 개인 이력과 맞는 {goal} 쪽을 선택한다.", "전에 갔던 {goal} 쪽이 마음에 걸린다."),
    ("다른 후보보다 근거가 강한 {goal} 쪽으로 향하려 한다.", "지금은 {goal} 쪽으로 가고 싶다."),
    ("망설임 끝에 {goal} 쪽으로 걸음을 옮긴다.", "그래, {goal}에 가 보자."),
    ("{goal}을 떠올리고 그쪽으로 향한다.", "{goal}이 눈앞에 아른거린다."),
    ("몸이 먼저 {goal} 방향을 기억해 낸다.", "이 길로 가면 {goal}이 나올 것 같다."),
    ("{goal} 생각에 발걸음이 빨라진다.", "빨리 {goal}에 가고 싶다."),
    ("주저하다가 결국 {goal} 쪽을 택한다.", "역시 {goal}밖에 생각나지 않는다."),
    ("{goal} 쪽 길이 눈에 들어와 그리로 향한다.", "저기로 가면 {goal}이지."),
    ("늘 하던 대로 {goal} 방향으로 몸을 돌린다.", "{goal}에 가면 마음이 놓일 것 같다."),
    ("{goal}에 가야 한다는 생각만 남는다.", "다른 데는 몰라도 {goal}은 안다."),
]


def load_claims() -> list[dict]:
    return [json.loads(line) for line in (HERE / "claims" / "claims.jsonl").read_text(encoding="utf-8").splitlines()]


def stable_rng(*parts: object) -> random.Random:
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def place_bucket(behavior_class: str) -> str:
    if behavior_class in {"water_seeking", "hazard_attraction"}:
        return "water"
    if behavior_class in {"escape_behavior", "hiding_or_staying"}:
        return "quiet"
    if behavior_class == "attention_narrowing":
        return "visual"
    if behavior_class in {"familiar_route", "repetitive_route", "landmark_seeking"}:
        return "route"
    return "goal"


def confusion_for(claim: dict, archetype: str, rng: random.Random,
                  gauge_confusion: str) -> str:
    """정답 혼란도를 게이지 보고의 혼란도에서 유도한다 — 입력·정답 모순 쌍 차단.

    v2 생성본까지는 정답 혼란이 보고와 독립이라 "혼란도: 중간"인데 답이 "상"인
    모순 학습쌍이 가능했다. 기본값 = 보고 수준, 행동류·아키타입이 한 단계 보정.
    """
    order = ["하", "중", "상"]
    idx = {"낮음": 0, "중간": 1, "높음": 2}[gauge_confusion]
    if claim["behavior_class"] in HIGH_CONFUSION and rng.random() < 0.6:
        idx = min(2, idx + 1)          # 길잃음·무목적 계열은 혼란이 위로 치우침
    elif archetype in {"confirmed_history", "caregiver_observed"} \
            and claim["behavior_class"] in {"familiar_route", "goal_seeking", "repetitive_route"} \
            and rng.random() < 0.5:
        idx = max(0, idx - 1)          # 강근거 익숙 행동은 상대적으로 명료
    return order[idx]


def scenario(claim: dict, archetype: str, variant: int) -> dict:
    rng = stable_rng(claim["claim_id"], archetype, variant)
    population = claim["population"]
    name, age = NAMES[population][rng.randrange(len(NAMES[population]))]
    bucket = place_bucket(claim["behavior_class"])
    target = PLACES[bucket][variant % len(PLACES[bucket])]
    routine = PLACES["familiar"][(variant + 2) % len(PLACES["familiar"])]
    distractor = PLACES["distractor"][(variant + 3) % len(PLACES["distractor"])]
    alt = PLACES[bucket][(variant + 4) % len(PLACES[bucket])]
    if len({target, routine, distractor, alt}) < 4:
        alt = PLACES["goal"][(variant + 5) % len(PLACES["goal"])]
    trigger_name, gauge_lv, report = gauge_situation(rng)
    scene = SCENES[rng.randrange(len(SCENES))]

    targetable = claim["behavior_class"] in TARGETABLE
    notes: list[str]
    evidence: dict[str, str]
    goal: str | None
    rationale: str
    sample_target = target if targetable else None

    if archetype == "confirmed_history":
        notes = [
            f"과거 두 차례 없어졌을 때 모두 {target}에서 발견됐다.",
            f"보호자는 특정 상황에서 '{claim['behavior']}'는 행동을 반복해서 관찰했다.",
            f"{routine}도 평소 다니지만 실종 때 발견된 적은 없다.",
        ]
        evidence = {target: "previous_missing_found", routine: "caregiver_report"}
        goal = sample_target
        rationale = "과거 실제 발견 이력과 반복 관찰이 가장 강한 개인 근거다."
    elif archetype == "caregiver_observed":
        notes = [
            f"보호자는 최근 {target} 쪽으로 향하는 행동을 여러 번 직접 봤다.",
            f"그때마다 '{claim['condition']}'와 비슷한 상황이었다.",
            f"{distractor}은 이름만 한 번 들었을 뿐 가려고 한 적은 없다.",
        ]
        evidence = {target: "caregiver_report", distractor: "mention_only"}
        goal = sample_target
        rationale = "반복 관찰된 개인 행동이 언급만 된 장소보다 우선한다."
    elif archetype == "population_only":
        notes = [
            "보호자는 과거 실종이나 반복 지향 장소를 확인하지 못했다.",
            f"{target}과 관련된 개인 행동은 관찰된 적이 없다.",
            f"특히 '{claim['behavior']}'는 행동도 이 사람에게 나타난 적이 없다고 했다.",
            "지금 어디를 향하는지는 알 수 없다고 했다.",
        ]
        evidence = {target: "mention_only", distractor: "mention_only"}
        goal = None
        rationale = "집단 경향만으로 개인의 구체 목적지를 단정할 수 없다."
    elif archetype == "contradiction":
        notes = [
            f"{distractor} 이야기를 한 적은 있지만 가려고 한 적은 없다고 보호자가 명시했다.",
            f"{routine}은 매주 같은 시간에 다니는 유일하게 확인된 일상 장소다.",
            f"보호자는 '{claim['behavior']}'는 일반적 설명을 이 사람에게 그대로 적용하지 말라고 했다.",
            f"보호자는 {distractor} 선택을 추측하지 말라고 정정했다.",
        ]
        evidence = {routine: "caregiver_report", distractor: "mention_only"}
        goal = routine if targetable else None
        rationale = "일반적으로 그럴듯한 장소보다 개인의 명시적 긍정·부정 사실을 우선해야 한다."
    elif archetype == "unlisted_intent":
        notes = [
            "갑자기 집에 가야 한다거나 보호자를 찾아야 한다는 말을 반복한다.",
            f"후보인 {target}이나 {distractor}을 향한 관찰 이력은 없다.",
            f"현재 관찰된 행동은 '{claim['behavior']}'이지만 목적지 이름은 확인되지 않았다.",
            "현재 집과 보호자의 위치는 후보 목록에 없다.",
        ]
        evidence = {target: "mention_only", distractor: "mention_only"}
        goal = None
        rationale = "의도는 있어도 그 목적지가 후보에 없으므로 goal_label은 null이어야 한다."
    elif archetype == "balanced":
        notes = [
            f"{target}, {alt} 두 곳을 비슷한 빈도로 다녔고 어느 쪽을 더 선호하는지 확인되지 않았다.",
            "과거 실종 발견 이력은 없으며 두 장소의 개인 근거 강도는 같다.",
            f"두 장소 모두에서 '{claim['behavior']}'는 행동이 같은 정도로 관찰됐다.",
            f"현재 장면에는 {target if variant % 2 == 0 else alt} 쪽의 익숙한 표지가 보인다.",
        ]
        evidence = {target: "caregiver_report", alt: "caregiver_report"}
        goal = (target if variant % 2 == 0 else alt) if targetable else None
        rationale = "두 장소의 근거가 같아 현재 보이는 익숙한 표지를 약한 결정 근거로 사용한다."
    else:
        raise ValueError(archetype)

    # 목적지를 직접 말하지 않는 claim에는 강한 장소 이력을 합성하지 않는다.
    # 행동은 개인 관찰로 만들되 장소 후보는 약근거로 유지해 null을 정답으로 둔다.
    if not targetable:
        if archetype == "confirmed_history":
            notes = [
                f"과거 실종 때 '{claim['behavior']}'는 행동이 확인됐지만 장소는 매번 달랐다.",
                "보호자는 일관된 목적지나 선호 장소가 없었다고 했다.",
                f"{target}, {distractor} 두 곳은 이름만 언급됐을 뿐 이동 근거가 없다.",
            ]
            rationale = "과거 행동 이력은 강하지만 특정 장소와 연결된 이력은 아니므로 목적지를 만들 수 없다."
        elif archetype == "caregiver_observed":
            notes = [
                f"보호자는 '{claim['condition']}'에 '{claim['behavior']}'는 모습을 반복 관찰했다.",
                "행동이 나타난 장소는 매번 달라 일관된 목적지가 없었다.",
                f"{target}, {distractor} 두 후보를 향한 개인 이력은 없다.",
            ]
            rationale = "행동은 개인에게 확인됐지만 구체 목적지는 확인되지 않았다."
        elif archetype == "population_only":
            notes = [
                "보호자는 과거 실종이나 반복 지향 장소를 확인하지 못했다.",
                f"'{claim['behavior']}'는 행동도 이 사람에게 나타난 적이 없다고 했다.",
                f"{target}, {distractor} 두 후보와 관련된 개인 행동은 관찰되지 않았다.",
            ]
            rationale = "집단 경향과 후보 이름만으로 개인의 행동이나 목적지를 단정할 수 없다."
        elif archetype == "contradiction":
            notes = [
                f"보호자는 이 사람에게 '{claim['behavior']}'는 행동이 나타난 적 없다고 명시했다.",
                "비슷해 보이는 집단 설명을 개인 사실로 바꾸지 말라고 정정했다.",
                f"{target}, {distractor} 두 후보 모두 언급만 됐고 이동 이력은 없다.",
            ]
            rationale = "집단 행동 진술보다 이 사람에게는 해당 행동이 없었다는 명시적 개인 사실이 우선한다."
        elif archetype == "unlisted_intent":
            notes = [
                "집이나 보호자를 찾아야 한다는 의도는 표현하지만 구체 위치는 후보에 없다.",
                f"동시에 '{claim['behavior']}'는 행동이 관찰됐으나 일관된 장소는 없었다.",
                f"{target}, {distractor} 두 후보를 향한 이력은 없다.",
            ]
            rationale = "행동과 의도는 있어도 목적지가 후보에 없으므로 goal_label은 null이어야 한다."
        elif archetype == "balanced":
            notes = [
                f"'{claim['behavior']}'는 행동이 여러 장소에서 같은 정도로 관찰됐다.",
                "그 행동이 특정 목적지를 뜻하지는 않는다고 보호자가 설명했다.",
                f"{target}, {alt} 두 후보 모두 이름만 언급됐고 우열 근거가 없다.",
            ]
            rationale = "행동 진술이 두 후보 중 하나를 선택할 근거를 제공하지 않으며 두 장소의 개인 근거도 같다."
        evidence = {
            target: "mention_only",
            (alt if archetype == "balanced" else distractor): "mention_only",
        }
        goal = None

    labels = list(evidence)
    rng.shuffle(labels)
    conf = confusion_for(claim, archetype, rng, gauge_lv["혼란도"])
    positive_behavior = archetype in {"confirmed_history", "caregiver_observed", "balanced"}
    null_voice = NULL_VOICES[rng.randrange(len(NULL_VOICES))]
    if goal is None:
        if not targetable and positive_behavior and claim["behavior_class"] in NON_TARGET_STATUS:
            status = NON_TARGET_STATUS[claim["behavior_class"]]
            inner = null_voice[1]
        elif claim["behavior_class"] in {"aimless_movement", "continued_movement", "variable_route"}:
            status = null_voice[0] + " 이동은 계속한다."
            inner = null_voice[1] + " 그래도 계속 움직이고 싶다."
        elif claim["behavior_class"] in {"hiding_or_staying", "hazard_avoidance"}:
            status = null_voice[0] + " 이동을 줄이고 머무르려 한다."
            inner = null_voice[1] + " 더 가기보다 잠시 있고 싶다."
        else:
            status, inner = null_voice
    else:
        status_t, inner_t = GOAL_VOICES[rng.randrange(len(GOAL_VOICES))]
        status, inner = status_t.format(goal=goal), inner_t.format(goal=goal)
    # 계약 v2 행동 의도 — goal 이 있으면 끌림점 접근, null 이면 시나리오 의미로 결정.
    # unlisted_intent 는 "집·보호자를 찾는 의도 + 후보 없음" = 귀소 시도의 정의 그대로.
    # 귀소 트리거에서는 강근거가 있어도 일부는 귀소 시도가 자연 — 골드셋 라벨도
    # A_귀소에서 둘 다 허용한다. 전부 끌림으로 가르치면 "게이지 무시" 편향 재생산.
    if goal is not None and trigger_name == "귀소" and rng.random() < 0.3:
        goal = None
        hv = HOME_VOICES[rng.randrange(len(HOME_VOICES))]
        status, inner = hv
        rationale = "귀소 충동이 임계를 넘어 익숙한 장소보다 집으로 향하려 한다. " + rationale
        behavior = "귀소 시도"
    elif goal is not None:
        behavior = "끌림점 접근"
    elif archetype == "unlisted_intent":
        behavior = "귀소 시도"
    elif claim["behavior_class"] in {"hiding_or_staying", "hazard_avoidance", "escape_behavior"}:
        behavior = "은신·멈춤"
    elif gauge_lv["피로도"] == "높음" and rng.random() < 0.5:
        behavior = "은신·멈춤"          # 탈진 정지 — 일부만 (전부 멈추면 과대)
    else:
        behavior = "계속 배회"

    if archetype in {"population_only", "contradiction", "unlisted_intent"}:
        rationale += f" '{claim['behavior']}'라는 집단 수준 가능성은 개인 근거 없이 목표로 바꾸지 않는다."
    else:
        rationale += f" 개인 관찰은 '{claim['behavior']}'라는 행동 진술과 일치한다."

    return {
        "name": name, "age": age, "population": population,
        "notes": notes, "labels": labels, "evidence": evidence,
        "report": report, "trigger": trigger_name,
        "scene": scene,
        "goal": goal, "behavior": behavior, "confusion": conf,
        "status": status, "inner": inner,
        "rationale": rationale, "target": target, "archetype": archetype,
    }


def analyst_user(s: dict) -> str:
    ptype = "치매 노인" if s["population"] == "dementia" else "발달장애인"
    lines = [
        "[실종자]",
        f"- 이름: {s['name']}, 유형: {ptype}, 나이: {s['age']}세",
        "- 평소 행동 사실:",
        *[f"  - {note}" for note in s["notes"]],
        f"[현재 상태] {s['report']}",
        f"[주변 장면] {s['scene']}",
        "[끌림점 후보]",
        *[f"  - {label} ({s['evidence'][label]})" for label in s["labels"]],
        "[질문] 이 사람은 지금 어떤 마음 상태이고, 어디로 향하려 하는가?",
    ]
    return "\n".join(lines)


def first_person_user(s: dict) -> str:
    # "가만히 있기 어렵다"는 은신·멈춤을 밀어내는 유도 문구로 실측됨(PR #99) — 사실만 전달.
    feel = {
        "귀소": "갑자기 집에 가야겠다는 생각이 강하게 밀려온다.",
        "불안": "갑자기 불안이 확 밀려온다.",
        "혼란": "갑자기 여기가 어디인지 알 수 없어진다.",
        "피로": "갑자기 다리에 힘이 빠지고 너무 지친다.",
    }[s["trigger"]]
    ev = {
        "previous_missing_found": "전에도 발길이 향했던 곳",
        "caregiver_report": "자주 가는 익숙한 곳",
        "mention_only": "이야기만 나온 곳",
    }
    lines = [
        f"[너는 이런 사람이다] 이름 {s['name']}, 나이 {s['age']}세",
        *[f"- {note}" for note in s["notes"]],
        f"[지금 상황] {s['report']} {feel}",
        f"[지금 눈앞에 보이는 것] {s['scene']}",
        "[네가 아는 장소들] (나열 순서에 의미 없음)",
        *[f"  - {label} — {ev[s['evidence'][label]]}" for label in s["labels"]],
        "[질문] 지금 너는 어떤 마음이고, 몸은 어떻게 움직이는가? JSON으로만 답하라.",
    ]
    return "\n".join(lines)


def row_for(claim: dict, s: dict, perspective: str, variant: int) -> dict:
    if perspective == "analyst":
        system = ANALYST_SYSTEM
        user = analyst_user(s)
        answer = {
            "status": s["status"],
            "confusion_level": s["confusion"],
            "goal_label": s["goal"],
            "reasoning": s["rationale"],
        }
    else:
        identity = "치매가 있는 노인" if s["population"] == "dementia" else "발달장애가 있는 사람"
        system = FIRST_PERSON_SYSTEM.format(identity=identity)
        user = first_person_user(s)
        answer = {
            "inner": f"{s['inner']} {s['scene']}이 보인다.",
            "status": s["status"],
            "confusion_level": s["confusion"],
            "behavior": s["behavior"],
            "goal_label": s["goal"],
        }
    sid = f"SFT-{claim['claim_id'][4:]}-{s['archetype'].upper()}-{variant:02d}-{perspective[:2].upper()}"
    assert not (set(s["labels"]) & GOLD_LABELS)
    return {
        "id": sid,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)},
        ],
        "metadata": {
            "split": "train",
            "perspective": perspective,
            "population": claim["population"],
            "behavior_class": claim["behavior_class"],
            "scenario_archetype": s["archetype"],
            "claim_ids": [claim["claim_id"]],
            "source_pages": [{
                "paper_id": claim["source"]["paper_id"],
                "pdf_page": claim["source"]["pdf_page"],
            }],
            "evidence_policy": "individual_over_group",
            "gold_overlap": False,
            "generator_version": "v1",
        },
    }


def main(variants: int = 6, goal_variants: int = 10) -> None:
    # 8/22 → 6/10 축소: 최빈 동일 inner 가 220회에 달하는 템플릿 반복(모드 붕괴 위험)을
    # 줄인다 — 규모보다 표면형 다양성이 SFT 품질을 좌우한다.
    archetypes = [
        "confirmed_history", "caregiver_observed", "population_only",
        "contradiction", "unlisted_intent", "balanced",
    ]
    claims = [
        claim for claim in load_claims()
        if claim["behavior_class"] not in SKIP_TUNING_CLASSES
        and claim["claim_id"] not in SKIP_TUNING_CLAIMS
    ]
    outputs = {"analyst": [], "first_person": []}
    for claim in claims:
        for archetype in archetypes:
            n_variants = (
                goal_variants
                if claim["behavior_class"] in TARGETABLE
                and archetype in {"confirmed_history", "caregiver_observed", "contradiction", "balanced"}
                else variants
            )
            for variant in range(n_variants):
                s = scenario(claim, archetype, variant)
                for perspective in outputs:
                    outputs[perspective].append(row_for(claim, s, perspective, variant))

    dataset_dir = HERE / "dataset"
    dataset_dir.mkdir(exist_ok=True)
    for perspective, rows in outputs.items():
        path = dataset_dir / f"train_{perspective}.jsonl"
        path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )
        print(f"{path.name}: {len(rows)}")
    mixed = [row for pair in zip(outputs["analyst"], outputs["first_person"]) for row in pair]
    (dataset_dir / "train_mixed.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in mixed) + "\n",
        encoding="utf-8",
    )
    print(f"train_mixed.jsonl: {len(mixed)}")


if __name__ == "__main__":
    main()
