"""마음 재해석의 behavior(닫힌 4종)를 보행에 반영하는 경로.

배경: 계약 v2 는 모델에게 behavior 를 강제해 받고 있었으나 sanitize_mind 가
confusion·goal_label 만 꺼내 쓰고 behavior 를 버렸다. 즉 "이 사람이 지금 어떻게
행동하는가"라는 판단이 생성만 되고 소비되지 않았다.

설계 원칙 두 가지가 테스트로 고정된다.

1. **기본 꺼짐 = 비트 단위 동일.** settings.mind_behavior_enabled 가 꺼져 있으면
   종착 분포가 이전과 완전히 같아야 한다. 켜는 순간 알림셀 실측값(0.5h 11 ·
   1h 22 · 2h 31 · 4h 40)과 봉인 test 조건이 재측정 대상이 되므로, 끈 상태의
   무변경은 기존 측정치를 지키는 계약이다.

2. **귀소는 목표 노드를 잡지 않는다.** 집은 전 워커가 공유하는 단 하나의 지점이라
   도달 종료를 걸면 그 한 칸이 흡수벽이 되어 종착 분포가 인위적으로 뭉친다
   (끌림점은 워커마다 흩어지므로 같은 문제가 없다). 방위만 집으로 주고 종료는
   기존 변위 예산·스텝 상한에 맡긴다.
"""

from pathlib import Path

import pytest

from app.config import settings
from app.geo import h3grid
from app.geo.roadnet import OSMnxNetwork
from app.phase2 import simulation
from app.phase2.guardrail import BEHAVIORS, sanitize_mind
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, Persona, PersonaType
from app.schemas.prediction import LognormalParams, MindState, PriorParams

FIXTURE = Path(__file__).parent / "fixtures" / "jeongneung_walk_800m.graphml"
LKP = GeoPoint(lat=37.6061, lng=127.0106)
ATTRACTION = GeoPoint(lat=37.6095, lng=127.0140)
# 집을 LKP 반대편에 둬야 "집 방향으로 걸었다"가 끌림점 방향과 구별된다.
HOME = GeoPoint(lat=37.6030, lng=127.0075)


@pytest.fixture(scope="module")
def net() -> OSMnxNetwork:
    return OSMnxNetwork.from_graphml(FIXTURE)


@pytest.fixture(autouse=True)
def _neutral_routing(monkeypatch):
    """도로 위계 선호를 끈다 — 이 파일은 behavior 반영만 검증한다."""
    monkeypatch.setattr(settings, "road_preference_strength", 0.0)


def _prior() -> PriorParams:
    return PriorParams(strategy_probs={"direction_keeping": 1.0},
                       attraction_weights={"시장": 1.0},
                       radius_lognormal=LognormalParams(mu=1.0, sigma=0.1),
                       reasoning="test")


def _persona() -> Persona:
    return Persona(
        id="t", type=PersonaType.dementia, name="테스트", age=78, home=HOME,
        attraction_points=[AttractionPoint(label="시장", location=ATTRACTION, weight=1.0)],
    )


def _force_fire(monkeypatch):
    from app.phase2 import gauges
    monkeypatch.setattr(gauges.Gauges, "mind_fired", lambda self, rng: "귀소")


def _fake_mind(monkeypatch, behavior: str, goal: str | None = None):
    """reinterpret_mind 가 주어진 behavior 를 내놓도록 고정."""
    from app import llm

    def fake(persona, current, report, labels, prior=None, scene=None, rng=None):
        return MindState(status="테스트", confusion=0.6, changed=True,
                         behavior=behavior), goal

    monkeypatch.setattr(llm.exaone, "reinterpret_mind", fake)


def _run(net, seed: int = 21, n: int = 40) -> dict[str, float]:
    return simulation.run_monte_carlo(LKP, _prior(), _persona(), 1.0, mode="agent",
                                      net=net, n_walkers=n, seed=seed)


# ── 계약: 어휘 검증 ────────────────────────────────────────────────


def test_sanitize_keeps_closed_vocabulary_behavior():
    """닫힌 4종은 MindState 로 통과한다."""
    for b in BEHAVIORS:
        mind, _ = sanitize_mind(
            {"status": "s", "confusion_level": "중", "behavior": b, "goal_label": None},
            MindState(), ["시장"])
        assert mind.behavior == b


def test_sanitize_drops_out_of_vocabulary_behavior():
    """어휘 밖·비문자열은 미판정(빈 문자열)으로 버린다 — goal_label 과 같은 원칙."""
    for bad in ("도망", "", None, 3, "끌림점접근"):   # 마지막은 공백 누락
        mind, _ = sanitize_mind(
            {"status": "s", "confusion_level": "중", "behavior": bad, "goal_label": None},
            MindState(), ["시장"])
        assert mind.behavior == ""


def test_behavior_vocabulary_matches_prompt_contract():
    """guardrail 어휘가 프롬프트 원문과 글자 단위로 같아야 한다.

    다르면 모델 출력이 전부 어휘 밖으로 떨어져 조용히 버려진다 — 형식은
    멀쩡하고 값만 사라지므로 자동 검사가 아니면 못 잡는다.
    """
    from app.llm.mind_v2 import _FP_RULES_V2
    for b in BEHAVIORS:
        assert f'"{b}"' in _FP_RULES_V2


# ── 계약: 기본 꺼짐이면 무변경 ──────────────────────────────────────


