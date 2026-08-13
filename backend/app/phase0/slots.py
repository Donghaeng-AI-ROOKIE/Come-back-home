"""Phase 0 온보딩 인터뷰 — 페르소나 축 기반 그라운딩 슬롯 스키마 (질문 뱅크).

「챗봇」 가드레일 원칙: 온보딩 후속질문은 **여기 정의된 슬롯을 채우는 질문만**
생성한다. 스키마 밖 자유질문(환각) 금지. Mi:dm 은 이 목록을 grounding 소스로 받는다.

「페르소나 축 고도화 회의록」(2026-07) 기반 — 몸축·마음축·행동축 3계층:
- 몸축:   얼마나 멀리·오래 걸을 수 있는가 → 반경·속도
- 마음축: 왜 특정 장소로 향하거나 상황을 피하려 하는가 → 목적지·POI·회피 가중치
- 행동축: 마음이 실제로 어떤 이동 방식으로 나타나는가 → 도주·정지·회귀 전략 확률

설계 결정(회의록·팀 합의):
- 대상 유형은 치매 1종 (2026-08-03 팀 결정 — 대상을 치매 실종자로 단일화).
  types 필드와 slots_for() 는 유형별 슬롯 분기 구조를 그대로 유지한다: 지금은
  전 슬롯이 치매용이라 필터가 통과만 하지만, 대상 확장 시 이 자리에 다시 붙는다.
- 씨앗 질문은 회의록 「실제 질문 형식」 원문 그대로. 어차피 Mi:dm 이 참고용으로만
  받아 매 턴 한 질문으로 재문장화한다(prompts.PHRASE_SYSTEM).
- 하위변수(walking_endurance, destination_retention 등)는 별도 슬롯이 아니라
  probes(꼬리질문 각도)로 내려간다 — 보호자 답이 얕을 때 파고드는 용도.
- answer_example(회의록 답변 예시)은 **첫 질문에서 낭독하지 않는다**(설문지화·앵커링
  방지). 꼬리질문 모드에서 답이 두루뭉술할 때만 구체성 눈높이로 활용.
- 축 점수(0.1~0.9) 산정은 인터뷰 중 하지 않는다 — 인터뷰는 관찰 사실 수집까지,
  점수는 종료 후 별도 컴파일 단계에서 회의록 기준표로 매긴다(재현성).

스코프 = **초기 온보딩(안정적 페르소나)만**. "실종 당시 상황"(옷차림·나간 말·
최근 트리거)은 Phase 1 신고 접수에서 수집하므로 여기 포함하지 않는다.
"""

import re
from enum import Enum

from pydantic import BaseModel

from app.schemas.persona import PersonaType

ALL_TYPES = frozenset(PersonaType)


class Axis(str, Enum):
    """회의록의 3계층 축 — 슬롯이 어느 축의 근거를 수집하는가."""
    body = "몸축"          # 이동 능력 → 반경·속도 파라미터
    mind = "마음축"        # 동기·취약성 → 목적지·POI·회피 가중치
    behavior = "행동축"    # 실제 이동 방식 → 전략 확률 (보조지표)
    profile = "기본필드"   # 축 없음 — Persona 필수 필드(identity/home)


class Tier(int, Enum):
    """질문 순서 (예측 기여도 기준). 낮을수록 먼저 묻는다."""
    route = 1     # 장소·경로·과거 이력 — 초기 방향 설정에 직결
    capacity = 2  # 능력·취약성 — 반경·속도 보정
    refine = 3    # 반응성 정밀화 — 상황별 전략 확률


class Sink(str, Enum):
    """수집된 답이 Persona 로 어떻게 떨어지는가."""
    field = "field"              # Persona 기본 필드 (name/age/type/home)
    attraction = "attraction"    # AttractionPoint — 좌표화 대상 장소
    behavior = "behavior"        # behavior_notes[] — 관찰된 행동 사실


