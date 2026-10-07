"""Fixed scoring for contract candidates; synthetic behavior agreement only.

Scene outcomes reuse note_policy_eval (the typed evaluator Population uses).
Critical checks compare the compiled policy with the authored reference policy
by typed fields only. An output failure fails every scene of that response.
"""
from __future__ import annotations

import json
from pathlib import Path

from experiments.mind_contract_ab_20261007 import completion
from experiments.mind_contract_ab_20261007.contracts import CANDIDATES
from experiments.mind_policy_candidates import note_policy_eval as ev
from experiments.mind_policy_candidates.condition_program import fixed

ROOT = Path(__file__).resolve().parents[1] / 'mind_policy_candidates' / 'evidence_diverse_20261006'
# Behaviors the corrected/other-person source explicitly withholds from this
# person. Authored with the 2026-10-06 profiles; not derived from model output.
WITHHELD = {'P04': ['avoid_water'], 'P21': ['wait'], 'P22': ['avoid_park'], 'P24': ['wait']}
CRITICAL = ('goal_scope_swap', 'explicit_rest_deleted', 'action_without_reference', 'withheld_action_injected')


def load(root=ROOT):
    people = {p['person_id']: p for p in json.loads((root / 'profiles.json').read_text())}
    scenes = json.loads((root / 'scenes.json').read_text())
    reference = json.loads((root / 'reference_policies.NOT_MODEL_INPUT.json').read_text())
    return people, scenes, reference


def scene_pass(decision, scene):
    """The frozen 2026-10-06 criterion: status, commands and possible commands."""
    return bool(decision and decision['status'] == scene['expected_status']
                and set(decision['commands']) == set(scene['expected_commands'])
                and (scene['expected_possible_commands'] is None
                     or set(decision['possible_commands']) == set(scene['expected_possible_commands'])))


def command(rule):
    if rule['action'] == 'avoid':
        return 'avoid_' + rule['feature']
    return rule['action']


def critical(policy, personal, reference, person_id):
    """Typed comparison with the reference; None policy is an output failure."""
    if policy is None:
        return []
    ready = fixed(personal)
    fixed_ids = {r.id for r in ready}
    fixed_commands = {command(r.model_dump()) for r in ready}
    own = [r.model_dump() for r in policy.rules if r.id not in fixed_ids]
    ref = [r for r in reference['rules'] if not r['id'].startswith('initial_env_')]
    found = []
    for r in ref:
        # Either a goal turned into a scope (walk near the park) or a goal also
        # used as the scope (start toward it only while already there).
        if r['action'] == 'seek' and any(r['goal_label'] in o['place_labels'] for o in own):
            found.append('goal_scope_swap')
        physical = any(a['fact'] in ('continuous_walk_minutes', 'distance_since_rest_m')
                       for row in r['when'] for a in row)
        if r['action'] == 'rest' and physical and not any(
                o['action'] == 'rest' and any(a['fact'] in ('continuous_walk_minutes', 'distance_since_rest_m')
                                              for row in o['when'] for a in row) for o in own):
            found.append('explicit_rest_deleted')
    # Restating an already compiled fixed rule adds no new behavior.
    if not ref and any(command(o) not in fixed_commands for o in own):
        found.append('action_without_reference')
    if any(command(o) in WITHHELD.get(person_id, []) for o in own):
        found.append('withheld_action_injected')
    return sorted(set(found))


def evaluate(candidate, public, personal, person_scenes, reference, person_id):
    status, value = completion.classify(public)
    row = {'completion': status, 'compile_error': None, 'valid': False}
    policy = None
    if status == 'complete_json':
        try:
            policy = CANDIDATES[candidate][2](value, personal)
        except Exception as error:  # noqa: BLE001 - every rejection is recorded, none repaired
            row['compile_error'] = str(error).splitlines()[0][:200]
        else:
            row['valid'] = True
    row['scenes'] = []
    for s in person_scenes:
        decision = ev.decide(policy, personal, s['scene']) if policy else None
        row['scenes'].append({'id': s['id'], 'expected': s['expected_commands'],
                              'decision': decision, 'pass': scene_pass(decision, s)})
    row['critical'] = critical(policy, personal, reference, person_id)
    row['policy'] = policy.model_dump() if policy else None
    return row


def summarize(rows):
    total = sum(len(r['scenes']) for r in rows)
    out = {'responses': len(rows), 'valid_responses': sum(r['valid'] for r in rows),
           'decisions': total, 'passed': sum(s['pass'] for r in rows for s in r['scenes']),
           'completion': {}, 'compile_errors': {}, 'critical': {k: 0 for k in CRITICAL}}
    for r in rows:
        out['completion'][r['completion']] = out['completion'].get(r['completion'], 0) + 1
        if r['compile_error']:
            out['compile_errors'][r['compile_error']] = out['compile_errors'].get(r['compile_error'], 0) + 1
        for c in r['critical']:
            out['critical'][c] += 1
    return out
