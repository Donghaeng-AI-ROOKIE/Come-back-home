"""P1-5 재설계(2026-07-31, 서영 지시) — "정답"을 텍스트 판단이 아니라 생성규칙으로 결정.

## 왜 다시 설계했나

기존 boundary_drafts.py 방식은 "이 제보가 layer2감인가"를 사람(Claude+서영)이 텍스트 읽고
판단해서 정답표를 만들었다. 그 정답표에 대해 정답률 최대인 r 을 찾으면, 그 r 은 결국
"그 판단과 가장 일치하는 값"일 뿐이다 — 서영이 정확히 짚은 문제: "내 판단이 잘못될 수도
있으니 정확한 정량적 이유가 필요하다".

## 새 방식 — "진짜 vs 가짜 목격 분리 정확도"(trust.py 원래 설계 의도)

trust.py 상단 주석에 원래 이렇게 적혀 있었다: "초기값은 도메인 판단, 합성 시나리오
(진짜 vs 가짜 제보 분리)로 튜닝 대상." 이걸 실제로 구현한다.

핵심: "정답"을 텍스트 내용이 아니라 **생성 시점에 이미 정해진 사실**로 만든다.
  - 가상 케이스(LKP·시각) 하나 고정.
  - "진짜"(genuine=True): 실제 도달가능반경(d_max) **안**의 좌표에 배치한 제보.
  - "가짜"(genuine=False): d_max **밖**의 좌표에 배치한 제보.
  - 이 좌표는 좌표계산(haversine)으로 나온 값이라 사람 판단이 전혀 안 들어간다 —
    "이 텍스트가 진짜인가"를 읽고 정하는 게 아니라 "이 텍스트를 어디 좌표에 놓을지"만
    무작위로 정하고, 진짜/가짜 여부는 그 좌표가 반경 안인지 밖인지로 자동 결정된다.

★핵심 설계 원칙(안 지키면 트리비얼해짐): 구체성과 진짜여부를 절대 얽지 않는다.
  4파전 70개 텍스트(gold_specificity 라벨 있음, 상18/중36/하16 골고루 분포)를 그대로
  재사용하되, **어느 텍스트가 진짜/가짜 그룹에 들어갈지는 좌표 배정과 완전히 독립적인
  무작위**로 정한다. 그러면 "진짜인데 구체성 하"(목격은 맞는데 잘 기억 못함)와
  "가짜인데 구체성 상"(확신에 차 자세히 말했지만 실제로 다른 곳/시간이었던 오인)이
  자연스럽게 섞인다 — 구체성만 보고 진짜/가짜를 맞힐 수 있으면 실험이 무의미해지므로,
  이 섞임이 실험이 유효하기 위한 전제조건이다.

## 측정 방법

각 r 에 대해 70개 전부의 p 를 계산하고, (genuine 레이블, p) 쌍들로 ROC-AUC 를 구한다.
AUC=1.0 이면 완벽 분리(모든 진짜의 p 가 모든 가짜의 p 보다 높음), 0.5 면 무작위와 같음.
r 을 스윕해서 AUC 최대인 r 을 찾는다 — 이 결과는 "정답을 가장 잘 맞히는 정책"이 아니라
"진짜와 가짜를 가장 잘 분리하는 파라미터"라는, 판단이 섞이지 않은 표준 이진분류 성능이다.

## 이 방식도 완전히 가정에서 자유롭진 않음 (정직하게 명시)

"가짜 목격 = 물리적으로 먼 거리"라는 정의 자체는 설계 선택이다(실제로는 인상착의 불일치,
없는 사람 지어내기 등 다른 가짜 유형도 있음 — 이번 실험은 개연성 축만 가짜여부와
연동하고, 구체성 축은 가짜여부와 무관하게 섞어서 "구체성:개연성 비율"을 재는 것이
목적이므로 이 정의로 충분하다). 다만 이전 방식과 결정적으로 다른 점은, 이 가정이
**텍스트 하나하나에 대한 개별 판단이 아니라 실험 전체에 적용되는 단일 규칙**이라
재현 가능하고 검증 가능하다.
"""

