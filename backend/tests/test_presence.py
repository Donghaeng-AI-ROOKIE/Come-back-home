"""익명 동시 참여자 수(presence) — TTL·상한·격리·개인정보 경계.

핵심 계약: 사건 단위 집계만, 좌표 미수집, TTL 후 흔적 없음, 종결 시 즉시 0.
"""

import pytest

from app.config import settings
from app.phase3 import presence


@pytest.fixture(autouse=True)
def _clean():
    """모듈 전역 dict 를 쓰므로 테스트 간 격리가 필수 — 앞뒤로 비운다."""
    presence.reset()
    yield
    presence.reset()


def test_distinct_tokens_accumulate():
    assert presence.heartbeat("c1", "tok-aaaaaaaa") == 1
    assert presence.heartbeat("c1", "tok-bbbbbbbb") == 2
    assert presence.heartbeat("c1", "tok-cccccccc") == 3


def test_same_token_is_idempotent():
    """같은 사람이 폴링을 반복해도 카운트가 부풀지 않는다 — 하트비트의 전제."""
    for _ in range(10):
        assert presence.heartbeat("c1", "tok-aaaaaaaa") == 1


def test_cases_are_isolated():
    """사건별로 따로 센다 — 다른 사건 참여자가 섞이면 사회적 증거가 거짓이 된다."""
    presence.heartbeat("c1", "tok-aaaaaaaa")
    presence.heartbeat("c1", "tok-bbbbbbbb")
    presence.heartbeat("c2", "tok-cccccccc")
    assert presence.count("c1") == 2
    assert presence.count("c2") == 1


def test_unknown_case_is_zero_not_error():
    assert presence.count("존재하지-않는-사건") == 0


def test_ttl_expiry_drops_watcher():
    """TTL 이 지나면 사라진다. monotonic 시계를 직접 못 돌리므로 ttl=0 으로 즉시 만료."""
    presence.heartbeat("c1", "tok-aaaaaaaa", ttl_sec=0)
    assert presence.count("c1") == 0


def test_expired_watcher_does_not_block_live_count():
    """만료된 토큰이 살아있는 토큰의 집계를 오염시키지 않는다."""
    presence.heartbeat("c1", "tok-expired0", ttl_sec=0)
    assert presence.heartbeat("c1", "tok-live0000") == 1


def test_ttl_refreshes_on_each_heartbeat():
    """만료 직전 토큰도 하트비트로 되살아난다 — 폴링이 계속되는 한 유지."""
    presence.heartbeat("c1", "tok-aaaaaaaa", ttl_sec=0)
    assert presence.count("c1") == 0
    assert presence.heartbeat("c1", "tok-aaaaaaaa", ttl_sec=60) == 1
    assert presence.count("c1") == 1


def test_prune_removes_empty_case_bucket():
    """빈 껍데기 dict 가 사건 수만큼 영구 누적되지 않는다 (메모리 누수 회귀)."""
    presence.heartbeat("c1", "tok-aaaaaaaa", ttl_sec=0)
    presence.count("c1")
    assert "c1" not in presence._watchers


def test_token_cap_saturates_without_evicting():
    """상한 초과 시 신규만 거절 — 기존 참여자가 밀려나지 않는다."""
    cap = settings.presence_max_tokens_per_case
    for i in range(cap):
        presence.heartbeat("c1", f"tok-{i:08d}")
    assert presence.count("c1") == cap

    # 신규 토큰은 거절되지만 카운트는 유지(감소하지 않음)
    assert presence.heartbeat("c1", "tok-overflow") == cap
    # 상한에 걸린 뒤에도 기존 토큰 갱신은 계속 받아야 한다
    assert presence.heartbeat("c1", "tok-00000000") == cap


def test_clear_wipes_case():
    presence.heartbeat("c1", "tok-aaaaaaaa")
    presence.clear("c1")
    assert presence.count("c1") == 0


def test_presence_module_never_takes_coordinates():
    """설계 계약의 회귀 방지: 셀·좌표 단위 집계 금지(그 자체가 위치정보).

    나중에 '더 정확한 근처 인원'을 위해 좌표 인자를 슬쩍 추가하려는 시도를
    여기서 깨뜨린다 — 온디바이스 지오펜싱 전제가 무너지는 지점이라
    코드리뷰가 아니라 테스트로 막는다.
    """
    import inspect

    for fn in (presence.heartbeat, presence.count, presence.clear):
        params = set(inspect.signature(fn).parameters)
        assert not params & {"lat", "lng", "cell", "cells", "location", "point"}, (
            f"{fn.__name__} 에 위치 인자가 생겼다 — presence.py 설계 계약 위반"
        )
