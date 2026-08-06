"""푸시 인프라 — 기기 레지스트리·셀 타겟팅·확률 문턱.

핵심 계약:
  - 기기에 좌표도 위치 이력도 붙지 않는다 (res7 칸 하나, 현재 값만)
  - 발송 대상은 예측 셀의 res7 부모 집합 안 기기뿐 (원 근사 없음)
  - 참여도 등급이 확률 문턱을 가르되 reflex 는 면제
  - 발송 실패가 접수·예측을 무너뜨리지 않는다
"""

from datetime import datetime, timedelta

import pytest

from app import storage
from app.config import settings
from app.geo import h3grid
from app.phase3 import alerts, devices, push
from app.schemas.common import GeoPoint
from app.schemas.device import Engagement, Platform

LKP = GeoPoint(lat=37.6061, lng=127.0106)
FAR = GeoPoint(lat=35.1796, lng=129.0756)  # 부산 — 같은 부모 셀에 절대 안 걸린다
TOKEN = "ExponentPushToken[aaaaaaaaaaaaaaaaaaaaaa]"


def _cell7(p: GeoPoint) -> str:
    return h3grid.cell_of(p, settings.push_target_res)


@pytest.fixture(autouse=True)
def _clean():
    devices.reset()
    yield
    devices.reset()


# ── 기기 레지스트리 ──────────────────────────────────────────


def test_register_stores_cell_and_level():
    d = devices.register(TOKEN, Platform.android, _cell7(LKP), Engagement.low)
    assert d.cell_res7 == _cell7(LKP)
    assert d.engagement == Engagement.low


def test_register_is_upsert_and_keeps_history():
    """앱 실행마다·칸이 바뀔 때마다 호출되는 엔드포인트다. 매번 새로 만들면 발송
    이력이 초기화돼 피로도 예산이 영영 리셋된다."""
    devices.register(TOKEN, Platform.android, _cell7(LKP))
    devices.record_sent([TOKEN])
    devices.register(TOKEN, Platform.android, _cell7(FAR))

    assert len(devices.all_devices()) == 1
    assert storage.devices.get(TOKEN).sent_count_24h() == 1


def test_register_updates_platform():
    devices.register(TOKEN, Platform.android)
    devices.register(TOKEN, Platform.ios)
    assert storage.devices.get(TOKEN).platform == Platform.ios


def test_location_is_overwritten_not_accumulated():
    """🚨 위치 이력을 남기지 않는다 — 남기는 순간 해상도와 무관하게 이동 궤적이
    되고, 거친 셀을 쓰기로 한 의미가 사라진다."""
    devices.register(TOKEN, Platform.android, _cell7(LKP))
    devices.register(TOKEN, Platform.android, _cell7(FAR))
    device = storage.devices.get(TOKEN)

    assert device.cell_res7 == _cell7(FAR)
    assert _cell7(LKP) not in repr(device.model_dump())  # 이전 칸이 어디에도 안 남는다


def test_missing_cell_does_not_erase_last_known():
    """이번에 위치를 못 구한 것과 "위치를 지웠다"는 다르다 — 마지막 칸까지 지우면
    그 사이 알림 대상에서 통째로 빠진다."""
    devices.register(TOKEN, Platform.android, _cell7(LKP))
    devices.register(TOKEN, Platform.android, None)
    assert storage.devices.get(TOKEN).cell_res7 == _cell7(LKP)


def test_device_has_no_coordinates():
    """설계 계약 회귀 방지: 기기에 좌표·정밀 셀·제보 이력이 붙지 않는다.

    나중에 "발송 정확도를 높이려고" 좌표를 추가하려는 시도를 코드리뷰가 아니라
    여기서 깨뜨린다 — 최소 해상도가 이 설계의 근거 전체다.
    """
    devices.register(TOKEN, Platform.android, _cell7(LKP))
    fields = set(storage.devices.get(TOKEN).model_dump().keys())
    assert not fields & {
        "lat", "lng", "location", "point", "coords", "cell_res9", "cells", "tips", "reports",
    }


def test_unregister():
    devices.register(TOKEN, Platform.android, _cell7(LKP))
    assert devices.unregister(TOKEN) is True
    assert devices.all_devices() == []
    assert devices.unregister(TOKEN) is False  # 두 번째는 False


def test_sent_history_prunes_beyond_24h():
    devices.register(TOKEN, Platform.android, _cell7(LKP))
    device = storage.devices.get(TOKEN)
    device.sent_at = [datetime.now() - timedelta(hours=30)]  # 창 밖
    storage.devices.save(TOKEN, device)

    devices.record_sent([TOKEN])
    assert len(storage.devices.get(TOKEN).sent_at) == 1


