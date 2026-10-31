"""app.phase3.time_resolve — time_kind/값 → seen_at 결정론적 변환.

가드레일 검증: LLM 은 명시값만 뽑고, 여기가 산술+오전/오후 판단+안전 클램프를 한다.

시계 시각("1시 15분")은 한국 시간이고, now·lkp_time·반환값은 저장 형식(서버 로컬 naive)이다.
운영 컨테이너는 UTC 라, 11/01 01:21 KST 운영 실측에서 "1시 15분"이 UTC 13:15(= 22:15 KST)로
저장돼 층2 경과 시간이 8분이 아니라 3시간 8분으로 잡혔다. 시계 시각 시험은 서버 시간대
세 곳(UTC·서울·뉴욕)에서 같은 한국 시각을 내야 한다.
"""

import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.phase3 import time_resolve

KST = ZoneInfo("Asia/Seoul")


def naive(iso: str) -> datetime:
    """저장 형식 그대로의 naive 시각(서버 로컬). 실측 UTC 값을 그대로 적을 때 쓴다."""
    return datetime.fromisoformat(iso)


NOW = naive("2026-07-21T16:00:00")
LKP_TIME = naive("2026-07-21T13:00:00")   # 3시간 전 실종 접수


def _set_tz(name):
    os.environ["TZ"] = name
    time.tzset()


@pytest.fixture(params=["UTC", "Asia/Seoul", "America/New_York"])
def server_tz(request):
    """서버 시간대를 바꿔 가며 돈다. 저장 시각은 그 시간대의 naive 다."""
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset unavailable")
    before = os.environ.get("TZ")
    _set_tz(request.param)
    yield request.param
    if before is None:
        os.environ.pop("TZ", None)
        time.tzset()
    else:
        _set_tz(before)


@pytest.fixture()
def utc_server():
    """운영 컨테이너와 같은 UTC 서버 — 실측 값을 그대로 넣는 회귀 시험용."""
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset unavailable")
    before = os.environ.get("TZ")
    _set_tz("UTC")
    yield
    if before is None:
        os.environ.pop("TZ", None)
        time.tzset()
    else:
        _set_tz(before)


def stored(kst: str) -> datetime:
    """한국 시각 문자열 → 지금 서버 시간대의 저장 형식(naive)."""
    return datetime.fromisoformat(kst).replace(tzinfo=KST).astimezone().replace(tzinfo=None)


def _resolve(**structured):
    return time_resolve.resolve_seen_at(structured, now=NOW, lkp_time=LKP_TIME)


def _clock(clock, meridiem=None, *, now, lkp):
    return time_resolve.resolve_seen_at(
        {"time_kind": "absolute", "time_clock": clock, "time_meridiem": meridiem},
        now=stored(now), lkp_time=stored(lkp))


# ── 상대 시각: 시계와 무관 — 저장 시각에서 그대로 뺀다(바꾸지 않음) ──────────────

def test_relative_minutes():
    assert _resolve(time_kind="relative", time_minutes_ago=30) == NOW - timedelta(minutes=30)


def test_relative_zero_is_now():
    assert _resolve(time_kind="relative", time_minutes_ago=0) == NOW


def test_relative_is_independent_of_server_timezone(server_tz):
    now, lkp = stored("2026-11-01T01:21:58"), stored("2026-10-31T21:30:00")
    out = time_resolve.resolve_seen_at({"time_kind": "relative", "time_minutes_ago": 10},
                                       now=now, lkp_time=lkp)
    assert out == now - timedelta(minutes=10)


def test_result_before_lkp_time_is_rejected():
    # relative 200분 전 = 3시간 전 접수 이전 시각 → 안전창 밖 → None
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


# ── 11/01 운영 실측 회귀 ────────────────────────────────────────────────────

def test_measured_case_utc_container(utc_server):
    """11/01 01:22 KST 운영 실측 값을 그대로 넣는다.

    created_at 2026-10-31T16:21:58(UTC naive = 01:21 KST), lkp_time 12:30(= 21:30 KST).
    "1시 15분"(오전/오후 없음) → 01:15 KST = 16:15 UTC. 예전 코드는 13:15 UTC(22:15 KST).
    """
    out = time_resolve.resolve_seen_at(
        {"time_kind": "absolute", "time_clock": "01:15", "time_meridiem": None},
        now=naive("2026-10-31T16:21:58"), lkp_time=naive("2026-10-31T12:30:00"))
    assert out == naive("2026-10-31T16:15:00")
    assert out.tzinfo is None


