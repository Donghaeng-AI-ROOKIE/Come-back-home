"""마음 검증용 대화 세트 — 실 Phase 0 추출을 거쳐 페르소나 뱅크를 만드는 대본.

axis_goldset(1문1축, 무균실)과 달리 실사용 분포를 겨냥한다:
  - 공간앵커 문답 포함 (옛집·단골·과거 발견 위치 — 근거 강/약 섞음)
  - 노이즈 포함 (정정 발화, 유사 중복 답, "잘 모르겠어요" 다수)
  - 빈약(콜드스타트급) 케이스 포함

5명 = 치매 편중/균형/빈약 + 치매 대조쌍(자전 강/약).
(발달 고착/회피 2명은 2026-08-03 치매 단독 스코프 전환으로 삭제.)
대조쌍은 autobiographical 답만 다르고 나머지 동일 — 근거 감도(B3) 검정용.

형식·소비자: experiments/chatbot_eval 의 Scenario/responder/runner 를 그대로 쓴다.
Expected 는 뱅크 생성 새너티 체크용 최소치만 채운다(채점이 목적이 아님).
"""
from __future__ import annotations

from experiments.chatbot_eval.scenarios import Expected, Scenario

_FB = "글쎄요, 잘 모르겠어요."


def _dem_common(**over: str) -> dict[str, str]:
    """치매 공통 베이스 — 마음 검증에 필요한 최소 축 + 공간앵커."""
    base = {
        "mobility_transport_capacity": "동네 안에서는 혼자 한 시간 정도 걸으세요. 버스는 이제 혼자 못 타세요.",
        "hazard_awareness_vulnerability": "신호는 지키시는데 복잡한 길에서는 옆에서 봐드려야 해요.",
        "communication_approach_vulnerability": "성함은 말씀하시는데 집 주소는 헷갈려 하세요.",
        "medication": "치매약 아침저녁으로 드세요.",
        "wayfinding_error_recovery_deficit": "익숙한 데서도 가끔 방향을 헷갈리시는데 한참 걸으시다 보면 못 돌아오세요.",
        "lost_behavior": "길을 잃으면 가만히 계시질 않고 계속 걸으세요.",
        "distress_induced_movement_reactivity": "불안하시면 안절부절 못하시고 문 쪽으로 가세요.",
    }
    base.update(over)
    return base


# ── 1. 치매 편중 — 옛집 강근거(과거 발견+습관) vs 시장 언급만. 유사 중복 노이즈 ──
MB_DEM_BIASED = Scenario(
    id="MB_dem_biased", title="뱅크 · 치매 편중(옛집 강근거) + 중복 노이즈",
    guardian_name="이보호", persona_type="dementia",
    answers=_dem_common(
        identity="어머니 박정순, 79세세요. 치매 진단 4년째예요.",
        home="성북구 정릉동 살아요. 정릉초등학교 근처요.",
        routine_destinations="가끔 시장 얘기를 하시긴 해요. 아, 그리고 아까 말한 것처럼 시장은 지나가듯 들르는 정도예요.",
        autobiographical_destination_pull="예전에 미아리에서 30년 사셨거든요. 해질녘만 되면 그 옛집에 가야 한다고 나서세요. 거의 매일요.",
        dementia_wandering_pattern="작년 가을에 실종되셨을 때 미아리 옛집 골목에서 찾았어요. 거기서 문을 두드리고 계셨대요.",
    ),
    area_answers={"옛집": "미아리요. 성북구 미아리고개 쪽이요.", "미아리": "성북구요.",
                  "시장": "정릉시장이요."},
    expected=Expected(name="박정순", age=79, attraction_labels=["옛집", "미아리"],
                      evidence={"미아리": "previous_missing_found"}),
)