class SlotSpec(BaseModel):
    """수집 슬롯 하나. Mi:dm 이 질문을 만들 grounding 단위."""
    key: str
    label: str
    guardian_label: str = ""                      # 보호자에게 보여줄 표현 (요약 카드 전용)
    axis: Axis
    axis_field: str = ""                          # 회의록 DB 필드명 — 축 점수 컴파일 대상
    tier: Tier
    sink: Sink
    types: frozenset[PersonaType] = ALL_TYPES     # 이 슬롯이 유효한 유형
    question: str                                 # 씨앗 질문 (회의록 원문, 참고용)
    probes: list[str] = []                        # 답이 얕을 때 파고들 꼬리질문 각도(=하위변수)
    # 이 슬롯에서 꼬리질문을 내보낼지. probes 는 비우지 않는다 — embed_text(슬롯 검색
    # 코퍼스)와 문장화 프롬프트가 같은 목록을 쓰므로, 비우면 랭킹까지 달라진다.
    # 파고들기만 끄고 싶을 때 이 플래그를 쓴다.
    probe_followup: bool = True
    # 첫 번째 probes 각도를 **모델 판정 없이 반드시 한 번 묻는다**.
    # 판정기(probe_gap)가 애매한 답을 '답했다'로 넘기는 슬롯에 쓴다 — 상세는
    # medication 슬롯의 주석 참고 (2026-08-07 사용자 결정).
    always_probe_first: bool = False
    filled_when: str                              # '충분히 채워짐' 기준 (follow-up 여부 판단)
    why: str                                      # SAR 근거 — 이 정보가 예측에 쓰이는 이유
    keywords: list[str] = []                      # 검색 부스팅·문맥 매칭용 어휘 (dense 위 lexical 힌트)
    risk: float = 0.0                             # 위험 부스트 — 질문순서(tier)와 별개로 안전상 우선
    answer_example: str = ""                      # 회의록 답변 예시 — 꼬리질문 모드 구체성 눈높이 전용

    @property
    def probe_labels(self) -> list[str]:
        """내부 태그를 뗀 표시용 probes — "(destination_retention)" 같은 꼬리표 제거."""
        return [re.sub(r"\s*\([a-z_]+\)\s*$", "", p).strip() for p in self.probes]

    @property
    def display_label(self) -> str:
        """보호자용 표현. 없으면 내부 라벨로 폴백(요약이 비는 것보다 낫다).

        label 은 내부 식별자 역할을 겸한다 — behavior_notes 의 '라벨: 노트' 접두와
        대시보드 귀속(static/dashboard.html)이 이 문자열에 걸려 있어 바꿀 수 없다.
        보호자 화면 문구는 그래서 별도 필드로 둔다.
        """
        return self.guardian_label or self.label

    @property
    def embed_text(self) -> str:
        """dense retrieval 코퍼스 표면. 히스토리-어웨어 쿼리와 코사인 비교 대상.

        answer_example 은 제외 — 예시 속 고유명사(지하철역·시장 등)가 무관 슬롯을
        검색에 끌어올리는 오염을 막는다.
        """
        parts = [self.label, self.question, *self.probes, *self.keywords, self.why]
        return " · ".join(parts)


# ── 슬롯 카탈로그 ────────────────────────────────────────────────────
# 순서 = 기본 질문 순서(tier→정의순). Mi:dm 은 답변 맥락에 따라 순서를 바꾸거나
# 유형 무관 슬롯을 건너뛴다.

_DEM = frozenset({PersonaType.dementia})

