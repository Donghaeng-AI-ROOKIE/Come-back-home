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


SCENARIOS: dict[str, Scenario] = {
    s.id: s for s in (D1_KIM, D2_DAEHEUNG, COR_AGE, COR_AREA, COR_RENAME,
                      COR_REMOVE, COR_ADD, PROBE_SPARSE, PROBE_RICH)
}
