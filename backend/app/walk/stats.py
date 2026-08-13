"""레벨·배지 규칙과 집계.

규칙을 서버에 두는 이유: 앱에서 계산하면 규칙을 바꿀 때마다 스토어 심사를 거친
앱 배포가 필요하고, 구버전 앱을 쓰는 사용자에게 다른 레벨이 보인다. 화면이
필요로 하는 값을 서버가 완성해서 준다.

**이 수치들은 전부 설계 판단이다.** 문헌이나 실측에서 나온 값이 아니라 참여를
유지할 만한 간격으로 우리가 정한 것이다 — 대외 서술에서 근거가 있는 것처럼
쓰지 않는다. 조정하려면 이 파일 한 곳만 고치면 된다.
"""

from datetime import datetime

from app.schemas.walk import Badge, WalkSession, WalkStats

# (레벨, 진입 누적 km, 표시명). 간격을 앞은 촘촘히 뒤는 성기게 둔다 —
# 초반에 레벨이 오르지 않으면 이탈하고, 후반에 자주 오르면 의미가 옅어진다.
LEVELS: tuple[tuple[int, float, str], ...] = (
    (1, 0.0, "새싹 워커"),
    (2, 3.0, "초보 워커"),
    (3, 10.0, "브론즈 워커"),
    (4, 30.0, "실버 워커"),
    (5, 50.0, "골드 워커"),
    (6, 100.0, "플래티넘 워커"),
)

# 배지 정의. threshold_km 이 있으면 누적 거리로, tip_count 가 있으면 제보 수로 딴다.
_BADGES: tuple[dict, ...] = (
    {"id": "first_tip", "label": "첫 제보자", "icon": "👀", "tip_count": 1},
    {"id": "km_10", "label": "10km 돌파", "icon": "🏃", "threshold_km": 10.0},
    {"id": "km_50", "label": "50km 돌파", "icon": "🥈", "threshold_km": 50.0},
    {"id": "km_100", "label": "100km 돌파", "icon": "⭐", "threshold_km": 100.0},
    {"id": "walk_10", "label": "산책 10회", "icon": "📅", "walk_count": 10},
)


def level_for(total_km: float) -> tuple[int, str, float]:
    """누적 거리 → (레벨, 표시명, 다음 레벨까지 남은 km).

    최고 레벨이면 남은 거리는 0.0 — 앱은 이 값이 0 이면 진행 문구를 감춘다.
    """
    level, label = LEVELS[0][0], LEVELS[0][2]
    remaining = 0.0
    for i, (lv, entry_km, name) in enumerate(LEVELS):
        if total_km >= entry_km:
            level, label = lv, name
            remaining = (LEVELS[i + 1][1] - total_km) if i + 1 < len(LEVELS) else 0.0
        else:
            break
    return level, label, round(max(0.0, remaining), 1)


def badges_for(total_km: float, walk_count: int, tip_count: int) -> list[Badge]:
    """미획득 배지도 함께 반환한다 — 앱이 흐리게 그려 다음 목표를 보여준다."""
    out: list[Badge] = []
    for b in _BADGES:
        if "threshold_km" in b:
            earned = total_km >= b["threshold_km"]
        elif "walk_count" in b:
            earned = walk_count >= b["walk_count"]
        else:
            earned = tip_count >= b["tip_count"]
        out.append(Badge(id=b["id"], label=b["label"], icon=b["icon"], earned=earned))
    return out


def aggregate(
    user_id: str,
    sessions: list[WalkSession],
    tip_count: int,
    now: datetime | None = None,
) -> WalkStats:
    """완료된 산책만 집계한다 — 진행 중인 세션은 거리가 확정되지 않았다."""
    now = now or datetime.now()
    done = [s for s in sessions if s.ended_at is not None]
    total_km = round(sum(s.distance_km for s in done), 2)
    month_km = round(sum(s.distance_km for s in done
                         if s.ended_at.year == now.year
                         and s.ended_at.month == now.month), 2)
    level, label, remaining = level_for(total_km)
    return WalkStats(
        user_id=user_id,
        total_km=total_km,
        month_km=month_km,
        walk_count=len(done),
        tip_count=tip_count,
        level=level,
        level_label=label,
        next_level_km=remaining,
        badges=badges_for(total_km, len(done), tip_count),
        recent=sorted(done, key=lambda s: s.ended_at, reverse=True)[:10],
    )
