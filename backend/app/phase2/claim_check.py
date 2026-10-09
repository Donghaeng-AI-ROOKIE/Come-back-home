"""K 해석 값의 제3 판독 — 엔진에 들어갈 값마다 다른 모델(Mi:dm)에게 좁은 예/아니오로 묻는다.

K 의 두 판독(초안·재검토)은 같은 모델이라 독립 검증이 아니다. 4회차 개발 세트에서
- 두 판독이 함께 틀린 값이 게이트를 통과했고(H6: "다른 물가는 그냥 지나치세요" → 물가 전체 회피),
- 재검토가 맞는 초안을 근거 없이 되돌렸으며(S4: 인용된 과거 발견지 → 미보고),
- 두 판독이 엇갈려 맞는 값이 막혔다(S2 숲 접근, H8 대처).
그래서 엔진에 들어갈 값과 저장할 보조 특성을 골라, 근거 기록과 그 값을 뜻하는 문장 하나를 주고 묻는다.

- 조건 과업의 주입 값(대처·방향·시간대 규칙·유형 전체 환경 반응): '아니오'면 미확인으로 내린다.
- 두 판독이 엇갈린 대처·방향·환경 값: 후보 중 딱 하나만 '예'면 그 값을 살린다.
- 핵심 과업의 과거 발견지: 발견지 값은 확인하고, 재검토가 되돌린 발견지는 다시 묻는다.
- 보조 특성: 해당 특성이 인용한 보호자 원문에서 확인하고, 부정·미확인 결과를 구분해 기록한다.

확인 호출이 실패하면(판정 없음) K 의 결과를 그대로 둔다 — 장애가 개인화를 지우지 않게.
질문 문장은 닫힌 값 어휘에서 만든다. 보호자 문장을 코드가 해석하지 않는다.
"""
from __future__ import annotations

from app.llm import midm, person_evidence
from app.llm.initial_behavior import evidence_notes

PERSIST = {"wait_for_help": "길을 잃으면 그 자리에 머물며 도움을 기다린다",
           "keep_moving": "길을 잃으면 멈추지 않고 계속 걷는다",
           "alternating": "길을 잃으면 걷다가 멈추기를 번갈아 한다"}
DIRECTION = {"same_heading": "길을 잃으면 처음 가던 방향으로 계속 간다",
             "change_heading": "길을 잃으면 가던 방향을 자주 바꾼다",
             "retrace": "길을 잃으면 방금 걸어온 길을 거꾸로 되돌아간다"}
PERIOD = {"clock_day": "낮(오전 6시~오후 6시)에", "clock_night": "밤(오후 6시~오전 6시)에"}
# 시간대 규칙은 '낮과 밤이 다르다'가 핵심이다 — 행동만 묻으면 시간대와 무관한 행동도 규칙으로
# 통과한다(6회차 H5·H10). 한 문장에 둘을 합쳐 물으면 뒤 절만 보고 답한다(7회차 H5) — 따로 묻는다.
DIFFERS = "대상자는 길을 잃었을 때 낮과 밤에 서로 다르게 행동한다고 보호자가 말했다."
RULE_ACTION = {"wait_for_help": "그 자리에 머물며 도움을 기다린다", "keep_moving": "멈추지 않고 계속 걷는다",
               "alternating": "걷다가 멈추기를 번갈아 한다", "same_heading": "처음 가던 방향으로 계속 간다",
               "change_heading": "가던 방향을 자주 바꾼다", "retrace": "방금 걸어온 길을 거꾸로 되돌아간다"}
SIGNAL_WHEN = {("crowded", "present"): "사람이 많을 때", ("crowded", "absent"): "사람이 많지 않을 때",
               ("noisy", "present"): "시끄러울 때", ("noisy", "absent"): "조용할 때"}
ACT_WHEN = {"approach": "그쪽으로 가거나 들어가는", "avoid": "피하거나 빠져나오는"}
FEATURE = {"water": "물가(강·호수·개천·분수 등)", "forest": "숲이나 산", "park": "공원", "market": "시장"}
RESPONSE = {"approach": "보이면 그쪽으로 가거나 들어가는 편이다", "avoid": "보이면 피하거나 멀리하는 편이다"}
SIGNAL = {("crowded", "present"): "사람이 많음", ("crowded", "absent"): "사람이 많지 않음",
          ("noisy", "present"): "시끄러움", ("noisy", "absent"): "조용함"}
