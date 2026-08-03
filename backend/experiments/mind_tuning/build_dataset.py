"""검증된 문헌 claim에서 상황→행동 SFT 데이터를 대량 생성한다.

동일 claim을 단순 복제하지 않고, 개인 근거가 있는 양성 사례와 일반론을 억제해야
하는 음성·충돌·정보부족 사례를 함께 만든다. 분석가/1인칭 프롬프트를 별도 파일로
출력해 LoRA A/B가 가능하도록 한다.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))            # backend
sys.path.insert(0, str(HERE.parent / "mind_goldset"))

import first_person as fp_mod  # noqa: E402 — 1인칭 v2 실빌더 (실험 모듈 재사용)

from app.schemas.common import GeoPoint  # noqa: E402
from app.schemas.persona import AttractionPoint, Persona, PersonaType  # noqa: E402
from app.schemas.prediction import LognormalParams, PriorParams  # noqa: E402

# 학습 입력을 자체 템플릿이 아니라 **운영·실험의 실제 빌더**로 생성한다
# (외부 리뷰 지적 4 — 학습 형식=서빙 형식 원칙 위반 교정).
_ex = importlib.import_module("app.llm.exaone")
fp_mod._CONTRACT = "v2"        # 1인칭 질문 문구를 v2(몸은 어떻게 움직이는가)로
_EV_W = {"previous_missing_found": 0.9, "caregiver_report": 0.5, "mention_only": 0.3}
_GEO = {"lat": 37.55, "lng": 127.0}
_STRATEGY = {"route_following": 0.3, "direction_keeping": 0.15, "random_walk": 0.15,
             "backtracking": 0.1, "staying_put": 0.1, "landmark_seeking": 0.2}


def persona_prior(s: dict) -> tuple[Persona, PriorParams]:
    ptype = PersonaType.dementia
    aps = [AttractionPoint(label=lb, location=GeoPoint(**_GEO),
                           weight=_EV_W[s["evidence"][lb]], evidence=s["evidence"][lb])
           for lb in s["labels"]]
    p = Persona(id="sft", name="(합성)", age=s["age"], type=ptype,
                home=GeoPoint(**_GEO), attraction_points=aps, behavior_notes=s["notes"])
    total = sum(a.weight for a in aps) or 1.0
    prior = PriorParams(strategy_probs=dict(_STRATEGY),
                        attraction_weights={a.label: a.weight / total for a in aps},
                        radius_lognormal=LognormalParams(mu=0.095, sigma=1.48),
                        reasoning="(합성 데이터 고정)")
    return p, prior


def scene_sentence(scene: str) -> str:
    """장면 문장 — 받침에 맞는 조사, 청각 장면은 들린다 (외부 리뷰 지적 2)."""
    last = scene[-1]
    jong = ("가" <= last <= "힣") and (ord(last) - 0xAC00) % 28 != 0
    verb = "들린다" if "소리" in scene else "보인다"
    return f"{scene}{'이' if jong else '가'} {verb}."

# 시스템 프롬프트는 상수로 두지 않는다 — row_for 가 운영(_mind_system_for)·실험
# (fp_mod._fp_system_v2_for)의 실제 함수를 호출한다 (학습 형식=서빙 형식).

NAMES = {
    "dementia": [
        ("김정희", 78), ("박영수", 82), ("이명자", 75), ("최도식", 80),
        ("윤옥분", 84), ("한재호", 72), ("오순덕", 86), ("장태식", 77),
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

# 기능 수준(중증도) 축 — v3 어댑터 confusion 미스 12건 중 11건의 원인이
# 이 축의 부재였다 (dev G03·G07: 경증 신호가 입력에 가득한데 학습 데이터에는
# 경증/중증 어휘가 0회 → 모델이 조건화할 수 없음). 문장은 조각 조합으로 생성해
# 템플릿 암기를 막는다. unspecified 는 문장을 넣지 않는다 — 신호 부재도 학습 대상.
SEVERITY_FRAGMENTS = {
    "dementia": {
        "mild": {
            "진단": ["작년에 진단을 받았다", "진단받은 지 얼마 안 됐다", "초기 처방 단계다"],
            "소통": ["대화는 아직 원활하다.", "말씀은 또렷하게 하신다.", "의사소통에 어려움이 없다."],
            "이동": ["혼자 마을버스도 탄다.", "동네 길은 정정하게 혼자 다닌다.", "가까운 곳은 혼자 다녀오신다."],
        },
        "severe": {
            "진단": ["진단받은 지 여러 해 됐다", "증상이 많이 진행됐다", "최근 부쩍 나빠지셨다"],
            "소통": ["요즘은 대화가 잘 안 된다.", "가족도 잘 못 알아보실 때가 있다.", "말씀이 자주 끊기고 뒤섞인다."],
            "이동": ["외출은 늘 동행이 필요했다.", "혼자 나가신 적이 거의 없다.", "집 앞도 혼자는 못 다니신다."],
        },
    },
}


def severity_sentence(population: str, severity: str, rng: random.Random) -> str | None:
    if severity == "unspecified":
        return None
    frag = SEVERITY_FRAGMENTS[population][severity]
    return (f"{frag['진단'][rng.randrange(len(frag['진단']))]}. "
            f"{frag['소통'][rng.randrange(len(frag['소통']))]} "
            f"{frag['이동'][rng.randrange(len(frag['이동']))]}")


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

# 행동별 문장 풀 — 계속 배회 풀에는 멈춤·은신 어휘를, 은신·멈춤 풀에는 이동 지속
# 어휘를 넣지 않는다 (validate 가 모순 검사로 강제).
WANDER_VOICES = [
    ("갈 곳을 정하지 못한 채 발걸음을 잇는다.", "어디로 가야 할지 떠오르지 않는다."),
    ("정한 곳 없이 계속 걷는다.", "그냥 발이 가는 대로 걷고 있다."),
    ("방향을 정하지 못한 채 이동을 계속한다.", "이 길이 맞는지 도무지 모르겠다."),
    ("뚜렷한 목적지 없이 걸음을 이어간다.", "정해진 곳 없이 움직이고 있다."),
    ("어느 쪽인지 확신하지 못한 채 계속 걷는다.", "아까 온 길이 어느 쪽이었더라."),
    ("길이 낯설어진 채로 발걸음을 옮긴다.", "여기가 어딘지 낯설게 느껴진다."),
    ("주위를 두리번거리며 계속 이동한다.", "길이 다 비슷비슷해 보인다."),
    ("목적지를 정하지 못한 채 눈에 띄는 쪽으로 걷는다.", "저쪽이 조금 익숙한 것 같기도 하다."),
    ("어디로 가는지 설명하지 못한 채 이동한다.", "왜 여기까지 왔는지 모르겠다."),
    ("갈피를 잡지 못하면서도 걸음은 이어진다.", "머릿속이 하얘졌는데 발은 계속 움직인다."),
    ("이리저리 방향을 바꾸며 계속 움직인다.", "이쪽인가 싶다가도 자꾸 헷갈린다."),
    ("정처 없이 골목을 따라 걷는다.", "걷다 보면 아는 데가 나올 것 같다."),
]

STAY_VOICES = [
    ("그 자리에 멈춰 움직이지 못한다.", "어떻게 해야 할지 몰라 그냥 서 있고 싶다."),
    ("더 가지 못하고 구석진 곳을 찾는다.", "조용한 데로 가서 좀 숨고 싶다."),
    ("이동을 멈추고 몸을 웅크린다.", "여기 잠깐 있으면 괜찮아질 것 같다."),
    ("걸음을 멈추고 앉을 곳을 찾는다.", "다리에 힘이 없어 잠시 앉고 싶다."),
    ("소란을 피해 눈에 띄지 않는 곳에 머문다.", "시끄러워서 아무도 없는 데로 가고 싶다."),
    ("한자리에 멈춰 주변만 살핀다.", "잘못 가면 더 헤맬 것 같아 그대로 있고 싶다."),
    ("구석으로 물러나 몸을 숨긴다.", "사람들 눈에 안 띄는 데가 편하다."),
    ("멈춰 선 채 어찌할 바를 모른다.", "그냥 여기 가만히 있고 싶다."),
    ("이동을 줄이고 가려진 자리를 찾는다.", "잠깐 숨을 데가 있으면 좋겠다."),
    ("발걸음을 멈추고 벽 쪽에 붙어 선다.", "여기서 조금만 쉬고 싶다."),
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
    out = []
    for line in (HERE / "claims" / "claims.jsonl").read_text(encoding="utf-8").splitlines():
        c = json.loads(line)
        # 노트에 삽입될 때 "'계속 걷는다.'라는 행동" 식으로 어색해지는 끝 마침표 정리
        c["behavior"] = c["behavior"].rstrip(". ")
        c["condition"] = c["condition"].rstrip(". ")
        out.append(c)
    return out


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
                  gauge_confusion: str, severity: str = "unspecified") -> str:
    """정답 혼란도 = 행동류·근거 상황(주) + 기능 수준(주) + 게이지(보조).

    v4(게이지 반향)의 실패 실측(exaone-mind 1차 게이트): 게이지 혼란을 그대로
    되돌리도록 학습돼 dev(게이지 항상 '중간')에서 중 63/64 붕괴 — 게이트 미달.
    게이지 값을 반향하는 LLM 은 정보를 추가하지 않는다. 골드셋 판정자들의 기대
    (인지 손상 심하거나 근거 빈약할수록 혼란↑, 강근거 익숙 행동은 명료)를 주축으로
    바꾸고, 게이지는 한 단계 보정으로 강등한다. 모순 차단은 유지 — 게이지 '높음'
    에서 하 금지, '낮음'에서 상 금지.

    기능 수준(v3 어댑터 실측 보강): 경증(대화 원활·단독 이동)은 한 단계 명료 쪽,
    중증은 한 단계 혼란 쪽. 단 정보 빈약(population_only)에서는 경증 하향을 막는다
    — 판단 근거 자체가 부족하면 명료 단정도 못 한다(dev G08 기대와 일치).
    빈약→상 비율도 40%→25%로 완화(G08 상 과잉 실측).
    """
    order = ["하", "중", "상"]
    if claim["behavior_class"] in HIGH_CONFUSION:
        idx = 2 if rng.random() < 0.6 else 1       # 길잃음·무목적 계열 = 혼란 우세
    elif archetype in {"confirmed_history", "caregiver_observed"} \
            and claim["behavior_class"] in {"familiar_route", "goal_seeking", "repetitive_route"}:
        idx = 0 if rng.random() < 0.6 else 1       # 강근거 익숙 행동 = 명료 우세
    elif archetype in {"population_only", "contradiction", "unlisted_intent"}:
        idx = 1 if rng.random() < 0.75 else 2      # 근거 빈약·상충 = 중 우세
    else:
        idx = rng.choice([0, 1, 2])                # 그 외 = 전 구간 표집
    if severity == "mild" and archetype != "population_only":
        idx = max(idx - 1, 0)
    elif severity == "severe":
        idx = min(idx + 1, 2)
    g = {"낮음": 0, "중간": 1, "높음": 2}[gauge_confusion]
    if g == 2:
        idx = max(idx, 1)                          # 게이지 높음이면 최소 중
    elif g == 0:
        idx = min(idx, 1)                          # 게이지 낮음이면 최대 중
    return order[idx]


def confusion_teacher(severity: str, archetype: str, trigger: str,
                      gauge_confusion: str) -> str:
    """정답 혼란도 = 검증된 규칙의 증류 (생성기 v6 — 결정론 교사).

    v1~v4 라벨은 rng 60/40 표집이라 같은 조건에 다른 정답이 붙었다 — 라벨
    노이즈가 '중 고착'(가장 안전한 답으로 도피)의 구조적 원인. dev 16/16 을
    실측한 rule_confusion.py 의 판정 구조를 3단 계약으로 증류해 라벨을 입력
    가시 신호(기능수준 문장·정보빈약 노트·트리거)의 순수 함수로 만든다:
      경증(비빈약) × 귀소 → 하 / 중증 × 불안 → 상 / 그 외 → 중.
    게이지 극단값과의 모순 차단만 유지(하한·상한 클램프 — 역시 결정론).
    """
    poor = archetype == "population_only"
    if severity == "mild" and not poor and trigger == "귀소":
        idx = 0
    elif severity == "severe" and trigger == "불안":
        idx = 2
    else:
        idx = 1
    g = {"낮음": 0, "중간": 1, "높음": 2}[gauge_confusion]
    if g == 2:
        idx = max(idx, 1)
    elif g == 0:
        idx = min(idx, 1)
    return ["하", "중", "상"][idx]


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
    severity = rng.choices(["mild", "unspecified", "severe"], weights=[3, 4, 3])[0]

    targetable = claim["behavior_class"] in TARGETABLE
    notes: list[str]
    evidence: dict[str, str]
    goal: str | None
    rationale: str
    sample_target = target if targetable else None

    if archetype == "confirmed_history":
        notes = [
            f"과거 두 차례 없어졌을 때 모두 {target}에서 발견됐다.",
            f"보호자는 특정 상황에서 '{claim['behavior']}'라는 행동을 반복해서 관찰했다.",
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
            f"특히 '{claim['behavior']}'라는 행동도 이 사람에게 나타난 적이 없다고 했다.",
            "지금 어디를 향하는지는 알 수 없다고 했다.",
        ]
        evidence = {target: "mention_only", distractor: "mention_only"}
        goal = None
        rationale = "집단 경향만으로 개인의 구체 목적지를 단정할 수 없다."
    elif archetype == "contradiction":
        notes = [
            f"{distractor} 이야기를 한 적은 있지만 가려고 한 적은 없다고 보호자가 명시했다.",
            f"{routine}은 매주 같은 시간에 다니는 유일하게 확인된 일상 장소다.",
            f"보호자는 '{claim['behavior']}'라는 일반적 설명을 이 사람에게 그대로 적용하지 말라고 했다.",
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
            f"두 장소 모두에서 '{claim['behavior']}'라는 행동이 같은 정도로 관찰됐다.",
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
                f"과거 실종 때 '{claim['behavior']}'라는 행동이 확인됐지만 장소는 매번 달랐다.",
                "보호자는 일관된 목적지나 선호 장소가 없었다고 했다.",
                f"{target}, {distractor} 두 곳은 이름만 언급됐을 뿐 이동 근거가 없다.",
            ]
            rationale = "과거 행동 이력은 강하지만 특정 장소와 연결된 이력은 아니므로 목적지를 만들 수 없다."
        elif archetype == "caregiver_observed":
            notes = [
                f"보호자는 '{claim['condition']}'에 '{claim['behavior']}'라는 모습을 반복 관찰했다.",
                "행동이 나타난 장소는 매번 달라 일관된 목적지가 없었다.",
                f"{target}, {distractor} 두 후보를 향한 개인 이력은 없다.",
            ]
            rationale = "행동은 개인에게 확인됐지만 구체 목적지는 확인되지 않았다."
        elif archetype == "population_only":
            notes = [
                "보호자는 과거 실종이나 반복 지향 장소를 확인하지 못했다.",
                f"'{claim['behavior']}'라는 행동도 이 사람에게 나타난 적이 없다고 했다.",
                f"{target}, {distractor} 두 후보와 관련된 개인 행동은 관찰되지 않았다.",
            ]
            rationale = "집단 경향과 후보 이름만으로 개인의 행동이나 목적지를 단정할 수 없다."
        elif archetype == "contradiction":
            notes = [
                f"보호자는 이 사람에게 '{claim['behavior']}'라는 행동이 나타난 적 없다고 명시했다.",
                "비슷해 보이는 집단 설명을 개인 사실로 바꾸지 말라고 정정했다.",
                f"{target}, {distractor} 두 후보 모두 언급만 됐고 이동 이력은 없다.",
            ]
            rationale = "집단 행동 진술보다 이 사람에게는 해당 행동이 없었다는 명시적 개인 사실이 우선한다."
        elif archetype == "unlisted_intent":
            notes = [
                "집이나 보호자를 찾아야 한다는 의도는 표현하지만 구체 위치는 후보에 없다.",
                f"동시에 '{claim['behavior']}'라는 행동이 관찰됐으나 일관된 장소는 없었다.",
                f"{target}, {distractor} 두 후보를 향한 이력은 없다.",
            ]
            rationale = "행동과 의도는 있어도 목적지가 후보에 없으므로 goal_label은 null이어야 한다."
        elif archetype == "balanced":
            notes = [
                f"'{claim['behavior']}'라는 행동이 여러 장소에서 같은 정도로 관찰됐다.",
                "그 행동이 특정 목적지를 뜻하지는 않는다고 보호자가 설명했다.",
                f"{target}, {alt} 두 후보 모두 이름만 언급됐고 우열 근거가 없다.",
            ]
            rationale = "행동 진술이 두 후보 중 하나를 선택할 근거를 제공하지 않으며 두 장소의 개인 근거도 같다."
        evidence = {
            target: "mention_only",
            (alt if archetype == "balanced" else distractor): "mention_only",
        }
        goal = None

    sev_sentence = severity_sentence(population, severity, rng)
    if sev_sentence:
        notes.insert(0, sev_sentence)

    labels = list(evidence)
    rng.shuffle(labels)
    conf = confusion_teacher(severity, archetype, trigger_name, gauge_lv["혼란도"])
    positive_behavior = archetype in {"confirmed_history", "caregiver_observed", "balanced"}

    # ── 1) 행동을 먼저 확정한다 — v3 정답 내부충돌(행동↔문장 모순 397건)의 원인이
    #       "문장 먼저, 행동 나중" 순서였다 (외부 리뷰 지적 1).
    if goal is not None and trigger_name == "귀소" and rng.random() < 0.3:
        # 귀소 트리거에서는 강근거가 있어도 일부는 귀소 시도가 자연 — 골드셋도 둘 다 허용.
        goal = None
        behavior = "귀소 시도"
        rationale = "귀소 충동이 임계를 넘어 익숙한 장소보다 집으로 향하려 한다. " + rationale
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

    # ── 2) 문장은 행동에서 유도한다 (행동별 풀 — 모순이 구조적으로 불가능) ──
    if behavior == "끌림점 접근":
        status_t, inner_t = GOAL_VOICES[rng.randrange(len(GOAL_VOICES))]
        status, inner = status_t.format(goal=goal), inner_t.format(goal=goal)
    elif behavior == "귀소 시도":
        status, inner = HOME_VOICES[rng.randrange(len(HOME_VOICES))]
    elif behavior == "은신·멈춤":
        status, inner = STAY_VOICES[rng.randrange(len(STAY_VOICES))]
        if positive_behavior and claim["behavior_class"] in ("hiding_or_staying", "hazard_avoidance"):
            status = NON_TARGET_STATUS[claim["behavior_class"]]
    else:  # 계속 배회
        status, inner = WANDER_VOICES[rng.randrange(len(WANDER_VOICES))]
        if positive_behavior and claim["behavior_class"] in NON_TARGET_STATUS \
                and claim["behavior_class"] not in ("hiding_or_staying", "hazard_avoidance"):
            status = NON_TARGET_STATUS[claim["behavior_class"]]

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
        "status": status, "inner": inner, "severity": severity,
        "rationale": rationale, "target": target, "archetype": archetype,
    }


def row_for(claim: dict, s: dict, perspective: str, variant: int) -> dict:
    p, prior = persona_prior(s)
    in_rng = stable_rng(claim["claim_id"], s["archetype"], variant, perspective, "input")
    if perspective == "analyst":
        # 운영 v1 경로의 실제 시스템·입력 빌더 그대로 (RAG 블록은 별도 턴이라 미포함)
        system = _ex._mind_system_for(p.type)
        user = _ex._build_mind_input(p, s["report"], s["labels"], prior, s["scene"], in_rng)
        answer = {
            "status": s["status"],
            "confusion_level": s["confusion"],
            "goal_label": s["goal"],
            "reasoning": s["rationale"],
        }
    else:
        # 1인칭 v2 실빌더 (mind_goldset/first_person.py — PR #99 실증 구성 그대로)
        system = fp_mod._fp_system_v2_for(p.type)
        user = fp_mod.build_fp_mind_input(p, s["report"], s["labels"], prior, s["scene"], in_rng)
        answer = {
            "inner": f"{s['inner']} {scene_sentence(s['scene'])}",
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
            "severity": s["severity"],
            "evidence_policy": "individual_over_group",
            "gold_overlap": False,
            "generator_version": "v7",
        },
    }


def main(variants: int = 5, goal_variants: int = 16) -> None:
    """v4: goal 16/null 5 로 재균형(v3 null 69% — 과수동 학습 위험, 리뷰 지적 6),
    논문(paper_id) 단위 train/validation 분리(지적 5), mixed 폐기(지적 3)."""
    archetypes = [
        "confirmed_history", "caregiver_observed", "population_only",
        "contradiction", "unlisted_intent", "balanced",
    ]
    claims = [
        claim for claim in load_claims()
        if claim["behavior_class"] not in SKIP_TUNING_CLASSES
        and claim["claim_id"] not in SKIP_TUNING_CLAIMS
    ]
    # 논문 단위 분할 — 같은 claim 의 변형이 train/val 양쪽에 들어가는 누수 차단.
    #
    # 2026-08-03 치매 단독 스코프 전환으로 DEV 계열 논문·claim 이 코퍼스에서 삭제됐다.
    # 기존 val(DEM-32·DEM-33)을 그대로 두면 **val 이 감시 지표로 쓸 수 없게 된다**:
    # DEM-32 는 repetitive_route·variable_route 의 유일한 출처라 val 로 빼면 그 두
    # 클래스가 train 에 아예 없어지고, val 194행 중 104행(54%)이 "학습된 적 없는
    # 클래스"가 된다. val loss 는 과적합 감시용인데 OOD 측정이 절반을 넘으면 그
    # 역할을 못 한다(HANDOFF_학습조건.md 평가 절).
    #
    # 그래서 DEM-32 는 train 으로 되돌리고 val 은 DEM-23+DEM-33 으로 재지정한다.
    # 후보 전수 비교(2026-08-03) 결과 이 조합만 (a) val 클래스가 전부 train 에 있고
    # (b) 행동 라벨 4종을 모두 덮으며 (c) val 비율 9%(134행)로 적정하다.
    val_papers = {"DEM-23", "DEM-33"}
    print(f"validation 논문(명시 지정): {sorted(val_papers)}")

    outputs = {"analyst": [], "first_person": []}
    for claim in claims:
        split = "validation" if claim["source"]["paper_id"] in val_papers else "train"
        for archetype in archetypes:
            n_variants = (
                goal_variants
                if claim["behavior_class"] in TARGETABLE
                and archetype in {"confirmed_history", "caregiver_observed", "contradiction", "balanced"}
                else variants
            )
            for variant in range(n_variants):
                s = scenario(claim, archetype, variant)
                # v7: '하' 라벨 train 행 3배 오버샘플 — v5 실측에서 소수 클래스
                # (8%)가 '중'으로 통째 흡수(하 출력 0/64)된 것의 표준 처방.
                # val 은 증량하지 않는다(감시 지표 왜곡 방지).
                reps = 3 if (split == "train" and s["confusion"] == "하") else 1
                for perspective in outputs:
                    row = row_for(claim, s, perspective, variant)
                    row["metadata"]["split"] = split
                    outputs[perspective].append(row)
                    for k in range(1, reps):
                        dup = json.loads(json.dumps(row, ensure_ascii=False))
                        dup["id"] = f"{row['id']}-O{k}"
                        outputs[perspective].append(dup)

    dataset_dir = HERE / "dataset"
    dataset_dir.mkdir(exist_ok=True)
    for old in dataset_dir.glob("train_mixed.jsonl"):
        old.unlink()                     # 혼합셋 폐기 — 계약이 달라 학습에 부적합
    for perspective, rows in outputs.items():
        for split_name, tag in (("train", "train"), ("validation", "val")):
            part = [r for r in rows if r["metadata"]["split"] == split_name]
            path = dataset_dir / f"{tag}_{perspective}.jsonl"
            path.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in part) + "\n",
                encoding="utf-8",
            )
            print(f"{path.name}: {len(part)}")


if __name__ == "__main__":
    main()
