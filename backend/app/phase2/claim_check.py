"""K 해석 값의 제3 판독 — 엔진에 들어갈 값마다 다른 모델(Mi:dm)에게 좁은 예/아니오로 묻는다.

K 의 두 판독(초안·재검토)은 같은 모델이라 독립 검증이 아니다. 4회차 개발 세트에서
- 두 판독이 함께 틀린 값이 게이트를 통과했고(H6: "다른 물가는 그냥 지나치세요" → 물가 전체 회피),
- 재검토가 맞는 초안을 근거 없이 되돌렸으며(S4: 인용된 과거 발견지 → 미보고),
- 두 판독이 엇갈려 맞는 값이 막혔다(S2 숲 접근, H8 대처).
그래서 엔진에 들어갈 값만 골라, 보호자 기록 전체와 그 값을 뜻하는 문장 하나를 주고 묻는다.

- 조건 과업의 주입 값(대처·방향·시간대 규칙·유형 전체 환경 반응): '아니오'면 미확인으로 내린다.
- 두 판독이 엇갈린 대처·방향·환경 값: 후보 중 딱 하나만 '예'면 그 값을 살린다.
- 핵심 과업의 과거 발견지: 발견지 값은 확인하고, 재검토가 되돌린 발견지는 다시 묻는다.

확인 호출이 실패하면(판정 없음) K 의 결과를 그대로 둔다 — 장애가 개인화를 지우지 않게.
질문 문장은 닫힌 값 어휘에서 만든다. 보호자 문장을 코드가 해석하지 않는다.
"""
from __future__ import annotations

from app.llm import midm
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


def _person(statement: str) -> str:
    return "대상자는 " + statement + "."


def environment_statement(feature: str, response: str, clauses=None) -> str:
    if not clauses:
        return (f"대상자는 {FEATURE[feature]}이(가) {RESPONSE[response]}. 어느 한 장소에서만 그런 것이 "
                "아니라 그런 곳이면 대체로 그렇다.")
    cond = " 또는 ".join(" 그리고 ".join(SIGNAL_WHEN[(c["signal"], c["state"])] for c in group) for group in clauses)
    return f"대상자는 {FEATURE[feature]}에서 {cond}에는 {ACT_WHEN[response]} 편이다."


def rule_statement(period: str, value: str) -> str:
    return f"대상자는 {PERIOD[period]} 길을 잃으면 {RULE_ACTION[value]}."


def found_statement(label: str) -> str:
    return f"대상자는 과거에 길을 잃었다가(실종됐다가) '{label}'에서 발견된 적이 있다."


def verify(parsed: dict, payload: dict) -> dict:
    """interpret() 결과를 제자리에서 고치고, 묻고 답한 것을 audit['claim_checks'] 에 남긴다."""
    notes = [n["text"] for n in evidence_notes(payload)]
    core, context = parsed["core"], parsed["context"]
    audit = parsed.setdefault("audit", {})
    checks: list[dict] = []

    asked: dict[str, bool | None] = {}

    def ask(field: str, statement: str, value) -> bool | None:
        if statement not in asked:   # 같은 사례 안에서 같은 문장은 한 번만 묻는다
            asked[statement] = midm.check_claim(notes, statement)
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

    # 3) 핵심 과업: 사건 시점에도 살아 있는 목적, 이동능력 등급
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
    audit["claim_checks"] = checks
    return parsed
