"""활성 경보 조회 — 앱을 직접 열었을 때 관문이 판정할 대상.

핵심 계약:
  - 서버가 **발송과 같은 기준으로** 고른다 (전체 목록을 내려주지 않는다)
  - 칸을 모르면 빈 목록 (fail-closed)
  - 종결 사건은 사라진다
  - 페이로드 모양이 푸시와 같다 (관문이 같은 코드로 판정하므로)
"""

from datetime import datetime, timedelta

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

LKP = GeoPoint(lat=37.6061, lng=127.0106)   # 정릉동
FAR = GeoPoint(lat=35.1796, lng=129.0756)   # 부산


def _cell7(p: GeoPoint) -> str:
    return h3grid.cell_of(p, settings.push_target_res)


def _make_case(lkp: GeoPoint = LKP, hours_ago: float = 0.5):
    case = intake.create_report(
        missing_type=PersonaType.dementia,
        lkp=lkp,
        lkp_time=datetime.now() - timedelta(hours=hours_ago),
    )
    case.report.appearance = Appearance(summary="회색 점퍼에 검은 바지")
    storage.cases.save(case.id, case)
    return case


@pytest.fixture(autouse=True)
def _clean():
    storage.reset_for_tests()
    yield
    storage.reset_for_tests()


# ── 타겟팅 ──────────────────────────────────────────────────


def test_returns_alert_for_matching_cell():
    case = _make_case()
    out = phase3_api.list_active_alerts(_cell7(LKP))
    assert [a["case_id"] for a in out] == [case.id]


def test_excludes_alert_for_other_cell():
    """🚨 이게 깨지면 조회가 무차별 브로드캐스트가 된다 — 발송에서 res7 로
    최소화해 둔 것을 조회 경로가 조용히 무효화하는 지점."""
    _make_case()
    assert phase3_api.list_active_alerts(_cell7(FAR)) == []


def test_no_cell_returns_empty():
    """위치를 모르면 어느 사건이 이 사람 것인지 고를 수 없다 — 아무거나
    돌려주면 틀린 사건을 보여주게 된다(fail-closed)."""
    _make_case()
    assert phase3_api.list_active_alerts(None) == []
    assert phase3_api.list_active_alerts("") == []


def test_closed_case_disappears():
    case = _make_case()
    assert phase3_api.list_active_alerts(_cell7(LKP))  # 종결 전엔 보인다
    lifecycle.close_case(case, CloseReason.found)
    storage.cases.save(case.id, case)
    assert phase3_api.list_active_alerts(_cell7(LKP)) == []


def test_two_cases_separate_by_location():
    """사람마다 다른 실종자가 뜬다 — fail-closed 의 근거이자, 목 경보 하나로는
    재현할 수 없던 상황."""
    near = _make_case(LKP)
    far = _make_case(FAR)

    assert [a["case_id"] for a in phase3_api.list_active_alerts(_cell7(LKP))] == [near.id]
    assert [a["case_id"] for a in phase3_api.list_active_alerts(_cell7(FAR))] == [far.id]


def test_sorted_by_issued_at_desc():
    """관문은 첫 항목부터 본다 — 최근 것이 앞에 와야 한다."""
    old = _make_case()
    old.created_at = datetime.now() - timedelta(hours=3)
    storage.cases.save(old.id, old)
    new = _make_case()

    out = phase3_api.list_active_alerts(_cell7(LKP))
    assert [a["case_id"] for a in out] == [new.id, old.id]


# ── 표현 ────────────────────────────────────────────────────


def test_payload_shape_matches_push():
    """앱은 푸시와 조회 두 경로로 경보를 알게 되고 **관문 판정은 같은 코드**가
    한다. 모양이 갈리면 "알림으로 온 건 뜨는데 앱을 열면 안 뜬다"가 된다."""
    case = _make_case()
    got = phase3_api.list_active_alerts(_cell7(LKP))[0]
    sent = alerts.send_alerts(case.id, alerts.select_reflex_cells(case.lkp), "요약", kind="reflex")

    # 대상 구역 계약이 같아야 한다 — 여기가 갈리면 판정이 어긋난다.
    shared = {"case_id", "kind", "target_cells", "target_res"}
    assert shared <= set(got) and shared <= set(sent)
    assert got["target_cells"] == sent["target_cells"]
    assert got["target_res"] == sent["target_res"]

    # ⚠️ `appearance` 는 두 경로에서 뜻이 다르다 — 푸시는 알림 본문에 넣을 **요약
    # 문자열**, 조회는 시민 화면 카드가 칩으로 그리는 **항목 배열**이다. 조회 쪽
    # 요약은 `summary` 에 있다. 이름이 같아 헷갈리기 쉬워 여기에 못박아 둔다.
    assert isinstance(sent["appearance"], str)
    assert isinstance(got["appearance"], list)
    assert isinstance(got["summary"], str)


def test_kind_is_reflex_before_prediction():
    """POA 가 없으면 신고 직후 골든타임 구간 — 1차 안전반경."""
    _make_case()
    assert phase3_api.list_active_alerts(_cell7(LKP))[0]["kind"] == "reflex"


def test_kind_becomes_poa_after_prediction():
    case = _make_case()
    case.current_poa = {c: 1 / 19 for c in h3grid.cells_within_k(LKP, 2)}
    storage.cases.save(case.id, case)
    assert phase3_api.list_active_alerts(_cell7(LKP))[0]["kind"] == "poa"


