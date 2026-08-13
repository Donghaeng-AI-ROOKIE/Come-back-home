"""Phase 3 — 익명 동시 참여자 수("지금 N명이 함께 보고 있어요").

쇼핑앱의 "n명이 보고 있습니다"와 같은 구조. 목적은 수색 참여의 사회적 증거
(social proof)이지 사용자 추적이 아니다.

## 왜 이렇게 단순한가

사용자 식별도, 실시간 인프라(WebSocket/Redis pub-sub)도 필요 없다. 필요한 건
"최근 T초 안에 이 사건 화면을 열어둔 앱 인스턴스가 몇 개인가" 하나뿐이고,
그건 불투명 토큰 → 만료시각 dict 로 끝난다. 폴링은 프론트의
react-query `refetchInterval` 이 담당한다.

## 개인정보 설계 (검토 결론 반영)

- **토큰은 클라이언트가 만든 난수**다. 서버는 그것이 누구인지 모르고, 알 방법도
  주지 않는다. 위치·제보 이력·기기 식별자 그 무엇도 붙이지 않는다.
- **집계는 사건 단위로만 한다. 셀 단위 집계는 금지.** 셀 단위 카운트는 곧
  "그 셀에 사람이 있다"는 위치 정보가 되고, 셀이 좁을수록(res9 ≈ 0.1km²)
  카운트 1은 특정 개인의 현재 위치와 다를 바 없어진다. 온디바이스 지오펜싱으로
  시민 위치를 서버에 안 올린다는 전제 전체가 여기서 무너지므로, 이 모듈은
  좌표를 **인자로도 받지 않는다**.
- TTL 이 지나면 흔적이 사라진다. 영속화하지 않는다.

## 운영 제약 ⚠️

모듈 레벨 dict 이므로 **단일 프로세스에서만 정확하다**. `run_dashboard.ps1` 은
uvicorn 을 `--workers` 없이 띄우므로 현재 전제는 성립한다. 워커를 늘리거나
gunicorn 으로 바꾸면 워커마다 자기 dict 만 보여 카운트가 1/N 로 쪼개진다 —
그때는 이 모듈의 함수 시그니처를 유지한 채 저장소만 Redis(키 `presence:{case}`,
`ZADD` + `ZREMRANGEBYSCORE`)로 갈아끼우면 된다.
"""

import time

from app.config import settings

# case_id → {token: 만료 monotonic 시각}
#
# 벽시계(time.time)가 아니라 time.monotonic 을 쓰는 이유: NTP 보정·서머타임으로
# 벽시계는 뒤로 점프할 수 있고, 그러면 이미 만료된 토큰이 되살아나거나(과다 집계)
# 살아있는 토큰이 즉시 만료된다(과소 집계). 단조 시계는 그런 점프가 없다.
_watchers: dict[str, dict[str, float]] = {}


def _prune(case_id: str, now: float) -> dict[str, float]:
    """만료 토큰 제거 후 해당 사건의 살아있는 토큰 맵 반환.

    별도 정리 태스크 없이 읽기·쓰기 시점에 게으르게 청소한다 — 조회되지 않는
    사건은 청소할 이유도 없고, 백그라운드 루프는 이 규모에 과하다.
    """
    live = {t: exp for t, exp in _watchers.get(case_id, {}).items() if exp > now}
    if live:
        _watchers[case_id] = live
    else:
        # 빈 dict 를 남기면 사건 수만큼 껍데기가 영구 누적된다.
        _watchers.pop(case_id, None)
    return live


def heartbeat(case_id: str, token: str, ttl_sec: float | None = None) -> int:
    """토큰의 생존을 갱신하고 현재 동시 참여자 수를 반환.

    프론트는 이 하나만 주기 호출하면 된다 — 갱신과 조회를 한 번에 끝내
    폴링 왕복을 절반으로 줄인다.
    """
    ttl_sec = settings.presence_ttl_sec if ttl_sec is None else ttl_sec
    now = time.monotonic()
    live = _prune(case_id, now)

    # 토큰 수 상한: 클라이언트가 매 요청 새 토큰을 보내면(버그든 악의든) dict 가
    # 무한히 자란다. 상한에 걸리면 신규 토큰만 거절하고 기존 토큰 갱신은 계속
    # 받는다 — 카운트가 포화될지언정 메모리가 터지거나 기존 참여자가 사라지지 않는다.
    if token not in live and len(live) >= settings.presence_max_tokens_per_case:
        return len(live)

    live[token] = now + ttl_sec
    _watchers[case_id] = live
    return len(live)


def count(case_id: str) -> int:
    """현재 동시 참여자 수 (갱신 없이 조회만)."""
    return len(_prune(case_id, time.monotonic()))


def clear(case_id: str) -> None:
    """사건 종결·파기 시 호출. 종결된 사건의 참여자 수는 의미가 없고,
    남겨두면 TTL 만료까지 유령 카운트가 표시된다."""
    _watchers.pop(case_id, None)


def reset() -> None:
    """테스트 격리용 — 모듈 전역 상태를 비운다."""
    _watchers.clear()
