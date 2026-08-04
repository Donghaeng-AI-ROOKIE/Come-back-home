"""목적지 예측 가드레일 — EXAONE prior 출력 검증·보정.

회의 결정(1차 기술회의 3번): 평가표 대신 가드레일 — "택도 없는 건 거르고".
LLM 은 확률·거리 calibration 이 약하다는 전제(아키텍처 결정사항)에 따라:
- 전략확률: 숫자 출력을 받되 알려진 6전략만 인정, ε-floor 후 재정규화
- 끌림점: 숫자 대신 상/중/하 정성 등급만 받아 고정 가중치로 매핑
  (LLM 이 임의 숫자를 지어내는 것 자체를 차단) 후, 보호자 발화에서 나온
  근거 태그(evidence) 계수와 곱셈 병합 — sanitize_attraction_levels 참고
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
    evidence_prior_weight,
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

# behavior_tendency(작업 P1-3, behavior_compiler 산출) → 부양 전략과 배율.
# LEVEL_WEIGHTS(상3/중2/하1) 규약에 앵커링한 잠정 곱셈 계수 — 신규 튜닝 대상 아님
# (재정규화+EPSILON floor를 거치므로 정확한 값보다 방향·매핑이 결과를 지배한다).
# 은신(hide)은 머무름(stay)보다 약하게 — 은신은 짧게 이동한 뒤 정지라 LKP 근처에
# 집중되지만 점질량은 아니다(반경 표집의 소량 퍼짐을 남겨 그 이동분을 근사한다).
# 은신의 "발견 난이도"(은폐)는 위치 확률이 아니라 알람/수색안내 레이어의 몫이라
# 여기서 다루지 않는다.
TENDENCY_BOOST = {
    "stay":      {"staying_put": 3.0},
    "move":      {"random_walk": 2.0},
    "backtrack": {"backtracking": 3.0},
    "hide":      {"staying_put": 1.8},
}


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
    """(EXAONE 등급 × evidence 계수) → 정규화 → 상한. 지어낸 라벨은 버리고 빠진 라벨은 '중'.

    두 신호의 곱셈 병합(팀 결정 2026-07-21):
      w(장소) = LEVEL_WEIGHTS[EXAONE 등급] × EVIDENCE_PRIOR_WEIGHTS[근거 태그]

    - EXAONE 등급(상/중/하): 실종 상황·라벨 맥락을 보고 추론한 지향 가능성.
    - evidence(발견지/관찰/언급): 보호자 발화에서 분류된 근거 강도 = 관측 사실.
    한쪽으로 override 하면 다른 쪽 정보가 사라진다. 곱은 "둘 다 높아야 높다"라
    보호자가 언급만 한 장소를 LLM 이 '상'으로 밀어올려도 0.3 배로 눌리고, 반대로
    과거 실제 발견지를 LLM 이 '하'로 깎아도 0.9 배가 남아 완전히 죽지 않는다.
    곱의 최대 배율은 9 배(3×0.9 : 1×0.3)지만 ATTRACTION_CAP 이 독식을 막는다.
    """
    if persona is None or not persona.attraction_points:
        return {}
    levels = raw if isinstance(raw, dict) else {}
    weights = {
        ap.label: (LEVEL_WEIGHTS.get(levels.get(ap.label), LEVEL_WEIGHTS["중"])
                   * evidence_prior_weight(ap.evidence))
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

    # 2) 끌림점가중치 — autobiographical_destination_pull (치매 기억 앵커 축)
    axis_key = {
        PersonaType.dementia: "autobiographical_destination_pull",
    }.get(persona.type if persona else None)
    if axis_key and axis_key in axis_scores and prior.attraction_weights:
        sharpened = _sharpen(prior.attraction_weights, axis_scores[axis_key], floor=0.0)
        updates["attraction_weights"] = _apply_cap(sharpened, ATTRACTION_CAP)

    # 3) 전략확률 — behavior_tendency 방향 틸트 (lost_behavior/dementia_wandering,
    # behavior_compiler 산출). floor=0 — 아래에서 한 번만 적용한다: 브랜치 안에서
    # 개별 floor 하면 이미 floor 된 값이 다시 배율을 받아 결과가 실행 순서에 민감해진다.
    if persona and persona.behavior_tendency:
        base = updates.get("strategy_probs", prior.strategy_probs)
        updates["strategy_probs"] = _tilt_by_tendency(
            base, persona.behavior_tendency, floor=0.0)

    # strategy_probs 를 건드린 브랜치가 있으면 ε-floor 는 여기서 딱 한 번만 적용한다.
    if "strategy_probs" in updates:
        updates["strategy_probs"] = _floor_renormalize(updates["strategy_probs"], EPSILON)

    return prior.model_copy(update=updates) if updates else prior


def _floor_renormalize(dist: dict[str, float], floor: float) -> dict[str, float]:
    """재정규화된 분포에 ε-floor 보장 + 재정규화 (0 확률 금지 원칙). 여러 틸트가
    strategy_probs 에 겹칠 때(2+4) 각자 floor 하지 않고 이 함수로 한 번만 적용한다."""
    floored = {k: max(v, floor) for k, v in dist.items()}
    total = sum(floored.values())
    return {k: v / total for k, v in floored.items()}


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
    return _floor_renormalize(normed, floor) if floor > 0 else normed


def _boost_strategies(
    dist: dict[str, float], boosts: dict[str, float], *, floor: float,
) -> dict[str, float]:
    """dist 의 특정 전략(들)에 boosts 배율을 곱하고 재정규화(+선택적 floor). 틸트가
    strategy_probs 에 겹칠 수 있으므로 각자 내부 floor 하지 않도록 floor=0 으로
    호출하고, 최종 floor 는 호출부에서 한 번만 준다."""
    boosted = {k: v * boosts.get(k, 1.0) for k, v in dist.items()}
    total = sum(boosted.values())
    if total <= 0:
        return dict(dist)  # 방어 — 입력에 0 이 없다는 전제라 이론상 도달 안 함
    normed = {k: v / total for k, v in boosted.items()}
    return _floor_renormalize(normed, floor) if floor > 0 else normed


def _tilt_by_tendency(
    dist: dict[str, float], tendency: str | None, *, floor: float = EPSILON,
) -> dict[str, float]:
    """behavior_tendency 에 해당하는 전략(들)에 TENDENCY_BOOST 배율을 곱하고 재정규화.

    모르는 tendency(닫힌 어휘 밖)면 원본을 그대로 반환 — persona.behavior_tendency 는
    behavior_compiler.TENDENCY_LABELS 값만 채워지지만, 방어적으로 한 번 더 검증한다.
    floor 기본값은 EPSILON(단독 호출 시 즉시 0 확률 금지 보장) — apply_axis_scores
    는 floor=0 으로 호출하고 최종 floor 를 한 번만 별도로 적용한다.
    """
    boosts = TENDENCY_BOOST.get(tendency)
    if not boosts:
        return dict(dist)
    return _boost_strategies(dist, boosts, floor=floor)


def sanitize_radius(raw_level, profile: LognormalParams) -> LognormalParams:
    """등급이 유효하면 μ 보정, 아니면 프로파일 그대로. σ 는 항상 프로파일 값."""
    adjust = RADIUS_MU_ADJUST.get(raw_level, 0.0) if isinstance(raw_level, str) else 0.0
    return LognormalParams(mu=profile.mu + adjust, sigma=profile.sigma)


# ── 마음 재해석 (H·A 트리거 → EXAONE) 출력 검증 ─────────────────────
# confusion 도 숫자를 직접 받지 않고 상/중/하 → 고정 절대값
CONFUSION_LEVELS = {"상": 0.85, "중": 0.6, "하": 0.35}
STATUS_MAX_CHARS = 50

# 계약 v2 의 닫힌 행동 어휘 — mind_v2._FP_RULES_V2 의 원문과 글자 단위로 같아야 한다
# (다르면 모델 출력이 전부 어휘 밖으로 떨어져 조용히 버려진다).
# goal_label 의 "실존 라벨만 인정"과 같은 원칙 — 어휘 밖은 미판정으로 버린다.
BEHAVIORS = ("끌림점 접근", "귀소 시도", "은신·멈춤", "계속 배회")


def sanitize_mind(data: dict, current: MindState, labels: list[str]) -> tuple[MindState, str | None]:
    """LLM 재해석 JSON → (검증된 MindState, 목표 끌림점 라벨 또는 None).

    goal_label 은 실존 끌림점 라벨일 때만 인정 — 지어낸 목적지 차단.
    behavior 도 같은 원칙으로 닫힌 어휘만 인정하고, 어휘 밖이면 빈 문자열로 둔다.
    보행에 실제로 반영할지는 시뮬레이션이 설정으로 결정한다 (여기서는 검증만).
    """
    status = data.get("status")
    status = status.strip()[:STATUS_MAX_CHARS] if isinstance(status, str) and status.strip() \
        else current.status
    confusion = CONFUSION_LEVELS.get(data.get("confusion_level"), current.confusion)
    goal = data.get("goal_label")
    goal = goal if isinstance(goal, str) and goal in labels else None
    behavior = data.get("behavior")
    behavior = behavior if isinstance(behavior, str) and behavior in BEHAVIORS else ""
    mind = MindState(status=status, confusion=confusion, changed=True, behavior=behavior)
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