def test_severity_follows_elapsed_time():
    """골든타임 안이면 빨강, 넘으면 앰버. 프론트 카운트다운과 같은 창을 쓴다."""
    _make_case(hours_ago=0.1)
    assert phase3_api.list_active_alerts(_cell7(LKP))[0]["severity"] == "critical"

    storage.reset_for_tests()
    _make_case(hours_ago=5)
    assert phase3_api.list_active_alerts(_cell7(LKP))[0]["severity"] == "active"


def test_issued_at_follows_last_alert():
    """"그만 볼래요"는 억제 시각보다 **나중에 발령된** 경보에만 뚫린다
    (utils/alertGate.shouldGate). 새 알림이 나갔으면 그 시각이어야 관문이 재무장한다."""
    case = _make_case()
    sent_at = datetime.now() + timedelta(minutes=5)
    case.last_alert_at = sent_at
    storage.cases.save(case.id, case)
    assert phase3_api.list_active_alerts(_cell7(LKP))[0]["issued_at"] == sent_at


def test_broken_case_does_not_hide_others():
    """🚨 사건 하나가 깨졌다고 다른 사건의 경보까지 안 보이면 골든타임에 최악이다.

    실제로 손상된 POA 셀 id 하나가 엔드포인트를 통째로 500 으로 만들었다.
    """
    broken = _make_case()
    broken.current_poa = {"not-a-cell": 1.0}     # h3 가 파싱 못 하는 값
    storage.cases.save(broken.id, broken)
    healthy = _make_case()

    out = phase3_api.list_active_alerts(_cell7(LKP))
    assert [a["case_id"] for a in out] == [healthy.id]


def test_payload_fields_are_fixed():
    """응답 필드를 못박는다 — 여기 없는 것이 늘면 시민 화면 노출 범위가 조용히 넓어진다."""
    _make_case()
    got = phase3_api.list_active_alerts(_cell7(LKP))[0]
    assert set(got) == {
        "case_id", "issued_at", "area", "severity", "kind",
        "target_cells", "target_res",
        "summary", "matched_person_id", "age", "appearance", "appearance_colors",
        "lkp", "lkp_time",
    }


def test_no_name_or_condition_in_payload():
    """🚨 조회 응답은 시민 앱으로 그대로 간다.

    **실명이 실리면 안 된다** — 이 응답은 주변 시민 누구나 받으므로 나이·인상착의로
    충분하고, 이름까지 뿌리면 목적(발견 제보)을 넘는 제공이 된다.
    수색 탭 안내 문구에는 이름이 들어가는데 그건 노출 범위가 다르다
    (storytelling.ToneParams.name 주석 참고) — 두 경로를 헷갈리지 않게 여기서 고정한다.

    진단 유형(missing_type)도 실리면 안 된다(§23 민감정보).
    """
    case = _make_case()
    persona = Persona(id=case.report.persona_id or "p1", type=PersonaType.dementia,
                      name="김순자", age=82, home=LKP)
    case.report.persona_id = persona.id
    storage.personas.save(persona.id, persona)
    storage.cases.save(case.id, case)

    got = phase3_api.list_active_alerts(_cell7(LKP))[0]
    blob = repr(got)
    assert persona.name not in blob, "실명이 조회 응답에 실렸다"
    assert case.report.missing_type.value not in blob
    assert got["age"] == 82, "나이는 시민 화면 카드가 쓰므로 와야 한다"


def test_area_is_blank_when_not_geocoded():
    """지역명은 **캐시에 있을 때만** 실린다.

    좌표에서 동 이름을 지어내지 않는다는 원칙은 그대로다. 달라진 것은 "이름을 아예
    모른다"에서 "미리 조회해 둔 것만 쓴다"로 바뀐 것 — 조회는 신고 접수 때 별도
    스레드가 하고(phase1.intake), 이 폴링 경로는 캐시만 읽는다. 테스트 환경은
    역지오코딩이 꺼져 있으므로(conftest) 항상 빈 문자열이어야 한다.
    """
    _make_case()
    assert phase3_api.list_active_alerts(_cell7(LKP))[0]["area"] == ""


def test_area_uses_cached_label_without_network(monkeypatch):
    """캐시에 이름이 있으면 그대로 실린다 — 이 경로는 외부 호출을 하지 않는다."""
    from app.geo import reverse

    case = _make_case()
    monkeypatch.setattr(reverse, "cached_label", lambda p: "[서울특별시 성북구] 정릉로")
    # 네트워크를 타는 경로가 호출되면 즉시 실패시킨다.
    monkeypatch.setattr(reverse, "label_for", lambda *a, **k: pytest.fail("폴링 경로가 외부 조회를 했다"))

    got = phase3_api.list_active_alerts(_cell7(LKP))[0]
    assert got["case_id"] == case.id
    assert got["area"] == "[서울특별시 성북구] 정릉로"


def test_appearance_colors_are_tags_not_images():
    """실루엣 아바타용 색 태그가 실린다 — 백엔드는 이미지를 만들지 않는다.

    사진을 받지 않는 설계(08-07)라 앱이 사람 사진을 띄우면 그건 실종자가 아닌
    남의 얼굴이 된다. 그 자리를 채우는 유일한 근거가 이 색 태그다.
    """
    _make_case()
    got = phase3_api.list_active_alerts(_cell7(LKP))[0]
    assert set(got["appearance_colors"]) == {"top", "bottom", "shoes"}
    assert all(isinstance(v, str) and v for v in got["appearance_colors"].values())
