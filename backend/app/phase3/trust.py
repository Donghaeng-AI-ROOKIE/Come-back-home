"""Phase 3 — 제보 신뢰도 p 산출 (신뢰 온도 측정).

p = 가중평균(시공간개연성·구체성). 각 항은 [0,1], 없는 신호는
가중치를 재정규화. docs: "제보 신뢰도 p 계산 방식".
- 시공간개연성: kinematic 상한 (알고리즘, geo.reachability)
- 구체성: 제보 구조화 LLM(app.llm.tip_llm) 상/중/하 등급 → 고정값 매핑

시민 제보 사진 대조는 하지 않기로 확정되어 제거됨(등록 사진 인상착의
인상착의는 Phase 1에서 보호자가 직접 입력하며 색상만 규칙 기반으로 추출한다).

p 는 이진(통과/파기)이 아니라 값 그대로 POA 갱신 모듈에 전달된다.
"""

from __future__ import annotations

import math
from datetime import datetime

from app.config import settings
from app.geo import reachability
from app.llm import tip_llm
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.tip import Tip

# 구체성 상/중/하 → 고정값 (LLM 에 숫자 직접 안 받는다 — 가드레일 패턴)
SPECIFICITY_LEVELS = {"상": 0.9, "중": 0.6, "하": 0.3}


def score_tip(
    tip: Tip,
    *,
    lkp: GeoPoint,
    lkp_time: datetime,
    persona_type: PersonaType,
    structured: dict | None = None,
) -> float:
    """제보 신뢰도 p 산출. 가중치 r=w1/w2=2.3 확정(P1-5, 2026-07-31) — 근거는 config.py
    trust_weight_plausibility 주석 및 experiments/trust_weight/ 참고.

    structured: 제보 구조화 결과(specificity 등급 등).
    없으면 tip.text 로 즉석 구조화.
    """
    if structured is None:
        structured = tip_llm.structure_tip(tip.text)

    terms: list[tuple[float, float]] = []  # (value, weight)

    # ① 시공간 개연성 — 위치가 있어야 계산. 시각은 seen_at→created_at fallback.
    if tip.location is not None:
        plaus = reachability.plausibility(
            lkp, lkp_time, tip.location, persona_type,
            seen_at=tip.seen_at, created_at=tip.created_at,
        )
        if math.isfinite(plaus):   # 좌표가 NaN 이면 항 제외 (p 오염 방지)
            terms.append((plaus, settings.trust_weight_plausibility))

    # ② 구체성 — 상/중/하 등급 매핑
    level = structured.get("specificity")
    if level in SPECIFICITY_LEVELS:
        terms.append((SPECIFICITY_LEVELS[level], settings.trust_weight_specificity))

    # 없는 신호는 빠졌으므로 남은 가중치로 재정규화 = 가중평균
    if not terms:
        return settings.trust_base_p  # 아무 신호도 없음 → 사전 신뢰
    total_w = sum(w for _, w in terms)
    p = sum(v * w for v, w in terms) / total_w if total_w > 0 else settings.trust_base_p
    return p if math.isfinite(p) else settings.trust_base_p   # 최종 방어


def has_specific_location_time(tip: Tip) -> bool:
    """층2(새 LKP) 자격 조건 — 위치와 시각이 모두 특정되어야 시뮬 앵커가 될 수 있다."""
    return tip.location is not None and tip.seen_at is not None