def test_sent_count_24h_window():
    devices.register(TOKEN, Platform.android, _cell7(LKP))
    now = datetime.now()
    device = storage.devices.get(TOKEN)
    device.sent_at = [now - timedelta(hours=1), now - timedelta(hours=25)]
    storage.devices.save(TOKEN, device)
    assert device.sent_count_24h(now) == 1


# ── 셀 타겟팅 ────────────────────────────────────────────────


def test_parent_cells_fold_prediction_grid():
    """예측 셀(res9) 수백 개 → res7 부모 소수. 푸시 페이로드(약 4KiB)에 실려야 한다."""
    cells = h3grid.cells_within_k(LKP, 8)
    parents = alerts.target_parent_cells(cells)
    assert 0 < len(parents) < len(cells) / 10


def test_devices_in_cells_selects_by_membership():
    inside = "ExponentPushToken[inside0000000000000000]"
    outside = "ExponentPushToken[outside000000000000000]"
    devices.register(inside, Platform.android, _cell7(LKP))
    devices.register(outside, Platform.android, _cell7(FAR))

    target = alerts.target_parent_cells(h3grid.cells_within_k(LKP, 2))
    assert {d.token for d in devices.devices_in_cells(target)} == {inside}


def test_device_without_location_is_excluded():
    """🚨 위치를 모르면 발송 대상에서 뺀다(fail-closed) — 사건이 여럿이면 어느
    것이 그 사람에게 해당되는지 알 수 없고, 아무거나 보내면 **틀린 사건**을 알린다."""
    devices.register(TOKEN, Platform.android, None)
    target = alerts.target_parent_cells(h3grid.cells_within_k(LKP, 2))
    assert devices.devices_in_cells(target) == []


# ── 확률 문턱 (피로도 예산) ──────────────────────────────────


def _peaked_poa() -> tuple[dict[str, float], str, str]:
    """LKP 중심만 뾰족한 분포와, 상대확률이 다른 두 부모 칸을 함께 돌려준다.

    바깥 셀 0.5 → 상대확률 0.45 (high·normal 문턱은 넘고 low 문턱 0.6 미만)
    """
    cells = h3grid.cells_within_k(LKP, 8)
    center = h3grid.cell_of(LKP)
    poa = {c: (1.0 if c == center else 0.5) for c in cells}
    rel = alerts.relative_prob_by_parent(poa)
    weak = [p for p, v in rel.items() if v < settings.push_prob_threshold["low"]]
    assert weak, "테스트 전제: 최고 칸 말고 약한 칸도 있어야 한다"
    return poa, _cell7(LKP), weak[0]


def test_relative_prob_uses_frontend_scale():
    """POA 원값은 합이 1이라 최고 셀도 실측 0.18 수준 — 그대로 문턱에 대면 아무에게도
    안 간다. 프론트 히트맵과 같은 상대 스케일(최고 셀 = 0.9)로 환산해야 지도 색과
    알림 여부가 일치한다."""
    poa, peak_cell, weak_cell = _peaked_poa()
    rel = alerts.relative_prob_by_parent(poa)
    assert rel[peak_cell] == pytest.approx(0.9)
    assert rel[weak_cell] == pytest.approx(0.45)


def test_peak_area_reaches_every_engagement_level():
    """가장 유력한 칸에서는 참여도와 무관하게 모두 받는다."""
    poa, peak_cell, _ = _peaked_poa()
    for level in Engagement:
        devices.reset()
        devices.register(TOKEN, Platform.android, peak_cell, level)
        r = alerts.send_alerts("case-1", list(poa), "요약", poa=poa)
        assert r["devices"] == 1, f"{level.value} 가 최고 확률 칸에서 걸러졌다"


def test_weak_area_filters_by_engagement():
    """같은 칸·같은 사건인데 참여도에 따라 발송이 갈린다 — S6 의 핵심."""
    poa, _, weak_cell = _peaked_poa()
    for level, expected in [(Engagement.high, 1), (Engagement.normal, 1), (Engagement.low, 0)]:
        devices.reset()
        devices.register(TOKEN, Platform.android, weak_cell, level)
        r = alerts.send_alerts("case-1", list(poa), "요약", poa=poa)
        assert r["devices"] == expected, f"{level.value} 기대 {expected}"
        assert r["in_area"] == 1  # 지오펜스는 통과했고 문턱에서만 갈렸다
        assert r["below_threshold"] == 1 - expected


def test_reflex_is_exempt_from_threshold():
    """🚨 골든타임 알림은 문턱 면제 — POA 가 나오기 전에 나가는 알림이라 확률이라는
    게 아직 없고, 피로도로 줄일 대상도 아니다."""
    poa, _, weak_cell = _peaked_poa()
    devices.register(TOKEN, Platform.android, weak_cell, Engagement.low)
    r = alerts.send_alerts("case-1", list(poa), "요약", kind="reflex", poa=poa)
    assert r["devices"] == 1


