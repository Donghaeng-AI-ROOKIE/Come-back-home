"""Connect K's semantic judgments to existing simulation inputs, once.

Multipliers are provisional engine conventions, not calibrated clinical probabilities.
Guardian language is interpreted by K; this module never searches it for keywords.
"""
from __future__ import annotations

from copy import deepcopy

from app.llm import person_evidence, person_scope, person_environment, initial_behavior
from app.phase2 import guardrail



# Goals that make a place a destination at the incident, after incident-time filtering.
CURRENT_GOALS = {"recent_action", "current_statement", *person_evidence.PERSISTENT_GOALS}


def agreed_environment(environment, scope):
    """A type-wide update requires agreement on direction AND spatial scope.

    The two tasks read the same evidence independently. Agreement is a consistency
    check, not proof of clinical correctness; disagreements remain in the audit.
    """
    proposals = person_environment.injectable(environment)
    accepted, disagreements = {}, []
    for feature, response in proposals.items():
        contextual = scope["environment"][feature]
        if contextual["scope"] == "explicit_category" and contextual["response"] == response:
            accepted[feature] = response
        else:
            disagreements.append({"feature": feature, "proposed_response": response,
                "proposed_scope": environment[feature]["scope"],
                "context_response": contextual["response"], "context_scope": contextual["scope"],
                "note_ids": sorted(set(environment[feature]["note_ids"] + contextual["note_ids"]))})
    return accepted, disagreements


def environment_from_context(scope):
    """Adapt typed K judgments to the engine contract; no guardian-text parsing."""
    scopes={'place_specific':'one_place','explicit_category':'category',
            'conditional_category':'category','unknown':'unknown'}
    conditions={'추가 조건 필요':'required','추가 조건 없음':'none_stated',
                '조건 미확인':'unknown'}
    return {f:{'note_ids':list(v['note_ids']),
               'basis':'reaction' if v['response']!='unknown' else 'unknown',
               'scope':scopes[v['scope']], 'condition':conditions.get(v['condition'],'unknown'),
               'response':v['response']} for f,v in scope['environment'].items()}


def combine(core: dict, scope: dict, payload: dict, environment: dict, *, verify_environment=True) -> dict:
    """Validate both contracts before replacing the two explicitly reviewed dimensions."""
    import json

    def response(value):
        return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}]}

    person_evidence.validate(response(core), payload)
    person_scope.validate(response(scope), payload)
    person_environment.validate(response(environment), payload)
    merged = deepcopy(core)
    p = scope["persistence"]
    merged["persistence"] = {
        "value": "conflict" if p["evidence"] == "conflicting" else p["value"],
        "note_ids": list(p["note_ids"]), "explanation": p["explanation"],
    }
    accepted, disagreements = (agreed_environment(environment, scope) if verify_environment
                               else (person_environment.injectable(environment), []))
    labels = {"water": "물가", "forest": "숲", "park": "공원", "market": "시장"}
    bases = {"reaction": "환경 반응 근거", "destination_only": "목적지 발언", "visit_only": "방문 이력", "unknown": "반응 미확인"}
    scopes = {"category": "환경 유형", "one_place": "특정 장소", "unknown": "범위 미확인"}
    conditions = {"required": "추가 조건 필요", "none_stated": "추가 조건 미보고", "unknown": "조건 미확인"}
    for feature, item in environment.items():
        merged["environment"][feature] = {
            "value": accepted.get(feature, "unknown"), "note_ids": list(item["note_ids"]),
            "explanation": f"{labels[feature]}: {bases[item['basis']]}, {scopes[item['scope']]}, {conditions[item['condition']]}." + (" 범위·반응 해석이 일치하지 않아 유형 전체 적용 보류." if any(x["feature"] == feature for x in disagreements) else ""),
        }
    return merged


