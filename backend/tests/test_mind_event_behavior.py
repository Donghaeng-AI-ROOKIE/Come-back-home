"""마음 재해석 트레이스가 behavior 를 싣는가.

behavior 는 보행에 실제로 반영되는 채널(mind_behavior_enabled)이고 어휘가 4종
뿐이라, 층마다 다른 답이 오는지 확인할 수 있는 유일한 필드다. status 는 자유
문장이라 표현만 달라도 달라 보인다 — 2026-08-07 실측에서 15콜 전부 같은
behavior 인데 status 는 5가지로 보였고, 트레이스에 behavior 가 없어 화면에서는
그 사실이 드러나지 않았다.
"""
from app.phase2 import simulation
from app.schemas.common import GeoPoint
from app.schemas.prediction import MindState


def test_mind_event_carries_behavior():
    mind = MindState(status="정릉시장 쪽으로 걸음을 옮긴다", confusion=0.6,
                     behavior="끌림점 접근", changed=True)
    ev = simulation._mind_event(
        walker_idx=3, step=7, loc=GeoPoint(lat=37.6, lng=127.0),
        trigger="[게이지] 귀소 임계 초과", source="pool", mind=mind, goal="정릉시장")

    assert ev.behavior == "끌림점 접근", "보행에 반영되는 채널이 트레이스에서 누락된다"
    assert ev.status == mind.status, "기존 필드가 밀려나면 안 된다"


def test_behavior_defaults_empty_when_unset():
    """미판정(빈 문자열)도 그대로 실린다 — 없는 것과 못 받은 것을 구분해야 한다."""
    ev = simulation._mind_event(
        walker_idx=0, step=0, loc=GeoPoint(lat=37.6, lng=127.0),
        trigger="t", source="heuristic", mind=MindState(), goal=None)

    assert ev.behavior == ""