# ── 2. 치매 균형 — 두 장소 비슷 빈도, 편향 없음 (B1 순서편향 검정 핵심) ──
MB_DEM_BAL = Scenario(
    id="MB_dem_bal", title="뱅크 · 치매 균형(복지관=경로당, 편향 없음)",
    guardian_name="최보호", persona_type="dementia",
    answers=_dem_common(
        identity="아버지 최영수, 75세입니다. 작년에 치매 진단받으셨어요.",
        home="성북구 정릉동이에요.",
        routine_destinations="복지관하고 경로당을 반반씩 가세요. 딱히 더 좋아하는 데는 없고 그날그날 달라요.",
        autobiographical_destination_pull="옛날 얘기는 가끔 하시는데 거길 찾아가려고 하신 적은 없어요.",
        dementia_wandering_pattern="실종되신 적은 아직 없어요.",
    ),
    area_answers={"복지관": "정릉동 주민센터 옆이요.", "경로당": "정릉3동이요."},
    expected=Expected(name="최영수", age=75, attraction_labels=["복지관", "경로당"]),
)

# ── 3. 치매 빈약 — 보호자가 잘 모름 + 나이 정정 노이즈 (절제 검정) ──
MB_DEM_POOR = Scenario(
    id="MB_dem_poor", title="뱅크 · 치매 빈약(원거리 보호자·정정 노이즈)",
    guardian_name="김며느리", persona_type="dementia",
    answers={
        # 유형 단어("치매") 필수 — 없으면 유형 판별 게이트가 같은 질문을 무한 반복
        # (실측 40턴, 재시도 상한 없음 — 제품 관찰로 기록).
        "identity": "시어머니세요. 치매가 있으세요. 성함은 오말순이시고 여든하나… 아니다, 지금 여든둘이세요.",
        "home": "성북구 정릉동에 혼자 사세요.",
        "routine_destinations": _FB,
        "autobiographical_destination_pull": "저희가 멀리 살아서 자세히는 몰라요. 죄송해요.",
        "dementia_wandering_pattern": _FB,
        "mobility_transport_capacity": "걷는 건 정정하신 걸로 알아요.",
        "medication": "약은 드시는데 무슨 약인지는 잘 몰라요.",
    },
    corrections=["아, 나이를 제가 잘못 말했네요. 여든둘이 맞아요. 82세요."],
    expected=Expected(name="오말순", age=82),
)

# ── 4·5. 치매 대조쌍 — autobiographical 강/약만 다름 (B3 근거 감도 검정) ──
_PAIR_BASE = dict(
    identity="아버지 정재호, 76세예요. 치매 중기세요.",
    home="성북구 정릉동입니다.",
    routine_destinations="경로당에 자주 가세요. 일주일에 서너 번요.",
    dementia_wandering_pattern="실종까지 가신 적은 없는데 늦게 들어오신 적은 몇 번 있어요.",
)

MB_DEM_PAIR_HI = Scenario(
    id="MB_dem_pair_hi", title="뱅크 · 대조쌍A 자전 강(고향 반복 시도)",
    guardian_name="정보호", persona_type="dementia",
    answers=_dem_common(**_PAIR_BASE,
        autobiographical_destination_pull="고향 방앗간 터에 가야 한다고 몇 번이나 나서셨어요. 지난달에도 버스 정류장까지 가신 걸 모시고 왔어요.",
    ),
    area_answers={"방앗간": "경기도 파주요.", "고향": "파주요.", "경로당": "정릉동이요."},
    expected=Expected(name="정재호", age=76, attraction_labels=["방앗간", "경로당"]),
)

MB_DEM_PAIR_LO = Scenario(
    id="MB_dem_pair_lo", title="뱅크 · 대조쌍B 자전 약(지나가듯 한 번)",
    guardian_name="정보호", persona_type="dementia",
    answers=_dem_common(**_PAIR_BASE,
        autobiographical_destination_pull="고향 방앗간 얘기를 지나가듯 한 번 하신 적은 있어요. 가려고 하신 적은 없고요.",
    ),
    area_answers={"방앗간": "경기도 파주요.", "고향": "파주요.", "경로당": "정릉동이요."},
    expected=Expected(name="정재호", age=76, attraction_labels=["경로당"]),
)

BANK_SCENARIOS = [MB_DEM_BIASED, MB_DEM_BAL, MB_DEM_POOR,
                  MB_DEM_PAIR_HI, MB_DEM_PAIR_LO]
