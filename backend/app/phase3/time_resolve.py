"""제보 구조화 결과(time_kind/time_minutes_ago/time_clock) → 실제 목격 datetime.

가드레일 패턴: LLM 은 시민이 명시한 값만 뽑고("30분 전", "3시쯤"), 상대→절대시각
산술은 여기서 결정론적으로 계산한다(app.llm.tip_llm.structure_tip 참고).

안전 클램프: 계산된 시각이 [lkp_time, now] 창을 벗어나면 버리고 None을 반환한다.
seen_at 은 층2(has_specific_location_time)에서 새 LKP 시각으로 그대로 쓰이므로,
실종 이전 목격("lkp_time 이전")이나 미래 목격("now 이후")은 명백한 오추출·산술
오류다 — 이런 값이 새 앵커를 오염시키지 않게 여기서 걸러 층1로 안전하게 강등한다.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

_CLOCK_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def resolve_seen_at(
    structured: dict,
    *,
    now: datetime,
    lkp_time: datetime,
) -> datetime | None:
    """time_kind/값 → 목격 datetime. vague/none/파싱 실패/창 밖 → None(층1 유지)."""
    kind = structured.get("time_kind")
    cand: datetime | None = None

    if kind == "relative":
        minutes = structured.get("time_minutes_ago")
        if isinstance(minutes, int) and not isinstance(minutes, bool) and minutes >= 0:
            cand = now - timedelta(minutes=minutes)
    elif kind == "absolute":
        m = _CLOCK_RE.match(str(structured.get("time_clock") or ""))
        if m:
            hour, minute = int(m.group(1)), int(m.group(2))
            cand = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if cand > now:   # 아직 안 온 시각으로 계산되면 어제로 — "3시"는 항상 과거
                cand -= timedelta(days=1)
    # kind == "vague" / "none" / 그 외 → cand 는 None 유지

    if cand is None:
        return None
    if cand > now or cand < lkp_time:   # 미래·실종 이전 목격은 불가능 → 오염 방지로 버림
        return None
    return cand