def test_measured_case_old_24h_output_is_dropped_not_misread(utc_server):
    """예전 지시문대로 모델이 "1시 15분"을 13:15 로 냈다면 13:15 KST(04:15 UTC)다.

    lkp(21:30 KST) 이전이라 버려 층1로 강등된다 — 22:15 KST 로 잘못 앵커링되지 않는다.
    """
    out = time_resolve.resolve_seen_at(
        {"time_kind": "absolute", "time_clock": "13:15", "time_meridiem": None},
        now=naive("2026-10-31T16:21:58"), lkp_time=naive("2026-10-31T12:30:00"))
    assert out is None


def test_measured_case_any_server_timezone(server_tz):
    out = _clock("01:15", now="2026-11-01T01:21:58", lkp="2026-10-31T21:30:00")
    assert out == stored("2026-11-01T01:15:00")


def test_explicit_pm_at_measured_moment_is_before_lkp(server_tz):
    # "오후 1시 15분" → 13:15 KST(04:15 UTC) — 실종(21:30 KST) 이전이라 None
    assert _clock("01:15", "pm", now="2026-11-01T01:21:58", lkp="2026-10-31T21:30:00") is None
    # 모델이 24시간제로 "13:15"+pm 을 내도 같은 결과
    assert _clock("13:15", "pm", now="2026-11-01T01:21:58", lkp="2026-10-31T21:30:00") is None


def test_explicit_am_at_measured_moment(server_tz):
    out = _clock("01:15", "am", now="2026-11-01T01:21:58", lkp="2026-10-31T21:30:00")
    assert out == stored("2026-11-01T01:15:00")


# ── 오전/오후 없는 시계 시각: 창 안의 가장 최근 후보 ─────────────────────────────

def test_daytime_three_oclock_is_this_afternoon(server_tz):
    # 낮 15:10 KST 에 "3시쯤" → 15:00 KST (03:00 은 더 오래전)
    out = _clock("03:00", now="2026-11-02T15:10:00", lkp="2026-11-02T12:00:00")
    assert out == stored("2026-11-02T15:00:00")


def test_daytime_three_oclock_utc_value(utc_server):
    # 같은 사례를 UTC 저장값으로: 15:00 KST = 06:00 UTC
    out = time_resolve.resolve_seen_at(
        {"time_kind": "absolute", "time_clock": "03:00", "time_meridiem": None},
        now=naive("2026-11-02T06:10:00"), lkp_time=naive("2026-11-02T03:00:00"))
    assert out == naive("2026-11-02T06:00:00")


def test_eleven_at_two_am_is_previous_night(server_tz):
    # 02:00 KST 에 "11시" → 전날 23:00 KST (lkp 22:00 이후라 채택)
    out = _clock("11:00", now="2026-11-02T02:00:00", lkp="2026-11-01T22:00:00")
    assert out == stored("2026-11-01T23:00:00")


def test_eleven_at_two_am_before_lkp_is_none(server_tz):
    # lkp 가 23:30 이면 23:00 은 실종 이전, 그 전 11:00 은 더 이전 → None
    assert _clock("11:00", now="2026-11-02T02:00:00", lkp="2026-11-01T23:30:00") is None


def test_future_pm_falls_back_to_am_inside_window(server_tz):
    # 15:10 KST 에 "3시 20분": 15:20 은 미래 → 오늘 03:20 이 창(lkp 02:00 이후) 안이면 채택
    out = _clock("03:20", now="2026-11-02T15:10:00", lkp="2026-11-02T02:00:00")
    assert out == stored("2026-11-02T03:20:00")


def test_future_clock_without_window_candidate_is_none(server_tz):
    # 15:10 KST 에 "3시 20분", lkp 12:00 → 15:20 미래, 03:20 실종 이전 → None
    assert _clock("03:20", now="2026-11-02T15:10:00", lkp="2026-11-02T12:00:00") is None
    # "오후 4시"는 오늘 16:00 미래, 어제 16:00 실종 이전 → None
    assert _clock("04:00", "pm", now="2026-11-02T15:10:00", lkp="2026-11-02T12:00:00") is None


def test_crosses_midnight(server_tz):
    # 00:20 KST 에 "11시 50분" → 전날 23:50 KST
    out = _clock("11:50", now="2026-11-01T00:20:00", lkp="2026-10-31T21:30:00")
    assert out == stored("2026-10-31T23:50:00")


def test_korean_date_not_utc_date(server_tz):
    """오늘·어제는 한국 날짜다. 08:30 KST 는 UTC 로 전날 23:30 이다.

    UTC 날짜로 "오늘 8시"를 잡으면 하루 전 08:00 KST 가 되어 lkp 이전으로 버려진다.
    """
    out = _clock("08:00", now="2026-11-01T08:30:00", lkp="2026-11-01T07:00:00")
    assert out == stored("2026-11-01T08:00:00")


