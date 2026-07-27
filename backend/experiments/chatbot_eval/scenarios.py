"""시나리오 뱅크 — 보호자 답변 대본 + 기대 페르소나.

각 시나리오는 (1) 챗봇 질문에 대한 보호자 답변(슬롯 화제별)과 (2) 종료 시
페르소나가 이래야 한다는 기대치를 쌍으로 들고 있다. responder 가 (1)을,
scorer 가 (2)를 소비한다.

확인 게이트는 **멀티턴**이다(정정 → 재요약 → 정정 → … → "네"). corrections 는
정정 발화를 순서대로 담고, 마지막에 affirm 이 자동으로 붙는다. 정정 유형은
[[airookie-confirmation-gate-corrections]]의 실측 케이스 — 나이·장소지역·장소이름·삭제·추가.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Expected:
    """종료 페르소나가 이래야 한다는 기대치 (실 Mi:dm 목표치). 필요한 것만 채운다."""
    name: str = ""
    age: int = 0
    attraction_labels: list[str] = field(default_factory=list)   # 있어야 할 끌림점(부분매칭)
    preferred_labels: list[str] = field(default_factory=list)    # 있어야 할 선호대상(발달, 좌표화 불가)
    absent_labels: list[str] = field(default_factory=list)       # 없어야 할 끌림점(삭제·이름정정)
    evidence: dict[str, str] = field(default_factory=dict)       # 라벨 → 기대 evidence enum
    area: dict[str, str] = field(default_factory=dict)           # 라벨 → 기대 지역(정정 검증)
    axis_fields: list[str] = field(default_factory=list)         # 기대 axis_evidence 키
    home_near: tuple[float, float] | None = None                 # 수색 원점 보호 검증(lat,lng)


@dataclass
class Scenario:
    """보호자 답변 대본 + 기대 페르소나."""
    id: str
    title: str
    guardian_name: str
    persona_type: str                    # "dementia" | "intellectual_disability"
    answers: dict[str, str]              # slot.key → 보호자 답변 (responder 가 질문을 역매칭)
    expected: Expected
    area_answers: dict[str, str] = field(default_factory=dict)   # 라벨 → 되묻기 주소 답
    extra_places: str = "아니요, 그 정도예요."
    corrections: list[str] = field(default_factory=list)         # 확인 게이트 정정 턴(순서대로)
    affirm: str = "네, 맞아요. 이대로 등록해주세요."
    fallback: str = "잘 모르겠어요."


# 정릉동(성북구) gazetteer 좌표 — 수색 원점 보호 검증용
_JEONGNEUNG = (37.6076, 127.0133)

# ── 치매 공통 답변 베이스 (D1) ──────────────────────────────────────────
# hazard/wayfinding 은 "모르"·"못 알아" 노트 필터를 피하도록 표현을 다듬음.
_DEM_BASE: dict[str, str] = {
    # identity: 규칙 폴백이 이름을 잡도록 "성함은 …," (쉼표로 조사 긁힘 방지)
    "identity": "성함은 김순자, 나이는 78세예요. 치매 진단을 받으셨어요.",
    "home": "성북구 정릉동이요. 정릉초등학교 근처예요.",
    "routine_destinations": "혼자 나가시면 주로 정릉시장에 가세요. 늘 같은 길로 다니세요.",
    "autobiographical_destination_pull":
        "예전에 면목동에서 방앗간을 오래 하셨는데, 아직도 새벽에 방앗간 문 열러 "
        "가야 한다고 자주 나가려 하세요.",
    "dementia_wandering_pattern":
        "작년에 한 번 못 돌아오신 적 있어요. 면목동 버스정류장 근처에서 발견됐고 "
        "계속 서성이고 계셨대요.",
    "mobility_transport_capacity":
        "쉬지 않고 30분 정도 걸으시고 1km는 혼자 가세요. 버스나 지하철은 혼자 못 타세요.",
    "hazard_awareness_vulnerability":
        "차가 오는 건 보시는데 신호는 잘 안 지키세요. 물가는 위험한 줄 인식이 약하세요.",
    "communication_approach_vulnerability":
        "이름을 부르면 쳐다보시는데 대답은 잘 안 하세요. 주소나 연락처는 말씀 못 하세요.",
    "medication": "혈압약이랑 치매약을 아침저녁으로 드세요. 거르면 어지러워하세요.",
    "wayfinding_error_recovery_deficit":
        "집 근처에서도 가끔 길을 헤매세요. 잘못 든 걸 스스로 알아채기 어려워 "
        "누가 도와드려야 돌아오세요.",
    "lost_behavior": "길을 잃으면 한자리에 안 계시고 계속 앞으로 걸어가세요.",
    "distress_induced_movement_reactivity":
        "누가 쫓아온다고 생각하시면 사람 없는 골목으로 숨으려 하세요.",
}

_DEM_AXES = [
    "route_environment_familiarity", "autobiographical_destination_pull",
    "dementia_wandering_pattern", "mobility_transport_capacity",
    "hazard_awareness_vulnerability", "communication_approach_vulnerability",
    "wayfinding_error_recovery_deficit", "lost_behavior",
    "distress_induced_movement_reactivity",
]


def _dem(over: dict[str, str] | None = None) -> dict[str, str]:
    d = dict(_DEM_BASE)
    if over:
        d.update(over)
    return d


# ── D1. 김순자 — 전 슬롯 베이스라인 ────────────────────────────────────
D1_KIM = Scenario(
    id="D1_kim", title="치매 · 정릉동 김순자 (베이스라인)",
    guardian_name="김보호", persona_type="dementia",
    answers=_dem(),
    area_answers={"방앗간": "면목동이요.", "옛집": "면목동이요."},
    expected=Expected(
        name="김순자", age=78,
        attraction_labels=["정릉시장", "방앗간", "면목동"],
        evidence={"면목동": "previous_missing_found", "방앗간": "caregiver_report",
                  "정릉시장": "caregiver_report"},
        axis_fields=_DEM_AXES, home_near=_JEONGNEUNG,
    ),
)


# ── D2. 대흥역 발견 (evidence 0.9) + 옛집 라벨생성·되묻기 ──────────────────
# 실측 핵심: "대흥역에서 발견"은 previous_missing_found(0.9), Mi:dm 이 이전 턴
# 장소를 되뱉는 백스톱 검증. autobiographical 은 지역 없는 "예전에 살던 집" →
# _ensure_past_place 라벨 생성 → 그 턴 주소 되묻기.
D2_DAEHEUNG = Scenario(
    id="D2_daeheung", title="치매 · 대흥역 발견(0.9) + 옛집 되묻기",
    guardian_name="박보호", persona_type="dementia",
    answers=_dem({
        "autobiographical_destination_pull":
            "예전에 살던 집에 가야 한다는 말씀을 자주 하세요. 거기로 가려고 하세요.",
        "dementia_wandering_pattern":
            "재작년에 실종되신 적 있는데 대흥역에서 발견됐어요. 계속 주변을 걷고 계셨대요.",
    }),
    area_answers={
        "예전에 살던 집": "마포구 신수동이요.", "살던 집": "마포구 신수동이요.",
        "옛집": "마포구 신수동이요.",
    },
    expected=Expected(
        name="김순자", age=78,
        attraction_labels=["대흥역", "살던 집"],
        evidence={"대흥역": "previous_missing_found"},
        axis_fields=_DEM_AXES, home_near=_JEONGNEUNG,
    ),
)


# ── 확인 게이트 정정 5유형 ────────────────────────────────────────────
# ① 나이 정정 — overwrite=True 경로 (first-wins 뚫기)
COR_AGE = Scenario(
    id="COR_age", title="정정① 나이 (78→80)",
    guardian_name="정정보호", persona_type="dementia",
    answers=_dem(),
    area_answers={"방앗간": "면목동이요."},
    corrections=["아니요, 나이가 틀렸어요. 78살이 아니라 80살이에요."],
    expected=Expected(name="김순자", age=80, home_near=_JEONGNEUNG),
)

# ② 장소 지역 정정 — set_area, **home 은 안 바뀌어야** (수색 원점 보호)
COR_AREA = Scenario(
    id="COR_area", title="정정② 장소지역 (방앗간 면목동→화곡동, home 보호)",
    guardian_name="정정보호", persona_type="dementia",
    answers=_dem(),
    area_answers={"방앗간": "면목동이요."},
    corrections=["방앗간은 면목동이 아니라 화곡동이에요."],
    expected=Expected(
        name="김순자", age=78,
        attraction_labels=["방앗간"], area={"방앗간": "화곡동"},
        home_near=_JEONGNEUNG,   # 정릉동 그대로여야 함
    ),
)

# ③ 장소 이름 정정 — rename (remove 오분류 방지)
COR_RENAME = Scenario(
    id="COR_rename", title="정정③ 장소이름 (원평중→원평초)",
    guardian_name="정정보호", persona_type="dementia",
    answers=_dem({
        "dementia_wandering_pattern":
            "작년에 원평중학교 앞에서 발견되셨어요. 주변을 계속 서성이고 계셨대요.",
    }),
    area_answers={"방앗간": "면목동이요.", "원평중학교": "면목동이요.",
                  "원평초등학교": "면목동이요."},
    corrections=["원평중학교가 아니라 원평초등학교예요."],
    expected=Expected(
        name="김순자", age=78,
        attraction_labels=["원평초등학교"], absent_labels=["원평중학교"],
        home_near=_JEONGNEUNG,
    ),
)

# ④ 삭제 — 빼달라는 의사가 있을 때만 remove
COR_REMOVE = Scenario(
    id="COR_remove", title="정정④ 삭제 (정릉시장 빼기)",
    guardian_name="정정보호", persona_type="dementia",
    answers=_dem(),
    area_answers={"방앗간": "면목동이요."},
    corrections=["정릉시장은 요즘 안 가세요. 정릉시장은 빼주세요."],
    expected=Expected(
        name="김순자", age=78,
        absent_labels=["정릉시장"], home_near=_JEONGNEUNG,
    ),
)

# ⑤ 추가 — add + 지역 없으면 되묻기
COR_ADD = Scenario(
    id="COR_add", title="정정⑤ 추가 (북한산 자주 감)",
    guardian_name="정정보호", persona_type="dementia",
    answers=_dem(),
    area_answers={"방앗간": "면목동이요.", "북한산": "성북구 정릉동이요."},
    corrections=["그리고 북한산에도 자주 가세요. 이것도 추가해주세요."],
    expected=Expected(
        name="김순자", age=78,
        attraction_labels=["북한산"], home_near=_JEONGNEUNG,
    ),
)


# ── 희소응답 프로브 — 가드 스윕용 ────────────────────────────────────
# 대부분 슬롯에 "모르겠어요"(무지)·"없어요"(부정)로 답한다. 효율 가드
# (무지소진·부정충족·중복방지)가 꺼지면 재질문이 폭증 → 질문수·중복질문으로
# 실효성이 드러난다. identity·home 만 실답(퍼널 진행에 필요).
PROBE_SPARSE = Scenario(
    id="PROBE_sparse", title="가드 스윕 프로브 · 희소응답(치매)",
    guardian_name="프로브", persona_type="dementia",
    answers={
        "identity": "성함은 이무명, 나이는 80세예요. 치매세요.",
        "home": "성북구 정릉동이요.",
        "routine_destinations": "딱히 없어요.",
        "autobiographical_destination_pull": "잘 모르겠어요.",
        "dementia_wandering_pattern": "그런 적 없어요.",
        "mobility_transport_capacity": "잘 모르겠어요.",
        "hazard_awareness_vulnerability": "잘 모르겠어요.",
        "communication_approach_vulnerability": "잘 모르겠어요.",
        "medication": "없어요.",
        "wayfinding_error_recovery_deficit": "잘 모르겠어요.",
        "lost_behavior": "잘 모르겠어요.",
        "distress_induced_movement_reactivity": "잘 모르겠어요.",
    },
    expected=Expected(name="이무명", age=80, home_near=_JEONGNEUNG),
)


# ── 풍부/드리프트 프로브 — 가드 스윕용(전제·여부먼저·중복·grounding) ──────
# 인용 주장("출근해야 한다고 하세요")으로 전제질문을, 상세 복약("거르시면…")으로
# 부정조건질문을, 다양한 화제(성당·시장·학교·역·약·계단)로 화제 드리프트를 유발한다.
# 답이 풍부해 무지·부정 가드는 거의 발동 안 함(희소 프로브와 상보적).
PROBE_RICH = Scenario(
    id="PROBE_rich", title="가드 스윕 프로브 · 풍부/드리프트(치매)",
    guardian_name="프로브", persona_type="dementia",
    answers={
        "identity": "저희 어머니 성함은 박정례, 나이는 82세이고 알츠하이머 치매를 앓고 계세요.",
        "home": "종로구 명륜동이요. 저희랑 같이 살아요.",
        "routine_destinations":
            "혼자 나가시면 늘 동네 성당하고 재래시장에 가세요. 성당은 매일 아침 미사 "
            "가시고 시장은 반찬거리 사러 가세요. 가는 길은 늘 똑같아요.",
        "autobiographical_destination_pull":
            "자꾸 학교에 출근해야 한다고 하세요. 예전에 명륜동 근처 중학교에서 오래 "
            "교사로 일하셨거든요. 지금도 아침이면 정장 입고 나가려고 하세요.",
        "dementia_wandering_pattern":
            "작년 여름에 한 번 못 찾을 뻔했어요. 혜화역 근처에서 발견됐는데 학교 "
            "찾아간다고 계속 걷고 계셨대요.",
        "mobility_transport_capacity":
            "다리는 아직 정정하셔서 쉬지 않고 한 시간은 걸으세요. 근데 버스는 혼자 "
            "잘 못 타시고 지하철만 예전 기억으로 가끔 타세요.",
        "hazard_awareness_vulnerability":
            "찻길 신호는 그럭저럭 지키시는데 계단이나 에스컬레이터를 무서워하세요.",
        "communication_approach_vulnerability":
            "이름 물으면 대답하시고 옛날 주소는 말하시는데 지금 주소는 헷갈려 하세요. "
            "낯선 사람이 친절하게 대하면 잘 따라가시는 편이라 그게 걱정이에요.",
        "medication":
            "치매약이랑 혈압약, 당뇨약까지 드세요. 약을 거르시면 밤에 잠을 안 "
            "주무시고 더 심하게 배회하세요. 밤에도 나가시려고 해요.",
        "wayfinding_error_recovery_deficit":
            "익숙한 길은 괜찮은데 조금만 벗어나면 방향을 잃으세요. 잘못 든 건 아예 "
            "모르시고 계속 가세요.",
        "lost_behavior":
            "길 잃으면 절대 안 멈추시고 어디든 계속 걸어가세요. 한번은 옆 동네까지 가셨어요.",
        "distress_induced_movement_reactivity":
            "누가 자기 물건 가져간다고 의심하실 때가 있는데 그럴 때 화내면서 밖으로 나가버리세요.",
    },
    area_answers={
        "학교": "명륜동이요.", "중학교": "명륜동이요.", "성당": "명륜동이요.",
        "재래시장": "명륜동이요.", "시장": "명륜동이요.",
    },
    expected=Expected(
        name="박정례", age=82,
        attraction_labels=["성당", "시장", "혜화역"],
        axis_fields=_DEM_AXES,
    ),
)


# ── 발달장애 시나리오 ────────────────────────────────────────────────
# DD1~DD3 은 chatbot_goldset/goldset_scenarios.py 의 발달 대화(G_P1~G_P3)에서
# 가져왔다. **골드셋 쪽은 사람 판정 증적이라 동결** — 하네스 사정으로 대본을
# 손볼 일이 생기면 여기만 고치고 골드셋은 건드리지 않는다(그래서 복사본이다).
#
# 발달 특화 슬롯 4종(preferred_target_seeking · elopement_pattern_consistency ·
# aversive_context_escape · transition_routine_disruption)이 모두 자극되도록
# 배치했다 — transition 은 DD1·DD_RICH 에서만 나온다(대상자 특성상 드물다).

_DD_AXES = [
    "route_environment_familiarity", "preferred_target_seeking",
    "elopement_pattern_consistency", "mobility_transport_capacity",
    "hazard_awareness_vulnerability", "communication_approach_vulnerability",
    "lost_behavior", "aversive_context_escape", "transition_routine_disruption",
]

DD1_JUNHO = Scenario(
    id="DD1_junho", title="발달 · 준호(지하철 선호·물 위험·감각회피)",
    guardian_name="준호모", persona_type="intellectual_disability",
    answers={
        "identity": "아들 준호예요. 열아홉 살이고 자폐성 발달장애가 있어요.",
        "home": "강서구 화곡동에 살아요.",
        "preferred_target_seeking": "지하철을 정말 좋아해요. 특히 5호선요. 역만 보이면 혼자라도 들어가려고 해요.",
        "hazard_awareness_vulnerability": "물도 좋아해서 안양천 분수대 쪽으로 자꾸 가려고 해요. 물가 위험한 건 잘 몰라요.",
        "elopement_pattern_consistency": "작년에 저랑 떨어져서 혼자 지하철 타고 세 정거장 갔다가 발견된 적 있어요.",
        "aversive_context_escape": "사이렌이나 큰 소리가 나면 귀 막고 화장실 같은 데로 숨어버려요.",
        "transition_routine_disruption": "복지관 하원 시간이 바뀌면 정류장에 그대로 서서 원래 버스만 기다려요.",
        # 골드셋 원본엔 없던 답변 — 기대 축(mobility)에 대응하는 답이 없으면
        # 리스폰더가 폴백("잘 모르겠어요")을 내서 축 커버리지가 부당하게 깎인다.
        "mobility_transport_capacity":
            "혼자 30분 넘게 걸어요. 버스는 못 타고 지하철은 아는 노선만 혼자 타요.",
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

DD2_SEOYEON = Scenario(
    id="DD2_seoyeon", title="발달 · 서연(편의점 선호·고정 버스노선)",
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
        # 골드셋 원본엔 없던 답변 — 기대 축(hazard)에 대응하는 답 보강.
        "hazard_awareness_vulnerability":
            "찻길 신호는 보는 편인데, 편의점 자동문만 보이면 앞뒤 안 보고 뛰어들어가요. "
            "주차장에서 차 오는 것도 잘 못 봐요.",
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

DD3_MINSU = Scenario(
    id="DD3_minsu", title="발달 · 민수(물 최우선 위험·반복 경로)",
    guardian_name="민수모", persona_type="intellectual_disability",
    answers={
        "identity": "민수예요. 열여섯이고 자폐예요. 말은 거의 안 해요.",
        "home": "중랑구 면목동에 살아요.",
        "preferred_target_seeking": "물을 너무 좋아해서 수영장이나 분수만 보면 뛰어들어요. 이게 제일 무서워요. 깊이를 몰라요.",
        # 발달엔 dementia_wandering_pattern 이 없어 '과거 발견'을 elopement 에 병합한다
        # (안 그러면 그 슬롯이 안 물어져 수영장 발견 근거가 유실됨 — 골드셋 스모크에서 확인).
        "elopement_pattern_consistency":
            "나가면 늘 같은 길로 동네 수영장 쪽으로 가요. 매번 그 방향이에요. "
            "재작년엔 수영장 앞에서 혼자 거기까지 가서 발견된 적도 있어요.",
        "aversive_context_escape": "큰 소리 나면 귀 막고 구석으로 가서 웅크려요.",
        "communication_approach_vulnerability": "이름 불러도 잘 안 쳐다봐요. 자기 이름이나 주소는 말 못 해요.",
        # 골드셋 원본엔 없던 답변 — 기대 축(mobility·hazard)에 대응하는 답 보강.
        "mobility_transport_capacity": "걷는 건 한참 걸어요. 버스나 지하철은 혼자 못 타요.",
        "hazard_awareness_vulnerability":
            "물 깊이를 몰라서 그냥 들어가요. 찻길도 신호 안 보고 뛰어서 건너요.",
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

# ── 발달 프로브 2종 — 가드 스윕용(치매 PROBE_sparse/rich 와 같은 역할) ──
# 희소: 위탁 초기라 대부분 판정불가. 효율 가드(무지소진·부정충족·중복)를 자극한다.
DD_SPARSE = Scenario(
    id="DD_sparse", title="가드 스윕 프로브 · 희소응답(발달)",
    guardian_name="지훈위탁", persona_type="intellectual_disability",
    answers={
        "identity": "지훈이고 스물다섯이에요. 지적장애가 있다고만 알고 있어요.",
        "home": "저희가 위탁으로 최근에 맡아서, 원래 어디 살았는지는 잘 몰라요. 지금은 동대문구요.",
        "routine_destinations": "딱히 없어요.",
        "preferred_target_seeking": "뭘 특별히 좋아하는지 아직 잘 모르겠어요. 온 지 얼마 안 돼서요.",
        "elopement_pattern_consistency": "혼자 나간 적은 아직 없어서 그런 이력은 몰라요.",
        "mobility_transport_capacity": "걷는 건 잘 걸어요. 그 외엔 잘 모르겠어요.",
        "hazard_awareness_vulnerability": "잘 모르겠어요.",
        "communication_approach_vulnerability": "이름은 대답해요. 나머지는 아직 잘 모르겠어요.",
        "medication": "없어요.",
        "lost_behavior": "잘 모르겠어요.",
        "aversive_context_escape": "글쎄요, 아직 파악 중이라 뭐라 말씀드리기가…",
        "transition_routine_disruption": "잘 모르겠어요.",
    },
    # 치매 PROBE_sparse 와 같이 내용 지표를 기대하지 않는다 — 프로브의 역할은
    # 효율 가드 자극이고, 무지 답변에 섞인 단편("걷는 건 잘 걸어요")은 노트 품질
    # 필터에 걸려 축으로 안 남는 게 정상이다(실측 축 0%).
    expected=Expected(name="지훈", age=25),
)

# 풍부: 답이 길고 화제가 다양해 전제질문·부정조건질문·화제 드리프트를 유발한다.
# 발달 12개 슬롯을 전부 채워 유형-슬롯 정합(치매 전용 슬롯 미출현)도 같이 본다.
DD_RICH = Scenario(
    id="DD_rich", title="가드 스윕 프로브 · 풍부/드리프트(발달)",
    guardian_name="하늘모", persona_type="intellectual_disability",
    answers={
        "identity": "아들 이하늘이고 스물셋이에요. 자폐성 장애가 있어요.",
        "home": "마포구 성산동이요. 저희랑 같이 살아요.",
        "routine_destinations":
            "혼자 나가면 늘 망원시장하고 동네 도서관에 가요. 가는 길이 정해져 있어서 "
            "늘 같은 골목으로만 다녀요.",
        "preferred_target_seeking":
            "버스를 정말 좋아해요. 특히 빨간 광역버스요. 정류장에 서서 몇 시간이고 "
            "버스 들어오는 걸 봐요. 차고지까지 따라간 적도 있어요.",
        "elopement_pattern_consistency":
            "혼자 나가면 늘 합정역 쪽으로 가요. 세 번 다 그 방향이었어요. "
            "두 번은 합정역 버스 정류장에서 발견됐어요.",
        "mobility_transport_capacity":
            "걷는 건 한 시간도 걸어요. 버스는 늘 타던 노선만 혼자 타고, 지하철은 "
            "환승을 못 해서 혼자는 안 태워요.",
        "hazard_awareness_vulnerability":
            "신호는 지키는데 차도랑 인도 구분을 잘 못 할 때가 있어요. 한강 쪽으로 "
            "가면 난간 넘어가려고 해서 겁이 나요.",
        "communication_approach_vulnerability":
            "이름은 말해요. 주소는 외웠는데 긴장하면 말이 안 나와요. 낯선 사람이 "
            "버스 얘기 꺼내면 그냥 따라가요.",
        "medication":
            "항경련제를 아침저녁으로 먹어요. 약을 거르면 그날은 예민해져서 "
            "밖으로 나가려고 해요.",
        "lost_behavior": "길을 잃으면 제자리에 안 있고 아는 정류장 찾을 때까지 계속 걸어요.",
        "aversive_context_escape":
            "형광등 깜빡이는 소리나 아기 우는 소리를 못 견뎌요. 그러면 그 자리를 "
            "바로 벗어나서 조용한 데로 가버려요.",
        "transition_routine_disruption":
            "주간보호센터 차량 시간이 바뀌거나 늘 타던 버스 노선이 우회하면 "
            "그 자리에 계속 서 있거나 원래 가던 길로 혼자 걸어가요.",
    },
    area_answers={
        "망원시장": "마포구요.", "시장": "마포구요.", "도서관": "성산동이요.",
        "합정역": "마포구요.", "차고지": "마포구요.",
    },
    expected=Expected(
        name="이하늘", age=23,
        attraction_labels=["망원시장", "도서관", "합정역"],
        preferred_labels=["버스"],
        axis_fields=_DD_AXES,
    ),
)


SCENARIOS: dict[str, Scenario] = {
    s.id: s for s in (D1_KIM, D2_DAEHEUNG, COR_AGE, COR_AREA, COR_RENAME,
                      COR_REMOVE, COR_ADD, PROBE_SPARSE, PROBE_RICH,
                      DD1_JUNHO, DD2_SEOYEON, DD3_MINSU, DD_SPARSE, DD_RICH)
}
