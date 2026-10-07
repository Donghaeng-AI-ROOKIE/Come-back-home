"""Scoring v2 for contract candidates; synthetic behavior agreement only.

Same as scoring.py (left unchanged: running stages are frozen to it) except
for one confirmed defect (code_review_d3.json, runner lens):

goal_scope_swap counted a rule limited to the goal place as a swap even when
the authored reference policy itself has that rule (DEV_P16_hard: wait only
after arriving at 솔빛쉼터; eval64 R_lost_reaction_03: wait at 가람역). Such a
place-limited reaction is faithful to the source, so v2 flags an own rule
whose scope contains a reference seek goal only when the reference has no rule
with the same (action, target, place scope). The walk scoped to the goal
(P14, 2026-10-06) is still flagged. Scene outcomes, the other three critical
checks and the scene criterion are imported unchanged from scoring.py.

Coverage (review of run_v2, 2026-10-07): two of the four critical types can be
revealed only on some data. withheld_action_injected needs a typed WITHHELD
list for the person (only P04/P21/P22/P24 exist; no eval64 id, no dev128
variant id), and action_without_reference fires only when the reference has no
own rule (no eval64 reference qualifies). measurable() reports, per response,
which types the data can reveal at all, so a gate never reads "no critical"
for a type it could not see. commands_not_in_reference() lists, for a human
reviewer only, own commands no reference rule has; it is not a critical check
and builds no list from guardian sentences.
"""
from __future__ import annotations

from experiments.mind_contract_ab_20261007.scoring import (  # noqa: F401 - unchanged v1 parts re-exported
    CRITICAL,
    ROOT,
    WITHHELD,
    command,
    load,
    scene_pass,
)
from experiments.mind_policy_candidates.condition_program import fixed

VERSION = 'scoring-v2-goal-scope-reference-aware-coverage-20261007'
PHYSICAL = ('continuous_walk_minutes', 'distance_since_rest_m')


def signature(rule):
    """(action, target, place scope); target is the seek goal or the avoided feature."""
    return (rule['action'], rule.get('goal_label'), rule.get('feature'),
            tuple(sorted(rule.get('place_labels') or ())))


def _physical(rule):
    return any(a['fact'] in PHYSICAL for row in rule['when'] for a in row)


def _own_reference(reference):
    return [r for r in reference['rules'] if not r['id'].startswith('initial_env_')]


def critical(policy, personal, reference, person_id):
    """Typed comparison with the reference; None policy is an output failure."""
    if policy is None:
        return []
    ready = fixed(personal)
    fixed_ids = {r.id for r in ready}
    fixed_commands = {command(r.model_dump()) for r in ready}
    own = [r.model_dump() for r in policy.rules if r.id not in fixed_ids]
    ref = _own_reference(reference)
    # Every combination the authored reference itself uses is legitimate.
    authored = {signature(r) for r in reference['rules']}
    found = []
    for r in ref:
        # A goal turned into a scope (walk near the park) or a goal also used
        # as the scope, unless the reference limits that very rule to the place.
        if r['action'] == 'seek' and any(r['goal_label'] in o['place_labels'] and signature(o) not in authored
                                         for o in own):
            found.append('goal_scope_swap')
        if r['action'] == 'rest' and _physical(r) and not any(o['action'] == 'rest' and _physical(o) for o in own):
            found.append('explicit_rest_deleted')
    # Restating an already compiled fixed rule adds no new behavior.
    if not ref and any(command(o) not in fixed_commands for o in own):
        found.append('action_without_reference')
    if any(command(o) in WITHHELD.get(person_id, []) for o in own):
        found.append('withheld_action_injected')
    return sorted(set(found))


def measurable(reference, person_id):
    """Critical types critical() can reveal for this reference at all, whatever the output."""
    ref = _own_reference(reference)
    found = []
    if any(r['action'] == 'seek' for r in ref):
        found.append('goal_scope_swap')
    if any(r['action'] == 'rest' and _physical(r) for r in ref):
        found.append('explicit_rest_deleted')
    if not ref:
        found.append('action_without_reference')
    if WITHHELD.get(person_id):
        found.append('withheld_action_injected')
    return found


def commands_not_in_reference(policy, personal, reference):
    """Own commands that neither a reference rule nor a fixed rule has; for human review, not critical."""
    if policy is None:
        return []
    ready = fixed(personal)
    fixed_ids = {r.id for r in ready}
    known = {command(r) for r in reference['rules']} | {command(r.model_dump()) for r in ready}
    return sorted({command(r.model_dump()) for r in policy.rules if r.id not in fixed_ids} - known)