def test_case_longer_than_a_day_takes_most_recent(server_tz):
    # 실종 이틀째 15:10 KST 에 "3시" → 가장 최근 15:00 (어제·그제 3시가 아님)
    out = _clock("03:00", now="2026-11-03T15:10:00", lkp="2026-11-01T09:00:00")
    assert out == stored("2026-11-03T15:00:00")


# ── 경계값 ────────────────────────────────────────────────────────────────

def test_clock_exactly_now_is_accepted(server_tz):
    out = _clock("03:10", now="2026-11-02T15:10:00", lkp="2026-11-02T12:00:00")
    assert out == stored("2026-11-02T15:10:00")


def test_clock_one_minute_after_now_is_rejected(server_tz):
    # 15:11 은 미래, 03:11 은 실종 이전 → None (미래 목격은 받지 않는다)
    assert _clock("03:11", now="2026-11-02T15:10:00", lkp="2026-11-02T12:00:00") is None


def test_clock_exactly_lkp_is_accepted(server_tz):
    out = _clock("09:30", "pm", now="2026-11-01T01:21:58", lkp="2026-10-31T21:30:00")
    assert out == stored("2026-10-31T21:30:00")


def test_clock_one_minute_before_lkp_is_rejected(server_tz):
    assert _clock("09:29", "pm", now="2026-11-01T01:21:58", lkp="2026-10-31T21:30:00") is None


def test_seconds_of_now_do_not_block_same_minute(server_tz):
    # now 01:15:59 에 "1시 15분" → 01:15:00 (초는 버린 시계 시각이 now 이전)
    out = _clock("01:15", now="2026-11-01T01:15:59", lkp="2026-10-31T21:30:00")
    assert out == stored("2026-11-01T01:15:00")


# ── 12시·24시간제·모순 ───────────────────────────────────────────────────────

def test_twelve_without_meridiem_picks_midnight_or_noon_by_window(server_tz):
    # 00:30 KST 에 "12시" → 오늘 00:00 (어제 12:00 은 실종 이전)
    assert _clock("12:00", now="2026-11-01T00:30:00", lkp="2026-10-31T21:30:00") == \
        stored("2026-11-01T00:00:00")
    # 13:00 KST 에 "12시" → 오늘 12:00
    assert _clock("12:00", now="2026-11-01T13:00:00", lkp="2026-10-31T21:30:00") == \
        stored("2026-11-01T12:00:00")


def test_twelve_with_meridiem(server_tz):
    now, lkp = "2026-11-01T13:00:00", "2026-10-31T21:30:00"
    assert _clock("12:00", "pm", now=now, lkp=lkp) == stored("2026-11-01T12:00:00")   # 정오
    assert _clock("12:00", "am", now=now, lkp=lkp) == stored("2026-11-01T00:00:00")   # 자정
    assert _clock("00:00", now=now, lkp=lkp) == stored("2026-11-01T00:00:00")


def test_24h_clock_is_unambiguous(server_tz):
    # "21시 40분" → 21:40 하나뿐 (09:40 후보 없음)
    assert _clock("21:40", now="2026-11-01T01:21:58", lkp="2026-10-31T21:30:00") == \
        stored("2026-10-31T21:40:00")


def test_meridiem_contradicting_24h_clock_is_dropped(server_tz):
    now, lkp = "2026-11-01T23:00:00", "2026-11-01T00:00:00"
    assert _clock("13:00", "am", now=now, lkp=lkp) is None
    assert _clock("00:30", "pm", now=now, lkp=lkp) is None


def test_unknown_meridiem_value_is_dropped(server_tz):
    assert _clock("01:15", "오후", now="2026-11-01T01:21:58", lkp="2026-10-31T21:30:00") is None


@pytest.mark.parametrize(("hour", "meridiem", "hours"), [
    (1, None, (1, 13)), (1, "am", (1,)), (1, "pm", (13,)),
    (11, None, (11, 23)), (11, "pm", (23,)),
    (12, None, (0, 12)), (12, "am", (0,)), (12, "pm", (12,)),
    (0, None, (0,)), (0, "am", (0,)), (0, "pm", ()),
    (13, None, (13,)), (13, "pm", (13,)), (13, "am", ()),
    (23, None, (23,)), (5, "evening", ()),
])
def test_clock_hours(hour, meridiem, hours):
    assert time_resolve.clock_hours(hour, meridiem) == hours


def test_malformed_clock_rejected():
    assert _resolve(time_kind="absolute", time_clock="25:99") is None
    assert _resolve(time_kind="absolute", time_clock="abc") is None
    assert _resolve(time_kind="absolute", time_clock=None) is None
    assert _resolve(time_kind="absolute", time_clock=115) is None
