"""Phase 3 — 층2(Phase 2 전체 재실행) 트리거 판정.

트리거 3가지 (아키텍처 보라 점선 '예측 기반 탐색'의 조건 라벨):
1. 고신뢰 목격으로 새 LKP 확정 (classify_tip 이 layer2 반환 → 호출부에서 처리)
2. 마지막 시뮬 후 경과 시간 임계치 (Koester 반경 확장 대응)
3. current_poa 가 baseline_poa 에서 크게 이탈 (KL divergence)
"""

import math
from datetime import datetime, timedelta

from app.config import settings
from app.schemas.case import Case


def kl_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    """KL(P‖Q) — P=현재(갱신 누적) 분포, Q=baseline(시뮬 직후) 분포."""
    eps = 1e-12
    cells = set(p) | set(q)
    return sum(
        p.get(c, 0.0) * math.log((p.get(c, 0.0) + eps) / (q.get(c, 0.0) + eps))
        for c in cells if p.get(c, 0.0) > 0
    )


def jensen_shannon_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    """JS(P,Q) — 대칭·유계([0, log2])·0-안전. D3(새 지역 알림) 예비스크린 전용.

    KL은 비교분포에서 질량 0인 칸에 도달하면 발산하는데, 그 칸이 바로
    "새 지역" 탐지 대상이라 KL은 이 용도에 못 쓴다. 새 지역 여부 자체는
    이 값이 아니라 alerts.select_new_region_cells() 의 집합차로 판정한다 —
    이 함수는 "전체적으로 많이 바뀌었나"만 보는 스칼라 예비 스크린.
    """
    cells = set(p) | set(q)
    m = {c: 0.5 * (p.get(c, 0.0) + q.get(c, 0.0)) for c in cells}
    return 0.5 * kl_divergence(p, m) + 0.5 * kl_divergence(q, m)


def should_rerun_phase2(case: Case, now: datetime | None = None) -> tuple[bool, str]:
    """주기·분포이탈 트리거 검사. (재실행 여부, 사유)

    새 LKP 트리거(1번)는 제보 처리 흐름에서 classify_tip 결과로 직접 발동되므로
    여기서는 2·3번만 본다.
    """
    now = now or datetime.now()

    if case.last_sim_at is None:
        return True, "첫 시뮬레이션 미실행"

    # 트리거 2 — 주기 재실행
    elapsed = now - case.last_sim_at
    if elapsed >= timedelta(minutes=settings.layer2_periodic_minutes):
        return True, f"주기 도달 ({int(elapsed.total_seconds() // 60)}분 경과)"

    # 트리거 3 — 분포 이탈
    if case.current_poa and case.baseline_poa:
        kl = kl_divergence(case.current_poa, case.baseline_poa)
        if kl > settings.kl_divergence_threshold:
            return True, f"분포 이탈 (KL={kl:.3f} > {settings.kl_divergence_threshold})"

    return False, "재실행 불필요"
