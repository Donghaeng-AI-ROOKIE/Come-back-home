"""Phase 3 — POA 갱신 2층 설계 (2026-07-03 확정, memory/project_poa_update_design.md).

층1 (베이지안 갱신, 게이트 통과 제보마다):
    새 POA(셀) ∝ 기존 POA(셀) × [ p·L(제보|셀) + (1−p)·1 ]
    - p: 제보 신뢰도. 제보가 진짜일 확률 p 만큼 내용(L) 반영,
      허위일 확률 (1−p) 만큼 무정보(1, 곱해도 분포 불변).
    - p 낮으면 likelihood 가 1에 수렴 → 자동으로 약한 반영.
    - 저신뢰 제보를 버리지 않는 이유: 같은 지역 약한 제보 3~4건 누적이
      유의미한 신호가 됨 (시민 제보 = 발견의 25%).

층2 (Phase 2 재실행, triggers.py):
    제보를 곱하는 게 아니라 시뮬 초기 조건(새 LKP)으로 사용 — 이 수식 안 씀.
    층2 직후 새 baseline 위에 잔여 유효 제보를 이 층1 수식으로 재적용.
"""

from datetime import datetime

from app.config import settings
from app.geo import h3grid
from app.schemas.common import GeoPoint
from app.schemas.tip import Tip, TipDecision


def classify_tip(p: float, has_location_time: bool) -> TipDecision:
    """제보 판정. 핵심 기준: '이 제보가 시뮬 출발점(LKP)을 바꾸는가?'

    - p < 0.2                       → 파기 (허위/스팸)
    - 0.2 ≤ p < 0.8                 → 층1만
    - p ≥ 0.8 + 위치·시각 특정       → 층1 + 층2 트리거
    - p ≥ 0.8 이지만 위치·시각 불특정 → 앵커 자격 없음 → 층1만
    """
    if p < settings.tip_discard_threshold:
        return TipDecision.discard
    if p >= settings.tip_lkp_threshold and has_location_time:
        return TipDecision.layer2
    return TipDecision.layer1


def mixed_likelihood(l_value: float, p: float) -> float:
    """혼합 likelihood: p·L + (1−p)·1"""
    return p * l_value + (1.0 - p)


def layer1_update(
    poa: dict[str, float],
    tip_location: GeoPoint,
    p: float,
) -> dict[str, float]:
    """층1 — 베이지안 POA 갱신.

    제보 위치 기준 셀별 L 커널을 만들어 혼합 likelihood 를 원소별 곱 후 정규화.
    """
    tip_cell = h3grid.cell_of(tip_location)
    l_by_cell = h3grid.likelihood_kernel(tip_cell, list(poa.keys()))

    updated = {cell: prob * mixed_likelihood(l_by_cell[cell], p)
               for cell, prob in poa.items()}

    total = sum(updated.values())
    if total <= 0:
        return dict(poa)  # 수치 붕괴 시 갱신 포기 (방어)
    return {c: v / total for c, v in updated.items()}


def reapply_tips(
    baseline_poa: dict[str, float],
    tips: list[Tip],
    since: datetime,
) -> dict[str, float]:
    """층2 직후 — 새 baseline POA 위에 새 LKP 시각 이후의 유효 제보를 재적용.

    유효 조건: 파기되지 않았고, 위치가 있고, 목격 시각이 새 LKP 시각 이후.
    """
    poa = dict(baseline_poa)
    for tip in tips:
        if tip.decision == TipDecision.discard or tip.p is None or tip.location is None:
            continue
        if tip.seen_at is None or tip.seen_at <= since:
            continue
        poa = layer1_update(poa, tip.location, tip.p)
    return poa
