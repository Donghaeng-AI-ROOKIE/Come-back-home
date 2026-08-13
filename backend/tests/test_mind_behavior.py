"""마음 재해석의 behavior(닫힌 4종)를 보행에 반영하는 경로.

배경: 계약 v2 는 모델에게 behavior 를 강제해 받고 있었으나 sanitize_mind 가
confusion·goal_label 만 꺼내 쓰고 behavior 를 버렸다. 즉 "이 사람이 지금 어떻게
행동하는가"라는 판단이 생성만 되고 소비되지 않았다.

**매핑은 문헌 근거로만 정한다** (2026-08-02 원문 대조). 코퍼스 34편 전문을 직접
검색해 확인한 근거는 다음과 같고, 각 테스트는 그 근거가 코드에 반영됐는지를 본다.

- 귀소 시도 — Rowe et al. 2011(DEM-31): 명시적 귀소 의도를 밝힌 8% 는 "과거 거주지·
  직장·친척 집"으로 가려 했다. **현재 집이 아니다.** 그리고 DEM-34 는 실종을
  "집으로 돌아오지 못하는 상태"로 정의한다 — 귀소는 실패하는 것이 정상이므로
  도달 판정을 걸지 않는다. 판정 지시서의 라벨 정의("길을 제대로 찾는지는 무관 —
  의도 기준")와도 일치한다.
- 계속 배회 — DEM-33(Algase Wandering Scale)의 random 패턴 조작적 정의: "walking in
  a haphazard fashion using multiple changes in direction, and no obvious route to
  the eventual stopping point". 매 스텝 무작위 방위가 이에 대응한다.
- 은신·멈춤 — DEM-31: 26% 가 최종 목격지 0.5마일 이내 자연 공간에서 발견되었고
  발견될 때까지 거의 이동하지 않았다. 체류가 아니라 이동 종료로 옮긴다.
- 끌림점 접근 — 기존 goal_label 경로가 이미 처리한다(신규 매핑 없음).

설계 계약 두 가지도 함께 고정한다.

1. **스위치가 꺼져 있으면 무변경.** 어떤 behavior 가 와도 종착 분포가 이전과 같아야
   한다. 기본값은 2026-08-04 켜짐으로 바뀌었지만 이 계약은 그대로 유지한다 — 끈
   구성이 ablation 의 기준선이고, 그것이 흔들리면 켠 효과를 잴 자가 사라진다.
   (알림셀 기준선은 experiments/alert_cells 로 옮겼다. 종전 주석값 0.5h 11 · 1h 22 ·
   2h 31 · 4h 40 은 재현 스크립트가 없어 폐기됐다.)
2. **근거가 가리키지 않는 대상에는 폴백하지 않는다.** 과거 장소가 등록돼 있지 않으면
   귀소 매핑을 아예 적용하지 않는다(현재 집으로 대신 보내지 않는다).
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
# 옛집은 끌림점 반대편에 둬야 "옛집 방향"이 "끌림점 방향"과 구별된다.
PAST_HOME = GeoPoint(lat=37.6030, lng=127.0075)
# 현재 집은 옛집과 다른 곳에 둔다 — 폴백이 일어나면 테스트가 잡아내도록.
CURRENT_HOME = GeoPoint(lat=37.6090, lng=127.0150)


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


def _persona(with_past_home: bool = True) -> Persona:
    aps = [AttractionPoint(label="시장", location=ATTRACTION, weight=1.0,
                           place_type="market")]
    if with_past_home:
        aps.append(AttractionPoint(label="옛집", location=PAST_HOME, weight=1.0,
                                   place_type="past_residence"))
    return Persona(id="t", type=PersonaType.dementia, name="테스트", age=78,
                   home=CURRENT_HOME, attraction_points=aps)


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


def _run(net, *, persona: Persona | None = None, seed: int = 21, n: int = 40) -> dict[str, float]:
    return simulation.run_monte_carlo(LKP, _prior(), persona or _persona(), 1.0,
                                      mode="agent", net=net, n_walkers=n, seed=seed)


def _mean_dist_km(poa: dict[str, float], origin: GeoPoint) -> float:
    """확률 가중 평균 거리 — 질량이 어느 쪽으로 쏠렸는지의 척도."""
    return sum(p * h3grid.haversine_km(origin, h3grid.cell_center(c))
               for c, p in poa.items())


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
    _fake_mind(monkeypatch, behavior)
    assert _run(net) == baseline


# ── 귀소 시도 — DEM-31 / DEM-34 ────────────────────────────────────


def test_homing_targets_past_residence_not_current_home(net, monkeypatch):
    """DEM-31 — 귀소 의도자는 과거 거주지·직장으로 향한다. 현재 집이 아니다.

    옛집과 현재 집을 서로 반대편에 두고, 질량이 옛집 쪽으로 가는지 본다.
    현재 집으로 잘못 보내면 이 테스트가 실패한다.
    """
    monkeypatch.setattr(settings, "mind_behavior_enabled", True)
    _force_fire(monkeypatch)

    _fake_mind(monkeypatch, "계속 배회")
    roam = _run(net)
    _fake_mind(monkeypatch, "귀소 시도")
    homing = _run(net)

    # 옛집 쪽으로는 가까워지고
    assert _mean_dist_km(homing, PAST_HOME) < _mean_dist_km(roam, PAST_HOME)
    # 현재 집 쪽으로는 가까워지지 않는다
    assert _mean_dist_km(homing, CURRENT_HOME) >= _mean_dist_km(roam, CURRENT_HOME)


def test_homing_skipped_when_no_past_place_registered(net, monkeypatch):
    """과거 장소가 없으면 귀소 매핑을 적용하지 않는다 (현재 집 폴백 금지).

    근거가 가리키는 대상이 없으면 아무것도 하지 않는 것이 정답이다 —
    임의 폴백은 문헌이 말하지 않은 곳으로 워커를 보낸다.
    """
    monkeypatch.setattr(settings, "mind_behavior_enabled", True)
    _force_fire(monkeypatch)
    p = _persona(with_past_home=False)

    _fake_mind(monkeypatch, "")
    baseline = _run(net, persona=p)
    _fake_mind(monkeypatch, "귀소 시도")
    assert _run(net, persona=p) == baseline


def test_homing_has_no_arrival_stop(net, monkeypatch):
    """귀소는 도달 판정이 없다 — DEM-34 는 실종을 "귀가 실패"로 정의한다.

    도달 종료를 걸면 발동 워커가 옛집 한 칸에 쌓여 종착 분포가 뭉친다.
    """
    monkeypatch.setattr(settings, "mind_behavior_enabled", True)
    _force_fire(monkeypatch)
    _fake_mind(monkeypatch, "귀소 시도")

    poa = _run(net)
    assert len(poa) > 1                 # 한 칸으로 붕괴하지 않음
    assert max(poa.values()) < 0.9      # 특정 칸이 질량을 독점하지 않음


# ── 계속 배회 — DEM-33 random 정의 ─────────────────────────────────


def test_roaming_clears_target_and_diverges_from_seeking(net, monkeypatch):
    """DEM-33 random — "뚜렷한 경로 없이" 걷는다. 목표 지향과 분포가 달라야 한다."""
    monkeypatch.setattr(settings, "mind_behavior_enabled", True)
    _force_fire(monkeypatch)

    _fake_mind(monkeypatch, "끌림점 접근", goal="시장")
    seek = _run(net)
    _fake_mind(monkeypatch, "계속 배회")
    roam = _run(net)

    assert seek != roam


def test_roaming_shrinks_displacement(net, monkeypatch):
    """무작위 방위 보행은 확산이라 변위가 √n 로만 자란다 — 방향 유지보다 덜 멀어진다.

    DEM-33 의 random 정의("multiple changes in direction")가 만드는 귀결이다.
    """
    monkeypatch.setattr(settings, "mind_behavior_enabled", True)
    _force_fire(monkeypatch)
    _fake_mind(monkeypatch, "계속 배회")
    roam = _mean_dist_km(_run(net), LKP)

    monkeypatch.setattr(settings, "mind_behavior_enabled", False)
    base = _mean_dist_km(_run(net), LKP)

    assert roam < base


# ── 은신·멈춤 — DEM-31 근거리 정지 발견 ────────────────────────────


def test_hiding_stops_movement(net, monkeypatch):
    """DEM-31 — 은신자는 발견될 때까지 거의 이동하지 않는다. 그 자리에서 종료."""
    monkeypatch.setattr(settings, "mind_behavior_enabled", True)
    _force_fire(monkeypatch)
    _fake_mind(monkeypatch, "은신·멈춤")
    hide = _mean_dist_km(_run(net), LKP)

    monkeypatch.setattr(settings, "mind_behavior_enabled", False)
    base = _mean_dist_km(_run(net), LKP)

    assert hide < base


def test_hiding_does_not_collapse_into_one_cell(net, monkeypatch):
    """은신 지점은 워커마다 흩어져 있으므로 종료를 걸어도 한 칸으로 뭉치지 않는다.

    귀소(공유 목적지)와 달리 은신은 각자 서 있던 자리라 흡수벽 문제가 없다 —
    이 차이가 두 라벨의 구현이 다른 이유다.
    """
    monkeypatch.setattr(settings, "mind_behavior_enabled", True)
    _force_fire(monkeypatch)
    _fake_mind(monkeypatch, "은신·멈춤")

    poa = _run(net)
    assert len(poa) > 1
    assert max(poa.values()) < 0.9


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
