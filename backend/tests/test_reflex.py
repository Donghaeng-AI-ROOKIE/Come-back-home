"""1차 안전반경 (Reflex Tasking) — 신고 직후 POA 없이 IPP 주변 즉시 알림.

아키텍처 문서: "수색 초반에는 확률 분석보다 즉시 확인이 중요 — IPP 주변
육각 격자 + 한두 칸에 즉시 1차 알림". 이 흐름이 Phase 2 예측 없이 도는지 검증.
"""

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app import storage
from app.api import phase3 as phase3_api
from app.config import settings
from app.geo import h3grid
from app.phase1 import intake
from app.phase3 import alerts
from app.privacy import lifecycle
from app.schemas.case import CloseReason
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType

LKP = GeoPoint(lat=37.5511, lng=126.9410)  # 서강대 인근


def _make_case():
    return intake.create_report(
        missing_type=PersonaType.dementia,
        lkp=LKP,
        lkp_time=datetime.now() - timedelta(minutes=10),
    )


# ── 셀 선택 ─────────────────────────────────────────────────────────

def test_reflex_cells_k2_is_19_hexes():
    """k-ring 2 = 중심 1 + 1링 6 + 2링 12 = 19셀 (res9 기준 반경 약 600m)."""
    cells = alerts.select_reflex_cells(LKP, k=2)
    assert len(cells) == 19
    from app.geo import h3grid
    assert h3grid.cell_of(LKP) in cells  # IPP 셀 포함


def test_reflex_cells_k0_is_center_only():
    assert len(alerts.select_reflex_cells(LKP, k=0)) == 1


def test_reflex_default_k_from_settings():
    cells = alerts.select_reflex_cells(LKP)
    assert len(cells) == len(alerts.select_reflex_cells(LKP, k=settings.reflex_kring))


# ── API — POA 없이 동작해야 한다 ────────────────────────────────────

def test_reflex_endpoint_works_without_poa():
    """POA 알림은 예측 전 409 지만, reflex 는 신고 직후 바로 돼야 한다."""
    case = _make_case()
    assert case.current_poa is None
    res = phase3_api.send_reflex_alerts(case.id)
    assert res["kind"] == "reflex"
    assert res["source_cells"] == 19
    # 발송 대상은 그 19개 셀의 res7 부모 — 폰이 보고하는 칸과 같은 해상도라야
    # 대조가 된다(2026-08-05 푸시 타겟팅 확정).
    assert res["target_res"] == settings.push_target_res
    assert res["target_cells"] == sorted(
        h3grid.parent_cells(alerts.select_reflex_cells(LKP), settings.push_target_res)
    )
    # 대조: POA 기반 알림은 여전히 예측 전 409 (기존 동작 불변)
    with pytest.raises(HTTPException) as exc:
        phase3_api.send_alerts(case.id)
    assert exc.value.status_code == 409


def test_reflex_endpoint_blocked_on_closed_case():
    case = _make_case()
    lifecycle.close_case(case, CloseReason.found)
    with pytest.raises(HTTPException) as exc:
        phase3_api.send_reflex_alerts(case.id)
    assert exc.value.status_code == 409


# ── 신고 접수 자동 발송 ─────────────────────────────────────────────

def test_intake_fires_reflex_alert(monkeypatch):
    sent = {}

    def fake_send(case_id, cells, summary, kind="poa"):
        sent.update(case_id=case_id, cells=cells, kind=kind)
        return {}

    monkeypatch.setattr(alerts, "send_alerts", fake_send)
    case = _make_case()
    assert sent["case_id"] == case.id
    assert sent["kind"] == "reflex"
    assert len(sent["cells"]) == 19


def test_intake_survives_reflex_failure(monkeypatch):
    """알림 발송이 죽어도 신고 접수는 계속돼야 한다 (골든타임 원칙)."""
    def boom(*args, **kwargs):
        raise RuntimeError("push infra down")

    monkeypatch.setattr(alerts, "send_alerts", boom)
    case = _make_case()
    assert storage.cases.get(case.id) is not None
