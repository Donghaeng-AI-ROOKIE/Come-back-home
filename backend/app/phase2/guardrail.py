"""목적지 예측 가드레일 — EXAONE prior 출력 검증·보정.

회의 결정(1차 기술회의 3번): 평가표 대신 가드레일 — "택도 없는 건 거르고".
LLM 은 확률·거리 calibration 이 약하다는 전제(아키텍처 결정사항)에 따라:
- 전략확률: 숫자 출력을 받되 알려진 6전략만 인정, ε-floor 후 재정규화
- 끌림점: 숫자 대신 상/중/하 정성 등급만 받아 고정 가중치로 매핑
  (LLM 이 임의 숫자를 지어내는 것 자체를 차단)
- 반경: 상/중/하 → Koester 프로파일 μ 만 소폭 보정, σ 는 프로파일 고정
항목별로 검증하며, 실패한 항목만 프로파일 통계 기본값으로 폴백한다.
"""

from app.schemas.persona import Persona
from app.schemas.prediction import LognormalParams, PriorParams

# ε-flooring — 어떤 전략도 확률 0 이 되지 않게 (탐색 다양성 보존)
EPSILON = 0.02
# 상/중/하 → 고정 가중치. LLM 의 정성 판단만 받고 수치화는 우리가 한다.
LEVEL_WEIGHTS = {"상": 3.0, "중": 2.0, "하": 1.0}
# 끌림점 하나가 분포를 독식하지 않게 상한 (끌림점 2개 이상일 때)
ATTRACTION_CAP = 0.6
# 반경 등급 → lognormal μ 보정. ±0.4 = 중앙값 거리 ×1.5 / ×0.67 (그 이상은 불허)
RADIUS_MU_ADJUST = {"상": 0.4, "중": 0.0, "하": -0.4}
REASONING_MAX_CHARS = 500


def sanitize_prior(data: dict, persona: Persona | None, default: PriorParams) -> PriorParams:
    """LLM JSON 출력 → 검증된 PriorParams. default = 프로파일 통계 기본값."""
    reasoning = data.get("reasoning")
    if not isinstance(reasoning, str):
        # 실측: 모델이 키를 "reason্ম" 처럼 어그러뜨린 사례 — reason* 키로 구제
        reasoning = next((v for k, v in data.items()
                          if isinstance(k, str) and k.startswith("reason")
                          and isinstance(v, str)), "")
    reasoning = reasoning.strip()[:REASONING_MAX_CHARS]
    weights = sanitize_attraction_levels(data.get("attraction_levels"), persona)
    return PriorParams(
        strategy_probs=sanitize_strategy_probs(data.get("strategy_probs"), default.strategy_probs),
        attraction_weights=weights if weights else default.attraction_weights,
        radius_lognormal=sanitize_radius(data.get("radius_level"), default.radius_lognormal),
        reasoning=reasoning or "[가드레일] reasoning 누락 — 파라미터만 사용",
    )


def sanitize_strategy_probs(raw, default: dict[str, float]) -> dict[str, float]:
    """알려진 전략만 인정, ε-floor 후 합=1 재정규화. 쓸 수 없는 출력이면 default."""
    if not isinstance(raw, dict):
        return dict(default)
    probs: dict[str, float] = {}
    for name in default:  # default 의 키 = 유효한 전략 목록. 모르는 전략은 버림
        v = raw.get(name)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0:
            probs[name] = float(v)
    if not probs or sum(probs.values()) <= 0:
        return dict(default)
    floored = {name: max(probs.get(name, 0.0), EPSILON) for name in default}
    total = sum(floored.values())
    return {name: v / total for name, v in floored.items()}


def sanitize_attraction_levels(raw, persona: Persona | None) -> dict[str, float]:
    """상/중/하 등급 → 고정 가중치 → 정규화 → 상한. 지어낸 라벨은 버리고 빠진 라벨은 '중'."""
    if persona is None or not persona.attraction_points:
        return {}
    levels = raw if isinstance(raw, dict) else {}
    weights = {
        ap.label: LEVEL_WEIGHTS.get(levels.get(ap.label), LEVEL_WEIGHTS["중"])
        for ap in persona.attraction_points
    }
    total = sum(weights.values())
    normed = {label: w / total for label, w in weights.items()}

    if len(normed) >= 2:  # 상한 초과분은 나머지에 비례 배분 (동시 초과는 합>1 이라 불가능)
        for label, share in normed.items():
            if share > ATTRACTION_CAP:
                excess = share - ATTRACTION_CAP
                rest_total = 1.0 - share
                for other in normed:
                    if other != label:
                        normed[other] += excess * (normed[other] / rest_total)
                normed[label] = ATTRACTION_CAP
                break
    return normed


def sanitize_radius(raw_level, profile: LognormalParams) -> LognormalParams:
    """등급이 유효하면 μ 보정, 아니면 프로파일 그대로. σ 는 항상 프로파일 값."""
    adjust = RADIUS_MU_ADJUST.get(raw_level, 0.0) if isinstance(raw_level, str) else 0.0
    return LognormalParams(mu=profile.mu + adjust, sigma=profile.sigma)
