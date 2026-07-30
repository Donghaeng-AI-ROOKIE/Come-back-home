"""P1-5/P1-6 — 신뢰도 p 가중치(r)·감쇠계수(k) 튜닝 시나리오.

노션 설계(2026-07-30, "[서영][P1-5+P1-6] 신뢰도 p 가중치·감쇠 튜닝 — 모델 연결 반영 재설계")의
5개 유형 표를 코드로 옮긴 것. 개연성(plausibility)·위치시각특정여부(has_location_time)는
실측(지오코딩)이 아니라 검증 목적에 맞게 주입한 값이다 — P1-5 설계의 "한 변수만 열기"
원칙대로, 구체성 출처(gold/모델)만 Stage A/B 로 바꾸고 개연성은 고정한다.

text 는 4파전 tip_llm_compare/scenarios.py 의 기존 라벨링 텍스트를 재사용(t01·t02·t04·t05)
하거나 경계 케이스 검증을 위해 새로 지었다(t03 — note 참고).

expected_decision 이 있는 셋(t01·t02·t05)은 "sanity" — 채점 대상. 어느 r 에서도 결과가
안 바뀌어야 정상이고, 바뀌면 설계가 잘못됐다는 신호다.
없는 셋(t03·t04, "경계")은 r 에 따라 갈리는 지점을 보는 게 목적이라 고정 정답을 넣지
않았다 — "정답 = 팀 판단" 원칙(한계로 명시됨). run_sweep.py 는 이 둘의 r 별 판정을
그대로 표로 남기고, 최종 판단(어느 r 을 쓸지)은 그 표를 보고 팀이 내린다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.tip import TipDecision


@dataclass
class TrustScenario:
    id: str
    text: str                              # Stage B 에서 tip_llm.structure_tip() 에 태울 원문
    gold_specificity: str                  # "상"|"중"|"하" — Stage A 입력(사람 정답 주입)
    plausibility: float                    # 개연성 주입값 [0,1] — 지오코딩 대신 직접 지정
    has_location_time: bool                # 층2 자격 조건(위치·시각 특정) 주입값
    expected_decision: TipDecision | None  # sanity 셋만 값 있음, 경계 셋은 None(팀 판단)
    note: str = ""
    draft: bool = False                    # True = Claude 초안 판정(서영 검토 전), scenarios_70.py 용


SCENARIOS: list[TrustScenario] = [
    TrustScenario(
        id="t01_clear_layer2",
        text="방금 전에 OO아파트 정문 앞에서 봤어요. 남색 조끼에 회색 모자 쓰신 할머니셨는데, "
             "편의점 쪽으로 천천히 걸어가셨어요.",
        gold_specificity="상",
        plausibility=1.0,
        has_location_time=True,
        expected_decision=TipDecision.layer2,
        note="명백층2 — 상한 sanity. 어느 r 에서도 층2 유지돼야 함(4파전 s01 텍스트 재사용).",
    ),
    TrustScenario(
        id="t02_clear_discard",
        text="그냥 신고합니다.",
        gold_specificity="하",
        plausibility=0.02,
        has_location_time=False,
        expected_decision=TipDecision.discard,
        note="명백파기 — 하한 sanity. 어느 r 에서도 파기 유지돼야 함(4파전 s20 텍스트 재사용).",
    ),
    TrustScenario(
        id="t03_boundary_a",
        text="동네 정자 근처에서 아까 봤어요.",
        gold_specificity="하",
        plausibility=1.0,
        has_location_time=True,
        expected_decision=None,
        note="경계A(핵심) — 물리적으로 완전 가능(plaus=1.0)한데 서술이 부실(spec=하). "
             "r 이 커질수록(개연성 비중↑) 층1→층2 로 넘어가는 지점을 봄. "
             "gold='하' 라벨 자체가 rubric 경계(장소·시각 둘 다 언급되나 모호 — 4파전 "
             "s13/s16 과 같은 '중/하 원리상 구분불가' 지점)라 의도적으로 골랐다. "
             "고정 정답 없음 — 결과표 보고 팀이 판단.",
    ),
    TrustScenario(
        id="t04_boundary_b",
        text="10분 전쯤 지하철역 3번 출구 근처요. 빨간 패딩 입으신 남자분이 역 반대편으로 "
             "급하게 가시더라고요.",
        gold_specificity="상",
        plausibility=0.4,
        has_location_time=True,
        expected_decision=None,
        note="경계B — 서술 완벽(spec=상)한데 물리적으로 좀 멂(plaus=0.4). t03 과 반대방향 "
             "민감도(r 이 작아질수록 층2→층1). 4파전 s02 텍스트 재사용. 고정 정답 없음.",
    ),
    TrustScenario(
        id="t05_no_location_time",
        text="제가 버스 기다리고 있었는데요, 405번이 안 와서 한참을 서 있었거든요. 그러다가 "
             "3시쯤에 봤어요. 파출소 앞에서. 검은 패딩에 회색 운동화 신은 남자분이 골목 안으로 "
             "뛰어 들어가셨어요.",
        gold_specificity="상",
        plausibility=1.0,
        has_location_time=False,
        expected_decision=TipDecision.layer1,
        note="위치·시각 불특정(주입) — 서술·개연성 다 높아도 층2 자격 없어 r 무관하게 항상 "
             "층1 이어야 함(회귀 sanity). 4파전 l06 텍스트 재사용.",
    ),
]
