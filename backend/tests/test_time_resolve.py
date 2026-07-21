"""app.phase3.time_resolve — time_kind/값 → seen_at 결정론적 변환.

가드레일 검증: LLM 은 명시값만 뽑고, 여기가 산술+안전 클램프를 한다.
"""

from datetime import datetime, timedelta

from app.phase3 import time_resolve

NOW = datetime(2026, 7, 21, 16, 0, 0)
LKP_TIME = datetime(2026, 7, 21, 13, 0, 0)   # 3시간 전 실종 접수


def _resolve(**structured):
    return time_resolve.resolve_seen_at(structured, now=NOW, lkp_time=LKP_TIME)


def test_relative_minutes():
    assert _resolve(time_kind="relative", time_minutes_ago=30) == NOW - timedelta(minutes=30)


def test_relative_zero_is_now():
    assert _resolve(time_kind="relative", time_minutes_ago=0) == NOW


def test_absolute_today():
    # now=16:00, clock=15:00 → 오늘 15:00 (미래 아님)
    assert _resolve(time_kind="absolute", time_clock="15:00") == NOW.replace(hour=15, minute=0)


def test_absolute_future_clock_rolls_back_a_day_then_window_rejects():
    # now=16:00, clock=17:00 → 계산상 "오늘 17시"는 미래라 어제로 밀림
    # → 어제 17시는 lkp_time(오늘 13시)보다도 이전 → 안전창 밖 → None
    assert _resolve(time_kind="absolute", time_clock="17:00") is None


def test_absolute_future_clock_within_window_still_accepted():
    # now=16:00, clock=15:30 → 오늘 15:30, lkp_time(13:00) 이후라 창 안 → 정상 채택
    assert _resolve(time_kind="absolute", time_clock="15:30") == NOW.replace(hour=15, minute=30)


def test_absolute_clock_exactly_now_is_accepted():
    # 경계값 — cand == now 는 "미래"가 아니므로(> 비교) 거부되지 않는다
    assert _resolve(time_kind="absolute", time_clock="16:00") == NOW


def test_result_before_lkp_time_is_rejected():
    # relative 200분 전 = 13시간 전 접수 이전 시각 → 안전창 밖 → None
    assert _resolve(time_kind="relative", time_minutes_ago=200) is None


def test_vague_returns_none():
    assert _resolve(time_kind="vague", time_minutes_ago=None, time_clock=None) is None


def test_none_kind_returns_none():
    assert _resolve(time_kind="none") is None


def test_missing_kind_returns_none():
    assert _resolve() is None


def test_negative_minutes_rejected():
    assert _resolve(time_kind="relative", time_minutes_ago=-10) is None


def test_non_int_minutes_rejected():
    assert _resolve(time_kind="relative", time_minutes_ago="30") is None


def test_bool_minutes_rejected():
    # bool 은 int 서브클래스라 isinstance(True, int) 가 True — 명시적으로 막아야 함
    assert _resolve(time_kind="relative", time_minutes_ago=True) is None


def test_malformed_clock_rejected():
    assert _resolve(time_kind="absolute", time_clock="25:99") is None
    assert _resolve(time_kind="absolute", time_clock="abc") is None
    assert _resolve(time_kind="absolute", time_clock=None) is None
