"""혼란도가 "목적지 인식 실패"로 소비되는 경로 (PR 후속, 2026-08-04).

배경: 혼란도는 그동안 κ(갈림길 방향 집중도) 하나로만 소비됐다. 채널별 ablation
(500워커 × seed 5, 정릉 3km)에서 혼란 "상"(κ=0.375)과 "하"(κ=1.625)의 종착 분포
차이가 seed 노이즈의 1.12배 — 즉 **집계 POA 를 못 움직였다.** 각도 집중도는
워커를 모으면 상쇄되고, 종료는 prior 가 뽑은 직선 변위가 정하기 때문이다.

**매핑은 문헌 근거로만 정한다** (2026-08-04 코퍼스 원문 대조,
experiments/mind_tuning/corpus/pages/*.jsonl 및 claims/claims.jsonl).

- 목적지 인식 실패 — CLM-0023(DEM-34 p6): "if a PWD was driving a routine route
  but became distracted and drove past their destination, they might have a
  difficult time recognizing their destination when they turned around and
  approached the location from a different direction." 도착이 곧 인지가 아니다.
- 회복 불가 — CLM-0015(DEM-31 p6): "unable to recover from way finding errors."
  그래서 한 번 놓친 목표를 되찾지 않는다.
- 지속 보행 파생 — CLM-0028(DEM-32 p8) + CLM-0031(DEM-33 p11): 길찾기 효과가
  떨어질수록 지속 보행이 늘고, 지속 보행은 배회의 핵심 차원이다. 목적지를 못
  알아본 워커가 변위 상한까지 계속 걷는 것이 이에 대응하므로 **지속 보행용
  파라미터를 따로 두지 않는다**(이중계상 방지).

κ 를 이 근거로 정당화하면 안 된다는 것도 함께 고정한다: DEM-32 의 상관계수는
각도가 아니라 "cycles per hour · proportion of time locomoting · direct
ambulation" 에 대한 값이다.

설계 계약 두 가지.
1. **strength=0 이면 무변경.** 노브를 끄면 이전 동작과 종착 분포가 같아야 한다.
2. **behavior 와 겹치지 않는다.** behavior 는 "무엇을 하려는가", 혼란도는 "그것을
   해내는가". 끌림점 접근 의도가 있어도 혼란하면 지나칠 수 있다.
"""

from pathlib import Path

import pytest

from app.config import settings
from app.geo import h3grid
from app.geo.roadnet import OSMnxNetwork
from app.phase2 import simulation
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, Persona, PersonaType
from app.schemas.prediction import LognormalParams, MindState, PriorParams

FIXTURE = Path(__file__).parent / "fixtures" / "jeongneung_walk_800m.graphml"
LKP = GeoPoint(lat=37.6061, lng=127.0106)
ATTRACTION = GeoPoint(lat=37.6095, lng=127.0140)


@pytest.fixture(scope="module")
def net() -> OSMnxNetwork:
    return OSMnxNetwork.from_graphml(FIXTURE)


@pytest.fixture(autouse=True)
def _neutral(monkeypatch):
    """도로 위계·환경 반응을 끈다 — 이 파일은 혼란도 소비만 검증한다."""
    monkeypatch.setattr(settings, "road_preference_strength", 0.0)
    monkeypatch.setattr(settings, "env_response_strength", 0.0)
    monkeypatch.setattr(settings, "mind_behavior_enabled", False)


def _prior() -> PriorParams:
    # landmark_seeking 1.0 — 전 워커가 끌림점을 목표로 잡게 해서 인식 판정이
    # 실제로 걸리는 구성으로 만든다.
    return PriorParams(strategy_probs={"landmark_seeking": 1.0},
                       attraction_weights={"시장": 1.0},
                       radius_lognormal=LognormalParams(mu=1.0, sigma=0.1),
                       reasoning="test")


def _persona() -> Persona:
    return Persona(id="t", type=PersonaType.dementia, name="테스트", age=78,
                   home=LKP,
                   attraction_points=[AttractionPoint(
                       label="시장", location=ATTRACTION, weight=1.0,
                       place_type="market")])


