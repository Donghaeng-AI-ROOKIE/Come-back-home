"""POA 자동 갱신 — 시간이 흐르면 지도도 늙는다.

## 왜 필요한가

경과시간은 이미 예측에 들어간다(반경 상한 = 경과 × 보행속도, 게이지 누적).
그런데 **예측을 다시 돌리는 주체가 없었다.** 5시간 실종으로 신고하면 5시간
시점 지도가 만들어지고, 두 시간이 더 지나 7시간이 돼도 화면은 5시간 지도였다.

재실행 판정(`triggers.should_rerun_phase2`)은 이미 있었다 — 45분 주기, KL 이탈,
새 LKP. 다만 그걸 **주기적으로 물어보는 쪽이 없었다.** `GET /rerun-check` 는
"지금 돌려야 하나요?"를 묻는 엔드포인트인데 아무도 묻지 않았다.

수색은 몇 시간씩 간다. 그동안 실종자는 계속 이동하는데 지도가 멈춰 있으면
골든타임을 다루는 서비스로서 성립하지 않는다.

## 무엇을 하지 않는가

**"못 찾았다"는 정보는 반영하지 않는다.** 알림을 보낸 구역에서 제보가 없었다면
그 구역 확률은 내려가야 한다(수색 이론의 POA 갱신). 그러려면 탐지확률(POD)이
필요한데 시민 몇 명이 실제로 그 구역을 봤는지 알 방법이 없다. 근거 없는 상수를
넣느니 하지 않는다 — 이건 다음 단계다.

그래서 이 모듈이 하는 일은 정확히 하나다: **같은 모델을 더 늦은 시점에서 다시
평가한다.** 베이지안 갱신이 아니다. 대외 서술에서 "지도가 스스로 학습한다"고
말하면 안 된다.
"""

import threading
import time

from app import storage
from app.config import settings
from app.phase3 import triggers
from app.schemas.case import CaseStatus

log = __import__("logging").getLogger(__name__)

# 살아있는 케이스만 대상 — 종결된 사건을 계속 재예측하면 파기 대기 중인
# 개인정보로 연산하는 셈이다(privacy.lifecycle 과 같은 경계).
_ACTIVE = {CaseStatus.intake, CaseStatus.predicted, CaseStatus.searching}


def refresh_due_cases(now=None) -> list[tuple[str, str]]:
    """재실행 조건을 만족한 케이스를 다시 예측한다. 반환: (case_id, 사유) 목록.

    한 건이 실패해도 나머지는 계속한다 — 한 케이스의 LLM 오류가 다른 사건의
    지도를 멈추게 하면 안 된다.
    """
    from app.phase2 import pipeline  # 지연 임포트 — 순환 참조 회피

    done: list[tuple[str, str]] = []
    for case in storage.cases.list():
        if case.status not in _ACTIVE:
            continue
        should, reason = triggers.should_rerun_phase2(case, now=now)
        if not should:
            continue
        try:
            pipeline.run_prediction(case, now=now)
            done.append((case.id, reason))
            log.info("[refresh] %s 재예측 — %s", case.id, reason)
        except Exception as e:  # noqa: BLE001 — 한 건 실패가 나머지를 막지 않는다
            log.warning("[refresh] %s 재예측 실패 — %s: %s", case.id, type(e).__name__, e)
    return done


def _loop(interval_s: float) -> None:
    while True:
        time.sleep(interval_s)
        try:
            refresh_due_cases()
        except Exception as e:  # noqa: BLE001 — 루프가 죽으면 갱신이 영영 멈춘다
            log.warning("[refresh] 주기 검사 실패(계속 진행) — %s", e)


def start(interval_s: float | None = None) -> threading.Thread | None:
    """백그라운드 갱신 시작. 껐거나 이미 돌고 있으면 None.

    검사 주기(기본 5분)와 재실행 주기(`layer2_periodic_minutes`, 45분)는 다르다.
    자주 **묻고** 가끔 **돌린다** — 판정은 싸고 예측은 비싸다(EXAONE 5호출).
    """
    if not settings.poa_refresh_enabled:
        return None
    for t in threading.enumerate():
        if t.name == "poa-refresher":
            return None
    interval = interval_s or settings.poa_refresh_interval_seconds
    th = threading.Thread(target=_loop, args=(interval,), name="poa-refresher", daemon=True)
    th.start()
    log.info("[refresh] POA 자동 갱신 시작 — %.0f초마다 검사", interval)
    return th
