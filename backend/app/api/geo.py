"""지오 API — 좌표를 사람이 읽는 장소 이름으로 바꾼다.

보호자 제보 알림이 제보를 위치별로 묶어 보여주는데, 묶음 제목이 좌표면 보호자가
어디인지 알 수 없다. 묶음은 앱이 만들고(같은 골목 제보를 한 카드로), 이름만
서버가 붙인다 — 외부 지오코딩 키·이용약관(초당 1건)·캐시를 앱마다 다루게 하는
것보다 서버 한 곳이 낫다.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.geo import reverse
from app.schemas.common import GeoPoint

router = APIRouter(prefix="/geo", tags=["지오 — 좌표 ↔ 장소명"])


class LabelsIn(BaseModel):
    points: list[GeoPoint]


class LabelsOut(BaseModel):
    labels: list[str]


@router.post("/labels", response_model=LabelsOut)
def labels(body: LabelsIn) -> LabelsOut:
    """좌표 목록 → 장소명 목록 (입력과 같은 순서).

    이름을 못 찾으면 그 자리는 좌표 문자열이 된다 — 목록이 통째로 실패하지
    않게 하려는 것이다(제보를 못 보는 것이 이름을 못 보는 것보다 나쁘다).
    """
    return LabelsOut(labels=reverse.labels_for(body.points))
