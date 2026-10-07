"""Offline counterexamples beyond the four authored scenes.

Compare *executable effects*, not rule text/order, on combinations of typed
conditions used by either policy. The original score and gold files stay frozen.
This is a development diagnostic against an authored reference, not a clinical
ground truth, a deployment gate, or proof over every reachable walking state.
No guardian keyword matching, model calls, or automatic policy repair.
"""
from __future__ import annotations

import argparse
from collections import Counter
from itertools import product
import json
import math
from pathlib import Path

from app.llm import mind_policy as m

VERSION = 'condition-counterexamples-v1-20261007'
ENGINE_KNOWN = {'is_walking', 'physical_arrival', 'fatigue_high'}


def _numbers(name, atoms):
    # Probe equality and both sides of each supplied threshold. These probes
    # are deliberately not presented as a floating-point equivalence proof.
    cut = sorted({float(a.value) for a in atoms})
    values = {0.0}
    for x in cut:
        values.update((x, x - 1e-6, x + 1e-6))
    values.update((a + b) / 2 for a, b in zip(cut, cut[1:]))
    return sorted(x for x in values if x >= 0 and (name != 'clock_hour' or x < 24))


def worlds(left, right):
    rules = [*left.rules, *right.rules]
    atoms = [a for r in rules for c in r.when for a in c]
    names = sorted({a.fact for a in atoms})
    domains = [([False, True] if n in ENGINE_KNOWN else [False, True, None])
               if n in m.BOOLEAN_FACTS else _numbers(n, [a for a in atoms if a.fact == n])
               for n in names]
    places = sorted({x for r in rules for x in r.place_labels})
    # Check each named scope, outside all named scopes, and unknown location.
    # Multiple simultaneous named scopes are not assumed spatially reachable.
    locations = [[], *[[x] for x in places], *([None] if places else [])]
    features = sorted({r.feature for r in rules if r.feature and not r.place_labels})
    potential = math.prod(map(len, domains)) * len(locations) * 3 ** len(features)

    def generate():
        for values in product(*domains):
            facts = dict(zip(names, values))
            # The walker resets these gauges when it stops. Do not diagnose
            # outputs by inventing impossible stationary movement counters.
            if facts.get('is_walking') is False and any(
                    facts.get(n, 0) > 0 for n in ('continuous_walk_minutes', 'distance_since_rest_m')):
                continue
            for near in locations:
                for feature_values in product((False, True, None), repeat=len(features)):
                    yield facts, near, dict(zip(features, feature_values))
    return potential, generate()


def effects(policy, facts, places, features):
    options, _ = m.possibilities(policy, facts, near_places=places, near_features=features)
    # IDs/evidence/order are irrelevant here. Scope was already evaluated;
    # goal, avoided feature and sourced holding duration do affect execution.
    values = {json.dumps({'action': r.action, 'goal': r.goal_label,
                          'feature': r.feature, 'hold_minutes': r.hold_minutes}, sort_keys=True)
              if r else json.dumps({'action': 'baseline'}, sort_keys=True) for r in options}
    return [json.loads(x) for x in sorted(values)]


def compare(candidate, reference, *, max_worlds=20000):
    if max_worlds < 1:
        raise ValueError('max_worlds must be positive')
    potential, cases = worlds(candidate, reference)
    checked = 0
    for facts, places, features in cases:
        if checked >= max_worlds:
            return {'status': 'incomplete', 'checked': checked, 'potential': potential,
                    'reason': 'probe_limit', 'counterexample': None}
        checked += 1
        try:
            expected = effects(reference, facts, places, features)
            actual = effects(candidate, facts, places, features)
        except ValueError as error:
            return {'status': 'incomplete', 'checked': checked, 'potential': potential,
                    'reason': str(error), 'counterexample': None}
        if actual != expected:
            return {'status': 'difference', 'checked': checked, 'potential': potential,
                    'counterexample': {'facts': facts, 'near_places': places,
                                       'near_features': features, 'reference': expected, 'candidate': actual}}
    return {'status': 'no_difference_in_probes', 'checked': checked,
            'potential': potential, 'counterexample': None}


def audit(scored, references, *, max_worlds=20000):
    rows = []
    cache = {}
    for row in scored['rows']:
        key = row['input_id']
        base = {'input_id': key, 'rep': row['rep'], 'family': row['family'],
                'original_scenes_all_pass': bool(row['scenes']) and all(s['pass'] for s in row['scenes'])}
        if row['policy'] is None:
            result = {'status': 'unusable_output', 'checked': 0, 'counterexample': None}
        else:
            ref = references[key]
            identity = json.dumps([row['policy'], ref], ensure_ascii=False, sort_keys=True)
            if identity not in cache:
                cache[identity] = compare(m.Policy.model_validate(row['policy']), m.Policy.model_validate(ref),
                                          max_worlds=max_worlds)
            result = cache[identity]
        rows.append(base | result)
    return {'version': VERSION, 'scope': 'development diagnostic, authored references; no clinical or path accuracy',
            'limits': 'numeric threshold probes; individual named scopes; current-state effects only, not action lifecycle',
            'original_scores_unchanged': True,
            'summary': {'responses': len(rows), 'status': dict(Counter(r['status'] for r in rows)),
                        'original_all_scenes_pass': sum(r['original_scenes_all_pass'] for r in rows),
                        'extra_differences_after_all_scenes_pass': sum(r['original_scenes_all_pass'] and
                            r['status'] == 'difference' for r in rows)}, 'rows': rows}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scored', type=Path, required=True)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.resolve() in (args.scored.resolve(), args.reference.resolve()):
        p.error('diagnostics must not overwrite frozen scores/references')
    result = audit(json.loads(args.scored.read_text()), json.loads(args.reference.read_text()))
    import hashlib
    result['inputs'] = {str(x): hashlib.sha256(x.read_bytes()).hexdigest()
                        for x in (args.scored, args.reference)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
