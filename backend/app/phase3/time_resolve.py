"""제보 구조화 결과(time_kind/time_minutes_ago/time_clock/time_meridiem) → 실제 목격 datetime.

가드레일 패턴: LLM 은 시민이 명시한 값만 뽑고("30분 전", "3시쯤", "오후"), 상대→절대시각
산술과 오전/오후 판단은 여기서 결정론적으로 계산한다(app.llm.tip_llm.structure_tip 참고).

시계 시각은 **한국 시간**이다. 시민은 "1시 15분"을 한국 벽시계로 말한다. 그런데 저장 시각
(now·lkp_time·seen_at)은 서버 로컬 naive 이고(schemas.common._to_local_naive), 운영 컨테이너는
UTC 다. 예전 코드는 `now.replace(hour=…)` 로 시계 시각을 서버 시계(UTC)에 그대로 꽂아
9시간 어긋났다(11/01 01:21 KST 운영 실측: "1시 15분" → 22:15 KST 로 저장). 그래서 시계 시각은
Asia/Seoul 로 놓은 뒤 저장 형식으로 바꿔 비교·반환한다(phase2.person_walk.korean_clock 과 같은
규칙 — naive 에 astimezone 을 부르면 서버 로컬로 읽는다).

오전/오후를 말하지 않은 1~12시는 두 시각(h, h+12)을 모두 후보로 두고, 오늘·어제(한국 날짜)
중에서 [lkp_time, now] 창 안의 가장 최근 시각을 고른다. 시민이 "1시 15분쯤 봤어요"라고 하면
대개 가장 최근의 1시 15분이기 때문이다.

안전 클램프: 계산된 시각이 [lkp_time, now] 창을 벗어나면 버리고 None을 반환한다.
seen_at 은 층2(has_specific_location_time)에서 새 LKP 시각으로 그대로 쓰이므로,
실종 이전 목격("lkp_time 이전")이나 미래 목격("now 이후")은 명백한 오추출·산술
오류다 — 이런 값이 새 앵커를 오염시키지 않게 여기서 걸러 층1로 안전하게 강등한다.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from datetime import time as clock_time
from zoneinfo import ZoneInfo

_CLOCK_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_KST = ZoneInfo("Asia/Seoul")
MERIDIEMS = ("am", "pm")


def clock_hours(hour: int, meridiem: str | None) -> tuple[int, ...]:
    """시민이 말한 시(0~23) + 오전/오후 → 가능한 24시간제 시 후보.

    - 13~23시·0시: 24시간제로 말한 값이라 그대로 하나. 오전/오후가 이와 어긋나면
      ("오전 13시", "오후 0시") 어느 쪽이 맞는지 알 수 없으므로 후보 없음.
    - 1~12시 + 오전/오후: 하나. 12시는 오전이면 0시(자정), 오후면 12시(정오).
    - 1~12시 + 오전/오후 없음: 두 개(h, h+12). 고르는 건 resolve_seen_at 의 창이다.
    """
    if meridiem is not None and meridiem not in MERIDIEMS:
        return ()
    if hour >= 13:
        return () if meridiem == "am" else (hour,)
    if hour == 0:
        return () if meridiem == "pm" else (0,)
    base = hour % 12   # 12시 → 0
    if meridiem == "am":
        return (base,)
    if meridiem == "pm":
        return (base + 12,)
    return (base, base + 12)


def _to_stored(korean: datetime, like: datetime) -> datetime:
    """한국 시각(aware) → `like`(now)와 같은 저장 형식. naive 면 서버 로컬 naive."""
    if like.tzinfo is None:
        return korean.astimezone().replace(tzinfo=None)
    return korean.astimezone(like.tzinfo)


def _resolve_clock(clock: str, meridiem: str | None, *, now: datetime,
                   lkp_time: datetime) -> datetime | None:
    """시계 시각(한국 시간) → 창 [lkp_time, now] 안의 가장 최근 후보. 없으면 None."""
    m = _CLOCK_RE.match(clock)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    now_kst = now.astimezone(_KST)          # naive 는 서버 로컬로 읽힌다
    lkp_kst = lkp_time.astimezone(_KST)
    today = now_kst.date()
    candidates = [
        datetime.combine(day, clock_time(h, minute), tzinfo=_KST)
        for h in clock_hours(hour, meridiem)
        for day in (today, today - timedelta(days=1))   # 가장 최근 후보는 늘 24시간 안
    ]
    inside = [c for c in candidates if lkp_kst <= c <= now_kst]
    if not inside:
        return None
    return _to_stored(max(inside), now)


def resolve_seen_at(
    structured: dict,
    *,
    now: datetime,
    lkp_time: datetime,
) -> datetime | None:
    """time_kind/값 → 목격 datetime. vague/none/파싱 실패/창 밖 → None(층1 유지).

    now·lkp_time 은 저장 형식(서버 로컬 naive)이고, 반환값도 같은 형식이다.
    """
    kind = structured.get("time_kind")
    cand: datetime | None = None

    if kind == "relative":
        # "N분 전"은 시계와 무관한 경과 시간이라 저장 시각에서 그대로 뺀다.
        minutes = structured.get("time_minutes_ago")
        if isinstance(minutes, int) and not isinstance(minutes, bool) and minutes >= 0:
            cand = now - timedelta(minutes=minutes)
    elif kind == "absolute":
        clock = structured.get("time_clock")
        if isinstance(clock, str):
            return _resolve_clock(clock, structured.get("time_meridiem"),
                                  now=now, lkp_time=lkp_time)
    # kind == "vague" / "none" / 그 외 → cand 는 None 유지

    if cand is None:
        return None
    if cand > now or cand < lkp_time:   # 미래·실종 이전 목격은 불가능 → 오염 방지로 버림
        return None
    return cand
