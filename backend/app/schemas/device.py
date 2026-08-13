"""시민 기기 등록 — 푸시 발송 대상.

## 이 엔티티가 개인정보 지형을 바꾼다

푸시를 보내려면 서버가 기기 토큰을 영속 저장해야 한다 — 토큰 없이는 발송 자체가
불가능하므로 회피할 수 없다. 즉 푸시를 도입하는 순간 서버는 **지속적 기기 식별자**를
갖는다. 남는 선택지는 *토큰에 무엇을 연결하느냐*뿐이다.

## 위치를 받기로 한 결정 (2026-08-05)

원래 설계는 "서버는 대상 셀 목록만 뿌리고 폰이 판정"(온디바이스 지오펜싱)이었다.
그러면 서버가 위치를 전혀 몰라도 됐지만, **앱이 완전히 종료돼 있으면 알림이 아예
전달되지 않는다** — 데이터 전용 푸시는 앱을 깨워야 하는데 국내 제조사 배터리
최적화가 백그라운드를 공격적으로 종료한다. 골든타임 알림에서 "올 수도 안 올 수도"는
실패라 그 설계를 포기했다.

대신 **정밀도를 최소로 깎는다.**

  ✅ cell_res7   ≈5km² 칸 하나. 예측 구역(실측 17km²)을 구분하기엔 충분하고
                 개인 위치는 안 드러난다. **폰이 좌표를 res7 로 바꿔서 보낸다** —
                 정밀 좌표는 기기를 떠난 적이 없다(서버를 믿을 필요가 없는 구조).
  ✅ engagement  참여도 등급 3값. 사람마다 다른 확률 문턱을 서버가 적용하는 데 쓴다.
                 원시 이력(열람·제보 횟수)은 여전히 폰에만 있다.

  ❌ 좌표·res9 셀    목적에 필요 이상. 판정은 거의 안 바뀌고 궤적만 남는다
  ❌ **위치 이력**   현재 값만 덮어쓴다. 이력을 남기는 순간 해상도와 무관하게
                     이동 궤적이 되고, 거친 셀을 쓰는 의미가 사라진다
  ❌ 제보 이력       익명 제보 약속이 깨진다
  ❌ 계정·연락처     시민 사용자 인증 자체가 없다

발송 기록(sent_at)만 예외로 남는데, 이건 **서버가 자기가 한 일을 아는 것**이라
추가 수집이 0이다. 알림 피로도 예산이 이 기록만으로 성립하도록 설계한 이유다.
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
    # iOS 확장 시 필요. 값이 android 하나뿐인 지금 넣어두는 이유: 나중에 섞이면
    # 어느 기기가 무엇인지 구분할 방법이 없고, 이미 등록된 것은 되돌아가 채울 수 없다.
    platform: Platform
    registered_at: datetime

    # ── 발송 대상 판정용 ────────────────────────────────────
    #: 현재 위치의 H3 res7 셀. **현재 값만 — 이력을 남기지 않는다.**
    #: None 이면 위치를 아직 못 받은 것(그 기기는 타겟 발송에서 제외된다).
    cell_res7: str | None = None
    #: 웹 푸시 구독(endpoint·keys). platform=web 일 때만 채워진다.
    #: 브라우저가 스스로 만들어 준 주소이며 개인 식별정보가 아니다.
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
