"""제보 접수는 즉시 끝나고, 무거운 재예측은 뒤에서 돈다.

현장 제보(2026-08-12): 제보 화면이 "전송 중…"에서 90초 가까이 멈춰 있었다
("무한 로딩"). 실측하니 신촌 사건에 망원역 제보를 넣었을 때 **88초** 걸렸고,
그 대부분이 새 지역 도로망 다운로드였다. 공개 경로의 프록시 상한(100초)을
넘기면 아예 실패로 보이기까지 했다.

제보한 시민은 현장에서 찾고 있다 — 재계산이 끝나기를 기다릴 이유가 없다.
"""
from datetime import datetime, timedelta

from fastapi import BackgroundTasks

from app import storage
from app.api import phase3 as phase3_api
from app.phase3 import tip_flow
from app.schemas.case import Case, CaseStatus
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.report import MissingReport


def _case_with_poa() -> Case:
    now = datetime.now()
    case = Case(
        id=storage.new_id(),
        report=MissingReport(
            id=storage.new_id(), missing_type=PersonaType.dementia,
            lkp=GeoPoint(lat=37.5551, lng=126.9368), lkp_time=now - timedelta(hours=1),
        ),
        lkp=GeoPoint(lat=37.5551, lng=126.9368),
        lkp_time=now - timedelta(hours=1),
        status=CaseStatus.predicted,
    )
    # 이 지도가 재계산 중에도 **살아 있어야** 한다.
    case.current_poa = {"8930e1d80c3ffff": 0.6, "8930e1d8083ffff": 0.4}
    storage.cases.save(case.id, case)
    return case


def test_tip_returns_without_running_prediction(monkeypatch):
    """제보 응답이 나갈 때까지 **예측이 돌면 안 된다.**"""
    calls: list[str] = []
    monkeypatch.setattr(tip_flow.pipeline, "run_prediction",
                        lambda *a, **k: calls.append("ran"))
    case = _case_with_poa()

    bg = BackgroundTasks()
    result = phase3_api.submit_tip(
        case.id,
        phase3_api.TipIn(text="신촌역 2번 출구에서 봤어요",
                         location=GeoPoint(lat=37.5545, lng=126.9330),
                         seen_at=datetime.now() - timedelta(minutes=20)),
        bg,
    )

    assert not isinstance(result, dict), "되묻기가 아니라 접수돼야 한다"
    assert calls == [], "응답 전에 예측이 돌면 제보자가 그만큼 기다리게 된다"

    saved = storage.cases.get(case.id)
    assert any(t.id == result.id for t in saved.tips), "제보는 즉시 저장돼야 한다"
    # 보호자 알림 탭은 case.tips 를 주기 조회한다 — 저장됐으면 바로 보인다.
    assert saved.current_poa, "재계산 중에도 기존 확률지도는 살아 있어야 한다"

    # 무거운 일은 백그라운드로 넘어가 있어야 한다(층2 확정 제보이므로).
    if tip_flow.needs_heavy(saved, result):
        assert bg.tasks, "재예측이 필요한데 백그라운드에 등록되지 않았다"
        for task in bg.tasks:
            task.func(*task.args, **task.kwargs)
        assert calls == ["ran"], "백그라운드에서는 예측이 실제로 돌아야 한다"


def test_discarded_tip_schedules_nothing():
    """폐기된 제보는 뒤에서 돌 일도 없다 — 쓸데없이 예측을 돌리면 안 된다."""
    case = _case_with_poa()
    from app.schemas.tip import Tip, TipDecision
    discarded = Tip(id="t1", case_id=case.id, text="그냥 지나가다가요",
                    p=0.1, decision=TipDecision.discard)
    assert tip_flow.needs_heavy(case, discarded) is False
