"""POA 자동 갱신 — 시간이 흐르면 지도도 다시 계산되는가.

경과시간은 예전부터 예측에 들어갔다(반경 상한 = 경과 × 보행속도). 그런데
**재실행을 요청하는 주체가 없어서**, 신고 시점 지도가 수색 내내 그대로였다.
5시간 실종으로 신고하면 7시간이 돼도 5시간 지도를 보고 있었다.

여기서 고정하는 것은 두 가지다.
1. 조건을 만족한 케이스만 다시 돈다 (종결·미도래는 건드리지 않는다)
2. 다시 돌면 **더 늦은 시점**의 지도가 된다 (경과시간이 실제로 늘어난다)
"""

from datetime import datetime, timedelta

from app import storage
from app.config import settings
from app.phase2 import refresher
from app.schemas.case import Case, CaseStatus, CloseReason
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.report import MissingReport

LKP = GeoPoint(lat=37.6061, lng=127.0106)


def _case(cid: str, *, lkp_hours_ago: float, last_sim_min_ago: float | None) -> Case:
    now = datetime.now()  # noqa: DTZ005 — Case 시각 필드는 naive(LocalNaiveDT)
    case = Case(
        id=cid,
        report=MissingReport(id=f"r-{cid}", persona_id=None,
                             missing_type=PersonaType.dementia, lkp=LKP,
                             lkp_time=now - timedelta(hours=lkp_hours_ago)),
        lkp=LKP, lkp_time=now - timedelta(hours=lkp_hours_ago),
    )
    if last_sim_min_ago is not None:
        case.status = CaseStatus.predicted
        case.last_sim_at = now - timedelta(minutes=last_sim_min_ago)
        case.current_poa = {"8930e1c30c7ffff": 1.0}
        case.baseline_poa = dict(case.current_poa)
    storage.cases.save(cid, case)
    return case


def test_periodic_case_is_refreshed():
    """주기(45분)를 넘긴 케이스는 다시 예측된다 — 이게 없어서 지도가 멈춰 있었다."""
    storage.cases.delete("refresh-due")
    _case("refresh-due", lkp_hours_ago=5,
          last_sim_min_ago=settings.layer2_periodic_minutes + 5)

    done = refresher.refresh_due_cases()

    assert any(cid == "refresh-due" for cid, _ in done), "주기 도달 케이스가 갱신되지 않았다"
    storage.cases.delete("refresh-due")


def test_fresh_case_is_left_alone():
    """방금 돈 케이스는 건드리지 않는다 — 매 검사마다 재예측하면 EXAONE 낭비다."""
    storage.cases.delete("refresh-fresh")
    _case("refresh-fresh", lkp_hours_ago=5, last_sim_min_ago=1)

    done = refresher.refresh_due_cases()

    assert all(cid != "refresh-fresh" for cid, _ in done)
    storage.cases.delete("refresh-fresh")


def test_closed_case_is_never_refreshed():
    """종결 케이스는 재예측하지 않는다.

    파기 대기 중인 개인정보로 연산하는 셈이고, run_prediction 이 status 를
    predicted 로 덮어써 종결 자체를 되살린다(privacy.lifecycle 과 같은 경계).
    """
    storage.cases.delete("refresh-closed")
    case = _case("refresh-closed", lkp_hours_ago=5,
                 last_sim_min_ago=settings.layer2_periodic_minutes + 60)
    case.status = CaseStatus.found
    case.close_reason = CloseReason.found
    case.closed_at = datetime.now()  # noqa: DTZ005 — 위와 같은 이유
    storage.cases.save(case.id, case)

    done = refresher.refresh_due_cases()

    assert all(cid != "refresh-closed" for cid, _ in done)
    assert storage.cases.get("refresh-closed").status is CaseStatus.found
    storage.cases.delete("refresh-closed")


def test_refresh_moves_prediction_forward_in_time():
    """재예측하면 **더 늦은 시점**의 지도가 된다.

    이게 이 기능의 전부다 — 같은 모델을 더 늦은 t 에서 평가한다.
    (베이지안 갱신이 아니다. "못 찾았다"는 정보는 아직 반영하지 않는다.)
    """
    storage.cases.delete("refresh-forward")
    case = _case("refresh-forward", lkp_hours_ago=5,
                 last_sim_min_ago=settings.layer2_periodic_minutes + 5)
    before = case.last_sim_at
    before_elapsed = (before - case.lkp_time).total_seconds() / 3600.0

    refresher.refresh_due_cases()

    after_case = storage.cases.get("refresh-forward")
    after_elapsed = (after_case.last_sim_at - after_case.lkp_time).total_seconds() / 3600.0
    assert after_case.last_sim_at > before, "재예측 시각이 갱신되지 않았다"
    assert after_elapsed > before_elapsed, "더 늦은 시점의 지도여야 한다"
    storage.cases.delete("refresh-forward")


def test_start_is_idempotent_and_respects_setting(monkeypatch):
    """중복 기동 금지 + 설정으로 끌 수 있어야 한다(테스트·오프라인 환경)."""
    monkeypatch.setattr(settings, "poa_refresh_enabled", False)
    assert refresher.start() is None, "꺼져 있는데 스레드가 떴다"