CATEGORY = ("explicit_category", "conditional_category")
# 사건 시점에도 살아 남는 목적(반복 방문·반복 발언)을 묻는다. 과거에 발견된 곳이기도 한 장소만 묻는다 —
# 최종 게이트 1회차 P01: "삼송역 같은 지하철역에서 찾은 적이 있어요"를 두 판독이 '평소 가는 곳'으로 읽었다.
# 모든 목적에 물으면 '분명히 적혀 있지 않은' 습관까지 내린다(9회차 H6: "호수공원 분수대 앞에만 가면 한참
# 서서 구경하세요"를 기준은 반복 방문으로 보는데 확인에서 탈락). 발견지와 목적지를 섞는 것이 이 확인의 과녁이다.
GOAL = {"habitual_visit": "대상자는 요즘도 평소에 '{label}'에 반복해서 가거나 가려고 한다(가족이 데려가는 경우 포함).",
        "repeated_statement": "대상자는 요즘 여러 날에 걸쳐 '{label}'에 가야 한다고 반복해서 말한다. "
                              "그곳을 다른 이름으로 부르는 경우도 포함한다."}
# 이동능력은 순서 있는 등급이다 — K 등급이 확인되지 않으면 바로 옆 등급만 묻고 하나만 맞을 때 바꾼다.
# 최종 게이트 1회차 P03: "걸어서 20분쯤" 걸리는 밭을 매일 다니는 사람을 B(집 근처 짧은 보행)로 읽었다.
MOBILITY = {"A": "대상자는 혼자서는 거의 걷지 못한다.",
            # 정의(집 근처 짧은 보행/휴식 필요)를 그대로 옮긴다. 10회차에 '몸이 약해 … 힘들어서 쉬어야'로 좁히자
            # 맞던 B 4건(S7·H5·H14·P09)이 떨어졌다 — H8(길 잃고 걷다 멈춤이 '자주 쉰다'로 읽힘) 한 건보다 손실이 크다.
            "B": "대상자는 집 근처만 짧게 걷고, 오래 걷지 못하거나 걷다가 자주 쉬어야 한다.",
            "C": "대상자는 혼자서 동네를 30분에서 1시간 정도 걸어 다닐 수 있다.",
            "D": "대상자는 혼자서 몇 km를 계속 걸을 수 있다.",
            "E": "대상자는 아주 먼 거리(10km 이상)를 걸어서 간 적이 있다."}
GRADES = "ABCDE"

# These are propositions about a typed K output, not keywords used to classify a
# guardian's text. Waiting for help does not establish that help was requested.
TRAIT = {
    "time_pattern": "대상자의 특정 시각·시간대·요일에 반복되는 행동이나 발언을 보호자가 보고했다.",
    "transport_use": "대상자가 걷기 외의 교통수단을 이용하거나 이용할 수 있다는 개인 정보를 보호자가 보고했다.",
    "rest_pattern": "대상자가 걷다가 신체적 휴식을 필요로 하거나 보행과 휴식을 반복한다고 보호자가 보고했다. 길을 잃어 가족을 기다리는 선택과는 구분한다.",
    "help_seeking": "대상자가 다른 사람에게 길을 묻거나 도와 달라고 요청한 행동을 보호자가 보고했다. 가족이 올 때까지 기다렸다는 사실만으로 요청 행동이 있었다고 판단하지 않는다.",
    "communication": "대상자가 다른 사람의 말이나 부름에 어떻게 반응하거나 의사소통하는지 보호자가 보고했다.",
    "person_seeking": "대상자가 특정 사람을 찾으려 하거나 만나기 위해 이동하려는 행동·발언을 보호자가 보고했다. 가족을 기다렸다는 사실만으로 가족을 찾아 이동한다고 판단하지 않는다.",
    "routine_route": "대상자가 반복해서 다니는 특정 경로나 늘 같은 길을 도는 습관을 보호자가 보고했다.",
    "wayfinding_failure": "대상자가 익숙한 곳을 알아보지 못하거나 목적지를 지나치거나 길을 찾지 못한 개인 경험을 보호자가 보고했다.",
    "hazard_unawareness": "대상자가 날씨·복장·주변 위험을 알아차리지 못하는 행동을 보호자가 보고했다.",
    "past_role": "대상자의 과거 직장이나 생활 역할에 관한 개인 정보를 보호자가 보고했다.",
    "hiding_or_staying": "대상자가 숨거나 한곳에서 오래 머무른 개인 행동을 보호자가 보고했다.",
}


