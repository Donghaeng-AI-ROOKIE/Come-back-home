"""Phase 3 — 1차 알림: POA 상위 셀 내 사용자에게 타겟 발송.

광범위 재난문자 대신 발견 확률이 높은 위치의 사용자에게만 보내
알림 피로도를 낮춘다 (핵심 차별점).
"""

import math

from app.config import settings
from app.geo import h3grid
from app.schemas.common import GeoPoint


def _cumulative_top_cells(
    ranked: list[tuple[str, float]],
    target_total: float,
    coverage: float,
    max_cells: int,
) -> list[str]:
    """확률 내림차순 목록에서 target_total 의 coverage 비율에 도달할 때까지
    셀을 누적 선택 (select_alert_cells·select_new_region_cells 공용 로직).

    셀 수 상한(max_cells)은 타겟팅 가드레일: 얇은 꼬리가 수천 셀에 퍼져
    있으면 커버리지 기준만으로는 사실상 무차별 발송이 된다(실측: topdown
    σ 오교정 시 21,950셀, 경과 20h 케이스 3,684셀). 상한에 걸리면 커버리지
    미달이어도 끊는다 — "타겟 알림" 이 서비스 전제이므로.
    """
    selected: list[str] = []
    acc = 0.0
    threshold = coverage * target_total
    for cell, prob in ranked:
        if len(selected) >= max_cells:
            break
        selected.append(cell)
        acc += prob
        if acc >= threshold:
            break
    return selected


def select_alert_cells(
    poa: dict[str, float],
    coverage: float | None = None,
    max_cells: int | None = None,
) -> list[str]:
    """확률 내림차순으로 누적 커버리지(기본 80%)에 도달할 때까지 셀 선택.

    반환된 셀 집합이 '1차 안전 반경' — 이 안의 사용자가 알림 대상.
    """
    # 기본값 대입은 `or` 가 아니라 `is None` — coverage=0.0·max_cells=0 을
    # 명시적으로 넘겨도 falsy 라 기본값으로 치환되던 버그 방지.
    coverage = settings.alert_coverage if coverage is None else coverage
    max_cells = settings.max_alert_cells if max_cells is None else max_cells
    # 비유한값(NaN/inf) 셀 제외 — 정렬 불안정·acc 오염(NaN 누적 시 커버리지
    # 판정 무력화) 방지. 상류(전략확률 가드레일)에서 막지만 심층 방어.
    ranked = sorted(
        ((c, p) for c, p in poa.items() if math.isfinite(p)),
        key=lambda kv: kv[1], reverse=True,
    )
    return _cumulative_top_cells(ranked, target_total=1.0, coverage=coverage, max_cells=max_cells)


def select_new_region_cells(
    current_poa: dict[str, float],
    last_alert_poa: dict[str, float],
    mass_threshold: float | None = None,
    coverage: float | None = None,
    max_cells: int | None = None,
) -> list[str]:
    """D3(3차 알림) 최종판정 — 마지막 알림 시점엔 없던 셀(집합차) 중,
    그 새 지역의 **합산** 질량이 임계를 넘을 때만 그 안에서 상위 커버리지만 발송.

    KL/JS가 아니라 집합차인 이유: 새 지역은 last_alert_poa 에서 질량이
    0인 칸인데 KL(new‖old)은 바로 그 지점에서 무한대로 터진다
    (하필 탐지하려는 지점에서 망가짐). 비교 기준이 "직전 POA"가 아니라
    "마지막 알림 시점 POA"인 이유: 작은 제보가 누적돼 서서히 새 동네로
    이동해도 직전 대비 변화량은 매 스텝 작아 영영 안 걸리기 때문 —
    마지막 알림 대비로 재야 누적 이동을 잡는다.

    질량 임계가 **셀 하나**가 아니라 **새 지역 전체 합**인 이유(실측으로 확인):
    시뮬레이션은 새 LKP 주변 확률을 여러 셀에 걸쳐 퍼뜨리므로 새로 생긴 확률은
    거의 항상 셀 하나가 아니라 수십~수백 개에 나눠 담긴다(실측: 새 셀 149개,
    최대 단일 셀 1.3% — 셀 단위 임계 0.05는 절대 못 넘김. 그런데 149개 합산은
    21% — 명백히 알림 가치가 있는 새 지역). 셀 단위 임계는 D3 가 원래 잡으려는
    바로 그 상황(새 LKP 로 넓게 퍼지는 직후)에서 항상 무반응이 되는 결함이었다.
    유의미하다고 판정된 뒤의 실제 타겟팅은 select_alert_cells 와 같은 커버리지
    +상한 로직(무차별 발송 방지)을 새 지역 부분집합에 그대로 재사용한다.
    """
    mass_threshold = (
        settings.new_region_mass_threshold if mass_threshold is None else mass_threshold
    )
    coverage = settings.alert_coverage if coverage is None else coverage
    max_cells = settings.max_alert_cells if max_cells is None else max_cells

    new_cells = set(current_poa) - set(last_alert_poa)
    ranked = sorted(
        ((c, current_poa[c]) for c in new_cells if math.isfinite(current_poa[c])),
        key=lambda kv: kv[1], reverse=True,
    )
    total_new_mass = sum(p for _, p in ranked)
    if total_new_mass < mass_threshold:
        return []
    return _cumulative_top_cells(ranked, target_total=total_new_mass, coverage=coverage, max_cells=max_cells)


def select_reflex_cells(lkp: GeoPoint, k: int | None = None) -> list[str]:
    """1차 안전반경 (Reflex Tasking) — POA 없이 IPP 주변 k-ring 선택.

    Koester 원칙: 수색 초반에는 복잡한 확률 분석보다 즉시 확인이 중요.
    신고 접수 직후 Phase 2 예측이 나오기 전의 골든타임을 이 알림이 메운다.
    예측 완료 후에는 select_alert_cells(POA 기반)로 전환.
    """
    k = settings.reflex_kring if k is None else k
    return h3grid.cells_within_k(lkp, k)


def send_alerts(case_id: str, cells: list[str], appearance_summary: str,
                kind: str = "poa") -> dict:
    """알림 발송 스텁.

    실제 구현: 셀 내 앱 사용자 조회(위치 인덱스) → 푸시 발송
    (인상착의 시각 자료 + 지도 하이라이트 포함).
    """
    # TODO: 푸시 인프라(FCM 등) + 사용자 위치 인덱스 연동
    if kind == "reflex":
        message = f"[돌아오길] 인근에서 실종이 발생했습니다. 주변을 확인해 주세요. {appearance_summary}"
    elif kind == "new_region":
        message = f"[돌아오길] 새로운 지역에서 실종자가 목격되었을 가능성이 있습니다. {appearance_summary}"
    else:
        message = f"[돌아오길] 근처에서 실종자가 목격되었습니다. {appearance_summary}"
    return {
        "case_id": case_id,
        "kind": kind,   # reflex(1차 안전반경) | poa(예측 기반 타겟) | new_region(3차, 새 지역 한정)
        "target_cells": len(cells),
        "message": message,
        "sent": False,
        "note": "푸시 인프라 미연동 — 스텁 응답",
    }
