"""골드셋 대화 8개를 하네스 시나리오로 — `02_시나리오_대화.md`의 보호자 발화 +
`03_정답표_v0.md`의 **사람 판정 정답**(판정자 김민아, 2026-07-23, Mi:dm 출력 열람 전).

answers = 02 의 보호자 발화(입력). expected = 03 의 정답을 기계적 전사(판단 아님).
판정불가/불확실 셀은 채점에서 제외(빈값)한다 — 예: D4 이름·나이(불확실), 저신호
시나리오의 판정불가 축. 없음(확정 부재)은 과다추출 검출로 잡힌다.
"""

from __future__ import annotations

from experiments.chatbot_eval.scenarios import Expected, Scenario


# ── 치매 4 ────────────────────────────────────────────────────────────
D1 = Scenario(
    id="G_D1_kim", title="골드셋 치매 · 김순자(옛 일터 회귀)",
    guardian_name="김보호", persona_type="dementia",
    answers={
        "identity": "저희 어머니예요. 성함은 김순자, 올해 일흔여덟이시고 치매 진단받으셨어요.",
        "home": "성북구 정릉동에 저희랑 같이 살아요. 정릉초등학교 근처요.",
        "routine_destinations": "혼자 나가시면 늘 정릉시장에 가세요. 반찬거리 사러요. 가는 길은 늘 같아요.",
        "autobiographical_destination_pull":
            "예전에 면목동에서 방앗간을 오래 하셨는데, 아직도 새벽에 방앗간 문 열러 "
            "가야 한다고 자주 나가려 하세요.",
        "dementia_wandering_pattern":
            "작년에 한 번 못 돌아오신 적 있어요. 면목동 버스정류장 근처에서 발견됐고 "
            "계속 서성이고 계셨대요.",
        "mobility_transport_capacity": "쉬지 않고 30분은 걸으세요. 근데 버스나 지하철은 혼자 못 타세요.",
        "lost_behavior": "길을 잃으면 한자리에 안 계시고 계속 앞으로만 걸어가세요.",
    },
    area_answers={"방앗간": "면목동이요.", "옛집": "면목동이요."},
    expected=Expected(
        name="김순자", age=78,
        attraction_labels=["정릉시장", "방앗간", "버스정류장"],
        evidence={"정릉시장": "caregiver_report", "방앗간": "caregiver_report",
                  "버스정류장": "previous_missing_found"},
        axis_fields=["mobility_transport_capacity", "lost_behavior",
                     "autobiographical_destination_pull", "dementia_wandering_pattern",
                     "route_environment_familiarity"],
    ),
)

D2 = Scenario(
    id="G_D2_lee", title="골드셋 치매 · 이판석(옛집 회귀·대흥역 발견)",
    guardian_name="이보호", persona_type="dementia",
    answers={
        "identity": "아버지 성함은 이판석, 여든둘이세요. 알츠하이머세요.",
        "home": "지금은 노원구 상계동 저희 집에서 모시고 있어요.",
        "autobiographical_destination_pull":
            "자꾸 예전에 살던 집에 가야 한다고 하세요. 젊을 때 사시던 데요. "
            "짐 싸서 나가려고 하신 적도 있어요.",
        "dementia_wandering_pattern":
            "재작년에 실종되셨었는데 대흥역에서 발견됐어요. 옛날 집 찾아가신다고 "
            "계속 걷고 계셨대요.",
        "medication": "치매약 드시는데 거르면 밤에 더 심하게 돌아다니세요. 밤에도 나가시려고 해요.",
        "communication_approach_vulnerability":
            "이름은 말하시는데 지금 주소는 헷갈려 하세요. 낯선 사람이 친절하게 굴면 잘 따라가세요.",
        "routine_destinations": "요즘은 딱히 혼자 가시는 데는 없어요. 늘 옛날 집 얘기만 하세요.",
    },
    area_answers={"예전에 살던 집": "마포구 신수동이요.", "옛집": "마포구 신수동이요.",
                  "살던 집": "마포구 신수동이요."},
    expected=Expected(
        name="이판석", age=82,
        attraction_labels=["살던 집", "대흥역"],
        evidence={"살던 집": "caregiver_report", "대흥역": "previous_missing_found"},
        axis_fields=["mobility_transport_capacity", "communication_approach_vulnerability",
                     "lost_behavior", "autobiographical_destination_pull",
                     "dementia_wandering_pattern"],
    ),
)

D3 = Scenario(
    id="G_D3_choi", title="골드셋 치매 · 최영자(집콕·저위험)",
    guardian_name="최보호", persona_type="dementia",
    answers={
        "identity": "어머니 최영자, 일흔여섯이고 경도 치매세요. 초기라 아직 많이 괜찮으세요.",
        "home": "은평구 응암동에서 혼자 사시는데 저희가 매일 들여다봐요.",
        "routine_destinations": "동네 복지관 다니시는 거 말곤 멀리는 안 나가세요. 집에 계시는 걸 좋아하세요.",
        "autobiographical_destination_pull": "옛날 얘기는 하셔도 어디 가야 한다거나 그런 건 없으세요.",
        "dementia_wandering_pattern": "실종된 적은 없어요. 길 잃으신 적도 없고요.",
        "communication_approach_vulnerability": "정신은 또렷하셔서 성함이랑 주소, 제 전화번호까지 다 말하세요.",
        "hazard_awareness_vulnerability": "다리는 튼튼하시고 신호도 잘 지키세요. 물가 이런 데도 조심하세요.",
    },
    expected=Expected(
        name="최영자", age=76,
        attraction_labels=["복지관"],
        evidence={"복지관": "caregiver_report"},
        axis_fields=["mobility_transport_capacity", "communication_approach_vulnerability",
                     "wayfinding_error_recovery_deficit"],
    ),
)

D4 = Scenario(
    id="G_D4_park", title="골드셋 치매 · 박순단(정보부족·판정불가)",
    guardian_name="박보호", persona_type="dementia",
    answers={
        "identity": "할머니신데 성함이… 박순단이실 거예요. 연세는 여든쯤 되셨어요.",
        "home": "얼마 전에 저희 집으로 오셨어요. 부천 쪽인데 정확한 동은 저도 잘…",
        "autobiographical_destination_pull": "예전 일은 저희가 잘 몰라요. 최근에 모시게 돼서요.",
        "dementia_wandering_pattern": "글쎄요, 그런 얘긴 못 들었어요.",
        "routine_destinations": "잘 모르겠어요. 오신 지 얼마 안 돼서 어딜 다니시는지…",
        "mobility_transport_capacity": "천천히 걷는 정도는 하세요. 그 외엔 잘 모르겠어요.",
        "communication_approach_vulnerability": "말수가 적으셔서 뭘 물어도 대답을 잘 안 하세요.",
    },
    # 이름·나이·유형 모두 판정불가(불확실)로 판정 → name/age 채점 제외(빈값).
    expected=Expected(
        axis_fields=["mobility_transport_capacity", "communication_approach_vulnerability"],
    ),
)


GOLDSET: dict[str, Scenario] = {
    s.id: s for s in (D1, D2, D3, D4)
}
