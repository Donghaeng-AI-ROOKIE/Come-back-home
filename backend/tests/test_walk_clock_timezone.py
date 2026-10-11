"""The walking engine clock must agree with the SAR prompt on any server timezone.

The app sends incident times as absolute instants; the schema stores them as
server-local naive time. The cloud worker runs in UTC. Before the fix the engine
read naive values as Korean time, so a 10:00 report ran clock rules at 01:00.
"""
import os
import time
from zoneinfo import ZoneInfo

import pytest

from app.phase2.person_walk import korean_clock
from app.schemas.report import MissingReport


def _report(lkp_time):
    return MissingReport.model_validate(dict(
        id="report-clock", persona_id="p-clock", missing_type="dementia",
        lkp={"lat": 37.6652, "lng": 126.7483}, lkp_time=lkp_time,
        situation="", environment_observations=[], behavior_observations=[]))


@pytest.fixture(params=["UTC", "Asia/Seoul", "America/New_York"])
def server_tz(request):
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset unavailable")
    before = os.environ.get("TZ")
    os.environ["TZ"] = request.param
    time.tzset()
    yield request.param
    if before is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = before
    time.tzset()


@pytest.mark.parametrize("sent", ["2026-10-10T10:00:00+09:00", "2026-10-10T01:00:00Z"])
def test_engine_clock_matches_korean_wall_clock(server_tz, sent):
    report = _report(sent)
    assert report.lkp_time.tzinfo is None  # stored as server-local naive time
    assert korean_clock(report.lkp_time).hour == 10
    # Same reading as the SAR prompt and person preparation.
    assert korean_clock(report.lkp_time).hour == report.lkp_time.astimezone(ZoneInfo("Asia/Seoul")).hour


def test_aware_timestamps_convert_directly(server_tz):
    from datetime import datetime
    assert korean_clock(datetime(2026, 10, 10, 1, 0, tzinfo=ZoneInfo("UTC"))).hour == 10