def _fake_mind(monkeypatch, confusion: float):
    from app import llm

    def fake(persona, current, report, labels, prior=None, scene=None, rng=None):
        return MindState(status="테스트", confusion=confusion, changed=True), None

    monkeypatch.setattr(llm.exaone, "reinterpret_mind", fake)


def _force_fire(monkeypatch):
    from app.phase2 import gauges
    monkeypatch.setattr(gauges.Gauges, "mind_fired", lambda self, rng: "귀소")


def _run(net, seed: int = 21, n: int = 80, mind: MindState | None = None) -> dict[str, float]:
    return simulation.run_monte_carlo(LKP, _prior(), _persona(), 1.0,
                                      mode="agent", net=net, n_walkers=n, seed=seed,
                                      mind=mind)


def _arrived_share(poa: dict[str, float]) -> float:
    """끌림점 셀에 도착해 멈춘 워커의 비율 — 인식 성공의 직접 지표."""
    return poa.get(h3grid.cell_of(ATTRACTION), 0.0)


# ── 계약 1: 노브를 끄면 인식 채널이 완전히 죽는다 ───────────────────
# κ 를 상수로 고정해야 이 계약을 잴 수 있다. 혼란도는 κ 로도 소비되므로,
# κ 를 살려 두면 "노브가 꺼졌는데도 결과가 달라진다"가 정상 동작이 된다
# (κ 차이). κ 를 묶어야 남는 차이가 곧 인식 채널의 몫이다.
_FIXED_KAPPA = 1.25   # 혼란도 0.5 일 때의 값


def test_strength_zero_kills_the_channel(net, monkeypatch):
    _force_fire(monkeypatch)
    monkeypatch.setattr(simulation, "_kappa", lambda c: _FIXED_KAPPA)
    monkeypatch.setattr(settings, "confusion_miss_strength", 0.0)

    _fake_mind(monkeypatch, confusion=0.85)
    high = _run(net)
    _fake_mind(monkeypatch, confusion=0.35)
    low = _run(net)

    assert high == low, "노브가 꺼졌는데 혼란도 차이가 종착 분포에 남았다"


def test_strength_on_makes_the_channel_live(net, monkeypatch):
    """위 테스트의 짝 — 같은 조건에서 노브만 켜면 분포가 달라져야 한다.

    둘을 함께 둬야 계약 1이 "아무것도 안 하는 코드라서 통과"하는 것을 배제한다.
    """
    _force_fire(monkeypatch)
    monkeypatch.setattr(simulation, "_kappa", lambda c: _FIXED_KAPPA)
    monkeypatch.setattr(settings, "confusion_miss_strength", 1.0)

    _fake_mind(monkeypatch, confusion=0.85)
    high = _run(net)
    _fake_mind(monkeypatch, confusion=0.35)
    low = _run(net)

    assert high != low, "노브를 켰는데 혼란도 차이가 종착 분포에 안 남았다"


# ── 계약 2: 혼란도가 높을수록 목적지를 덜 알아본다 ──────────────────
def test_high_confusion_misses_destination_more(net, monkeypatch):
    _force_fire(monkeypatch)
    monkeypatch.setattr(settings, "confusion_miss_strength", 1.0)

    _fake_mind(monkeypatch, confusion=0.35)   # 하
    low = _arrived_share(_run(net))
    _fake_mind(monkeypatch, confusion=0.85)   # 상
    high = _arrived_share(_run(net))

    assert high < low, f"혼란 상({high:.3f})이 하({low:.3f})보다 더 도착해선 안 된다"


# ── 계약 3: 판정 함수의 확률 규약 ───────────────────────────────────
@pytest.mark.parametrize("confusion,strength,expected", [
    (1.0, 1.0, False),   # 실패확률 100%
    (0.0, 1.0, True),    # 명료하면 항상 알아본다
    (0.85, 0.0, True),   # 노브 0 이면 혼란도와 무관하게 항상 인정
])
def test_recognition_probability_contract(confusion, strength, expected, monkeypatch):
    import random
    monkeypatch.setattr(settings, "confusion_miss_strength", strength)
    rng = random.Random(0)
    assert all(simulation._recognizes_destination(rng, confusion) is expected
               for _ in range(50))


