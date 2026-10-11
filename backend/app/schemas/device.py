"""시민 기기 등록과 현재 알림 위치.

서버 설정의 H3 res7/8/9 중 한 해상도로 변환한 현재 셀 하나를 저장한다.
res9는 기존 res7보다 작은 위치 구역을 드러낸다. 면적이 줄어드는 알림 대상과
일치시키기 위한 변경이며, 좌표를 보내지 않는다고 위치 정보가 없어지는 것은 아니다.
현재 셀만 덮어쓰고 이동 이력·원시 좌표·제보 이력을 연결하지 않는다.
새 fine 셀 및 인증 웹 위치는 5분이 지나면 대상 판정에서 제외한다.
기존 res7 클라이언트는 교차 영역 근사로 지원하며, fine 위치를 복원하지 않는다.
구독/토큰과 소유 계정은 등록 해제로 지울 수 있다. 발송 시각은 24시간 창으로 보존한다.
"""

from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field


class Platform(str, Enum):
    android = "android"
    ios = "ios"
    # 홈 화면에 설치한 웹앱. 주소가 Expo 토큰이 아니라 브라우저 구독이라
    # 발송 경로가 다르다(phase3/webpush.py).
    web = "web"


class Engagement(str, Enum):
    """참여도 등급 — 폰이 계산해서 알려준다(원시 이력은 안 보낸다).

    프론트 `utils/alertBudget.ts` 의 engagementLevel() 과 값이 같아야 한다.
    """
    high = "high"
    normal = "normal"
    low = "low"


class Device(BaseModel):
    """등록된 시민 기기 하나."""

    # Expo Push 토큰 (ExponentPushToken[...] 형식). 이것이 곧 식별자이자 주소다.
    token: str
    owner_id: str = ""  # cloud subscription ownership, derived from auth.uid()
    location_updated_at: datetime | None = None
    entry_sent_at: dict[str, datetime] = Field(default_factory=dict)
    # iOS 확장 시 필요. 값이 android 하나뿐인 지금 넣어두는 이유: 나중에 섞이면
    # 어느 기기가 무엇인지 구분할 방법이 없고, 이미 등록된 것은 되돌아가 채울 수 없다.
    platform: Platform
    registered_at: datetime

    # ── 발송 대상 판정용 ────────────────────────────────────
    #: 현재 위치의 H3 res7 셀. **현재 값만 — 이력을 남기지 않는다.**
    #: None 이면 위치를 아직 못 받은 것(그 기기는 타겟 발송에서 제외된다).
    cell_res7: str | None = None
    #: Current negotiated res7/8/9 cell. Only this current value is retained;
    #: cell_res7 is populated only for the res7 compatibility path.
    location_cell: str | None = None
    #: 웹 푸시 구독(endpoint·keys). platform=web 일 때만 채워진다.
    #: 브라우저별 지속 식별자. 외부 공개·로그 출력을 금지한다.
    web_subscription: dict | None = None
    #: 참여도 등급. 모르면 normal 로 본다(기본 문턱).
    engagement: Engagement = Engagement.normal

    # ── 피로도 예산 입력 ────────────────────────────────────
    last_sent_at: datetime | None = None
    #: 발송 시각 이력 — 24시간 창으로 잘라 쓴다. 무한히 쌓이지 않도록
    #: 기록 시점에 창 밖을 버린다(record_sent 참고).
    sent_at: list[datetime] = Field(default_factory=list)

    def sent_count_24h(self, now: datetime | None = None) -> int:
        """최근 24시간 발송 건수 — 알림 피로도 예산의 입력."""
        now = now or datetime.now()
        cutoff = now - timedelta(hours=24)
        return sum(1 for t in self.sent_at if t >= cutoff)
