"""기기 레지스트리 — 푸시 발송 대상 관리.

개인정보 경계는 `schemas/device.py` 주석 참고. 요약하면 **토큰과 발송 기록만**
두고 위치·제보 이력·계정은 붙이지 않는다.
"""

from datetime import datetime, timedelta

from app import storage
from app.schemas.device import Device, Engagement, Platform

# 발송 이력 보관 창. 피로도 예산이 24시간 기준이라 그보다 길게 들고 있을 이유가 없다.
_SENT_HISTORY_WINDOW = timedelta(hours=24)


def register(
    token: str,
    platform: Platform,
    cell_res7: str | None = None,
    engagement: Engagement = Engagement.normal,
    now: datetime | None = None,
) -> Device:
    """기기 등록 (upsert).

    같은 토큰으로 다시 부르면 새로 만들지 않고 기존 기록을 유지한다 — 앱을 켤
    때마다, 그리고 위치 칸이 바뀔 때마다 호출되는 엔드포인트라 매번 새로 만들면
    발송 이력이 초기화되어 피로도 예산이 영영 리셋된다.

    ⚠️ **위치는 덮어쓴다. 이전 값을 남기지 않는다.** 이력을 쌓기 시작하면
    res7 이든 res9 든 결국 이동 궤적이 되고, 해상도를 낮춘 의미가 사라진다
    (schemas/device.py 참고).
    """
    now = now or datetime.now()
    existing: Device | None = storage.devices.get(token)
    if existing is not None:
        # 재설치·기기 변경으로 플랫폼이 바뀔 수 있으니 그것만 갱신.
        existing.platform = platform
        # cell_res7=None 은 "이번엔 위치를 못 구했다"는 뜻이지 "지웠다"가 아니다 —
        # 마지막으로 알던 칸을 지우면 그 사이 알림 대상에서 통째로 빠진다.
        if cell_res7 is not None:
            existing.cell_res7 = cell_res7
        existing.engagement = engagement
        return storage.devices.save(token, existing)
    return storage.devices.save(
        token,
        Device(
            token=token, platform=platform, registered_at=now,
            cell_res7=cell_res7, engagement=engagement,
        ),
    )


def unregister(token: str) -> bool:
    """등록 해제. 알림 수신 거부·앱 삭제 시 호출.

    푸시 토큰은 지속적 기기 식별자이므로 **지우는 경로가 반드시 있어야 한다.**
    """
    if storage.devices.get(token) is None:
        return False
    storage.devices.delete(token)
    return True


def all_devices() -> list[Device]:
    """등록된 기기 전체 (운영·디버그용). 발송에는 devices_in_cells 를 쓴다."""
    return storage.devices.list()


def devices_in_cells(cells: set[str]) -> list[Device]:
    """대상 res7 셀 집합 안에 있는 기기만.

    위치를 아직 못 받은 기기(cell_res7=None)는 **제외된다.** 어느 사건이 그
    사람에게 해당되는지 알 수 없는데 아무거나 보내면 **틀린 사건**을 알리게 되기
    때문이다 — 프론트 지오펜스를 fail-closed 로 둔 것과 같은 판단.
    """
    return [d for d in storage.devices.list() if d.cell_res7 is not None and d.cell_res7 in cells]


def record_sent(tokens: list[str], now: datetime | None = None) -> None:
    """발송 기록. 24시간 창 밖의 이력은 이 시점에 버린다."""
    now = now or datetime.now()
    cutoff = now - _SENT_HISTORY_WINDOW
    for token in tokens:
        device: Device | None = storage.devices.get(token)
        if device is None:
            continue
        device.sent_at = [t for t in device.sent_at if t >= cutoff]
        device.sent_at.append(now)
        device.last_sent_at = now
        storage.devices.save(token, device)


def reset() -> None:
    """테스트 격리용."""
    for device in storage.devices.list():
        storage.devices.delete(device.token)
