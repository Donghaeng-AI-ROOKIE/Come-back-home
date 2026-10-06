"""Show a compiler candidate its executable counterfactual effects, not just prose.

Counterfactuals come from the typed draft, never keyword-parsed caregiver text.
They are development diagnostics, not observed patient states or target labels.
"""
import json
from copy import deepcopy
from app.llm import mind_policy
from experiments.mind_policy_candidates import compact16


def probes(draft, personal):
    policy = compact16.compile(draft, personal)
    result = []
    for rule in policy.rules:
        for clause in rule.when:
            active = {name: False for name in mind_policy.BOOLEAN_FACTS}
            active.update(continuous_walk_minutes=0, distance_since_rest_m=0,
                          clock_hour=8, is_walking=True)
            for atom in clause:
                active[atom.fact] = atom.value
            scenes = [("draft_rule_conditions_true", active)]
            for atom in clause:
                changed = deepcopy(active)
                changed[atom.fact] = (not atom.value if type(atom.value) is bool
                                      else max(0., atom.value - 1) if atom.op == 'gte'
                                      else atom.value + 1)
                scenes.append(("change_" + atom.fact, changed))
            features = {feature: feature == rule.feature for feature in ('market', 'park', 'forest', 'water')}
            for name, facts in scenes:
                chosen, _ = mind_policy.possibilities(policy, facts,
                    near_places=rule.place_labels, near_features=features)
                result.append({
                    "probe": name, "rule_being_inspected": rule.id,
                    "counterfactual_facts": facts,
                    "near_registered_place_labels": rule.place_labels,
                    "near_feature_categories": features,
                    "actions_selected_by_executor": [{"rule_id": r.id, "action": r.action,
                        "minutes": r.hold_minutes, "target": r.goal_label} if r else {"action": "population_baseline"}
                        for r in chosen],
                })
            if rule.action == 'avoid':
                chosen, _ = mind_policy.possibilities(policy, active, near_places=[], near_features=features)
                result.append({"probe": "same_category_but_none_of_the_registered_places",
                    "rule_being_inspected": rule.id, "counterfactual_facts": active,
                    "near_registered_place_labels": [], "near_feature_categories": features,
                    "actions_selected_by_executor": [r.action if r else "population_baseline" for r in chosen]})
    return result


def request(personal, model, draft):
    body = compact16.request(personal, model, draft=draft)
    body['messages'][0]['content'] += '''
You are reviewing the EXECUTABLE EFFECT, not whether the draft explanation sounds plausible.
Each supplied counterfactual is hypothetical, not a new observation. A rule with gte=40 causes a walking command AFTER 40 minutes. It does not encode capacity to walk for 40 minutes. A category-only avoidance can apply at a place that the caregiver never observed. Check these consequences against the original scope and temporal meaning. Remove or narrow an unsupported command instead of claiming the counterfactual is an observed habit.
Review every unused note as well. Keep uncertainty rather than inventing priorities between distinct responses. Return only the corrected compact JSON, with the exact same keys and action tokens.'''
    data = json.loads(body['messages'][1]['content'])
    data['hypothetical_executor_probes'] = probes(draft, personal)
    data['probe_limitation'] = 'These cover only predicates already present in the draft. Missing personal reactions must still be checked against all original notes.'
    body['messages'][1]['content'] = json.dumps(data, ensure_ascii=False)
    return body
