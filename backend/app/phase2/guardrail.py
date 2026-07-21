"""목적지 예측 가드레일 — EXAONE prior 출력 검증·보정.

회의 결정(1차 기술회의 3번): 평가표 대신 가드레일 — "택도 없는 건 거르고".
LLM 은 확률·거리 calibration 이 약하다는 전제(아키텍처 결정사항)에 따라:
- 전략확률: 숫자 출력을 받되 알려진 6전략만 인정, ε-floor 후 재정규화
- 끌림점: 숫자 대신 상/중/하 정성 등급만 받아 고정 가중치로 매핑
  (LLM 이 임의 숫자를 지어내는 것 자체를 차단)
- 반경: 상/중/하 → Koester 프로파일 μ 만 소폭 보정, σ 는 프로파일 고정
항목별로 검증하며, 실패한 항목만 프로파일 통계 기본값으로 폴백한다.
"""

import math

from app.schemas.persona import (
    AttractionPoint,
    EnvResponse,
    Persona,
    PersonaType,
    RouteFamiliarity,
)
from app.schemas.prediction import LognormalParams, MindState, PriorParams

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
        # 비유한값(inf/NaN) 거부 — json.loads 는 "1e400"·"Infinity" 를 inf 로 파싱한다.
        # inf 가 통과하면 정규화에서 NaN 이 되어 rng.choices 가 예측을 통째로 죽인다.
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0:
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
    return _apply_cap(normed, ATTRACTION_CAP)


def _apply_cap(weights: dict[str, float], cap: float) -> dict[str, float]:
    """분포에서 하나가 cap 을 넘지 않게 재분배. 초과분은 나머지에 비례 배분
    (동시 초과는 합>1 이라 불가능하므로 한 번만 확인하면 된다)."""
    normed = dict(weights)
    if len(normed) >= 2:
        for label, share in normed.items():
            if share > cap:
                excess = share - cap
                rest_total = 1.0 - share
                for other in normed:
                    if other != label:
                        normed[other] += excess * (normed[other] / rest_total)
                normed[label] = cap
                break
    return normed


def apply_axis_scores(
    prior: PriorParams,
    axis_scores: dict[str, float],
    persona: Persona | None,
    base_radius: LognormalParams,
) -> PriorParams:
    """축점수(phase0.axis_scoring, 0.1~0.9)를 PriorParams 에 결정론적으로 반영.

    LLM 스텁 여부와 무관하게 exaone.generate_prior() 끝에서 항상 실행된다 —
    가드레일 안에만 넣으면 로컬 개발(대부분 스텁 모드)에서 효과가 안 보인다.

    반경은 axis_score 가 있으면 LLM 등급을 무시하고 축 기준으로 재계산한다
    (축점수는 quote 검증·다수결을 거쳐 LLM 의 단발 등급보다 신뢰도가 높은
    신호이므로 override). 전략확률·끌림점가중치는 이미 계산된 값 위에
    곱셈 틸트만 가한다(파괴적 override 아님).
    """
    updates = {}

    # 1) 반경 — mobility_transport_capacity (몸축, 유일한 반경 신호)
    if "mobility_transport_capacity" in axis_scores:
        score = axis_scores["mobility_transport_capacity"]
        level = "하" if score < 0.3 else ("중" if score < 0.7 else "상")
        mu = base_radius.mu + RADIUS_MU_ADJUST[level]
        updates["radius_lognormal"] = LognormalParams(mu=mu, sigma=base_radius.sigma)

    # 2) 전략확률 — elopement_pattern_consistency (발달장애 전용 행동축)
    if (persona and persona.type == PersonaType.intellectual_disability
            and "elopement_pattern_consistency" in axis_scores):
        updates["strategy_probs"] = _sharpen(
            prior.strategy_probs, axis_scores["elopement_pattern_consistency"],
            floor=EPSILON)

    # 3) 끌림점가중치 — autobiographical_destination_pull(치매) / preferred_target_seeking(발달)
    axis_key = {
        PersonaType.dementia: "autobiographical_destination_pull",
        PersonaType.intellectual_disability: "preferred_target_seeking",
    }.get(persona.type if persona else None)
    if axis_key and axis_key in axis_scores and prior.attraction_weights:
        sharpened = _sharpen(prior.attraction_weights, axis_scores[axis_key], floor=0.0)
        updates["attraction_weights"] = _apply_cap(sharpened, ATTRACTION_CAP)

    return prior.model_copy(update=updates) if updates else prior


def _sharpen(dist: dict[str, float], score: float, *, floor: float) -> dict[str, float]:
    """score(0.1~0.9)로 분포 쏠림(sharpness) 조정. score=0.5 면 무변화.

    gamma>1 → 1등에 더 쏠림(뾰족해짐), gamma<1 → 평평해짐(균등에 가까워짐).
    gamma 는 방어적으로 클램프 — score 가 이론상 0.1~0.9 지만, 클램프 없이
    극단값이 들어오면 사실상 결정론적 선택이 되어버릴 수 있다.
    """
    gamma = max(0.2, min(2.0, 1.0 + 2.0 * (score - 0.5)))
    powered = {k: v ** gamma for k, v in dist.items()}
    total = sum(powered.values())
    if total <= 0:
        return dict(dist)  # 방어 — 입력에 0 이 없다는 전제라 이론상 도달 안 함
    normed = {k: v / total for k, v in powered.items()}
    if floor > 0:  # 전략확률용 — 재정규화 후 다시 floor 보장 (0 확률 금지 원칙 유지)
        floored = {k: max(v, floor) for k, v in normed.items()}
        t2 = sum(floored.values())
        normed = {k: v / t2 for k, v in floored.items()}
    return normed


