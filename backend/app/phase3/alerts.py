"""Phase 3 — 1차 알림: POA 상위 셀 내 사용자에게 타겟 발송.

광범위 재난문자 대신 발견 확률이 높은 위치의 사용자에게만 보내
알림 피로도를 낮춘다 (핵심 차별점).
"""

import math

from app.config import settings
from app.geo import h3grid
from app.schemas.common import GeoPoint


def select_alert_cells(
    poa: dict[str, float],
    coverage: float | None = None,
    max_cells: int | None = None,
) -> list[str]:
    """확률 내림차순으로 누적 커버리지(기본 80%)에 도달할 때까지 셀 선택.

    반환된 셀 집합이 '1차 안전 반경' — 이 안의 사용자가 알림 대상.

    셀 수 상한(max_cells)은 타겟팅 가드레일: topdown 해석적 분포의 얇은 꼬리가
    수천 셀에 퍼져 있으면 80% 커버리지가 사실상 무차별 발송이 된다
    (실측: σ 오교정 시 21,950셀, 경과 20h 케이스 3,684셀). 상한에 걸리면
    커버리지 미달이어도 끊는다 — "타겟 알림" 이 서비스 전제이므로.
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
    selected: list[str] = []
    acc = 0.0
    for cell, prob in ranked:
        if len(selected) >= max_cells:
            break
        selected.append(cell)
        acc += prob
        if acc >= coverage:
            break
    return selected


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
    message = (
        f"[돌아오길] 인근에서 실종이 발생했습니다. 주변을 확인해 주세요. {appearance_summary}"
        if kind == "reflex"
        else f"[돌아오길] 근처에서 실종자가 목격되었습니다. {appearance_summary}"
    )
    return {
        "case_id": case_id,
        "kind": kind,   # reflex(1차 안전반경) | poa(예측 기반 타겟)
        "target_cells": len(cells),
        "message": message,
        "sent": False,
        "note": "푸시 인프라 미연동 — 스텁 응답",
    }
