"""Phase 2 — prior, 마음 상태, POA 분포."""

from datetime import datetime

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


class MindState(BaseModel):
    """마음 예측 — EXAONE이 추론하는 현재 심리 상태. 바뀔 때만 LLM 재호출."""
    status: str = "이동 중"                   # 예: "쉬는 중", "귀가 시도", "갑자기 가고 싶은 곳 생김"
    confusion: float = 0.5                    # 0(명료)~1(극심한 혼란)
    changed: bool = False


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
    poa_combined: POA                         # α-pool 통합 + POD 적용 후
