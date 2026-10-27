"""제보 장소의 위치어("앞"·"근처"·"2번 출구")가 지오코딩을 막지 않는가.

10/27 운영 측정: 목격 제보 "킨텍스역 만남의 광장 앞에서 …"는 구조화가 장소를
"킨텍스역 만남의 광장 앞"으로 정확히 뽑았는데, 그 문자열 그대로는 지오코더가
못 찾아 위치 없는 층1이 됐다. "킨텍스역 만남의 광장"은 LKP 75m 로 찾힌다.
"""
from datetime import datetime, timedelta

import pytest

from app.geo.geocode import GeoResult, base_place_name
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
# 10/27 운영 사건 7ccf1a190cd3(군포 수리동)의 LKP 와, 운영 워커에서 "능내초등학교"로 찾은 지점.
GUNPO_LKP = GeoPoint(lat=37.3553725, lng=126.9155875)
NEUNGNAE = GeoPoint(lat=37.3546, lng=126.92115)  # GUNPO_LKP 에서 약 0.5km


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


@pytest.mark.parametrize(("text", "base"), [
    # 10/27 운영 사건 7ccf1a190cd3: "능내초등학교 앞쪽" → None, "능내초등학교" → LKP 0.5km.
    ("능내초등학교 앞쪽", "능내초등학교"),
    ("대흥역 2번 출구 앞쪽", "대흥역"),
    ("망원한강공원 부근", "망원한강공원"),
    ("망원시장 인근", "망원시장"),
    ("수리산역 근방", "수리산역"),
    ("성산아파트 뒤쪽", "성산아파트"),
    ("성산아파트 옆쪽", "성산아파트"),
    # 원래 떼던 꼬리말은 그대로 뗀다.
    ("대흥역 2번 출구", "대흥역"),
    ("대흥역 앞 근처", "대흥역"),
])
def test_base_place_name_strips_side_and_vicinity_words(text, base):
    assert base_place_name(text) == base


@pytest.mark.parametrize("text", ["광장 동쪽", "골목 쪽", "망원시장"])
def test_a_bare_direction_word_is_kept(text):
    # '쪽' 하나만 떼는 규칙은 없다 — "○○ 동쪽"처럼 장소 이름의 일부일 수 있다.
    assert base_place_name(text) == text


def test_front_side_tip_is_found_by_its_base_name(monkeypatch):
    geo = _FakeGeo({"능내초등학교": NEUNGNAE})
    monkeypatch.setattr(tip_flow, "_GEO", geo)
    assert tip_flow._geocode_tip_location("능내초등학교 앞쪽", GUNPO_LKP) == NEUNGNAE
    assert geo.calls == ["능내초등학교 앞쪽", "능내초등학교"]


@pytest.mark.parametrize("text", ["능내초등학교 앞쪽에서", "능내초등학교에서", "능내초등학교 앞에서"])
def test_trailing_particle_is_dropped_after_exact_query_fails(monkeypatch, text):
    # 구조화 프롬프트는 조사를 떼라고 하지 않는다. 모델 비교 실험에서 다른 모델이
    # "시장에서"·"편의점에서"를 낸 기록이 있다(experiments/tip_llm_compare/results).
    geo = _FakeGeo({"능내초등학교": NEUNGNAE})
    monkeypatch.setattr(tip_flow, "_GEO", geo)
    assert tip_flow._geocode_tip_location(text, GUNPO_LKP) == NEUNGNAE
    assert geo.calls == [text, "능내초등학교"]


def test_particle_alone_is_not_queried_as_empty_text(monkeypatch):
    geo = _FakeGeo({})
    monkeypatch.setattr(tip_flow, "_GEO", geo)
    assert tip_flow._geocode_tip_location("에서", LKP) is None
    assert geo.calls == ["에서"]


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


def test_witness_tip_with_front_side_word_gets_location(case, monkeypatch):
    # 10/27 운영: "10분 전 쯤 능내초등학교 앞쪽에서 봤어요"가 위치 없는 층1이 됐다.
    geo = _FakeGeo({"공원": PARK})
    monkeypatch.setattr(tip_flow, "_GEO", geo)
    stub = tip_flow.tip_llm.structure_tip
    monkeypatch.setattr(tip_flow.tip_llm, "structure_tip", lambda text: {**stub(text), "location_text": "공원 앞쪽"})

    tip = tip_flow.process_tip(
        case, text="10분 전 쯤 공원 앞쪽에서 회색 점퍼 입은 할아버지를 봤어요",
        seen_at=datetime.now() - timedelta(minutes=10),  # noqa: DTZ005 — 위와 같은 이유
        defer_heavy=True)

    assert tip.location == PARK
    assert geo.calls == ["공원 앞쪽", "공원"]
