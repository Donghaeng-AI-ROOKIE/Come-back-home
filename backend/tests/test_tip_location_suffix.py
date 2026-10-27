"""제보 장소의 위치어("앞"·"근처"·"2번 출구")가 지오코딩을 막지 않는가.

10/27 운영 측정: 목격 제보 "킨텍스역 만남의 광장 앞에서 …"는 구조화가 장소를
"킨텍스역 만남의 광장 앞"으로 정확히 뽑았는데, 그 문자열 그대로는 지오코더가
못 찾아 위치 없는 층1이 됐다. "킨텍스역 만남의 광장"은 LKP 75m 로 찾힌다.
"""
from datetime import datetime, timedelta

import pytest

from app.geo.geocode import GeoResult
from app.phase0 import interview
from app.phase1 import intake
from app.phase2 import pipeline
from app.phase3 import tip_flow
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, PersonaType
from app.schemas.report import Appearance

LKP = GeoPoint(lat=37.5511, lng=126.9410)
PARK = GeoPoint(lat=37.5480, lng=126.9350)  # LKP 에서 약 0.6km
FAR = GeoPoint(lat=37.3000, lng=126.9410)   # LKP 에서 약 28km — ANCHOR_MAX_KM(20) 밖


class _FakeGeo:
    """질의 → 결과 표. 어떤 순서로 무엇을 물었는지 기록한다."""

    def __init__(self, table: dict):
        self.table = table
        self.calls: list[str] = []

    def locate(self, query, anchor=None):
        self.calls.append(query)
        point = self.table.get(query)
        return None if point is None else GeoResult(point, precision="poi", source="fake", matched=query)


def test_suffix_is_stripped_after_exact_query_fails(monkeypatch):
    geo = _FakeGeo({"킨텍스역 만남의 광장": PARK})
    monkeypatch.setattr(tip_flow, "_GEO", geo)
    assert tip_flow._geocode_tip_location("킨텍스역 만남의 광장 앞", LKP) == PARK
    assert geo.calls == ["킨텍스역 만남의 광장 앞", "킨텍스역 만남의 광장"]


@pytest.mark.parametrize("text", ["공원 근처", "공원 2번 출구", "공원 건너편", "공원 앞 근처"])
def test_other_position_words(monkeypatch, text):
    monkeypatch.setattr(tip_flow, "_GEO", _FakeGeo({"공원": PARK}))
    assert tip_flow._geocode_tip_location(text, LKP) == PARK


def test_exact_match_wins_without_second_query(monkeypatch):
    geo = _FakeGeo({"공원 앞": PARK, "공원": FAR})
    monkeypatch.setattr(tip_flow, "_GEO", geo)
    assert tip_flow._geocode_tip_location("공원 앞", LKP) == PARK
    assert geo.calls == ["공원 앞"]


def test_far_exact_match_falls_back_to_base_name(monkeypatch):
    geo = _FakeGeo({"공원 앞": FAR, "공원": PARK})
    monkeypatch.setattr(tip_flow, "_GEO", geo)
    assert tip_flow._geocode_tip_location("공원 앞", LKP) == PARK


def test_far_matches_are_still_rejected(monkeypatch):
    monkeypatch.setattr(tip_flow, "_GEO", _FakeGeo({"공원 앞": FAR, "공원": FAR}))
    assert tip_flow._geocode_tip_location("공원 앞", LKP) is None


def test_text_without_position_word_is_queried_once(monkeypatch):
    geo = _FakeGeo({})
    monkeypatch.setattr(tip_flow, "_GEO", geo)
    assert tip_flow._geocode_tip_location("이름 없는 골목", LKP) is None
    assert geo.calls == ["이름 없는 골목"]


@pytest.fixture()
def case(monkeypatch):
    from app import llm

    # 기대값이 실모델 응답에 흔들리지 않게 스텁 추출을 강제한다(test_tip_time_reask 와 같은 이유).
    monkeypatch.setattr(type(llm.tip_llm), "is_stub", property(lambda self: True))
    persona = interview.register_persona(
        None,
        name="김실종", age=78, ptype=PersonaType.dementia,
        home=GeoPoint(lat=37.5500, lng=126.9400),
        attraction_points=[AttractionPoint(label="공원", location=PARK, weight=1.0)],
        behavior_notes=["해질녘에 공원 방향으로 걷는 습관"],
    )
    c = intake.create_report(
        missing_type=PersonaType.dementia,
        lkp=LKP,
        lkp_time=datetime.now() - timedelta(hours=1),  # noqa: DTZ005 — Case 시각 필드는 naive(LocalNaiveDT)
        persona_id=persona.id,
        appearance=Appearance(top="회색 점퍼", bottom="검정 바지", shoes="흰색 운동화"),
    )
    pipeline.run_prediction(c, seed=42)
    return c


def test_witness_tip_with_position_word_gets_location(case, monkeypatch):
    geo = _FakeGeo({"공원": PARK})
    monkeypatch.setattr(tip_flow, "_GEO", geo)
    stub = tip_flow.tip_llm.structure_tip
    monkeypatch.setattr(tip_flow.tip_llm, "structure_tip", lambda text: {**stub(text), "location_text": "공원 앞"})

    tip = tip_flow.process_tip(
        case, text="10분 전에 공원 앞에서 회색 점퍼 입은 할아버지를 봤어요",
        seen_at=datetime.now() - timedelta(minutes=10),  # noqa: DTZ005 — 위와 같은 이유
        defer_heavy=True)

    assert tip.location == PARK
    assert geo.calls == ["공원 앞", "공원"]
