"""종결 사건 조회 — 시민 화면의 '상황 종료' 카드와 상세 화면.

핵심 계약:
  - 제보 수는 폐기 판정(discard)을 뺀 수다 ("여러분의 제보 N건 덕분에…")
  - 수색 시간은 신고(사건 생성)부터 종결까지의 분이다
  - 발견(found)만 보인다 — 신고 철회는 "무사히 돌아갔습니다"가 사실이 아니다
  - 이름·최종 목격 위치·인상착의는 싣지 않는다
"""

from datetime import UTC, datetime, timedelta

import pytest

from app import storage
from app.api import phase3 as phase3_api
from app.config import settings
from app.geo import h3grid
from app.phase1 import intake
from app.phase3 import alerts
from app.privacy import lifecycle
from app.schemas.case import CloseReason
from app.schemas.common import GeoPoint
from app.schemas.persona import Persona, PersonaType
from app.schemas.report import Appearance
from app.schemas.tip import Tip, TipDecision

LKP = GeoPoint(lat=37.6061, lng=127.0106)   # 정릉동


def _cell7(p: GeoPoint) -> str:
    return h3grid.cell_of(p, settings.push_target_res)


def _make_case():
    case = intake.create_report(
        missing_type=PersonaType.dementia,
        lkp=LKP,
        # 시간대가 붙은 시각을 줘도 스키마(LocalNaiveDT)가 로컬 naive 로 바꾼다.
        lkp_time=datetime.now(UTC) - timedelta(hours=1),
    )
    case.report.appearance = Appearance(summary="회색 점퍼에 검은 바지")
    storage.cases.save(case.id, case)
    return case


def _tip(case, i: int, decision: TipDecision | None) -> Tip:
    return Tip(id=f"t{i}", case_id=case.id, text="정릉천 산책로에서 봤어요", decision=decision)


def _close(case, reason=CloseReason.found, now=None):
    lifecycle.close_case(case, reason, now=now)
    return storage.cases.get(case.id)


@pytest.fixture(autouse=True)
def _clean():
    storage.reset_for_tests()
    yield
    storage.reset_for_tests()


def test_discarded_tips_are_not_counted():
    """폐기된 제보는 수색에 반영되지 않았다 — "덕분에"에 넣으면 사실이 아니다."""
    case = _make_case()
    case.tips = [
        _tip(case, 1, TipDecision.discard),
        _tip(case, 2, TipDecision.layer1),
        _tip(case, 3, TipDecision.layer2),
        _tip(case, 4, TipDecision.discard),
    ]
    storage.cases.save(case.id, case)
    _close(case)

    got = phase3_api.list_resolved_alerts(_cell7(LKP))[0]
    assert got["tip_count"] == 2


def test_no_tips_counts_zero():
    _close(_make_case())
    assert phase3_api.list_resolved_alerts(_cell7(LKP))[0]["tip_count"] == 0


def test_search_minutes_runs_from_report_to_close():
    case = _make_case()
    # created_at 은 접수 순간(로컬 naive)으로 채워져 있다 — 거기서 세 시간 당긴다.
    reported = case.created_at - timedelta(hours=3)
    case.created_at = reported
    storage.cases.save(case.id, case)
    _close(case, now=reported + timedelta(hours=2, minutes=5, seconds=40))

    got = phase3_api.list_resolved_alerts(_cell7(LKP))[0]
    assert got["search_minutes"] == 125, "초는 버리고 분만 센다"


def test_search_minutes_is_none_without_close_time():
    """종결 시각이 없으면 계산할 수 없다 — 0 으로 지어내지 않는다."""
    case = _make_case()
    assert alerts.describe_resolved(case)["search_minutes"] is None


def test_search_minutes_is_none_when_close_precedes_report():
    case = _make_case()
    case = _close(case, now=case.created_at - timedelta(minutes=3))
    assert alerts.describe_resolved(case)["search_minutes"] is None


def test_withdrawn_case_stays_out():
    """신고 철회는 목록에 없다 — 카드가 "무사히 돌아갔습니다"라고 말하기 때문이다."""
    withdrawn = _make_case()
    found = _make_case()
    _close(withdrawn, CloseReason.withdrawn)
    _close(found, CloseReason.found)

    out = phase3_api.list_resolved_alerts(_cell7(LKP))
    assert [a["case_id"] for a in out] == [found.id]


def test_payload_has_no_name_lkp_or_appearance():
    """종결 응답은 주변 시민 누구나 받는다 — 찾는 데 쓰던 정보는 여기서 끝난다."""
    case = _make_case()
    persona = Persona(id="p1", type=PersonaType.dementia, name="김순자", age=82, home=LKP)
    case.report.persona_id = persona.id
    storage.personas.save(persona.id, persona)
    storage.cases.save(case.id, case)
    _close(case)

    got = phase3_api.list_resolved_alerts(_cell7(LKP))[0]
    assert set(got) == {
        "case_id", "area", "age", "closed_at", "close_reason",
        "tip_count", "search_minutes",
        "target_cells", "target_res", "targeting_policy",
    }
    for key in ("name", "lkp", "lkp_time", "appearance", "appearance_colors", "summary"):
        assert key not in got
    blob = repr(got)
    assert persona.name not in blob, "실명이 종결 응답에 실렸다"
    assert "회색 점퍼" not in blob, "인상착의가 종결 응답에 실렸다"
    assert got["age"] == 82
