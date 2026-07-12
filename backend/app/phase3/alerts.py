"""Phase 3 — 1차 알림: POA 상위 셀 내 사용자에게 타겟 발송.

광범위 재난문자 대신 발견 확률이 높은 위치의 사용자에게만 보내
알림 피로도를 낮춘다 (핵심 차별점).
"""

from app.config import settings


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
    coverage = coverage or settings.alert_coverage
    max_cells = max_cells or settings.max_alert_cells
    ranked = sorted(poa.items(), key=lambda kv: kv[1], reverse=True)
    selected: list[str] = []
    acc = 0.0
    for cell, prob in ranked:
        selected.append(cell)
        acc += prob
        if acc >= coverage or len(selected) >= max_cells:
            break
    return selected


def send_alerts(case_id: str, cells: list[str], appearance_summary: str) -> dict:
    """알림 발송 스텁.

    실제 구현: 셀 내 앱 사용자 조회(위치 인덱스) → 푸시 발송
    (인상착의 시각 자료 + 지도 하이라이트 포함).
    """
    # TODO: 푸시 인프라(FCM 등) + 사용자 위치 인덱스 연동
    return {
        "case_id": case_id,
        "target_cells": len(cells),
        "message": f"[돌아오길] 근처에서 실종자가 목격되었습니다. {appearance_summary}",
        "sent": False,
        "note": "푸시 인프라 미연동 — 스텁 응답",
    }