@pytest.mark.parametrize("behavior", BEHAVIORS)
def test_disabled_switch_leaves_distribution_identical(net, monkeypatch, behavior):
    """스위치가 꺼져 있으면 어떤 behavior 가 와도 종착 분포가 동일하다.

    기존 실측값(알림셀·봉인 test 조건)을 지키는 계약이다.
    """
    monkeypatch.setattr(settings, "mind_behavior_enabled", False)
    _force_fire(monkeypatch)

    _fake_mind(monkeypatch, "")
    baseline = _run(net)
    for b in (behavior,):
        _fake_mind(monkeypatch, b)
        assert _run(net) == baseline


# ── 반영: 각 행동의 방향성 ──────────────────────────────────────────


def _mean_dist_km(poa: dict[str, float], origin: GeoPoint) -> float:
    """확률 가중 평균 이탈거리 — 분포가 좁아졌는지 넓어졌는지의 척도."""
    return sum(p * h3grid.haversine_km(origin, h3grid.cell_center(c))
               for c, p in poa.items())


def _baseline_dist(net, monkeypatch, origin: GeoPoint) -> float:
    """스위치를 끈 상태(= 기존 동작)의 평균 이탈거리."""
    monkeypatch.setattr(settings, "mind_behavior_enabled", False)
    d = _mean_dist_km(_run(net), origin)
    monkeypatch.setattr(settings, "mind_behavior_enabled", True)
    return d


def test_hide_shrinks_displacement(net, monkeypatch):
    """은신·멈춤 — 체류가 스텝·시간을 소비하므로 기존 동작보다 덜 멀어져야 한다."""
    monkeypatch.setattr(settings, "mind_behavior_enabled", True)
    _force_fire(monkeypatch)
    _fake_mind(monkeypatch, "은신·멈춤")

    base = _baseline_dist(net, monkeypatch, LKP)
    hide = _mean_dist_km(_run(net), LKP)

    assert hide < base


def test_roaming_shrinks_displacement_more_than_hiding(net, monkeypatch):
    """계속 배회가 은신보다 더 강한 수축이다 — 무작위 방위 보행은 확산이라
    변위가 √n 로만 자라기 때문. 두 라벨의 효과 방향이 구별되는지 고정한다.
    """
    monkeypatch.setattr(settings, "mind_behavior_enabled", True)
    _force_fire(monkeypatch)

    _fake_mind(monkeypatch, "은신·멈춤")
    hide = _mean_dist_km(_run(net), LKP)
    _fake_mind(monkeypatch, "계속 배회")
    roam = _mean_dist_km(_run(net), LKP)

    assert roam < hide


def test_homing_pulls_toward_home(net, monkeypatch):
    """귀소 시도 — 집 쪽으로 질량이 이동해야 한다."""
    monkeypatch.setattr(settings, "mind_behavior_enabled", True)
    _force_fire(monkeypatch)

    _fake_mind(monkeypatch, "계속 배회")
    roam_to_home = _mean_dist_km(_run(net), HOME)
    _fake_mind(monkeypatch, "귀소 시도")
    homing_to_home = _mean_dist_km(_run(net), HOME)

    assert homing_to_home < roam_to_home


def test_homing_does_not_collapse_into_one_cell(net, monkeypatch):
    """귀소가 집 한 칸을 흡수벽으로 만들지 않아야 한다.

    도달 종료를 걸면 발동 워커 전원이 같은 셀에 쌓여 종착 분포가 뭉친다.
    방위만 주는 설계라면 셀이 여러 개로 남는다.
    """
    monkeypatch.setattr(settings, "mind_behavior_enabled", True)
    _force_fire(monkeypatch)
    _fake_mind(monkeypatch, "귀소 시도")

    poa = _run(net)
    assert len(poa) > 1                 # 한 칸으로 붕괴하지 않음
    assert max(poa.values()) < 0.9      # 특정 칸이 질량을 독점하지 않음


def test_roaming_clears_target(net, monkeypatch):
    """계속 배회 — 목표를 해제하므로 끌림점 지향과 분포가 달라야 한다."""
    monkeypatch.setattr(settings, "mind_behavior_enabled", True)
    _force_fire(monkeypatch)

    _fake_mind(monkeypatch, "끌림점 접근", goal="시장")
    seek = _run(net)
    _fake_mind(monkeypatch, "계속 배회")
    roam = _run(net)

    assert seek != roam


# ── 안전: 종료 보장 ────────────────────────────────────────────────


@pytest.mark.parametrize("behavior", BEHAVIORS)
def test_all_behaviors_terminate_and_normalize(net, monkeypatch, behavior):
    """어떤 행동에서도 워커가 사라지거나 무한히 돌지 않는다 (POA 합 = 1)."""
    monkeypatch.setattr(settings, "mind_behavior_enabled", True)
    _force_fire(monkeypatch)
    _fake_mind(monkeypatch, behavior, goal="시장" if behavior == "끌림점 접근" else None)

    poa = _run(net)
    assert poa
    assert abs(sum(poa.values()) - 1.0) < 1e-6


def test_dwell_budget_bounded(net, monkeypatch):
    """체류가 길어져도 스텝 상한이 종료를 보장한다 (무한 체류 방지)."""
    monkeypatch.setattr(settings, "mind_behavior_enabled", True)
    monkeypatch.setattr(settings, "mind_hide_dwell_steps", simulation._MAX_STEPS * 10)
    _force_fire(monkeypatch)
    _fake_mind(monkeypatch, "은신·멈춤")

    poa = _run(net, n=8)
    assert abs(sum(poa.values()) - 1.0) < 1e-6
