"""Phase 2 — prior, 마음 상태, POA 분포."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LognormalParams(BaseModel):
    """Koester 이동 거리 분포 (km). 프로파일·경과시간에 따라 스케일."""
    mu: float
    sigma: float


class PriorParams(BaseModel):
    """EXAONE Top-down 출력 — 좌표가 아니라 가중치·파라미터만 (LLM calibration 한계 반영)."""
    strategy_probs: dict[str, float]          # Hashimoto 6전략 확률 (합=1)
    attraction_weights: dict[str, float]      # 끌림점 label → 가중치 (합=1, 없으면 빈 dict)
    radius_lognormal: LognormalParams
    reasoning: str = ""                       # Few-shot CoT 추론 근거
    # prior 가 실제로 어디서 나왔는지. **폴백은 조용히 일어난다** — 호출이 실패해도
    # 예측은 통계 기본값으로 계속 돌기 때문에, 화면만 보면 개인화가 빠진 것을 모른다
    # (2026-08-05 실측: 첫 호출 30초 타임아웃 → 전 구간 통계값으로 예측 완료).
    # 이 필드가 그 구분을 API 계약으로 올려 앱이 배너로 알릴 수 있게 한다.
    #   "exaone"   — 실호출 성공, 개인 맥락 반영
    #   "fallback" — 호출·파싱 실패로 프로파일 통계 기본값 (개인화 없음)
    #   "stub"     — 키 미설정으로 애초에 호출하지 않음 (개인화 없음)
    source: Literal["exaone", "fallback", "stub"] = "exaone"
    # 폴백 사유(예외 타입). source != "exaone" 일 때만 채워진다 — 운영 진단용.
    fallback_reason: str = ""


class MindState(BaseModel):
    """마음 예측 — EXAONE이 추론하는 현재 심리 상태. 바뀔 때만 LLM 재호출."""
    status: str = "이동 중"                   # 예: "쉬는 중", "귀가 시도", "갑자기 가고 싶은 곳 생김"
    confusion: float = 0.5                    # 0(명료)~1(극심한 혼란)
    changed: bool = False
    # 계약 v2 의 닫힌 행동 어휘 (guardrail.BEHAVIORS). 빈 문자열 = 미판정.
    # 보행 반영은 settings.mind_behavior_enabled 가 켜졌을 때만 — 기본은 기록 전용이다.
    behavior: str = ""


class POA(BaseModel):
    """Probability of Area — H3 셀별 확률 분포 (합=1)."""
    cells: dict[str, float]
    source: str                               # "topdown" | "bottomup" | "statistical" | "combined" | "updated"
    generated_at: datetime = Field(default_factory=datetime.now)


class PredictionResult(BaseModel):
    case_id: str
    prior: PriorParams
    poa_topdown: POA
    poa_bottomup: POA
    poa_statistical: POA
    poa_combined: POA                         # α-pool 통합 결과 (최종)
