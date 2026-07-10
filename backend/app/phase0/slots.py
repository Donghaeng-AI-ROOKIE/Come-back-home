"""Phase 0 온보딩 인터뷰 — 그라운딩 슬롯 스키마 (질문 뱅크).

「챗봇」 가드레일 원칙: 온보딩 후속질문은 **여기 정의된 슬롯을 채우는 질문만**
생성한다. 스키마 밖 자유질문(환각) 금지. Mi:dm 은 이 목록을 grounding 소스로 받는다.

「인터뷰질문조사」(Park 2024 / Generative Agent 논문 기반) 를 4개 전문가 렌즈로 구조화:
- 공간지리: 장소 이력 → 후보지 좌표 (attraction_points)
- 행동분석: 성격 → 이동 스타일 (behavior_notes)
- 임상:     인지·신체 → 이동 반경·속도 제약
- 수색구조:  과거 이력·감각 → 행동 패턴·발견 가능성

스코프 = **초기 온보딩(안정적 페르소나)만**. "실종 당시 상황"(옷차림·나간 말·
최근 트리거)은 Phase 1 신고 접수에서 수집하므로 여기 포함하지 않는다.
"""

from enum import Enum

from pydantic import BaseModel

from app.schemas.persona import PersonaType

ALL_TYPES = frozenset(PersonaType)


class Lens(str, Enum):
    """4개 전문가 페르소나 렌즈 (인터뷰질문조사 구조 반영)."""
    geo = "공간지리"       # 장소 이력 → 후보 좌표화
    behavior = "행동분석"   # 성격 → 이동 스타일
    clinical = "임상"       # 인지·신체 → 이동 반경·속도 제약
    sar = "수색구조"        # 과거 이력·감각 → 패턴 매칭·발견 가능성


class Tier(int, Enum):
    """긴급성 기반 질문 순서 (골든타임 원칙). 낮을수록 먼저 묻는다."""
    route = 1        # 경로·장소 — 초기 방향 설정에 직결
    personality = 2  # 성격·의사결정·신체 — 이동 스타일 보정
    refine = 3       # 감각·인지·심리 — 페르소나 정밀화


class Sink(str, Enum):
    """수집된 답이 Persona 로 어떻게 떨어지는가."""
    field = "field"              # Persona 기본 필드 (name/age/type/home)
    attraction = "attraction"    # AttractionPoint — 좌표화 대상 장소
    behavior = "behavior"        # behavior_notes[] — 관찰된 행동 사실


class SlotSpec(BaseModel):
    """수집 슬롯 하나. Mi:dm 이 질문을 만들 grounding 단위."""
    key: str
    label: str
    lens: Lens
    tier: Tier
    sink: Sink
    types: frozenset[PersonaType] = ALL_TYPES   # 이 슬롯이 유효한 유형
    question: str                                # 대표 질문 (씨앗)
    probes: list[str] = []                       # 답이 얕을 때 파고들 꼬리질문 각도
    filled_when: str                             # '충분히 채워짐' 기준 (follow-up 여부 판단)
    why: str                                     # SAR 근거 — 이 정보가 예측에 쓰이는 이유
    keywords: list[str] = []                     # 검색 부스팅·문맥 매칭용 어휘 (dense 위 lexical 힌트)
    risk: float = 0.0                            # 위험 부스트 — 질문순서(tier)와 별개로 안전상 우선

    @property
    def embed_text(self) -> str:
        """dense retrieval 코퍼스 표면. 히스토리-어웨어 쿼리와 코사인 비교 대상."""
        parts = [self.label, self.question, *self.probes, *self.keywords, self.why]
        return " · ".join(parts)


# ── 슬롯 카탈로그 ────────────────────────────────────────────────────
# 순서 = 기본 질문 순서(tier→lens). Mi:dm 은 답변 맥락에 따라 순서를 바꾸거나
# 유형 무관 슬롯을 건너뛴다.

_DEM = frozenset({PersonaType.dementia})
_CHILD = frozenset({PersonaType.child})
_ID = frozenset({PersonaType.intellectual_disability})
_CHILD_ID = frozenset({PersonaType.child, PersonaType.intellectual_disability})