from __future__ import annotations

import importlib.util
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.geo import reachability  # noqa: E402
from app.schemas.common import GeoPoint  # noqa: E402
from app.schemas.persona import PersonaType  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "tlc_scenarios", BACKEND / "experiments" / "tip_llm_compare" / "scenarios.py"
)
_tlc = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("tlc_scenarios", _tlc)
_spec.loader.exec_module(_tlc)

LKP = GeoPoint(lat=37.5511, lng=126.9410)
LKP_TIME = datetime(2026, 7, 31, 12, 0, 0)
CREATED_AT = LKP_TIME + timedelta(hours=1)  # dt_h=1 고정 → d_max = v_max(치매 4.32km/h)*1h
PERSONA = PersonaType.dementia
D_MAX_KM = reachability.vmax_kmh(PERSONA) * reachability.elapsed_hours(LKP_TIME, None, CREATED_AT)

_rng = random.Random(7)  # boundary_drafts 실험(seed 42)과 겹치지 않게 다른 seed


def _point_at_distance_km(km: float, bearing_deg: float) -> GeoPoint:
    """LKP 에서 bearing 방향으로 km 만큼 이동한 좌표(단순 근사, degree당 111.32km).
    real-world 정밀도는 필요 없음 — plausibility() 계산이 이 근사와 일관되게 haversine
    을 쓰므로 상대적 거리 판정만 맞으면 된다."""
    import math
    dlat = (km * math.cos(math.radians(bearing_deg))) / 111.32
    dlng = (km * math.sin(math.radians(bearing_deg))) / (111.32 * math.cos(math.radians(LKP.lat)))
    return GeoPoint(lat=LKP.lat + dlat, lng=LKP.lng + dlng)


@dataclass
class GenuineScenario:
    id: str
    text: str
    gold_specificity: str
    genuine: bool          # ★정답 — 좌표가 d_max 안/밖인지로 결정, 텍스트 판단 아님
    location: GeoPoint
    distance_km: float      # 참고용(디버그) — d_max 와 비교해서 genuine 과 일관되는지 확인용


def build_genuine_scenarios() -> list[GenuineScenario]:
    scenarios = list(_tlc.SCENARIOS)
    order = list(range(len(scenarios)))
    _rng.shuffle(order)  # 텍스트 순서(카테고리 뭉침)와 무관하게 진짜/가짜 배정
    half = len(order) // 2

    result = []
    for rank, idx in enumerate(order):
        sc = scenarios[idx]
        genuine = rank < half
        bearing = _rng.uniform(0, 360)
        if genuine:
            distance = _rng.uniform(0.0, D_MAX_KM)          # 반경 안 — 다양한 거리
        else:
            distance = _rng.uniform(D_MAX_KM * 1.1, D_MAX_KM * 3.5)  # 반경 밖 — 살짝~많이 초과 다양하게
        loc = _point_at_distance_km(distance, bearing)
        result.append(GenuineScenario(
            id=sc.id, text=sc.text, gold_specificity=sc.gold_specificity,
            genuine=genuine, location=loc, distance_km=round(distance, 3),
        ))
    return result


GENUINE_SCENARIOS: list[GenuineScenario] = build_genuine_scenarios()

if __name__ == "__main__":
    import sys as _s
    if hasattr(_s.stdout, "reconfigure"):
        _s.stdout.reconfigure(encoding="utf-8")
    n_genuine = sum(1 for s in GENUINE_SCENARIOS if s.genuine)
    print(f"d_max={D_MAX_KM:.3f}km, genuine={n_genuine}, fake={len(GENUINE_SCENARIOS)-n_genuine}")
    from collections import Counter
    for label in (True, False):
        specs = Counter(s.gold_specificity for s in GENUINE_SCENARIOS if s.genuine == label)
        print(f"  genuine={label}: 구체성분포={dict(specs)}")
