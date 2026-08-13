from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel


class GeoPoint(BaseModel):
    lat: float
    lng: float


def _to_local_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone().replace(tzinfo=None)


# 프로젝트 시각 컨벤션은 naive 로컬 시각. 브라우저 toISOString() 의 'Z'(UTC) 나
# '+09:00' 붙은 시각이 API 로 들어오면 로컬로 변환 후 tz 를 떼어,
# naive 시각과의 뺄셈(now - lkp_time, seen_at <= since 등) TypeError 를 입구에서 차단.
LocalNaiveDT = Annotated[datetime, AfterValidator(_to_local_naive)]
