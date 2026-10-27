"""사건의 지역명 — 경보·종결 카드의 "[고양시 일산서구] 킨텍스로".

## 왜 사건에 저장하나
경보 목록(`GET /phase3/alerts`)은 시민 앱이 15초마다 부르는 폴링 경로라 외부 조회를
하지 않고 역지오코딩 캐시만 읽는다(geo/reverse.cached_label). 그 캐시는 **워커
메모리**라 재시작하면 비고, 채우는 일은 신고 접수 때 한 번뿐이었다. 그래서 재시작
뒤에는 진행 중 사건의 경보가 "내 주변 인근", 종결 카드가 "[] 어르신"이 됐다
(10/27 운영, 화면 쪽은 #324 로 막음).

접수 때 얻은 이름을 **그 이름이 가리키는 좌표와 함께** 사건에 저장한다
(Case.area_label, Case.area_label_point). 사건 본문에 들어 있으므로 파기
(privacy.lifecycle.purge_case)와 함께 지워진다. 시민에게 이미 보내던 값이라 새로
모으는 개인정보도 아니다.

## 읽는 순서(area_of)
1. 저장한 이름이 지금 LKP 의 것이면 그것.
2. 아니면 지금 LKP 의 캐시 이름 — 층2 제보로 LKP 가 옮겨 간 경우, 그리고 이 변경 전에
   접수돼 저장한 이름이 없는 사건(이전과 같은 동작).
3. 그것도 없으면 저장한 옛 이름 — LKP 가 옮겨 갔어도 같은 사건의 지역이다. "내 주변"
   보다 낫다.
어느 단계도 외부 조회를 하지 않는다.
"""

from __future__ import annotations

import threading
import time

from app import storage
from app.config import settings
from app.geo import reverse
from app.schemas.case import Case
from app.schemas.common import GeoPoint

#: 접수 때 이름 조회를 몇 번까지 해 보는가. 실패한 좌표는 reverse 가 10분
#: (_FAIL_TTL_SEC) 동안 다시 묻지 않으므로 그보다 조금 길게 쉬었다 다시 묻는다.
ATTEMPTS = 3
RETRY_WAIT_SEC = 610.0


def _same_point(a: GeoPoint | None, b: GeoPoint | None) -> bool:
    """역지오코딩 캐시와 같은 반올림(소수 4자리, 약 11m)으로 같은 자리인가."""
    if a is None or b is None:
        return False
    return (round(a.lat, 4), round(a.lng, 4)) == (round(b.lat, 4), round(b.lng, 4))


def area_of(case: Case) -> str:
    """경보·종결 응답의 지역명. 폴링 경로라 네트워크를 타지 않는다(위 순서)."""
    if case.area_label and _same_point(case.area_label_point, case.lkp):
        return case.area_label
    return reverse.cached_label(case.lkp) or case.area_label


@storage.serialize_case
def _store(case_id: str, point: GeoPoint, label: str) -> None:
    """사건 잠금 안에서 저장한다 — 재예측이 같은 사건 객체를 제자리에서 바꾸는 중에
    덜 바뀐 사건을 디스크에 쓰지 않게(storage.saved_copy 주석 참고)."""
    case = storage.cases.get(case_id)
    if case is None:
        return   # 그사이 파기됐으면 되살리지 않는다
    case.area_label = label
    case.area_label_point = point
    storage.cases.save(case_id, case)


def remember(case_id: str, *, sleep=time.sleep) -> None:
    """이 사건 LKP 의 이름을 얻어(외부 조회) 사건에 저장한다. 접수 스레드에서 부른다.

    얻는 과정에서 역지오코딩 캐시도 채워진다(예전 reverse.warm 과 같은 효과).
    실패하면 ATTEMPTS 번까지 다시 해 본다. 끝내 못 얻으면 저장하지 않는다 — 앱은
    "내 주변"으로 물러난다. 좌표에서 이름을 지어내지 않는다.
    """
    for attempt in range(ATTEMPTS):
        case = storage.cases.get(case_id)
        if case is None:
            return
        point = case.lkp
        if case.area_label and _same_point(case.area_label_point, point):
            return
        try:
            label = reverse.label_for(point, fallback="")
        except Exception:  # noqa: BLE001 — 이름 조회 실패가 접수 스레드를 죽이면 안 된다
            label = ""
        if label:
            _store(case_id, point, label)
            return
        # 워커 로그는 WARNING 이상만 남기므로 print 로 낸다. 사건 ID 와 횟수만 — 좌표는
        # 남기지 않는다. 10/27 운영에서 재시작 없이도 접수 2분 뒤까지 이름이 비어 있었는데
        # 조회 실패가 어디에도 기록되지 않아 원인을 알 수 없었다.
        print(f"[area] 지역명 조회 실패 case={case_id} attempt={attempt + 1}/{ATTEMPTS}")
        if attempt + 1 < ATTEMPTS:
            sleep(RETRY_WAIT_SEC)


def start(case_id: str) -> None:
    """접수 직후 별도 스레드로 remember 를 돌린다 — 골든타임에 외부 조회를 기다리지 않는다."""
    if not settings.reverse_geocode_on_intake:
        return
    threading.Thread(target=remember, args=(case_id,), daemon=True,
                     name=f"case-area-{case_id}").start()