SLOTS: list[SlotSpec] = [
    # ── Tier 1 · 장소·경로·과거 이력 ──────────────────────────────
    SlotSpec(
        key="identity", label="대상자 성함·나이", guardian_label="성함과 나이",
        axis=Axis.profile, tier=Tier.route, sink=Sink.field,
        question="등록하실 어르신의 성함과 나이를 알려주세요.",
        probes=["나이를 만 나이로 확인"],
        filled_when="이름·나이 2가지가 모두 특정됨",
        why="Koester 치매 이동거리 프로파일 적용 대상 식별 — 나이는 보행 능력 추정의 기준.",
    ),
    SlotSpec(
        key="home", label="현재 거주지", guardian_label="지내시는 곳",
        axis=Axis.profile, tier=Tier.route, sink=Sink.field,
        question="지금 살고 계신 집(또는 주로 머무시는 곳)의 주소나 동네를 알려주세요.",
        probes=["동/도로명 수준까지", "요양원·주간보호센터·복지관이면 그 위치도"],
        filled_when="지오코딩 가능한 동네·주소 수준으로 특정됨",
        why="시뮬레이션 원점(LKP 대체) 및 POA 격자 중심.",
        answer_example="서울 중랑구 면목동 ○○아파트에 살고, 주중 낮에는 주간보호센터에 계십니다.",
    ),
    SlotSpec(
        key="routine_destinations", label="혼자 자주 가는 곳·경로",
        guardian_label="혼자 다니시는 곳", axis=Axis.mind,
        axis_field="route_environment_familiarity", tier=Tier.route, sink=Sink.attraction,
        question="혼자 나가실 때 주로 어디에 가시나요? (마트, 공원, 경로당 등) 가는 길도 정해져 있나요?",
        probes=[
            "가장 자주 가는 1곳",
            "가는 방향·경유지 — 정해진 길이 있는지",
            "익숙한 길에서는 헤매지 않는지(익숙한 경로 목록화)",
            "산책 코스가 있으면 도는 방향",
        ],
        filled_when="단골 목적지 1곳 이상 + 대략 경로/방향 (또는 '혼자 안 나감' 확인)",
        why="route_following 앵커 + 익숙한 경로에서 혼란 감소(route_environment_familiarity 근거).",
        keywords=["마트", "공원", "경로당", "산책", "매일", "늘 가던", "단골"],
    ),
    SlotSpec(
        key="autobiographical_destination_pull", label="자전적 기억 기반 목적지",
        guardian_label="자꾸 찾으시는 옛 장소",
        axis=Axis.mind, axis_field="autobiographical_destination_pull",
        tier=Tier.route, sink=Sink.attraction, types=_DEM,
        question="대상자가 반복해서 찾거나 가려고 하는 과거의 장소가 있나요? 옛집, 예전 직장, 시장, 병원, 약국, 종교시설처럼 구체적인 장소를 알려주세요.",
        probes=[
            "장소를 동네·지명 수준으로 특정 (옛집/직장/시장/병원/종교시설 순회)",
            "'고향 가고 싶다', '일하러 간다' 같은 반복 발화",
            "본인을 젊은 시절·현역으로 인식하는지 (활성 앵커 시대 판정)",
            "지금 집을 '남의 집'이라 여기며 나가려 하는지",
            "그리워하는 사람(옛 친구·돌아가신 가족)과 연관된 장소",
            "실제 가려다 목격됐는지, 말만 하는지 (anchor 근거 강도)",
        ],
        filled_when="반복 지향 장소가 동네 수준으로 특정되거나 '없음' 확인 (있으면 근거 유형 포함)",
        why="치매 기억 앵커 — anchors(장소·근거·강도)로 개인별 POI 가중. 과거회귀 배회의 대표 목적지.",
        keywords=["옛날 집", "예전 집", "고향", "살던 곳", "이사", "친정", "시골집",
                  "직장", "회사", "가게", "일터", "출근", "일하러", "시장",
                  "젊은 시절", "현역", "몇 년도", "착각", "옛 교회", "옛 절",
                  "그리워", "보러 간다", "남의 집"],
        answer_example="예전에 살던 집에 가야 한다는 말을 자주 합니다. 과거 실종 당시에도 옛집 근처에서 발견됐습니다.",
    ),
    SlotSpec(
        key="dementia_wandering_pattern", label="과거 실종·배회 행동 패턴",
        guardian_label="예전에 길 잃으셨을 때",
        axis=Axis.behavior, axis_field="dementia_wandering_pattern",
        tier=Tier.route, sink=Sink.behavior, types=_DEM,
        question="과거에 길을 잃거나 실종된 적이 있다면, 어디에서 발견됐고 어떤 행동을 하고 있었는지 알려주세요.",
        probes=[
            "발견 장소를 동네 수준으로",
            "발견 당시 행동 — 계속 걷기·같은 구간 왕복·되돌아가기·숨어 있음",
            "그 행동이 여러 번 반복됐는지",
            "그때 가려던 목적지 (기억 앵커 근거로 연결)",
        ],
        filled_when="이력 유무 확인 + 있으면 발견 장소와 당시 행동, 반복 여부까지",
        why="개인 재현성 — 과거 발견지는 강력한 사전확률. 반복 행동은 전략 확률(배회·회귀·은신) 직결.",
        keywords=["실종", "발견", "배회", "못 돌아오", "파출소", "경찰서", "지구대"],
        answer_example="두 번 모두 집에서 약 1km 떨어진 시장 근처에서 발견됐고, 주변을 계속 반복해서 걷고 있었습니다.",
    ),

    # ── Tier 2 · 능력·취약성 ──────────────────────────────────────
    SlotSpec(
        key="mobility_transport_capacity", label="이동·교통 능력",
        guardian_label="얼마나 걸으실 수 있는지",
        axis=Axis.body, axis_field="mobility_transport_capacity",
        tier=Tier.capacity, sink=Sink.behavior,
        question="대상자는 평소 보호자의 도움 없이 얼마나 오래 또는 멀리 걸을 수 있나요?",
        probes=[
            "쉬지 않고 걷는 시간·거리 (walking_endurance)",
            "걸음이 빠른 편인지 느린 편인지 (walking_speed)",
            "보호자 없이 혼자 외출이 가능한지 (outdoor_independence)",
            "무릎·허리·보조기구 등 신체 제한 (physical_limitations)",
        ],
        filled_when="보행 지속(시간·거리)이 드러남",
        why="몸축 — 최대 반경·속도·이동시간 파라미터. "
            "차량 이용·운전 가능성은 탐색 반경·방법이 통째로 바뀌는 별개 시나리오라 이 축에서 제외(2026-07-17 팀 결정). "
            "대중교통 이용 가능성도 같은 이유로 이 축에서 제외(2026-07-24 안1 결정) — 미확인 대중교통 이용으로 "
            "반경 밖에서 발견되는 경우는 Phase 3 제보가 흡수한다(고신뢰 제보 → 새 LKP 재예측 → D3 새 지역 알림).",
        keywords=["걸어", "보행", "지팡이", "휠체어", "무릎", "허리"],
        answer_example="쉬지 않고 약 30분 정도 걸을 수 있고, 집에서 1km 정도까지 혼자 이동할 수 있습니다.",
    ),
    SlotSpec(
        key="hazard_awareness_vulnerability", label="환경 위험 취약성",
        guardian_label="위험한 곳을 피하실 수 있는지",
        axis=Axis.mind, axis_field="hazard_awareness_vulnerability",
        tier=Tier.capacity, sink=Sink.behavior,
        question="대상자는 차도, 횡단보도, 물가, 계단처럼 위험한 장소를 스스로 알아보고 피할 수 있나요?",
        probes=[
            "차도·횡단보도에서 신호를 지키는지",
            "물가(강·호수)의 위험을 인식하는지",
            "계단·높은 곳에서 조심하는지",
            "실제로 위험했던 사례",
        ],
        filled_when="차도·물가·계단 중 위험 인식 수준이 구체 사례와 함께 드러남",
        why="위험 지형(차도·물가·추락) 접근·통과 확률 보정과 수색 안전 우선순위.",
        keywords=["차도", "찻길", "횡단보도", "신호", "물가", "계단", "위험", "아찔"],
        risk=0.10,
        answer_example="차가 오는 것은 알아보지만 신호를 잘 지키지 못합니다. 물가나 높은 계단의 위험성은 잘 인식하지 못합니다.",
    ),
    SlotSpec(
        key="communication_approach_vulnerability", label="의사소통·접근 취약성",
        guardian_label="누가 말을 걸었을 때 반응",
        axis=Axis.mind, axis_field="communication_approach_vulnerability",
        tier=Tier.capacity, sink=Sink.behavior,
        question="대상자는 이름을 부르거나 간단한 질문을 했을 때 어떻게 반응하나요? 자신의 이름, 주소 또는 보호자 연락처를 말할 수 있는지도 알려주세요.",
        probes=[
            "낯선 시민이나 경찰이 다가와 말을 걸면 어떻게 행동하는지",
            "자기 이름·주소·연락처를 말할 수 있는지",
            "경찰 제복을 보면 따르는지, 피하는지",
            "태워주거나 데려간다고 하면 따라갈 가능성 (유인 취약성)",
        ],
        filled_when="호명·질문 반응과 낯선 사람/경찰 접근 반응이 모두 드러남",
        why="발견 가능성·현장 구조 접근 전략, 유인(비배회 이탈) 위험 분기.",
        keywords=["이름", "부르면", "대답", "낯선 사람", "경찰", "제복", "따라가", "도망"],
        answer_example="이름을 부르면 쳐다보지만 대답은 잘하지 않습니다. 자신의 이름은 말할 수 있지만 주소와 연락처는 말하지 못합니다.",
    ),
    SlotSpec(
        key="medication", label="복약·건강 상태", guardian_label="드시는 약과 건강 상태",
        axis=Axis.body, tier=Tier.capacity, sink=Sink.behavior,
        question="복용 중인 약이 있나요? 거르면 어떤 증상이 나타나나요? 야간·추위·더위에 이동하기 어려운 상태인가요?",
        probes=["거르면 나타나는 증상", "야간 이동 가능성", "추위·더위 취약성"],
        # 첫 각도('거르면 나타나는 증상')는 판정 없이 반드시 묻는다 (2026-08-07 결정).
        # 판정기가 "치매약을 아침저녁으로 드시는데 가끔 거르고 나가십니다"를 증상까지
        # 답한 것으로 넘겨(3/3), 꼬리질문이 야간·추위로 건너뛰었다. 그 둘은 이 슬롯에
        # 묶여 있을 뿐 약과 무관해 보여 보호자에겐 "복약 꼬리질문이 없다"로 읽힌다.
        # 거른 뒤 증상은 생존 골든타임 추정의 직접 입력이라 놓치면 안 된다.
        always_probe_first=True,
        filled_when="건강 제약(약·야간·기후) 중 유의미한 항목이 드러남",
        why="생존 골든타임·야간 이동 가능성 추정. (회의록 축 밖 — 몸축 보조 정보로 유지)",
        keywords=["약", "복용", "야간", "밤", "추위", "더위", "혈압", "당뇨"],
        answer_example="혈압약과 치매약을 아침저녁으로 드시고, 거르면 어지러워하십니다. 밤에도 나가신 적이 있습니다.",
    ),
    SlotSpec(
        key="wayfinding_error_recovery_deficit", label="길찾기 오류·경로 회복 취약성",
        guardian_label="길을 잘못 드셨을 때 돌아오시는지",
        axis=Axis.mind, axis_field="wayfinding_error_recovery_deficit",
        tier=Tier.capacity, sink=Sink.behavior, types=_DEM,
        question="대상자는 익숙한 동네에서도 길을 잘못 들거나 목적지를 잊는 경우가 있나요? 길을 잘못 들었을 때 스스로 알아차리고 돌아올 수 있는지도 알려주세요.",
        probes=[
            "가는 도중 목적지를 잊는지 (destination_retention)",
            "아는 건물·가게를 못 알아보는지 (landmark_recognition)",
            "갈림길에서 방향을 못 정하고 헤매는지 (intersection_decision)",
            "잘못 간 것을 스스로 알아차리는지 (route_error_awareness)",
            "알아차리면 혼자 돌아오는지, 도움이 필요한지 (route_recovery_ability)",
        ],
        filled_when="길 잃음 빈도와 오류 자각·복귀 능력이 모두 드러남",
        why="어느 기능이 손상됐는지로 전략 분기 — 오류 자각 가능할 때만 backtracking, 심한 혼란은 목적지 상실 random walk.",
        keywords=["길 잃", "헤매", "방향", "갈림길", "잊", "못 알아보", "되돌아"],
        answer_example="집 근처에서도 가끔 방향을 잃습니다. 잘못 간 것을 스스로 알아차리지 못하고 다른 사람의 도움을 받아야 돌아옵니다.",
    ),

    # ── Tier 3 · 반응성 정밀화 ────────────────────────────────────
    SlotSpec(
        key="lost_behavior", label="길 잃었을 때 행동", guardian_label="길을 잃으시면 하시는 행동",
        axis=Axis.behavior, axis_field="lost_behavior", tier=Tier.refine, sink=Sink.behavior,
        question="길을 잃으시면 보통 어떻게 하시나요? 한자리에 머무시는 편인가요, 계속 걸으시나요, 아니면 숨으시나요?",
        probes=["머무름·계속 이동·은신 중 우세 경향", "구체적 목격 사례"],
        # 꼬리질문 끔 (2026-08-07 사용자 결정). 이 슬롯은 답 한 마디에 우세 경향이
        # 그대로 드러난다 — "그 자리에 가만히 서계세요" = 머무름. 그걸 저장하면 되지
        # 되물을 일이 아닌데, 남은 각도가 '구체적 목격 사례'뿐이라 꼬리질문이
        # "실제로 그런 모습을 보신 적이 있나요?"가 되어 방금 한 말을 되묻는 꼴이었다.
        # 다른 슬롯의 파고들기(PR #64)는 그대로 — 씨앗 질문이 첫 물음표에서 잘려
        # 못 묻는 하위 항목(예: 복약의 '거르면 어떤 증상')은 이 통로가 유일하다.
        probe_followup=False,
        filled_when="머무름·계속이동·숨음 중 우세 경향이 드러남",
        why="staying_put vs 이동 — 수색 반경 확장 속도를 좌우하는 최우선 변수. 과거 실종 이력이 없을 때의 행동축 백업.",
        keywords=["길 잃", "헤매", "제자리", "계속 걸", "돌아다", "숨", "주저앉"],
        risk=0.10,
        answer_example="길을 잃으면 그 자리에 서서 기다리지 않고 계속 앞으로 걸어갑니다.",
    ),
    SlotSpec(
        key="distress_induced_movement_reactivity", label="정서적 불편에 따른 이동 반응성",
        guardian_label="불안하거나 초조하실 때 하시는 행동",
        axis=Axis.mind, axis_field="distress_induced_movement_reactivity",
        tier=Tier.refine, sink=Sink.behavior, types=_DEM,
        question="대상자가 불안하거나 초조해지거나, 누군가 자신을 해친다고 의심할 때 이동 행동이 어떻게 달라지나요?",
        probes=[
            "일반 불안·초조 / 해친다는 의심(피해적 위협) / 돌봄 저항 — 어느 상황인지 구분",
            "실제 목격된 반응만 — 도망가기·숨기·계속 걷기·멈추기 중 무엇인지",
            "그때 향하는 장소 유형 (골목·건물 안쪽 등)",
        ],
        filled_when="불안·의심 시 실제 반응 방향이 드러나거나 '변화 없음' 확인",
        why="확인된 반응 방향(escape/hide/pacing/freeze)만 전략 확률에 반영 — 점수만으로 회피 장소 예측 금지.",
        keywords=["불안", "초조", "쫓아온다", "훔쳐", "의심", "망상", "도망", "숨",
                  "저항", "화를 내"],
        answer_example="누가 쫓아온다고 생각하면 사람이 없는 골목이나 건물 안쪽으로 숨으려고 합니다.",
    ),
]


# ── 조회 헬퍼 ────────────────────────────────────────────────────────

def slots_for(ptype: PersonaType, tiers: list[int] | None = None) -> list[SlotSpec]:
    """해당 유형에 유효한 슬롯만, 질문 순서(tier→정의순)대로.

    tiers: 지정하면 그 tier(들)의 슬롯만 반환 — 신고 전 미니챗([1]만)·보완챗
    ([2,3]만) 같은 부분 인터뷰에 쓴다. None(기본값)이면 지금까지와 동일하게
    전체 슬롯을 반환한다(기존 호출부는 전부 인자를 안 넘기므로 동작 불변).
    """
    relevant = [s for s in SLOTS if ptype in s.types]
    if tiers is not None:
        relevant = [s for s in relevant if s.tier.value in tiers]
    return sorted(relevant, key=lambda s: s.tier.value)


def slot_by_key(key: str) -> SlotSpec | None:
    return next((s for s in SLOTS if s.key == key), None)