def compile_person(core, scope, payload, persona, sar, default, *, environment=None):
    separate_environment = environment is not None
    if environment is None:
        environment = environment_from_context(scope)
    z = combine(core, scope, payload, environment, verify_environment=separate_environment)
    # generate_prior records the exact pre-tilt distribution, before epsilon flooring.
    if not sar.strategy_before_behavior and persona.behavior_tendency in guardrail.TENDENCY_BOOST:
        raise ValueError("missing_pre_behavior_strategy_snapshot")
    strategy = dict(sar.strategy_before_behavior or sar.strategy_probs)
    trace = [{"consumer": "strategy_probs", "action": "start_before_legacy_behavior_tilt"}]

    def boost(reason, factors):
        nonlocal strategy
        strategy = guardrail._boost_strategies(strategy, factors, floor=0)
        trace.append({"consumer": "strategy_probs", "semantic_evidence": reason, "factors": factors})

    persistence, direction = z["persistence"]["value"], z["direction"]["value"]
    if persistence == "wait_for_help":
        boost("persistence.wait_for_help", guardrail.TENDENCY_BOOST["stay"])
    elif persistence == "keep_moving":
        boost("persistence.keep_moving", {"staying_put": 1 / 3})
    if direction == "change_heading":
        boost("direction.change_heading", {"random_walk": 2., "direction_keeping": 1 / 3})
    elif direction == "same_heading":
        boost("direction.same_heading", {"direction_keeping": 3.})
    elif direction == "retrace":
        boost("direction.retrace", guardrail.TENDENCY_BOOST["backtrack"])
    current = [k for k, v in z["goals"].items() if v["value"] in CURRENT_GOALS]
    if current:
        boost("current_destination", {"landmark_seeking": 2.})
    if current and all(z["routes"][k]["value"] == "new_route" for k in current):
        boost("destination_without_route_experience", {"route_following": 1 / 3})
    strategy = guardrail.sanitize_strategy_probs(strategy, sar.strategy_probs)

    levels = {k: "상" if v["value"] in CURRENT_GOALS
              else "하" if v["value"] == "explicit_rejection" else "중"
              for k, v in z["goals"].items()}
    # Evidence strength comes from K's reading of the guardian's own words, not from
    # onboarding tags that surface-word rules may have upgraded or downgraded.
    evidence = {k: "previous_missing_found" if z["found_history"][k]["value"] == "found_here"
                else "caregiver_report" if z["goals"][k]["value"] in person_evidence.PERSISTENT_GOALS
                else "mention_only" for k in z["goals"]}
    weights = guardrail.sanitize_attraction_levels(levels, persona, evidence=evidence)
    route_grades = dict(zip(person_evidence.ROUTES[:5], [.1, .3, .5, .7, .9]))
    routes = [{"route": k, "score": route_grades[v["value"]]}
              for k, v in z["routes"].items() if v["value"] in route_grades]
    axis = dict(persona.axis_scores)
    mobility = z["mobility"]["value"]
    radius = sar.radius_lognormal
    if mobility in {"A", "B", "C", "D", "E"}:
        axis["mobility_transport_capacity"] = dict(zip("ABCDE", [.1, .3, .5, .7, .9]))[mobility]
        level = "하" if mobility in {"A", "B"} else "중" if mobility == "C" else "상"
        radius = guardrail.sanitize_radius(level, default.radius_lognormal)
    accepted_environment, environment_disagreements = (agreed_environment(environment, scope)
        if separate_environment else (person_environment.injectable(environment), []))
    env = [{"feature": k, "direction": "접근" if response == "approach" else "회피", "strength": .5}
           for k, response in accepted_environment.items()]
    conditional_environment = set()
    for feature,item in scope['environment'].items():
        clauses=item.get('condition_clauses', [])
        if (item['scope'] in {'conditional_category','explicit_category'} and item['response'] in {'approach','avoid'}
                and item['condition']=='추가 조건 필요' and clauses and not separate_environment):
            env.append({'feature':feature,'direction':'접근' if item['response']=='approach' else '회피',
                        'strength':.5,'condition_clauses':deepcopy(clauses)})
            conditional_environment.add(feature)
    for section, after in [("attraction_weights", weights), ("route_familiarity", routes),
                           ("env_responses", env), ("radius_lognormal", radius.model_dump())]:
        trace.append({"consumer": section, "after": after})

    # Preserve all dimensions and missing evidence in the structured contract, including
    # place-specific and conditional reactions the current engine cannot execute.
    unrepresented = []
    for feature, value in environment.items():
        if value["response"] != "unknown" and feature not in accepted_environment and feature not in conditional_environment:
            unrepresented.append({"feature": "environment." + feature, "scope": value["scope"],
                                  "reason": "engine_has_no_place_or_condition_specific_environment_input"})
    if z["emotion"]["value"] == "reported":
        unrepresented.append({"feature": "emotion", "reason": "no_calibrated_emotion_to_strategy_mapping"})
    if persistence == "alternating":
        unrepresented.append({"feature": "persistence", "reason": "no_observed_wait_walk_timing_model"})
    if scope["persistence"]["pattern"] == "conditional":
        unrepresented.append({"feature": "persistence", "reason": "initial_context_only_not_future_time_transition"})
    for trait in z["other_traits"]:
        unrepresented.append({"feature": "trait." + trait["type"], "period": trait["period"],
                              "note_ids": list(trait["note_ids"]), "reason": "no_engine_consumer_yet"})
    coverage = {n["id"]: [key for key, leaf in person_evidence.leaves(z) if n["id"] in leaf["note_ids"]]
                         + ["trait." + t["type"] for t in z["other_traits"] if n["id"] in t["note_ids"]]
                for n in payload["notes"]}
    # Render semantic state; a separate free-form model explanation must not silently
    # turn unobserved events into absent events or repeated visits into daily visits.
    goal_text = {"habitual_visit": "반복 방문 습관", "repeated_statement": "반복해서 가려는 발언", "recent_action": "최근 이동 관찰", "current_statement": "현재 가려는 의도 진술", "historical_only": "과거 관련 정보만 확인", "explicit_rejection": "현재 거부 진술", "unknown": "목적지 관계 미확인", "conflict": "목적지 보고 상충"}
    route_text = {"new_route": "경로 경험 없음", "accompanied_only": "동행 경험만 확인", "partial_recognition": "일부 구간 인식", "repeated_independent": "반복 독립 이동 경험", "routine_independent": "익숙한 경로의 독립 이동 경험", "unknown": "경로 인지 미확인", "conflict": "경로 보고 상충"}
    persistence_text = {"wait_for_help": "길을 잃었을 때 도움을 기다린 근거", "keep_moving": "길을 잃었을 때 이동을 이어간 근거", "alternating": "이동과 대기를 번갈아 한 근거", "unknown": "길 잃음 대응 미확인", "conflict": "길 잃음 대응 보고 상충"}
    direction_text = {"same_heading": "같은 방향을 유지한 근거", "change_heading": "이동 중 방향을 바꾼 근거", "retrace": "왔던 길을 되짚은 근거", "unknown": "방향 선택 미확인", "conflict": "방향 선택 보고 상충"}
    mobility_text = {"A": "독립 보행 제약", "B": "짧은 보행과 휴식 필요", "C": "생활권 보행 능력", "D": "수 km 보행 능력", "E": "장거리 보행 이력", "unknown": "보행 능력 미확인", "conflict": "보행 능력 보고 상충"}
    sentences = [f"{k}: {goal_text[v['value']]}, {route_text[z['routes'][k]['value']]}"
                 + (", 과거 실종 때 발견된 곳" if z["found_history"][k]["value"] == "found_here" else "")
                 for k, v in z["goals"].items()]
    sentences += [persistence_text[persistence], direction_text[direction], mobility_text[mobility]]
    if scope["persistence"]["pattern"] == "conditional":
        sentences.append("길 잃음 대응은 사건 조건에 따라 달라짐")
    if environment_disagreements:
        sentences.append("환경 반응의 적용 범위 해석이 일치하지 않아 일반화 보류")
    summary = ". ".join(sentences) + "."
    interpretation = {
        "version": person_evidence.VERSION, "status": "applied", "model": "K-EXAONE",
        "summary": summary or "초기 행동을 해석할 개인 관찰 정보 미확인.",
        "semantic_contract": z, "context_scope": {"persistence": deepcopy(scope["persistence"])},
        "model_explanations_unverified": True, "environment_contract": deepcopy(environment), "environment_disagreements": environment_disagreements, "coverage": coverage,
        "environment_method": "separate_contract_agreement" if separate_environment else "single_context_contract",
        "unassigned_note_ids": [n for n, features in coverage.items() if not features],
        "conditional_environment": {f:deepcopy(scope['environment'][f]) for f in conditional_environment},
        "environment_conditions": {f:deepcopy(v.get('condition_clauses', [])) for f,v in scope['environment'].items()},
        "condition_execution": "requires location/time-scoped observations; missing or conflicting signals stay neutral",
        "unrepresented": unrepresented, "projection_trace": trace, "sar_source": sar.source,
        "retrieval_audit": payload.get("retrieval_audit", []),
        "source_audit": {
            "evidence_note_ids": [n['id'] for n in initial_behavior.evidence_notes(payload)],
            "excluded_derived_note_ids": [n['id'] for n in payload['notes']
                if n['id'] not in {x['id'] for x in initial_behavior.evidence_notes(payload)}],
            "quality": "guardian_original" if any(n['provenance']=='guardian_original'
                for n in initial_behavior.evidence_notes(payload)) else "derived_only_unverified",
            "limitation": "원문이 없는 추출 정보는 개인 사실로 확정하지 않으며 별도 확인 필요",
        },
        "limitations": ["수치 배율은 잠정 규약이며 임상 보정값이 아님",
                        "실제 기억한 경로·보행 후 휴식 간격·도움 요청은 현재 엔진이 직접 재현하지 못함",
                        "원문·해석을 보존해도 모든 특성이 경로로 실행된다는 뜻은 아님",
                        "기존 자동 추출 경로·환경 입력을 이번 사건 근거로 재구성; 보호자 원본은 변경하지 않음"],
    }
    # Never embed raw note text, model response, reasoning tokens or SAR full prior in the API object.
    return sar.model_copy(update={
        "strategy_probs": strategy, "attraction_weights": weights, "radius_lognormal": radius,
        "reasoning": interpretation["summary"], "initial_interpretation": interpretation,
        "persona_adjustments": {"persona_id": persona.id, "persona_version": persona.version,
                                "axis_scores": axis, "route_familiarity": routes, "env_responses": env},
    })
