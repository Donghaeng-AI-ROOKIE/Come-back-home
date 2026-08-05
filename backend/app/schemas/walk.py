"""안심 산책 — 시민 참여 기록.

수색 파이프라인(Phase 0~3)과 목적이 다르다. 저쪽은 "실종자가 어디 있는가"를
계산하고, 이쪽은 "시민이 알림을 받을 준비가 되어 있는가"를 유지한다. 알림은
받을 사람이 그 자리에 있어야 의미가 있고, 평상시 앱을 열 이유가 없으면 알림
시점에 앱이 지워져 있다. 산책 기록은 그 이유를 만드는 장치다.

**개인정보 경계**: 산책 경로 좌표는 저장하지 않는다. 시작·종료 시각과 거리
합계만 남긴다. 경로를 남기면 "시민의 상시 위치 이력"이 되어 수색 목적을 넘고,
Phase 3 알림에도 경로가 아니라 현재 위치만 필요하다.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class WalkSession(BaseModel):
    """산책 1회. 진행 중이면 ended_at 이 None."""
    id: str
    user_id: str
    started_at: datetime
    ended_at: datetime | None = None
    distance_km: float = 0.0
    duration_min: float = 0.0
    # 표시용 지역명(예: "망원 한강공원 일대"). 좌표가 아니라 라벨만 — 위 경계 참조.
    area_label: str = ""


class Badge(BaseModel):
    """획득 가능한 배지 1종. earned=False 면 앱이 흐리게 표시한다."""
    id: str
    label: str
    icon: str
    earned: bool = False
    earned_at: datetime | None = None


class WalkStats(BaseModel):
    """마이페이지 집계 — 앱의 '내 안심 기록' 화면이 이 한 덩어리로 그린다.

    화면이 필요로 하는 것을 서버가 계산해서 준다. 앱에서 레벨 규칙을 계산하면
    규칙을 바꿀 때마다 앱 배포가 필요해지고, 기기마다 다른 값이 보일 수 있다.
    """
    user_id: str
    total_km: float
    month_km: float                    # 이번 달 누적 (홈 상단 카드)
    walk_count: int
    tip_count: int                     # 실종자 제보 건수
    level: int
    level_label: str                   # 예: "실버 워커"
    next_level_km: float               # 다음 레벨까지 남은 거리
    badges: list[Badge] = Field(default_factory=list)
    recent: list[WalkSession] = Field(default_factory=list)
