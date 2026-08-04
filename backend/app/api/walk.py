"""안심 산책 API — 시민 참여 기록·집계.

Phase 0~3(수색 파이프라인)과 분리된 도메인이다. 케이스가 없어도 동작해야 한다 —
평상시에 시민이 앱을 여는 이유가 이쪽이고, 실종 사건은 드물게 일어난다.

인증은 아직 없다. `user_id` 를 그대로 받되 기본값을 두어 데모가 흐른다.
실서비스에서는 토큰의 subject 로 대체할 자리이고, 그 전까지는 남의 user_id 를
넣으면 남의 기록이 보인다 — 공개 배포 전 반드시 막아야 한다.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import storage
from app.schemas.walk import WalkSession, WalkStats
from app.walk import stats as walk_stats

router = APIRouter(prefix="/walk", tags=["안심 산책 — 시민 참여"])

DEMO_USER_ID = "demo-citizen"


class WalkStartIn(BaseModel):
    user_id: str = DEMO_USER_ID
    area_label: str = ""            # 표시용 지역명. 좌표는 받지 않는다(schemas/walk.py 경계).


class WalkEndIn(BaseModel):
    """거리·시간은 앱이 측정해 보낸다.

    서버가 경로 좌표로 재계산하지 않는 것은 의도된 설계다 — 재계산하려면 경로를
    받아 저장해야 하고, 그 순간 시민의 상시 위치 이력이 된다. 거리 값을 앱이
    부풀릴 수 있다는 한계는 받아들인다(수색 정확도가 아니라 참여 지표다).
    """
    distance_km: float = Field(ge=0, le=200)     # 하루 200km 초과는 도보가 아니다
    duration_min: float = Field(ge=0, le=1440)


def _sessions_of(user_id: str) -> list[WalkSession]:
    return [s for s in storage.walk_sessions.list() if s.user_id == user_id]


@router.post("/sessions", response_model=WalkSession)
def start_walk(body: WalkStartIn):
    """산책 시작. 진행 중 세션이 이미 있으면 그것을 그대로 돌려준다 —
    앱이 화면 복귀 때 재호출해도 세션이 중복 생성되지 않게 한다."""
    for s in _sessions_of(body.user_id):
        if s.ended_at is None:
            return s
    session = WalkSession(
        id=storage.new_id(),
        user_id=body.user_id,
        started_at=datetime.now(),
        area_label=body.area_label,
    )
    return storage.walk_sessions.save(session.id, session)


@router.post("/sessions/{session_id}/end", response_model=WalkSession)
def end_walk(session_id: str, body: WalkEndIn):
    session = storage.walk_sessions.get(session_id)
    if session is None:
        raise HTTPException(404, "산책 세션 없음")
    if session.ended_at is not None:
        raise HTTPException(409, "이미 종료된 산책")
    session.ended_at = datetime.now()
    session.distance_km = body.distance_km
    session.duration_min = body.duration_min
    return storage.walk_sessions.save(session.id, session)


@router.get("/sessions/active", response_model=WalkSession | None)
def active_walk(user_id: str = DEMO_USER_ID):
    """앱 재시작 시 진행 중이던 산책을 복원한다. 없으면 null."""
    for s in _sessions_of(user_id):
        if s.ended_at is None:
            return s
    return None


@router.get("/stats", response_model=WalkStats)
def get_stats(user_id: str = DEMO_USER_ID):
    """마이페이지·홈 상단 카드가 이 하나로 그려진다 (레벨 규칙은 walk/stats.py)."""
    return walk_stats.aggregate(
        user_id, _sessions_of(user_id),
        tip_count=storage.walk_tip_counts.get(user_id) or 0)