def _person(statement: str) -> str:
    return "대상자는 " + statement + "."


def environment_statement(feature: str, response: str, clauses=None) -> str:
    if not clauses:
        return (f"대상자는 {FEATURE[feature]}이(가) {RESPONSE[response]}. 어느 한 장소에서만 그런 것이 "
                "아니라 그런 곳이면 대체로 그렇다.")
    cond = " 또는 ".join(" 그리고 ".join(SIGNAL_WHEN[(c["signal"], c["state"])] for c in group) for group in clauses)
    return f"대상자는 {FEATURE[feature]}에서 {cond}에는 {ACT_WHEN[response]} 편이다."


def category_scope_statement(feature: str) -> str:
    return (f"보호자는 대상자의 {FEATURE[feature]} 반응을 특정한 한 장소에만 국한하지 않고 "
            "그 유형의 장소 전반에 해당하는 개인 반응으로 설명했다. 한 장소에서만 관찰했고 "
            "다른 곳은 모른다고 했다면 유형 전체의 반응으로 설명한 것이 아니다. "
            "반응에 혼잡·소음 같은 발동 조건이 있다는 사실과 장소 범위는 별개다.")


def rule_statement(period: str, value: str) -> str:
    return f"대상자는 {PERIOD[period]} 길을 잃으면 {RULE_ACTION[value]}."


def found_statement(label: str) -> str:
    return f"대상자는 과거에 길을 잃었다가(실종됐다가) '{label}'에서 발견된 적이 있다."


def historical_route_statement(label: str) -> str:
    return (f"대상자가 과거에 '{label}'까지 가는 길을 혼자 반복해서 걸어 다녔다는 "
            "구체적인 경험을 보호자가 보고했다. 그곳에서 일하거나 살았다는 사실만으로 "
            "혼자 그 길을 걸었다고 추정하지 않는다. 현재도 그 길을 잘 찾는다는 판단과는 별개다.")


def _condition_cubes(positive):
    """Minimal positive DNF for two verified Boolean signals, never text parsing.

    Unconfirmed cells are excluded. A uniform table does not prove an unqualified
    reaction, so leave that case for review instead of dropping every condition.
    """
    from itertools import product
    universe = set(product((False, True), repeat=2))
    if not positive or positive == universe:
        return []
    candidates = []
    for cube in product((None, False, True), repeat=2):
        covered = {row for row in universe if all(v is None or v == x for v,x in zip(cube,row))}
        if covered and covered <= positive:
            candidates.append((cube,covered))
    maximal = [(cube,covered) for cube,covered in candidates
               if not any(covered < other for _,other in candidates)]
    return [[{'signal':signal,'state':'present' if value else 'absent'}
             for signal,value in zip(('crowded','noisy'),cube) if value is not None]
            for cube,_ in maximal]


def route_statement(label, value):
    table = {
        'new_route': f"대상자는 '{label}'까지 가는 경로를 경험한 적이 없다고 보호자가 명시했다. 경험 여부를 모른다는 말이나 몸 능력의 제약만으로 경험이 없다고 판단하지 않는다.",
        'accompanied_only': f"대상자는 '{label}'까지 동행해서 다녀본 경험만 있고 혼자 이동한 경험은 확인되지 않았다고 보호자가 보고했다.",
        'partial_recognition': f"대상자가 '{label}' 경로의 일부 구간이나 표식을 알아본 개인 경험을 보호자가 보고했다.",
        'repeated_independent': historical_route_statement(label),
        'routine_independent': f"대상자가 현재도 일상적으로 '{label}'까지 혼자 걸어 다닌다고 보호자가 보고했다.",
    }
    return table.get(value)


