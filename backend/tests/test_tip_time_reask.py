"""Phase 3 — 시각 되묻기 게이트: 위치O·시각X·폴백 p ≥ 층2 문턱(0.8)만 되묻는다.

단조성 근거(모듈 docstring 참고): seen_at ≤ created_at 이 항상 성립해
개연성(폴백) ≥ 개연성(실제) → p(폴백) ≥ p(실제). 그래서 폴백 p 가 이미
0.8 미만이면 실제 시각을 받아도 층2에 못 가므로 되묻지 않는다.
"""

from datetime import datetime, timedelta

import pytest

from app.phase0 import interview
from app.phase1 import intake
from app.phase2 import pipeline
from app.phase3 import tip_flow
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, PersonaType
from app.schemas.tip import Tip, TipDecision

LKP = GeoPoint(lat=37.5511, lng=126.9410)
PARK = GeoPoint(lat=37.5480, lng=126.9350)  # LKP 에서 약 0.6km — 도보 상한(4.5km/h) 안쪽


@pytest.fixture()
def case():
    persona = interview.register_persona(
        None,
        name="김실종", age=78, ptype=PersonaType.dementia,
        home=GeoPoint(lat=37.5500, lng=126.9400),
        attraction_points=[
            AttractionPoint(label="공원", location=PARK, weight=1.0),
        ],
        behavior_notes=["해질녘에 공원 방향으로 걷는 습관"],
    )
    c = intake.create_report(
        missing_type=PersonaType.dementia,
        lkp=LKP,
        lkp_time=datetime.now() - timedelta(hours=1),
        persona_id=persona.id,
        photo_bytes=b"stub",
        document_bytes=b"stub",
    )
    pipeline.run_prediction(c, seed=42)
    return c


def test_time_reask_triggered_when_strong_tip_lacks_seen_at(case):
    # 위치 명시 + 위치단서·외모단서(시각단서 없음) → 스텁 구체성 "중"(0.6)
    # + 개연성 1.0(반경 안) → p ≈ 0.846 ≥ 0.8, 시각만 없음 → 되묻기 발동
    result = tip_flow.process_tip(
        case, text="공원 앞에서 점퍼 입은 사람을 봤어요",
        location=PARK)
    assert result == {"status": "need_more", "missing": ["time"], "reason": "layer2_needs_time"}
    assert case.tips == []  # 되물을 땐 저장하지 않는다


def test_time_reask_skipped_with_force(case):
    # 위와 동일 조건 + force=True → 되묻지 않고 확정 접수(시각 없어 층2 자격은 없음 → 층1)
    tip = tip_flow.process_tip(
        case, text="공원 앞에서 점퍼 입은 사람을 봤어요",
        location=PARK, force=True)
    assert isinstance(tip, Tip)
    assert tip.decision == TipDecision.layer1
    assert tip in case.tips


def test_no_reask_when_fallback_p_below_threshold(case):
    # 위치·외모 단서 없는 밋밋한 텍스트 → 구체성 "하"(0.3) → p ≈ 0.731 < 0.8
    # → 단조성상 실제 시각을 받아도 층2 불가 → 되묻지 않고 바로 처리
    tip = tip_flow.process_tip(
        case, text="비슷한 사람을 본 것 같아요",
        location=PARK)
    assert isinstance(tip, Tip)
    assert tip.seen_at is None
    assert tip.p < 0.8
    assert tip.decision in (TipDecision.layer1, TipDecision.discard)


def test_seen_at_provided_bypasses_gate(case):
    # 시각이 이미 명시돼 있으면 게이트 조건(seen_at is None)이 거짓 → 바로 판정
    seen = datetime.now() - timedelta(minutes=10)
    tip = tip_flow.process_tip(
        case, text="방금 공원 벤치에 앉아 계신 걸 봤어요",
        location=PARK, seen_at=seen)
    assert tip.seen_at == seen
    assert tip.decision == TipDecision.layer2


def test_no_reask_without_location(case):
    # 위치가 없으면(스텁은 location_text 를 항상 None 으로 반환 — 명시 좌표도 안 줌)
    # 시각 게이트 조건(location is not None)이 거짓 → 미발동. 위치 게이트가 선행이라
    # force=True 로 넘겨도 시각 되묻기로 새지 않고 그대로 판정까지 간다.
    tip = tip_flow.process_tip(
        case, text="공원 앞에서 점퍼 입은 사람을 봤어요",
        force=True)
    assert isinstance(tip, Tip)
    assert tip.location is None
