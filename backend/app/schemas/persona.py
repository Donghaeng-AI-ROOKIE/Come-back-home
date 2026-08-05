"""Phase 0 — 보호자 사전 등록으로 만들어지는 페르소나."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import GeoPoint


class PersonaType(str, Enum):
    """대상 유형 — 치매 단독 스코프(2026-08-03 팀 결정).

    본선 방향 확정으로 대상을 치매 실종자 하나로 좁혔다. enum 을 유지하는 이유는
    저장 데이터·API 계약(`type: "dementia"`)의 하위호환과, 유형별 상수 테이블
    (Koester 프로파일·보행속도·피로배수)의 조회 키가 이미 이 타입이기 때문이다.
    """
    dementia = "dementia"                          # 치매 노인


class AttractionEvidence(str, Enum):
    """장소가 왜 중요한지의 근거 강도 — 추출 단계에서만 분류 가능(이후 복원 불가).

    자유 텍스트가 아니라 enum 3종으로 제한 — 제보 구체성을 상/중/하로만 받는
    기존 가드레일 패턴과 동일.
    """
    previous_missing_found = "previous_missing_found"  # 과거 실종 때 실제 발견된 곳
    caregiver_report = "caregiver_report"              # 보호자가 반복 지향을 직접 관찰
    mention_only = "mention_only"                      # 지나가듯 언급만


# evidence → 초기 weight 계수 (팀 결정 2026-07-21). 이 값은 "고정"이 아니라
# EXAONE 등급(상/중/하)과 **곱셈 병합**된다 — phase2.guardrail.sanitize_attraction_levels.
# 두 신호는 서로 다른 것을 본다: evidence 는 보호자 발화의 근거 강도(관측 사실),
# EXAONE 등급은 실종 상황·라벨 맥락의 지향 가능성(추론). 어느 한쪽 override 는
# 다른 쪽 정보를 버리므로 곱으로 합의시키고, 정규화·상한(ATTRACTION_CAP)이
# 한 장소의 독식을 막는다.
EVIDENCE_PRIOR_WEIGHTS: dict[str, float] = {
    "previous_missing_found": 0.9,   # 과거 실제 발견지 — 가장 강한 근거
    "caregiver_report": 0.5,         # 보호자 관찰
    "mention_only": 0.3,             # 언급만
}


def evidence_prior_weight(evidence) -> float:
    """evidence → 계수. 모르는 값은 최약 근거로 (coerce_evidence 와 같은 원칙)."""
    key = evidence.value if isinstance(evidence, AttractionEvidence) else str(evidence)
    return EVIDENCE_PRIOR_WEIGHTS.get(key, EVIDENCE_PRIOR_WEIGHTS["mention_only"])


class AttractionPoint(BaseModel):
    """끌림점 — 과거 직장, 옛집, 자주 가던 공원 등. Phase 2 prior의 핵심 입력."""
    label: str
    location: GeoPoint
    # 상대 중요도 — 명시하지 않으면 evidence 계수(EVIDENCE_PRIOR_WEIGHTS)로 채워진다
    # (아래 검증자). EXAONE 등급과 곱셈 병합돼 prior.attraction_weights 가 되고,
    # LLM 실패·스텁이면 이 값 단독으로 정규화된다.
    weight: float = 1.0
    precision: str = "unknown"   # 지오코딩 정밀도 poi>address>dong>approx — Phase 2 반경 보정용
    place_type: str = ""         # 장소 유형 (past_home/workplace/market 등 — LLM 추출 그대로)
    evidence: AttractionEvidence = AttractionEvidence.mention_only  # 기본값 = 최약 근거 (하위호환)
    # 어느 온보딩 슬롯에서 왔는지 — slots.SlotSpec.key 원문(예: "routine_destinations",
    # "autobiographical_destination_pull"). unfamiliarity 게이지 폴백 판단에 사용
    # (route_familiarity 컴파일러 대상 구분, app/phase2/gauges.py 참고).
    origin_slot: str = ""

    @model_validator(mode="before")
    @classmethod
    def _weight_from_evidence(cls, data):
        """weight 미지정 시 evidence 계수로 채운다 — 생성 경로마다 중복 매핑 금지.

        지오코딩(geo.geocode)·POI 매칭(geo.poi)·시드·저장 데이터 복원이 모두 이
        한 규칙을 지나게 해서 weight 와 evidence 가 어긋나는 상태를 만들지 않는다.
        명시된 weight(예: seed.py 의 수동 가중)는 그대로 존중한다.
        """
        if isinstance(data, dict) and data.get("weight") is None:
            return {**data, "weight": evidence_prior_weight(data.get("evidence"))}
        return data


class RouteFamiliarity(BaseModel):
    """경로·환경 익숙함 — 사람이 아니라 (사람, 경로) 쌍의 속성이라 axis_scores 와
    분리된 장소별 관계 변수 (축 방향 개정, 2026-07-17: app/phase0/axis_rubric.md 참고).
    컴파일러는 app/phase0/route_familiarity_compiler.py (PR #44)."""
    route: str
    score: float


class EnvResponse(BaseModel):
    """개인 환경 반응 — "물가만 보면 다가간다" 같은, 축 기준표에 없는 특성.

    축(axis_scores)은 성향 눈금이라 "무엇에" 반응하는지를 못 담는다. 이 목록이
    그 자리를 채운다 (PR #21 과제1 "페르소나 컴파일"). 컴파일러는
    app/phase0/env_response_compiler.py.

    feature 는 envlayer 카테고리 닫힌 어휘만 — 지어낸 대상은 가드레일이 버린다.
    """
    feature: str        # water | forest | park | market (envlayer 카테고리)
    direction: str      # "접근" | "회피"
    strength: float     # 0.1~0.9 — 등급을 코드가 매핑한 값


class Persona(BaseModel):
    id: str
    type: PersonaType
    name: str
    age: int
    home: GeoPoint
    attraction_points: list[AttractionPoint] = []
    behavior_notes: list[str] = []   # "해질녘에 옛 직장 방향으로 걷는 습관" 등 인터뷰 추출 사실
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
    # (route_familiarity_compiler 가 채움, RouteFamiliarity 참고). 원료가 되는 보호자 근거는
    # axis_evidence["route_environment_familiarity"]/axis_quotes["route_environment_familiarity"]
    # 에 그대로 쌓여 있음 — 필드 이름이 서로 달라 헷갈리지 않도록 명시.
    route_familiarity: list[RouteFamiliarity] = []
    # 개인 환경 반응 — behavior_notes 자유 텍스트에서 컴파일 (EnvResponse 참고).
    # 축은 "얼마나" 반응하는지의 눈금이라 "무엇에" 반응하는지를 못 담는다.
    env_responses: list[EnvResponse] = []
    # 길 잃음/과거 배회 행동 경향 — behavior_compiler 가 채움.
    # "stay"|"move"|"backtrack"|"hide"|None. lost_behavior + dementia_wandering_pattern
    # 두 행동 슬롯을 우선순위(과거 실종이력 > 일반 경향)로 해소한 단일 신호.
    # Phase2 guardrail 이 strategy_probs 방향 틸트로 소비한다.
    behavior_tendency: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)

    # 온보딩 없는 신고 흐름(2026-08) — 어느 보호자 소유인지. 로그인 시스템이 아직
    # 없어 명시적 값으로 받는다(persona_id/case_id 등 기존 식별자들과 같은 전제).
    guardian_id: str = ""
    # supplement/update 로 같은 persona 에 병합 저장할 때마다 1씩 증가.
    # 동시수정 완전방지(버전 충돌 거부)는 하지 않음 — 최소한의 변경 흔적만 남긴다.
    version: int = 0
    # 지금까지 이 persona 에 실제로 답변된 슬롯 tier 집합(SlotSpec.tier.value 값,
    # 1=route/2=capacity/3=refine). 신고 전 미니챗이 Tier1만 채우면 [1]만 들어가고,
    # 이후 보완챗이 나머지를 채우면 [1,2,3]이 된다 — persona 상태(none/partial/
    # complete) 판정의 유일한 근거.
    completed_tiers: list[int] = []


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
    draft_behaviors: list[str] = []
    # 어느 슬롯을 겨냥했을 때 나온 노트인지 — {slot_key: [노트...]}.
    # finalize 에서 슬롯의 axis_field 로 묶어 Persona.axis_evidence 가 된다.
    slot_notes: dict[str, list[str]] = {}
    # 근거가 나온 보호자 원발화 원문 — {slot_key: [발화...]}. 노트는 Mi:dm 재서술이라
    # 정보가 깎이므로 원문을 병행 보존 → finalize 에서 Persona.axis_quotes 가 된다.
    slot_quotes: dict[str, list[str]] = {}
    awaiting_confirmation: bool = False   # 요약 확인("이게 맞나요?") 대기 중
    asked_more_places: bool = False       # 요약 전 '추가 장소 스윕' 1회 보장용 플래그
    # 지역 표기 없는 끌림점의 주소 되묻기 — 없으면 지오코딩이 실패해 그 장소가
    # 페르소나에서 통째로 사라진다(라이브 실측 2026-07-21: "예전에 살던 집").
    pending_area_label: str | None = None  # 지금 주소를 되묻고 있는 장소 라벨
    asked_area_labels: list[str] = []      # 이미 되물은 라벨 (장소당 1회만)
    # 하위 항목(SlotSpec.probes) 꼬리질문을 이미 던진 슬롯 — 슬롯당 1회 보장용.
    # Mi:dm 이 얕은 답에도 slot_filled=true 를 내서 probes 가 한 번도 안 쓰이던 실측.
    probed_keys: list[str] = []
    # Mi:dm 호출 실패 가시화 — 폴백(빈 추출·씨앗 질문)으로 인터뷰는 계속 진행하되,
    # 장애가 "이상한 반복 인터뷰"로만 체감되지 않게 API 응답에 그대로 노출한다.
    llm_call_failures: int = 0            # 이 세션에서 Mi:dm 호출 실패 누적
    llm_degraded: bool = False            # 실패가 1회라도 있었나 — UI 배지용
    done: bool = False
    persona_id: str | None = None
    # 개인정보 파기 — 미완료인 채 방치된 세션(draft 에 이름·주소 초안이 남는다)을
    # TTL 로 쓸어내기 위한 마지막 활동 시각 (privacy/lifecycle.purge_expired)
    last_active_at: datetime = Field(default_factory=datetime.now)

    # ── 온보딩 없는 신고 흐름(2026-08) — 순수 추가 필드, 전부 기본값이면 기존
    #    동작과 완전히 동일하다. ────────────────────────────────────────
    # "create"(신규 등록) | "supplement"(보완챗, 나머지 tier만). 이미 등록된 정보를
    # "고치는" 것은 챗봇 재질문이 아니라 PersonaDetailScreen(구조화 수정 화면,
    # PATCH /phase0/personas/{id})이 담당한다(2026-08-06 팀 통합 결정 — 챗봇
    # update 모드는 만들지 않기로 함).
    # create 가 기본값 — 지금 하나뿐이던 온보딩 흐름과 동일 취급.
    mode: str = "create"
    # 이 세션이 물을 슬롯의 tier 집합. None = 전체(기존 동작 그대로).
    # 신고 전 미니챗은 [1](Tier.route)만, 보완챗은 [2,3]만 넣는다.
    target_tiers: list[int] | None = None
    # 어느 보호자의 세션인지 — Persona.guardian_id 와 같은 이유로 명시값.
    guardian_id: str = ""
    # True 면 요약 확인("이게 맞나요?") 게이트를 건너뛰고 마지막 답변 직후 바로
    # finalize_persona 를 호출한다 — 신고 전 긴급 미니챗 전용(왕복 한 번도
    # 아낀다). 그 외 모든 흐름(create/scope=all, supplement)은 여전히 확인
    # 게이트를 거친다.
    skip_confirmation: bool = False
