"""E2E 대시보드용 디버그 트레이스 스키마.

예측 파이프라인은 원래 집계 POA 만 반환한다 — 대시보드가 "왜 이 확률지도가
나왔는가"를 보여주려면 워커 궤적과 EXAONE 호출 이벤트를 별도 채널로 수집해야
한다. 이 트레이스는 시연·디버그 전용이며 예측 결과 자체에는 영향을 주지 않는다
(수집만 하고 로직 분기 없음).
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import GeoPoint
from app.schemas.prediction import PredictionResult, PriorParams

# 전 궤적을 다 담으면 500 워커 × 최대 300 스텝이라 응답이 수 MB 로 커진다.
# 지도에 겹쳐 그릴 수 있는 수준(앞쪽 워커 표본)만 경로를 기록하고,
# 마음 이벤트(EXAONE 트리거)는 전 워커에서 수집한다 — 점만 찍으면 되므로 싸다.
MAX_TRACED_PATHS = 80


class MindEvent(BaseModel):
    """워커 1명의 마음 재해석(H·A 트리거) 이벤트 — 지도 위 점 + 호버 툴팁 재료."""
    walker_idx: int
    step: int
    location: GeoPoint                 # 트리거가 발동한 도로망 노드 좌표
    trigger: str                       # 게이지 자연어 리포트 (EXAONE 에 준 [현재 상태])
    source: str                        # "exaone"(실호출) | "pool"(풀 표집) | "stub" | "heuristic"
    status: str                        # 재해석된 마음 상태
    confusion: float
    goal: str | None = None            # 목표 전환된 끌림점 라벨 (없으면 None)
    prompt: str | None = None          # 실호출일 때만 — EXAONE 입력 전문
    response_raw: str | None = None    # 실호출일 때만 — EXAONE 응답 원문


class WalkerTrace(BaseModel):
    """워커 1명의 보행 궤적 (앞쪽 MAX_TRACED_PATHS 명만 기록)."""
    walker_idx: int
    strategy: str
    path: list[list[float]]            # [[lat, lng], ...] 스텝별 노드 좌표
    mind_fired: bool = False           # 이 워커에서 마음 재해석이 발동했는가


class SimTrace:
    """run_monte_carlo 에 넘기는 수집기 — 예측 1회 스코프."""

    def __init__(self, max_paths: int = MAX_TRACED_PATHS) -> None:
        self.max_paths = max_paths
        self.walkers: list[WalkerTrace] = []
        self.mind_events: list[MindEvent] = []

    def trace_path(self, walker_idx: int) -> bool:
        return walker_idx < self.max_paths


class PredictionDebug(BaseModel):
    """예측 1회의 디버그 번들 — storage.debug_traces 에 case_id 로 저장."""
    case_id: str
    generated_at: datetime = Field(default_factory=datetime.now)
    seed: int | None = None
    roadnet: bool = False              # 도로망 그래프 위를 걸었는가 (False = 연속 공간 폴백)
    exaone_stub: bool = True           # EXAONE 이 스텁 모드였는가
    prior_prompt: str | None = None    # generate_prior 실호출 입력 (스텁이면 None)
    prior_response_raw: str | None = None
    walkers: list[WalkerTrace] = []
    mind_events: list[MindEvent] = []
    result: PredictionResult | None = None   # 4층 POA — 대시보드 레이어 전환용

    @property
    def prior(self) -> PriorParams | None:
        return self.result.prior if self.result else None