def test_without_poa_threshold_is_not_applied():
    """확률을 안 넘기면 문턱을 적용하지 않는다 — 없는 근거로 거르면 조용한 누락이 된다."""
    devices.register(TOKEN, Platform.android, _cell7(LKP), Engagement.low)
    r = alerts.send_alerts("case-1", h3grid.cells_within_k(LKP, 2), "요약")
    assert r["devices"] == 1


def test_server_threshold_matches_client():
    """서버·앱 문턱이 어긋나면 사용자는 "알림은 왔는데 앱은 구역 밖이라 한다" 같은
    모순을 본다. 프론트 utils/alertBudget.ts 의 PROB_THRESHOLD 와 같아야 한다."""
    assert settings.push_prob_threshold == {"high": 0.3, "normal": 0.45, "low": 0.6}


# ── 발송 ────────────────────────────────────────────────────


def test_payload_carries_target_cells():
    """앱 안 관문이 원 근사가 아니라 셀 판정을 하도록 대상 칸 목록을 실어 보낸다."""
    devices.register(TOKEN, Platform.android, _cell7(LKP))
    r = alerts.send_alerts("case-1", h3grid.cells_within_k(LKP, 2), "회색 점퍼", kind="reflex")

    assert r["target_res"] == settings.push_target_res
    assert _cell7(LKP) in r["target_cells"]
    assert r["sent"] == 1


def test_send_alerts_completes_title_and_body():
    """서버가 문구를 완성한다 — iOS 는 앱 코드가 돌기 전에 OS 가 알림을 띄우므로
    폰에서 조립하는 구조면 빈 알림이 뜬다."""
    devices.register(TOKEN, Platform.android, _cell7(LKP))
    r = alerts.send_alerts("case-1", h3grid.cells_within_k(LKP, 1), "회색 점퍼")
    assert r["title"]
    assert "회색 점퍼" in r["body"]


def test_send_alerts_kind_changes_copy():
    titles = {
        kind: alerts.build_message(kind, "요약")[0]
        for kind in ("reflex", "poa", "new_region")
    }
    assert len(set(titles.values())) == 3  # 셋 다 달라야 한다


def test_send_alerts_with_no_devices_does_not_fail():
    """등록 기기가 0이어도 예외 없이 끝나야 한다 — 신고 접수 경로에서 호출되므로
    알림 실패가 접수·예측을 무너뜨리면 안 된다."""
    r = alerts.send_alerts("case-1", h3grid.cells_within_k(LKP, 1), "요약")
    assert r["devices"] == 0
    assert r["sent"] == 0


def test_send_alerts_records_send_history():
    devices.register(TOKEN, Platform.android, _cell7(LKP))
    alerts.send_alerts("case-1", h3grid.cells_within_k(LKP, 1), "요약")
    assert storage.devices.get(TOKEN).sent_count_24h() == 1


def test_push_is_stubbed_by_default():
    """테스트가 외부 서비스를 타지 않는다. push_enabled 기본값이 False 인 이유."""
    assert settings.push_enabled is False
    r = push.send([TOKEN], title="t", body="b", data={})
    assert r["stub"] is True
    assert r["sent"] == 1


def test_push_send_with_no_tokens_short_circuits():
    r = push.send([], title="t", body="b", data={})
    assert r == {"sent": 0, "failed": 0, "tickets": [], "stub": False}


def test_alert_copy_avoids_certainty():
    """알림 문구도 실종자 위치를 단정하면 안 된다.

    수색 안내(storytelling)에만 검증기를 걸어두고 알림 문구를 놓쳤던 회귀가 있었다
    ("내 주변에 실종자가 있어요"). 같은 금칙어 목록으로 여기서도 막는다.

    reflex 는 예외 — "실종이 발생했어요"는 사실이다. 단정하면 안 되는 건
    실종자의 **위치**이지 실종 발생 자체가 아니다.
    """
    from app.phase3 import storytelling

    for kind in ("poa", "new_region", "reflex"):
        title, body = alerts.build_message(kind, "회색 점퍼")
        for token in storytelling._FORBIDDEN_CERTAINTY:
            assert token not in title, f"{kind} 제목에 확정 표현: {token}"
            assert token not in body, f"{kind} 본문에 확정 표현: {token}"


def test_alert_copy_has_no_condition_disclosure():
    """푸시는 잠금화면에 뜨고 넓은 지역에 간다 — 진단명이 절대 실리면 안 된다."""
    from app.phase3 import storytelling

    for kind in ("poa", "new_region", "reflex"):
        title, body = alerts.build_message(kind, "회색 점퍼")
        for token in storytelling._FORBIDDEN_CONDITION:
            assert token not in title + body, f"{kind} 문구에 질환·장애 노출: {token}"