def verify(parsed: dict, payload: dict) -> dict:
    """interpret() 결과를 제자리에서 고치고, 묻고 답한 것을 audit['claim_checks'] 에 남긴다."""
    cited_answers = {}
    def check_cited(source_notes, statement):
        key = (tuple(source_notes), statement)
        if key not in cited_answers:
            cited_answers[key] = midm.check_claim(source_notes, statement)
        return cited_answers[key]

    notes = [n["text"] for n in evidence_notes(payload)]
    core, context = parsed["core"], parsed["context"]
    audit = parsed.setdefault("audit", {})
    checks: list[dict] = []

    asked: dict[str, bool | None] = {}

    def ask(field: str, statement: str, value) -> bool | None:
        if statement not in asked:   # 같은 사례 안에서 같은 문장은 한 번만 묻는다
            asked[statement] = check_cited(notes, statement)
            checks.append({"field": field, "value": value, "statement": statement, "answer": asked[statement]})
        return asked[statement]

    def rule_holds(period: str, value: str, field: str, rule) -> bool | None:
        """낮밤 차이와 그 시간대 행동을 따로 물어 합친다. 하나라도 '아니오'면 False, 둘 다 '예'면 True."""
        differs = ask("behavior_rules:day_night", DIFFERS, None)
        if differs is False:
            return False
        action = ask(field, rule_statement(period, value), rule)
        if action is False:
            return False
        return True if (differs and action) else None

    held = "제3 판독에서 확인되지 않아 적용 보류."
    # 1) 조건 과업의 주입 값 — '아니오'면 내린다
    p = context["persistence"]
    if p["value"] in PERSIST and ask("persistence", _person(PERSIST[p["value"]]), p["value"]) is False:
        p.update(value="unknown", pattern="unresolved", explanation=held)
    b = context.get("baseline_direction")
    if b and b["value"] in DIRECTION and ask("baseline_direction", _person(DIRECTION[b["value"]]), b["value"]) is False:
        b["value"] = "unknown"
    kept = []
    for rule in context.get("behavior_rules", []):
        if rule["value"] in RULE_ACTION and rule_holds(rule["period"], rule["value"], "behavior_rules",
                                                       [rule["period"], rule["dimension"], rule["value"]]) is False:
            continue
        kept.append(rule)
    if "behavior_rules" in context:
        context["behavior_rules"] = kept
        if not kept:
            context.pop("behavior_rules")
    for feature, e in context["environment"].items():
        if e["response"] in RESPONSE and e["scope"] in CATEGORY and ask(
                "environment." + feature, environment_statement(feature, e["response"], e.get("condition_clauses")),
                [e["response"], e["scope"]]) is False:
            e.update(response="unknown", scope="unknown", condition="조건 미확인", explanation=held)
            e.pop("condition_clauses", None)

    # 2) 두 판독이 엇갈린 값 — 후보 중 딱 하나만 '예'면 살린다
    for d in audit.get("context_disagreements", []):
        field = d.get("field")
        if field in ("persistence", "baseline_direction"):
            table = PERSIST if field == "persistence" else DIRECTION
            candidates = [v for v in dict.fromkeys([d.get("draft"), d.get("review")]) if v in table]
            confirmed = [v for v in candidates if ask(field + ":disagreement", _person(table[v]), v) is True]
            if len(confirmed) == 1 and candidates:
                if field == "persistence":
                    p.update(value=confirmed[0], evidence="supported", pattern="consistent",
                             explanation="두 판독이 엇갈려 제3 판독으로 확인한 값.")
                elif b is not None:
                    b["value"] = confirmed[0]
                d["resolved"] = confirmed[0]
        elif field == "behavior_rules" and d.get("rule") and d.get("note_ids"):
            period, dimension, value = d["rule"]
            table = PERSIST if dimension == "persistence" else DIRECTION
            rules = context.setdefault("behavior_rules", [])
            if value in table and not any((r["period"], r["dimension"]) == (period, dimension) for r in rules) \
                    and rule_holds(period, value, "behavior_rules:disagreement", d["rule"]) is True:
                rules.append({"period": period, "dimension": dimension, "value": value, "note_ids": list(d["note_ids"])})
                d["resolved"] = d["rule"]
            if not rules:
                context.pop("behavior_rules")
        elif isinstance(field, str) and field.startswith("environment."):
            feature = field.split(".", 1)[1]
            # (반응, 범위, 조건식) 후보 — 유형 전체 반응과 조건부 반응(조건식 포함)을 함께 본다(7회차 H12:
            # 초안의 '붐비는 장날 시장 회피'가 재검토 unknown 과 엇갈려 막혔다)
            candidates = []
            for side in ("draft", "review"):
                x, clauses = d.get(side), d.get(side + "_clauses") or []
                if not (isinstance(x, list) and x[0] in RESPONSE):
                    continue
                if x[1] == "explicit_category" or (x[1] == "conditional_category" and clauses):
                    cand = (x[0], x[1], clauses if x[1] == "conditional_category" else [])
                    if cand not in candidates:
                        candidates.append(cand)
            confirmed = [c for c in candidates if ask(field + ":disagreement",
                                                      environment_statement(feature, c[0], c[2]), [c[0], c[1]]) is True]
            if len(confirmed) == 1 and feature in context["environment"]:
                response, scope, clauses = confirmed[0]
                context["environment"][feature].update(
                    response=response, scope=scope,
                    condition="추가 조건 필요" if clauses else "추가 조건 없음",
                    explanation="두 판독이 엇갈려 제3 판독으로 확인한 반응.")
                if clauses:
                    context["environment"][feature]["condition_clauses"] = clauses
                d["resolved"] = [response, scope]

    # If a conditional reading was rejected, do not invert its polarity or its
    # Boolean expression. Ask the cited source about the two reactions and the
    # four signal combinations independently. This can recover an omitted OR
    # without mistaking "does not avoid" for "approaches".
    by_note = {n['id']: n['text'] for n in evidence_notes(payload)}
    condition_recovery = []
    for feature, e in context['environment'].items():
        disputed = [d for d in audit.get('context_disagreements', [])
                    if d.get('field') == 'environment.' + feature
                    and (d.get('draft_clauses') or d.get('review_clauses'))]
        ids = [i for i in e.get('note_ids', []) if i in by_note]
        if e['response'] != 'unknown' or not disputed or not ids:
            continue
        cited = [by_note[i] for i in ids]
        reactions = {}
        for response in ('approach','avoid'):
            statement = (f"보호자는 대상자가 {FEATURE[feature]}을(를) 마주쳤을 때 "
                         f"{ACT_WHEN[response]} 행동을 직접 관찰했다고 보고했다. 조건이 붙은 관찰도 포함한다. "
                         "피하지 않았다는 말만으로 접근했다고 판단하지 않으며, 목적지로 가려는 의도만으로 마주친 반응을 추정하지 않는다.")
            reactions[response] = check_cited(cited,statement)
        confirmed = [r for r,v in reactions.items() if v is True]
        entry = {'feature':feature,'note_ids':ids,'reactions':reactions,'cells':[]}
        condition_recovery.append(entry)
        if len(confirmed) != 1 or any(v is None for v in reactions.values()):
            continue
        response = confirmed[0];positive = set()
        for crowded,noisy in ((False,False),(False,True),(True,False),(True,True)):
            clauses = [[{'signal':'crowded','state':'present' if crowded else 'absent'},
                        {'signal':'noisy','state':'present' if noisy else 'absent'}]]
            answer = check_cited(cited, environment_statement(feature,response,clauses))
            entry['cells'].append({'crowded':crowded,'noisy':noisy,'answer':answer})
            if answer is True:positive.add((crowded,noisy))
        clauses = _condition_cubes(positive)
        if clauses and all(cell['answer'] is not None for cell in entry['cells']):
            e.update(response=response,scope='conditional_category',condition='추가 조건 필요',
                     condition_clauses=clauses,explanation='원문에서 반응 방향과 조건 조합을 따로 확인. 장소 범위는 별도 판독.')
            entry['recovered_clauses'] = clauses
    audit['condition_recovery'] = condition_recovery

    # A condition can hold at one place without applying to every place of its
    # category. Check spatial scope separately after disagreement recovery too.
    scope_checks = []
    for feature, e in context['environment'].items():
        if e['response'] in RESPONSE and e['scope'] == 'conditional_category':
            answer = ask('environment.' + feature + ':category_scope',
                         category_scope_statement(feature), e['scope'])
            scope_checks.append({'feature': feature, 'answer': answer})
            if answer is False:
                e['scope'] = 'place_specific'
                e['explanation'] = '반응 조건은 보존하되 유형 전체에 일반화할 근거가 없어 장소별 관찰로 제한.'
    audit['environment_scope_checks'] = scope_checks

    # 3) 핵심 과업: 사건 시점에도 살아 있는 목적, 이동능력 등급
    # A candidate label is not evidence of a past personal relationship either.
    for label, leaf in core['goals'].items():
        if leaf['value'] == 'historical_only':
            statement = (f"대상자에게 '{label}'을(를) 생활 목적지로 이용했거나 그곳에서 살거나 일했거나 "
                         "그곳으로 가려는 행동·발언을 한 과거 개인 이력이 보호자 원문에 있다. "
                         "비교용 후보나 장소 주변에서의 환경 반응 관찰만으로 생활 목적지 이력이 있다고 판단하지 않는다.")
            if ask('goals.' + label + ':historical_relationship', statement, 'historical_only') is False:
                leaf.update(value='unknown', period='unspecified', explanation=held)
    for label, leaf in core["goals"].items():
        found_too = core["found_history"].get(label, {}).get("value") == "found_here"
        if leaf["value"] in GOAL and found_too and ask("goals." + label, GOAL[leaf["value"]].format(label=label),
                                                       leaf["value"]) is False:
            leaf.update(value="unknown", period="unspecified", explanation=held)
    m = core.get("mobility")
    if m and m["value"] in MOBILITY and ask("mobility", MOBILITY[m["value"]], m["value"]) is False:
        i = GRADES.index(m["value"])
        nearby = [GRADES[j] for j in (i - 1, i + 1) if 0 <= j < len(GRADES)]
        confirmed = [g for g in nearby if ask("mobility:neighbor", MOBILITY[g], g) is True]
        if len(confirmed) == 1:
            m.update(value=confirmed[0], explanation="K 등급이 확인되지 않아 제3 판독으로 확인한 옆 등급.")
        else:
            m.update(value="unknown", explanation=held)

    # 4) 핵심 과업의 과거 발견지
    for label, leaf in core["found_history"].items():
        if leaf["value"] == "found_here" and ask("found_history." + label, found_statement(label), "found_here") is False:
            leaf.update(value="not_reported", note_ids=[])
    for change in audit.get("core_review_changes", []):
        label = change["field"].split(".", 1)[1]
        if (change["draft"] == "found_here" and change["review"] == "not_reported" and label in core["found_history"]
                and core["found_history"][label]["value"] == "not_reported"
                and ask("found_history." + label + ":review_reversal", found_statement(label), "found_here") is True):
            core["found_history"][label].update(value="found_here", note_ids=list(change["draft_note_ids"]))
            change["resolved"] = "found_here"
    # A discontinued destination can still have a known route history. Do not
    # collapse "does not go now" into "has never had independent experience".
    # A model judges the cited passage; the code does not parse guardian words.
    original_by_id = {n['id']: n['text'] for n in evidence_notes(payload)}
    history_checks = []
    for label, route in core.get('routes', {}).items():
        goal = core['goals'].get(label, {})
        if route['value'] != 'unknown' or goal.get('value') != 'historical_only':
            continue
        ids = sorted({i for i in goal.get('note_ids', []) if i in original_by_id})
        if not ids:
            continue
        statement = historical_route_statement(label)
        answer = check_cited([original_by_id[i] for i in ids], statement)
        history_checks.append({'place': label, 'note_ids': ids, 'statement': statement, 'answer': answer,
                               'current_navigation_ability': 'not_established_by_past_experience'})
        if answer is True:
            route.update(value='repeated_independent', note_ids=ids,
                         explanation='보호자 원문에서 과거의 반복 독립 보행 경험 확인. 현재 길찾기 능력을 확정하지 않음.')
    audit['route_history_checks'] = history_checks
    # The chosen value and its citation must agree. A correct route value with a
    # mobility note as its only citation is still an evidence-link error.
    citation_checks = []
    draft_routes = audit.get('route_draft_candidates', {})
    for label, route in core.get('routes', {}).items():
        statement = route_statement(label,route['value'])
        if not statement:
            continue
        ids = [i for i in route.get('note_ids', []) if i in original_by_id]
        answer = check_cited([original_by_id[i] for i in ids],statement) if ids else False
        record = {'place':label,'value':route['value'],'note_ids':ids,'answer':answer}
        citation_checks.append(record)
        if answer is False:
            draft = draft_routes.get(label,{})
            alternate = [i for i in draft.get('note_ids',[]) if i in original_by_id]
            alternative_answer = (check_cited([original_by_id[i] for i in alternate],statement)
                if draft.get('value')==route['value'] and set(alternate)!=set(ids) and alternate else False)
            record.update(alternative_note_ids=alternate,alternative_answer=alternative_answer)
            if alternative_answer is True:
                route['note_ids'] = alternate
            else:
                route.update(value='unknown',explanation='경로 경험의 인용 근거가 확인되지 않아 보류.')
    audit['route_citation_checks'] = citation_checks
    if core.get('emotion',{}).get('value') == 'reported':
        emotion_statement = ('보호자가 대상자의 불안·공포·그리움·분노 등의 정서 상태를 직접 보고했다. '
                             '장소를 피하거나 접근한 행동만으로 정서 상태를 추정하지 않는다.')
        if ask('emotion',emotion_statement,'reported') is False:
            core['emotion'].update(value='unknown',explanation=held)
    # A short-walking grade is not itself a rest cycle. If the extra trait was
    # omitted by both readings, ask its original mobility evidence explicitly.
    if core.get('mobility',{}).get('value') == 'B' and not any(t['type']=='rest_pattern' for t in core.get('other_traits',[])):
        ids = [i for i in core['mobility'].get('note_ids',[]) if i in original_by_id]
        answer = check_cited([original_by_id[i] for i in ids],TRAIT['rest_pattern']) if ids else False
        audit['missing_rest_check'] = {'note_ids':ids,'answer':answer}
        if answer is True and len(core['other_traits']) < person_evidence.MAX_TRAITS:
            core['other_traits'].append({'type':'rest_pattern','period':'unspecified','note_ids':ids})
    audit["claim_checks"] = checks
    # 5) Additional personal traits remain part of the representation even before
    # there is a walking consumer. Check their own cited notes as well, so a correct
    # waiting observation cannot silently grow into an unobserved help request.
    by_id = {n['id']: n['text'] for n in evidence_notes(payload)}
    kept_traits = []
    trait_checks = []
    rejected_traits = []
    unconfirmed_traits = []
    restored_traits = []
    trait_cache = {}
    final_types = {t['type'] for t in core.get('other_traits', [])}
    candidates = [(t,False) for t in core.get('other_traits', [])]
    candidates += [(t,True) for t in audit.get('trait_review_omissions', [])
                   if t['type'] not in final_types]
    for trait, was_omitted in candidates:
        statement = TRAIT.get(trait['type'])
        if statement is None:  # "other" has no specific proposition to confirm.
            if not was_omitted:
                kept_traits.append(trait)
            unconfirmed_traits.append({**trait, 'reason': 'no_specific_trait_contract'})
            continue
        ids = tuple(sorted(set(trait['note_ids'])))
        key = (statement, ids)
        if key not in trait_cache:
            cited = [by_id[i] for i in ids if i in by_id]
            trait_cache[key] = check_cited(cited, statement) if cited else False
        answer = trait_cache[key]
        trait_checks.append({'type': trait['type'], 'note_ids': list(ids),
                             'statement': statement, 'answer': answer})
        if answer is False:
            rejected_traits.append(dict(trait))
        else:
            if was_omitted:
                if answer is True and len(kept_traits) < person_evidence.MAX_TRAITS:
                    if trait not in kept_traits:
                        kept_traits.append(trait)
                        restored_traits.append(dict(trait))
                elif answer is True:
                    unconfirmed_traits.append({**trait, 'reason': 'output_capacity_requires_review'})
            else:
                kept_traits.append(trait)
            if answer is None:
                unconfirmed_traits.append({**trait, 'reason': 'verification_unavailable'})
    core['other_traits'] = kept_traits
    audit['trait_checks'] = trait_checks
    audit['rejected_traits'] = rejected_traits
    audit['unconfirmed_traits'] = unconfirmed_traits
    audit['restored_traits'] = restored_traits
    return parsed