def sanitize_radius(raw_level, profile: LognormalParams) -> LognormalParams:
    """등급이 유효하면 μ 보정, 아니면 프로파일 그대로. σ 는 항상 프로파일 값."""
    adjust = RADIUS_MU_ADJUST.get(raw_level, 0.0) if isinstance(raw_level, str) else 0.0
    return LognormalParams(mu=profile.mu + adjust, sigma=profile.sigma)


# ── 마음 재해석 (H·A 트리거 → EXAONE) 출력 검증 ─────────────────────
# confusion 도 숫자를 직접 받지 않고 상/중/하 → 고정 절대값
CONFUSION_LEVELS = {"상": 0.85, "중": 0.6, "하": 0.35}
STATUS_MAX_CHARS = 50


def sanitize_mind(data: dict, current: MindState, labels: list[str]) -> tuple[MindState, str | None]:
    """LLM 재해석 JSON → (검증된 MindState, 목표 끌림점 라벨 또는 None).

    goal_label 은 실존 끌림점 라벨일 때만 인정 — 지어낸 목적지 차단.
    """
    status = data.get("status")
    status = status.strip()[:STATUS_MAX_CHARS] if isinstance(status, str) and status.strip() \
        else current.status
    confusion = CONFUSION_LEVELS.get(data.get("confusion_level"), current.confusion)
    goal = data.get("goal_label")
    goal = goal if isinstance(goal, str) and goal in labels else None
    mind = MindState(status=status, confusion=confusion, changed=True)
    return mind, goal


# ── route_familiarity 컴파일러 (작업5) 출력 검증 ────────────────────
# A~E → 고정값. 팀 확정 기준표(축 점수 CHOICE_SCORE 와 동일 5단계 스케일) —
# 0.1=처음 가거나 거의 경험 없음 / 0.3=방문 경험은 있으나 혼자 이동 경험 거의 없음 /
# 0.5=가끔 이용, 일부 랜드마크·구간만 앎 / 0.7=반복 이용하는 익숙한 경로+혼자 이동 경험 /
# 0.9=일상적으로 반복 이용하는 핵심 생활경로+최근까지 독립 이동. F(판정 불가)는
# 매핑에 없어 자동으로 버려진다 — "언급됐지만 이 기준표로 판단할 근거가 부족함".
ROUTE_LEVEL_SCORES = {"A": 0.1, "B": 0.3, "C": 0.5, "D": 0.7, "E": 0.9}

# 개인 환경 반응(EnvResponse) — 닫힌 어휘. envlayer 가 실제로 수집하는 카테고리만
# 인정한다(_OSM_CATEGORIES 와 같은 집합) — 지어낸 대상은 소비할 데이터가 없다.
ENV_FEATURES = ("water", "forest", "park", "market")
ENV_DIRECTIONS = ("접근", "회피")
# 등급 → 강도. axis_scoring·route_familiarity 와 같은 5단계 스케일을 3단계로 쓴다
# (강도는 "약/중/강"이면 충분하고, 단계를 늘리면 LLM 이 가짜 정밀도를 만든다).
ENV_STRENGTH_SCORES = {"하": 0.3, "중": 0.5, "상": 0.9}


def sanitize_env_responses(raw: dict) -> list[EnvResponse]:
    """다수결·quote 검증을 거친 {feature: (direction, strength)} → 검증된 목록.

    마지막 방어선 — 닫힌 어휘 밖 feature/direction 과 규정 밖 강도는 버린다
    (sanitize_mind() 의 goal_label "실존 라벨만 인정"과 같은 원칙).
    """
    if not isinstance(raw, dict):
        return []
    valid_strengths = set(ENV_STRENGTH_SCORES.values())
    out: list[EnvResponse] = []
    for feature, item in raw.items():
        if feature not in ENV_FEATURES or not isinstance(item, tuple | list) or len(item) != 2:
            continue
        direction, strength = item
        if direction not in ENV_DIRECTIONS:
            continue
        if (not isinstance(strength, (int, float)) or isinstance(strength, bool)
                or strength not in valid_strengths):
            continue
        out.append(EnvResponse(feature=feature, direction=direction,
                               strength=float(strength)))
    return out


def sanitize_route_familiarity(
    raw: dict, targets: list[AttractionPoint],
) -> list[RouteFamiliarity]:
    """다수결·quote 검증을 거친 {라벨: 점수} → 검증된 RouteFamiliarity 리스트.

    다수결·quote 검증(axis_scoring._majority/_quote_exists 재사용)은
    route_familiarity_compiler 가 담당 — 여기서는 최종 결과값만 검증하는
    마지막 방어선이다. 실존 라벨만 인정(sanitize_mind() 의 goal_label 검증과
    동일 원칙)하고, ROUTE_LEVEL_SCORES 5단계 값이 아닌 점수는 버린다.
    """
    if not isinstance(raw, dict):
        return []
    valid_labels = {ap.label for ap in targets}
    valid_scores = set(ROUTE_LEVEL_SCORES.values())
    out = []
    for label, score in raw.items():
        if (label in valid_labels and isinstance(score, (int, float))
                and not isinstance(score, bool) and score in valid_scores):
            out.append(RouteFamiliarity(route=label, score=float(score)))
    return out