def test_strength_zero_does_not_consume_rng(monkeypatch):
    """노브가 꺼져 있으면 난수를 뽑지 않아야 한다.

    뽑으면 rng 스트림이 밀려 이전 구성과 종착 분포가 달라진다 — 계약 1의
    "무변경"이 조용히 깨지는 경로라 별도로 못 박는다.
    """
    import random
    monkeypatch.setattr(settings, "confusion_miss_strength", 0.0)
    rng = random.Random(0)
    before = rng.getstate()
    simulation._recognizes_destination(rng, 0.85)
    assert rng.getstate() == before


# ── 계약 4: 놓친 목표를 되찾지 않는다 (CLM-0015) ────────────────────
def test_missing_destination_reduces_arrivals(net, monkeypatch):
    """전원 인식 실패면 끌림점 셀에서 끝나는 비율이 크게 떨어져야 한다.

    0 이 되지는 않는다 — 셀은 육각형이라, 목표를 잃고 배회하던 워커가 변위
    상한에 걸려 우연히 그 칸에서 멈출 수 있다. 그래서 "0 이어야 한다"가 아니라
    "노브를 끈 구성 대비 크게 준다"로 잰다. (첫 작성 때 0 을 기대했다가
    16.25% 가 남아 실패했고, 관찰 방법이 틀렸던 것으로 확인했다.)
    """
    _force_fire(monkeypatch)
    _fake_mind(monkeypatch, confusion=1.0)

    monkeypatch.setattr(settings, "confusion_miss_strength", 0.0)
    off = _arrived_share(_run(net))
    monkeypatch.setattr(settings, "confusion_miss_strength", 1.0)
    on = _arrived_share(_run(net))

    assert on < off / 2, f"인식 실패 100%인데 도착 비율이 충분히 안 줄었다 ({off:.3f} → {on:.3f})"


# ── 계약 5: 플레이스홀더 혼란도로는 걸지 않는다 ─────────────────────
# 이 계약이 이 파일에서 가장 중요하다. 처음 구현은 이것을 어겼고, 그 결과
# **효과의 2/3 이상이 근거 없는 기본값에서 나왔다** (2026-08-04 dem3 실호출 실측:
# 알림셀 1h 14.0 → 전 워커 적용 19.3 / 발동 워커만 15.7). MindState 기본값 0.5 는
# 신호가 아니라 중립값이므로, 그 값으로 도달 실패를 걸면 안 된다.
def _no_fire(monkeypatch):
    from app.phase2 import gauges
    monkeypatch.setattr(gauges.Gauges, "mind_fired", lambda self, rng: None)


def test_placeholder_confusion_does_not_trigger_miss(net, monkeypatch):
    """마음이 한 번도 발동하지 않으면 노브를 켜도 종착 분포가 그대로여야 한다."""
    _no_fire(monkeypatch)

    monkeypatch.setattr(settings, "confusion_miss_strength", 0.0)
    off = _run(net, mind=MindState(confusion=0.85))   # changed=False (기본값)
    monkeypatch.setattr(settings, "confusion_miss_strength", 1.0)
    on = _run(net, mind=MindState(confusion=0.85))

    assert off == on, "판정된 적 없는 혼란도(changed=False)로 도달 실패가 걸렸다"


def test_known_confusion_applies_without_firing(net, monkeypatch):
    """상류가 판정한 혼란도(changed=True)면 발동 없이도 첫 걸음부터 적용된다.

    혼란도 규칙 산정이 들어와 페르소나 단위로 값을 채우는 경로를 미리 고정한다 —
    그때 이 게이트를 다시 손대지 않아도 되도록.
    """
    _no_fire(monkeypatch)

    monkeypatch.setattr(settings, "confusion_miss_strength", 0.0)
    off = _arrived_share(_run(net, mind=MindState(confusion=0.85, changed=True)))
    monkeypatch.setattr(settings, "confusion_miss_strength", 1.0)
    on = _arrived_share(_run(net, mind=MindState(confusion=0.85, changed=True)))

    assert on < off, f"판정된 혼란도인데 노브가 안 들었다 (off {off:.3f} → on {on:.3f})"
