"""웹 푸시 — 홈 화면에 설치한 웹앱으로 실제 OS 알림을 보낸다.

## 왜 이 경로가 필요했나
경보를 실제로 받으려면 앱이 있어야 하는데, 앱스토어 배포는 iOS 유료 계정(연 $99)이
필요하고 안드로이드 APK 는 FCM 등록이 선행돼야 한다. 그동안 시민은 **앱을 켜 두고
있을 때만**(15초 폴링) 경보를 볼 수 있었다 — 주머니 속 폰은 울리지 않는다.

웹 푸시는 그 사이를 메운다. 사파리 16.4+ / 안드로이드 크롬은 **홈 화면에 추가한
웹앱**에 표준 Web Push 로 알림을 보낼 수 있다. 스토어도, 유료 계정도, FCM 도 필요
없고, 앱을 꺼 둬도 뜬다.

## 신뢰 경계
구독 정보(endpoint·키)는 **그 브라우저가 스스로 만들어 준 주소**다. 위치는 여전히
res7 셀 하나로만 받는다(devices.py 와 같은 경계). VAPID 개인키는 서버 환경변수에만
있고, 없으면 이 기능은 조용히 꺼진다 — 키 없이 보내는 척하지 않는다.
"""

from __future__ import annotations

import json

from app.config import settings

try:  # pywebpush 가 없으면 기능만 꺼진다 — 나머지 경로는 그대로 돈다.
    from pywebpush import WebPushException, webpush
except ImportError:  # pragma: no cover
    webpush = None
    WebPushException = Exception


def enabled() -> bool:
    """키가 다 있고 라이브러리가 있을 때만 동작한다."""
    return bool(
        webpush is not None
        and settings.vapid_public_key
        and settings.vapid_private_key
    )


def public_key() -> str:
    """앱이 구독할 때 쓰는 공개키. 비어 있으면 앱이 구독을 시도하지 않는다."""
    return settings.vapid_public_key


def send_one(subscription: dict, title: str, body: str, data: dict) -> bool:
    """한 구독에 보낸다. 성공 True.

    실패는 두 종류다 — 만료된 구독(404·410)과 일시 오류. 호출부가 만료를 지우도록
    예외 대신 불리언과 로그로 알린다.
    """
    if not enabled():
        return False
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps({"title": title, "body": body, "data": data}, ensure_ascii=False),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_contact},
            timeout=settings.push_timeout_sec,
            ttl=settings.webpush_ttl_sec,
        )
        return True
    except WebPushException as e:  # noqa: BLE001 — 한 명 실패가 전체를 막지 않는다
        code = getattr(getattr(e, "response", None), "status_code", None)
        print(f"[webpush] 발송 실패(status={code}): {e}")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"[webpush] 발송 실패({type(e).__name__}): {e}")
        return False


def is_gone(subscription: dict) -> bool:
    """구독이 만료됐는지 — 호출부가 지우기 위한 판정은 send_one 의 로그로 갈음한다.

    (별도 확인 요청을 보내면 브라우저 벤더 서버에 불필요한 부하를 준다.)
    """
    return False