SLOTS: list[SlotSpec] = [
    # ── Tier 1 · 공간지리 (장소·경로) ──────────────────────────────
    SlotSpec(
        key="identity", label="대상자 성함·나이·유형", lens=Lens.geo, tier=Tier.route,
        sink=Sink.field,
        question="등록하실 분의 성함과 나이, 그리고 어떤 상황이신지(치매 어르신 / 아동 / 지적장애) 알려주세요.",
        probes=["나이를 만 나이로 확인", "유형이 모호하면 진단·상황을 한 번 더"],
        filled_when="이름·나이·유형 3가지가 모두 특정됨",
        why="Koester 연령·유형별 이동거리 프로파일 선택의 기준.",
    ),
    SlotSpec(
        key="home", label="현재 거주지", lens=Lens.geo, tier=Tier.route, sink=Sink.field,
        question="지금 살고 계신 집(또는 실종 직전 주로 머무시던 곳)의 주소나 동네를 알려주세요.",
        probes=["동/도로명 수준까지", "요양원·주간보호센터면 그 위치도"],
        filled_when="지오코딩 가능한 동네·주소 수준으로 특정됨",
        why="시뮬레이션 원점(LKP 대체) 및 POA 격자 중심.",
    ),
    SlotSpec(
        key="past_residences", label="과거 거주지(시간 역순)", lens=Lens.geo, tier=Tier.route,
        sink=Sink.attraction, types=_DEM,
        question="지금 집에 오시기 전에는 어디에 사셨나요? 그 전에는요?",
        probes=["가장 오래 산 집", "'옛날 집' 이라고 자주 말하는 곳", "동네 이름·랜드마크로 특정"],
        filled_when="과거 거주지 1곳 이상이 동네 수준으로 특정됨",
        why="치매 과거회귀 — '옛집으로 간다'는 배회의 대표 목적지.",
        keywords=["옛날 집", "예전 집", "고향", "살던 곳", "이사", "친정", "시골집"],
    ),
    SlotSpec(
        key="long_workplace", label="오래 다닌 직장·가게 위치", lens=Lens.geo, tier=Tier.route,
        sink=Sink.attraction, types=_DEM,
        question="오래 다니셨던 직장이나 운영하시던 가게가 있었다면 어느 동네였나요?",
        probes=["'출근한다'며 나가는지", "지명·업종으로 위치 좁히기"],
        filled_when="직장/가게 위치가 동네 수준으로 특정되거나 '없음'이 확인됨",
        why="자기를 현역으로 인식하면 '출근' 동선을 시뮬레이션해야 함.",
        keywords=["직장", "회사", "가게", "장사", "일터", "출근", "일하러"],
    ),
    SlotSpec(
        key="routine_destinations", label="혼자 자주 가는 곳·경로", lens=Lens.geo, tier=Tier.route,
        sink=Sink.attraction,
        question="혼자 나가실 때 주로 어디에 가시나요? (마트, 공원, 경로당, 놀이터 등) 가는 길도 정해져 있나요?",
        probes=["가장 자주 가는 1곳", "가는 방향·경유지", "산책 코스가 있으면 도는 방향"],
        filled_when="단골 목적지 1곳 이상 + 대략 경로/방향",
        why="route_following 전략의 핵심 앵커 — 익숙한 경로 우선 탐색.",
    ),
    SlotSpec(
        key="recurring_place", label="반복 언급하는 과거 장소", lens=Lens.geo, tier=Tier.route,
        sink=Sink.attraction,
        question="어린 시절·젊은 시절을 보낸 동네나, 옛 교회·절·자녀 학교처럼 자꾸 얘기하시는 옛 장소가 있나요?",
        probes=["'가고 싶다'고 말하는 곳", "지명으로 특정", "지금도 그 방향으로 가려 하는지"],
        filled_when="반복 언급 장소 1곳 이상이 특정되거나 '없음' 확인",
        why="정서적 끌림점 — attraction_weight 상향 대상.",
        keywords=["고향", "옛 교회", "옛 절", "자녀 학교", "젊은 시절"],
    ),
    SlotSpec(
        key="prior_missing", label="과거 실종·발견 이력", lens=Lens.geo, tier=Tier.route,
        sink=Sink.behavior,
        question="예전에도 혼자 나가셔서 못 돌아오신 적이 있나요? 그때는 어디서 발견되셨나요?",
        probes=["발견 장소를 동네 수준으로", "그때 가려던 목적지"],
        filled_when="과거 이력 유무 확인 + 있으면 발견 위치",
        why="개인 재현성 — 과거 발견지는 강력한 사전확률.",
    ),

    # ── Tier 2 · 행동분석 (성격 → 이동 스타일) ─────────────────────
    SlotSpec(
        key="lost_behavior", label="길 잃었을 때 행동", lens=Lens.behavior, tier=Tier.personality,
        sink=Sink.behavior,
        question="길을 잃으시면 보통 어떻게 하시나요? 한자리에 머무시는 편인가요, 계속 걸으시나요, 아니면 숨으시나요?",
        probes=["머무름/직진/배회/숨음 중 어디에 가까운지", "구체적 목격 사례"],
        filled_when="머무름·계속이동·숨음 중 우세 경향이 드러남",
        why="staying_put vs 이동 — 수색 반경 확장 속도를 좌우하는 최우선 변수.",
        keywords=["길 잃", "헤매", "제자리", "계속 걸", "돌아다", "숨", "주저앉"],
        risk=0.10,
    ),
    SlotSpec(
        key="stranger_response", label="낯선 사람 반응", lens=Lens.behavior, tier=Tier.personality,
        sink=Sink.behavior,
        question="낯선 사람이 말을 걸면 어떻게 반응하시나요? (경계 / 회피 / 친근하게)",
        probes=["도움을 청하는 편인지 혼자 해결하는 편인지"],
        filled_when="대인 반응 경향이 드러남",
        why="발견 가능성(POD)·구조 용이성 추정.",
    ),
    SlotSpec(
        key="crowd_pathing", label="사람·길 선호", lens=Lens.behavior, tier=Tier.personality,
        sink=Sink.behavior,
        question="사람 많은 곳을 좋아하시나요, 조용한 곳을 찾으시나요? 갈림길에선 큰길과 골목 중 어디로 가시나요?",
        probes=["번화가 vs 외진 곳", "익숙한 큰길 vs 지름길·골목"],
        filled_when="인파 선호 + 길 선택 경향이 드러남",
        why="이동 격자 가중(대로 vs 이면도로) 및 POD 지형 선택.",
    ),
    SlotSpec(
        key="follows_strangers", label="유인 취약성", lens=Lens.behavior, tier=Tier.personality,
        sink=Sink.behavior, types=_CHILD_ID,
        question="모르는 사람이 태워주거나 데려가겠다고 하면 따라갈 가능성이 있나요?",
        probes=["차량 동승 가능성", "경계심 수준"],
        filled_when="유인 취약성 정도가 드러남",
        why="비배회형 이탈(유인) 위험 — 예측 모델 분기.",
    ),
    SlotSpec(
        key="uniform_response", label="경찰·유니폼 반응", lens=Lens.behavior, tier=Tier.personality,
        sink=Sink.behavior, types=_CHILD_ID,
        question="경찰관이나 제복 입은 사람을 보면 다가가시나요, 피하시나요?",
        probes=["도움 요청 가능성 vs 회피"],
        filled_when="유니폼 반응 경향이 드러남",
        why="자폐·지적장애는 회피 성향이 잦아 구조 접근 전략을 바꿔야 함.",
    ),

    # ── Tier 2 · 임상 (인지·신체 → 반경·속도) ─────────────────────
    SlotSpec(
        key="mobility", label="보행 능력·제약", lens=Lens.clinical, tier=Tier.personality,
        sink=Sink.behavior,
        question="한 번에 얼마나 걸으실 수 있나요? 무릎·허리 등 걷는 데 불편한 곳이 있나요?",
        probes=["도보 지속 거리/시간", "보행 보조기구 여부"],
        filled_when="이동 반경 제약이 정성적으로라도 드러남",
        why="Koester 반경 lognormal 상한 보정.",
    ),
    SlotSpec(
        key="transit", label="대중교통 이용 능력", lens=Lens.clinical, tier=Tier.personality,
        sink=Sink.behavior,
        question="걸어서만 다니시나요, 버스·지하철도 타실 줄 아시나요? 교통카드를 갖고 계신가요?",
        probes=["대중교통 단독 이용 가능 여부", "교통카드 소지"],
        filled_when="도보 전용 vs 대중교통 가능이 구분됨",
        why="대중교통 가능 시 탐색 반경이 급격히 넓어짐(비연속 이동).",
    ),
    SlotSpec(
        key="medication", label="복약·건강 상태", lens=Lens.clinical, tier=Tier.personality,
        sink=Sink.behavior,
        question="복용 중인 약이 있나요? 거르면 어떤 증상이 나타나나요? 야간·추위·더위에 이동하기 어려운 상태인가요?",
        probes=["마지막 복용 시각", "결약 시 증상", "야간 이동 가능성", "체온 취약성"],
        filled_when="건강 제약(약·야간·기후) 중 유의미한 항목이 드러남",
        why="생존 골든타임·야간 이동 가능성 추정.",
    ),

    # ── Tier 3 · 임상 (치매 인지 상태) ─────────────────────────────
    SlotSpec(
        key="time_perception", label="시간·나이 인식", lens=Lens.clinical, tier=Tier.refine,
        sink=Sink.behavior, types=_DEM,
        question="어르신이 지금을 몇 년도로, 본인을 몇 살쯤으로 여기시나요? 스스로 젊은 시절로 여기며 행동하실 때가 있나요?",
        probes=["현재를 과거로 인식하는지", "그때의 역할(직장인·육아 등)"],
        filled_when="시간 인식 상태(현재 인식 / 특정 과거 회귀)가 드러남",
        why="30대 직장인으로 인식하면 '출근' 동선을 시뮬레이션 목적지로.",
        keywords=["젊은 시절", "옛날 사람", "몇 년도", "자기 나이", "현역", "착각", "예전으로"],
    ),
    SlotSpec(
        key="home_recognition", label="현재 집 인식", lens=Lens.clinical, tier=Tier.refine,
        sink=Sink.behavior, types=_DEM,
        question="지금 집을 '우리 집'으로 여기시나요, 아니면 '남의 집'이라며 나가려 하시나요?",
        probes=["집을 떠나려는 배회 동기 여부"],
        filled_when="현재 거주지 인식이 드러남",
        why="'집에 간다'며 옛집으로 향하는 배회의 촉발 여부.",
    ),

    # ── Tier 3 · 수색구조 (감각·심리 정밀화) ───────────────────────
    SlotSpec(
        key="sensory_attraction", label="강하게 끌리는 대상", lens=Lens.sar, tier=Tier.refine,
        sink=Sink.attraction, types=_CHILD_ID,
        question="물·기차·자동차·동물처럼 유독 집착해서 보러 가거나 만지려는 대상이 있나요?",
        probes=["물가(강·호수·수영장) 접근 성향 — 최우선 확인", "그 대상이 있는 근처 장소"],
        filled_when="집착 대상 유무 + 있으면 관련 장소",
        why="자폐 아동 물가 접근은 최우선 위험 — POA 상향 및 즉시 알림.",
        keywords=["물", "강", "호수", "수영장", "분수", "분수대", "기차", "지하철", "자동차", "동물", "집착", "뛰어가"],
        risk=0.15,
    ),
    SlotSpec(
        key="sensory_avoidance", label="자극 회피·숨는 성향", lens=Lens.sar, tier=Tier.refine,
        sink=Sink.behavior, types=_CHILD_ID,
        question="큰 소리·사이렌·붐비는 곳에서 어떻게 반응하나요? 좁은 구석이나 차 밑처럼 눈에 안 띄는 곳에 숨는 편인가요?",
        probes=["과잉자극 시 도주 vs 은신", "숨는 장소 유형"],
        filled_when="자극 반응(도주/은신) 경향이 드러남",
        why="은신형이면 근거리 정밀 수색, 도주형이면 반경 확장.",
    ),
    SlotSpec(
        key="name_response", label="호명·반응 자극", lens=Lens.sar, tier=Tier.refine,
        sink=Sink.behavior, types=_CHILD_ID,
        question="이름을 부르면 대답하나요? 특별히 반응하는 말·노래·캐릭터가 있나요?",
        probes=["호명 반응 여부", "유인 가능한 키워드"],
        filled_when="호명 반응 + 반응 자극 유무",
        why="현장 수색자의 호명·유인 전략 설계.",
    ),
    SlotSpec(
        key="cherished_person", label="그리워하는 사람·연관 장소", lens=Lens.sar, tier=Tier.refine,
        sink=Sink.attraction,
        question="특별히 그리워하거나 자주 찾으시는 분(옛 친구, 돌아가신 가족, 단골 가게 주인 등)이 있나요? 그분과 연관된 장소는 어디인가요?",
        probes=["'보러 간다'고 말하는 대상", "그 사람이 있는/있던 장소"],
        filled_when="그리움 대상 유무 + 있으면 연관 장소",
        why="'엄마 보러 간다' 류 목적지 단서 — attraction_point.",
    ),
    SlotSpec(
        key="repeated_phrases", label="반복하는 말", lens=Lens.sar, tier=Tier.refine,
        sink=Sink.behavior,
        question="'고향 가고 싶다', '일하러 간다'처럼 반복해서 하시는 말이 있나요?",
        probes=["그 말이 가리키는 목적지·방향"],
        filled_when="반복 발화 유무 + 있으면 함의된 목적지",
        why="발화는 배회 목적지의 직접 단서.",
    ),
]


# ── 조회 헬퍼 ────────────────────────────────────────────────────────

def slots_for(ptype: PersonaType) -> list[SlotSpec]:
    """해당 유형에 유효한 슬롯만, 질문 순서(tier→정의순)대로."""
    relevant = [s for s in SLOTS if ptype in s.types]
    return sorted(relevant, key=lambda s: s.tier.value)


def slot_by_key(key: str) -> SlotSpec | None:
    return next((s for s in SLOTS if s.key == key), None)
