"""Phase 0 → 3 end-to-end 스모크 테스트 (모델 전부 스텁, API 키 불필요)."""

from datetime import datetime, timedelta

import pytest

from app import storage
from app.phase0 import interview
from app.phase1 import intake
from app.phase2 import pipeline
from app.phase3 import alerts, tip_flow
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, PersonaType
from app.schemas.tip import TipDecision

LKP = GeoPoint(lat=37.5511, lng=126.9410)  # 서강대 인근


@pytest.fixture()
def case():
    persona = interview.register_persona(
        None,
        name="김실종", age=78, ptype=PersonaType.dementia,
        home=GeoPoint(lat=37.5500, lng=126.9400),
        attraction_points=[
            AttractionPoint(label="옛 직장", location=GeoPoint(lat=37.5560, lng=126.9450), weight=2.0),
            AttractionPoint(label="공원", location=GeoPoint(lat=37.5480, lng=126.9350), weight=1.0),
        ],
        behavior_notes=["해질녘에 옛 직장 방향으로 걷는 습관"],
    )
    return intake.create_report(
        missing_type=PersonaType.dementia,
        lkp=LKP,
        lkp_time=datetime.now() - timedelta(hours=1),
        persona_id=persona.id,
        photo_bytes=b"stub",
        document_bytes=b"stub",
    )


def test_full_pipeline(case):
    # Phase 1 산출물
    assert case.report.appearance is not None
    assert case.report.reporter is not None

    # Phase 2 — 예측 (top-down/bottom-up/통계 3종 계산, 결합은 bottom-up·통계 2-way)
    result = pipeline.run_prediction(case, seed=42)
    for poa in (result.poa_topdown, result.poa_bottomup, result.poa_statistical, result.poa_combined):
        assert sum(poa.cells.values()) == pytest.approx(1.0)
        assert len(poa.cells) > 1

    # Phase 3 — 알림 셀 선정 (누적 80% 커버)
    cells = alerts.select_alert_cells(case.current_poa)
    assert 0 < len(cells) < len(case.current_poa)

    # Phase 3 — 층1 제보 (위치는 있지만 시각 불특정 → 층2 자격 없음)
    tip1 = tip_flow.process_tip(
        case, text="공원 근처에서 비슷한 분을 본 것 같아요",
        location=GeoPoint(lat=37.5480, lng=126.9350))
    assert tip1.decision in (TipDecision.layer1, TipDecision.discard)
    assert sum(case.current_poa.values()) == pytest.approx(1.0)

    # Phase 3 — 층2 제보 (위치·시각 특정 + 구체적 서술 → 고신뢰, 새 LKP)
    seen = datetime.now() - timedelta(minutes=10)
    tip2 = tip_flow.process_tip(
        case, text="방금 공원 벤치에 앉아 계신 걸 봤어요",
        location=GeoPoint(lat=37.5480, lng=126.9350),
        seen_at=seen)
    assert tip2.p is not None and tip2.p >= 0.8
    assert tip2.decision == TipDecision.layer2
    # 새 LKP 로 앵커 교체 확인
    assert case.lkp.lat == pytest.approx(37.5480)
    assert case.lkp_time == seen
    assert sum(case.current_poa.values()) == pytest.approx(1.0)
