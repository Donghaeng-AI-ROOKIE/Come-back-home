"""Phase 0 — 보호자 사전 등록으로 만들어지는 페르소나."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.common import GeoPoint


class PersonaType(str, Enum):
    dementia = "dementia"                          # 치매 노인
    intellectual_disability = "intellectual_disability"  # 지적장애인


class AttractionEvidence(str, Enum):
    """장소가 왜 중요한지의 근거 강도 — 추출 단계에서만 분류 가능(이후 복원 불가).

    자유 텍스트가 아니라 enum 3종으로 제한 — 제보 구체성을 상/중/하로만 받는
    기존 가드레일 패턴과 동일. evidence → 초기 weight 계수는 팀 회의 미결
    (제안: 발견지 0.9 / 관찰 0.5 / 언급 0.3) — 결정 전까지 태그만 저장·전달한다.
    """
    previous_missing_found = "previous_missing_found"  # 과거 실종 때 실제 발견된 곳
    caregiver_report = "caregiver_report"              # 보호자가 반복 지향을 직접 관찰
    mention_only = "mention_only"                      # 지나가듯 언급만


class AttractionPoint(BaseModel):
    """끌림점 — 과거 직장, 옛집, 자주 가던 공원 등. Phase 2 prior의 핵심 입력."""
    label: str
    location: GeoPoint
    weight: float = 1.0   # 상대 중요도 (EXAONE prior 생성 시 재조정됨)
    precision: str = "unknown"   # 지오코딩 정밀도 poi>address>dong>approx — Phase 2 반경 보정용
    place_type: str = ""         # 장소 유형 (past_home/workplace/market 등 — LLM 추출 그대로)
    evidence: AttractionEvidence = AttractionEvidence.mention_only  # 기본값 = 최약 근거 (하위호환)
    # 어느 온보딩 슬롯에서 왔는지 — slots.SlotSpec.key 원문(예: "routine_destinations",
    # "autobiographical_destination_pull"). unfamiliarity 게이지 폴백 판단에 사용
    # (route_familiarity 컴파일러 대상 구분, app/phase2/gauges.py 참고).
    origin_slot: str = ""


class PreferredTarget(BaseModel):
    """발달장애 선호 대상 중 좌표로 특정되지 않는 카테고리 선호 — '지하철', '자동문' 등.

    좌표가 특정되는 대상(단골 역)은 attraction_points 경로로 간다. 카테고리 선호는
    지오코딩이 불가능하므로 여기 저장했다가 Phase 2 에서 LKP 주변의 해당 카테고리
    POI 만 매칭한다 (회의록: 모든 지하철역 일괄 가중치 금지, 등록된 대상만 반영).
    """
    label: str            # "지하철", "자동문", "편의점" 등 보호자 표현
    target_type: str = "" # transport/facility/sensory/person/activity (LLM 분류, 자유)
    evidence: AttractionEvidence = AttractionEvidence.mention_only


class RouteFamiliarity(BaseModel):
    """경로·환경 익숙함 — 사람이 아니라 (사람, 경로) 쌍의 속성이라 axis_scores 와
    분리된 장소별 관계 변수 (축 방향 개정, 2026-07-17: app/phase0/axis_rubric.md 참고).
    컴파일러(보호자 발화 → 이 목록) 는 미구현 — 스키마만 선반영, 백로그."""
    route: str
    score: float


class Persona(BaseModel):
    id: str
    type: PersonaType
    name: str
    age: int
    home: GeoPoint
    attraction_points: list[AttractionPoint] = []
    behavior_notes: list[str] = []   # "해질녘에 옛 직장 방향으로 걷는 습관" 등 인터뷰 추출 사실
    # 카테고리 선호 (발달장애) — 좌표화 불가 대상. Phase 2 가 LKP 주변 POI 매칭에 사용.
    preferred_targets: list[PreferredTarget] = []
    # 축별 근거 — {축 DB 필드명(slots.SlotSpec.axis_field): 관찰 사실 노트}.
    # 인터뷰가 수집한 사실을 몸축·마음축·행동축 필드로 묶어둔 것. 이후 축 점수
    # (0.1~0.9) 컴파일 단계의 입력이 된다. behavior_notes 의 부분집합 재구성이라
    # 기존 소비자(Phase 2 게이지 등)에는 영향 없음.
    axis_evidence: dict[str, list[str]] = {}
    # 축별 보호자 원발화 — Mi:dm 재서술 노트(axis_evidence)의 정보 손실을 우회하는
    # 채점 1차 근거 (골드셋 실험: 원문 quote 검증이 환각 필터로 작동).
    axis_quotes: dict[str, list[str]] = {}
    # 축 점수(0.1~0.9) — phase0.axis_scoring 이 채움. F(판정 불가)·근거 없음 축은
    # 키 자체가 없다 → Phase 2 는 없는 축을 유형 기본 prior 로 폴백.
    # 리포트의 축별 F·quote 실패 카운트 = 앞단 추출 품질 감시 지표.
    axis_scores: dict[str, float] = {}
    axis_scoring_report: dict = {}
    # 경로별 익숙함 — route_environment_familiarity 는 축이 아니라 관계 변수라 여기 분리
    # (미구현 컴파일러 대상, RouteFamiliarity 참고). 원료가 되는 보호자 근거는
    # axis_evidence["route_environment_familiarity"]/axis_quotes["route_environment_familiarity"]
    # 에 그대로 쌓여 있음 — 필드 이름이 서로 달라 헷갈리지 않도록 명시.
    route_familiarity: list[RouteFamiliarity] = []
    created_at: datetime = Field(default_factory=datetime.now)


class InterviewSession(BaseModel):
    """Mi:dm 챗봇 인터뷰 세션 — 종료 시 Persona 로 변환된다.

    적응형 엘리시테이션 상태를 함께 들고 다닌다: 검색이 다음 슬롯을 고르고
    Mi:dm 이 추출/문장화하며 채워진 슬롯·누적 추출을 여기 쌓는다.
    """
    id: str
    guardian_name: str
    persona_type: PersonaType | None = None   # 첫 답에서 확정
    messages: list[dict] = []        # {"role": "assistant"|"user", "text": ...}
    filled_keys: list[str] = []      # 충족된 슬롯 key
    asked_counts: dict[str, int] = {}    # 물었지만 안 채워진 슬롯 횟수(반복 억제)
    prev_target_key: str | None = None   # 직전에 겨냥한 슬롯 (추출 대상)
    # 누적 추출 (종료 시 Persona 로 변환)
    draft_fields: dict = {}                       # name/age/home
    draft_attractions: list[dict] = []            # [{"label","area_text","place_type","evidence"}]
    draft_preferred: list[dict] = []              # [{"label","target_type","evidence"}] 좌표화 불가 선호
    draft_behaviors: list[str] = []
    # 어느 슬롯을 겨냥했을 때 나온 노트인지 — {slot_key: [노트...]}.
    # finalize 에서 슬롯의 axis_field 로 묶어 Persona.axis_evidence 가 된다.
    slot_notes: dict[str, list[str]] = {}
    # 근거가 나온 보호자 원발화 원문 — {slot_key: [발화...]}. 노트는 Mi:dm 재서술이라
    # 정보가 깎이므로 원문을 병행 보존 → finalize 에서 Persona.axis_quotes 가 된다.
    slot_quotes: dict[str, list[str]] = {}
    awaiting_confirmation: bool = False   # 요약 확인("이게 맞나요?") 대기 중
    asked_more_places: bool = False       # 요약 전 '추가 장소 스윕' 1회 보장용 플래그
    # Mi:dm 호출 실패 가시화 — 폴백(빈 추출·씨앗 질문)으로 인터뷰는 계속 진행하되,
    # 장애가 "이상한 반복 인터뷰"로만 체감되지 않게 API 응답에 그대로 노출한다.
    llm_call_failures: int = 0            # 이 세션에서 Mi:dm 호출 실패 누적
    llm_degraded: bool = False            # 실패가 1회라도 있었나 — UI 배지용
    done: bool = False
    persona_id: str | None = None
    # 개인정보 파기 — 미완료인 채 방치된 세션(draft 에 이름·주소 초안이 남는다)을
    # TTL 로 쓸어내기 위한 마지막 활동 시각 (privacy/lifecycle.purge_expired)
    last_active_at: datetime = Field(default_factory=datetime.now)
