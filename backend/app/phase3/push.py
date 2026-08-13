"""Expo Push Service 발송 클라이언트.

## 왜 FCM 을 직접 부르지 않는가
FCM 은 구글 것이라 안드로이드로만 간다. iOS 를 붙이려면 애플 APNs 로 보내는
**두 번째 발송 경로**를 서버에 따로 짜야 한다. Expo Push Service 를 경유하면
토큰 형식이 하나로 통일되고 Expo 가 FCM(안드로이드)/APNs(iOS)로 갈라 보낸다 —
iOS 추가가 "APNs 키 등록 + 빌드"로 끝나고 이 파일은 안 바뀐다.
안드로이드 우선으로 가되 확장 비용을 낮추기로 한 결정(2026-08-05).

## 알림 문구는 서버가 완성한다
안드로이드는 데이터만 보내고 앱이 알림을 직접 만들 수 있어서 그렇게 짜기 쉽지만,
**iOS 는 앱 코드가 돌기 전에 OS 가 먼저 알림을 띄운다.** 폰에서 문구를 조립하는
구조로 만들면 iOS 에서 빈 알림이 뜬다. title/body 를 여기서 채워 보낸다.

## 스텁 모드
`settings.push_enabled` 가 False 면 네트워크를 타지 않고 결정적 응답을 돌려준다
(llm/base.py 와 같은 idiom). 테스트가 외부 서비스에 의존하지 않게 하는 장치이자,
키·크레덴셜 없이 파이프라인 전체를 돌려보기 위한 것.
"""

import httpx

from app.config import settings
from app.phase3 import devices, webpush
from app.schemas.device import Platform

# 공식 엔드포인트. 배치 상한 100건/요청, 프로젝트당 600건/초.
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
# Expo 가 한 요청에 받는 최대 메시지 수.
MAX_BATCH = 100


class PushError(Exception):
    """발송 실패 — 호출부가 알림 실패로 인해 접수·예측을 막지 않도록 잡아 쓴다."""


def _chunk(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def send(
    tokens: list[str],
    title: str,
    body: str,
    data: dict,
    *,
    priority: str = "high",
    channel_id: str = "alerts",
) -> dict:
    """토큰들에 같은 알림을 발송하고 집계 결과를 반환.

    priority="high": 실종 경보는 도즈 모드(안드로이드 절전)에서도 즉시 떠야 한다.
    channel_id: 안드로이드 알림 채널. 앱이 같은 id 로 채널을 만들어 둬야 소리·중요도가
    적용된다 — 없으면 기본 채널로 조용히 떨어진다.
    """
    if not tokens:
        return {"sent": 0, "failed": 0, "tickets": [], "stub": False}

    # 웹 푸시 구독은 Expo 토큰이 아니라 브라우저가 준 주소다 — 다른 경로로 보낸다.
    # 한 사건의 수신자 안에 두 종류가 섞이므로 여기서 갈라 준다(호출부는 모른다).
    web_devices = [d for d in devices.all_devices()
                   if d.platform == Platform.web and d.token in set(tokens)]
    web_tokens = {d.token for d in web_devices}
    expo_tokens = [tk for tk in tokens if tk not in web_tokens]

    web_sent = 0
    web_failed = 0
    for d in web_devices:
        if d.web_subscription and webpush.send_one(d.web_subscription, title, body, data):
            web_sent += 1
        else:
            web_failed += 1

    if not expo_tokens:
        return {"sent": web_sent, "failed": web_failed, "tickets": [], "stub": False}
    tokens = expo_tokens

    if not settings.push_enabled:
        # 스텁: 네트워크 없이 "보낸 셈" 친다. 실패 0 으로 두면 호출부의 집계 코드가
        # 실경로와 같은 모양을 타므로, 나중에 켰을 때 처음 도는 경로가 줄어든다.
        return {"sent": len(tokens) + web_sent, "failed": web_failed,
                "tickets": [], "stub": True}

    headers = {"Content-Type": "application/json"}
    if settings.expo_access_token:
        # 선택이지만 권장 — 토큰이 유출돼도 남이 우리 프로젝트 이름으로 못 보낸다.
        headers["Authorization"] = f"Bearer {settings.expo_access_token}"

    tickets: list[dict] = []
    failed = 0
    for batch in _chunk(tokens, MAX_BATCH):
        messages = [
            {
                "to": token,
                "title": title,
                "body": body,
                "data": data,
                "priority": priority,
                "channelId": channel_id,
                "sound": "default",
            }
            for token in batch
        ]
        try:
            resp = httpx.post(
                EXPO_PUSH_URL, json=messages, headers=headers,
                timeout=settings.push_timeout_sec,
            )
            resp.raise_for_status()
            tickets.extend(resp.json().get("data", []))
        except (httpx.HTTPError, ValueError) as e:
            # 한 배치가 실패해도 나머지는 계속 보낸다 — 500명 중 100명이 못 받는 것과
            # 전원이 못 받는 것은 다르다.
            failed += len(batch)
            tickets.append({"status": "error", "message": str(e)})

    # ticket status 가 "error" 인 건 전송 자체가 거부된 것(무효 토큰 등).
    ticket_errors = sum(1 for t in tickets if t.get("status") == "error")
    return {
        "sent": len(tokens) - failed - ticket_errors + web_sent,
        "failed": failed + ticket_errors + web_failed,
        "tickets": tickets,
        "stub": False,
    }
