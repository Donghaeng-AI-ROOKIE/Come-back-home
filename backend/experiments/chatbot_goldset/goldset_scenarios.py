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


# ── 발달장애 4 ────────────────────────────────────────────────────────
P1 = Scenario(
    id="G_P1_junho", title="골드셋 발달 · 준호(지하철·물·감각회피)",
    guardian_name="준호모", persona_type="intellectual_disability",
    answers={
        "identity": "아들 준호예요. 열아홉 살이고 자폐성 발달장애가 있어요.",
        "home": "강서구 화곡동에 살아요.",
        "preferred_target_seeking": "지하철을 정말 좋아해요. 특히 5호선요. 역만 보이면 혼자라도 들어가려고 해요.",
        "hazard_awareness_vulnerability": "물도 좋아해서 안양천 분수대 쪽으로 자꾸 가려고 해요. 물가 위험한 건 잘 몰라요.",
        "elopement_pattern_consistency": "작년에 저랑 떨어져서 혼자 지하철 타고 세 정거장 갔다가 발견된 적 있어요.",
        "aversive_context_escape": "사이렌이나 큰 소리가 나면 귀 막고 화장실 같은 데로 숨어버려요.",
        "transition_routine_disruption": "복지관 하원 시간이 바뀌면 정류장에 그대로 서서 원래 버스만 기다려요.",
    },
    area_answers={"안양천": "강서구요.", "분수대": "안양천이요."},
    expected=Expected(
        name="준호", age=19,
        attraction_labels=["분수대"],
        preferred_labels=["지하철"],
        evidence={"분수대": "caregiver_report"},
        axis_fields=["mobility_transport_capacity", "hazard_awareness_vulnerability",
                     "preferred_target_seeking", "elopement_pattern_consistency",
                     "aversive_context_escape", "transition_routine_disruption"],
    ),
)

P2 = Scenario(
    id="G_P2_seoyeon", title="골드셋 발달 · 서연(편의점·자동문·버스노선)",
    guardian_name="서연모", persona_type="intellectual_disability",
    answers={
        "identity": "딸 서연이고 스물둘이에요. 지적장애 2급이에요.",
        "home": "관악구 신림동 살아요.",
        "preferred_target_seeking":
            "편의점을 엄청 좋아해요. 자동문 열리는 걸 계속 보고 싶어 해서 편의점마다 들어가려고 해요.",
        "elopement_pattern_consistency": "혼자 나가면 꼭 6번 버스를 타요. 늘 같은 노선이에요. 두 번 다 종점에서 발견됐어요.",
        "communication_approach_vulnerability":
            "이름은 말하는데 주소는 잘 몰라요. 누가 뭐 사준다고 하면 따라가서 그게 제일 걱정이에요.",
        "aversive_context_escape": "사람 많고 시끄러운 데는 싫어하는데, 그렇다고 도망가거나 하진 않아요.",
        "mobility_transport_capacity": "버스는 혼자 타요. 근데 길은 잘 몰라서 늘 타던 것만 타요.",
    },
    expected=Expected(
        name="서연", age=22,
        attraction_labels=["종점"],
        preferred_labels=["편의점"],
        evidence={"종점": "previous_missing_found"},
        axis_fields=["mobility_transport_capacity", "hazard_awareness_vulnerability",
                     "communication_approach_vulnerability", "preferred_target_seeking",
                     "elopement_pattern_consistency"],
    ),
)

P3 = Scenario(
    id="G_P3_minsu", title="골드셋 발달 · 민수(물 최우선 위험·반복경로)",
    guardian_name="민수모", persona_type="intellectual_disability",
    answers={
        "identity": "민수예요. 열여섯이고 자폐예요. 말은 거의 안 해요.",
        "home": "중랑구 면목동에 살아요.",
        "preferred_target_seeking": "물을 너무 좋아해서 수영장이나 분수만 보면 뛰어들어요. 이게 제일 무서워요. 깊이를 몰라요.",
        # 발달장애엔 dementia_wandering_pattern 슬롯이 없어 '과거 발견'을 elopement 로 병합
        # (안 그러면 그 슬롯이 안 물어져 수영장 발견 근거가 유실됨 — 스모크에서 발견).
        "elopement_pattern_consistency":
            "나가면 늘 같은 길로 동네 수영장 쪽으로 가요. 매번 그 방향이에요. "
            "재작년엔 수영장 앞에서 혼자 거기까지 가서 발견된 적도 있어요.",
        "aversive_context_escape": "큰 소리 나면 귀 막고 구석으로 가서 웅크려요.",
        "communication_approach_vulnerability": "이름 불러도 잘 안 쳐다봐요. 자기 이름이나 주소는 말 못 해요.",
    },
    area_answers={"수영장": "면목동이요.", "분수": "면목동이요."},
    expected=Expected(
        name="민수", age=16,
        attraction_labels=["수영장"],
        preferred_labels=["물"],
        evidence={"수영장": "previous_missing_found"},
        axis_fields=["mobility_transport_capacity", "hazard_awareness_vulnerability",
                     "preferred_target_seeking", "elopement_pattern_consistency",
                     "aversive_context_escape"],
    ),
)

P4 = Scenario(
    id="G_P4_jihun", title="골드셋 발달 · 지훈(정보부족·판정불가)",
    guardian_name="지훈위탁", persona_type="intellectual_disability",
    answers={
        "identity": "지훈이고 스물다섯이에요. 지적장애가 있다고만 알고 있어요.",
        "home": "저희가 위탁으로 최근에 맡아서, 원래 어디 살았는지는 잘 몰라요. 지금은 동대문구요.",
        "preferred_target_seeking": "뭘 특별히 좋아하는지 아직 잘 모르겠어요. 온 지 얼마 안 돼서요.",
        "elopement_pattern_consistency": "혼자 나간 적은 아직 없어서 그런 이력은 몰라요.",
        "aversive_context_escape": "글쎄요, 아직 파악 중이라 뭐라 말씀드리기가…",
        "mobility_transport_capacity": "걷는 건 잘 걸어요. 그 외엔 잘 모르겠어요.",
        "communication_approach_vulnerability": "이름은 대답해요. 나머지는 아직 잘 모르겠어요.",
    },
    # 선호대상·과거이력 등 대부분 판정불가. 확정 가능한 것만 채점.
    expected=Expected(
        name="지훈", age=25,
        axis_fields=["mobility_transport_capacity", "communication_approach_vulnerability"],
    ),
)


GOLDSET: dict[str, Scenario] = {
    s.id: s for s in (D1, D2, D3, D4, P1, P2, P3, P4)
}
