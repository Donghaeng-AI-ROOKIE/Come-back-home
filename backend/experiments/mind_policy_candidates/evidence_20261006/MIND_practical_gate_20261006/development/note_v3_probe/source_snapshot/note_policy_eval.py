"""Offline scoring for the note interpreter; not patient-location accuracy.

The outcome uses the same typed evaluator as Population. It does not parse a
guardian sentence, alter a rule, or call a model to grade another model.
"""
from collections import Counter
from math import ceil
from app.llm import mind_policy as m


def scene_input(scene):
    facts = {name: scene.get(name) for name in m.FACTS}
    action = scene.get('current_action')
    facts['is_walking'] = None if action is None else action in ('walk', 'avoid', 'seek')
    nearby = {}
    for feature, limit in (('market', 60), ('park', 60), ('forest', 60), ('water', 100)):
        distance = scene.get('map_distance_m', {}).get(feature)
        nearby[feature] = None if distance is None else distance <= limit
        for signal in ('noisy', 'crowded'):
            # These inputs explicitly describe a synthetic local scene. They
            # are not inferred from a road/OSM category or real observations.
            facts[feature+'.'+signal] = scene.get(signal) if nearby[feature] else None
    place = scene.get('current_place_label')
    return facts, None if place is None else [place], nearby


def decide(policy, personal, scene):
    facts, places, features = scene_input(scene)
    outcomes, unknown = m.possibilities(policy, facts, near_places=places, near_features=features)
    labels = [p['label'] for p in personal['places']]
    commands = set()
    for rule in outcomes:
        if rule is None:
            commands.add('baseline')
        elif rule.action == 'avoid':
            commands.add('avoid_'+rule.feature)
        elif rule.action == 'seek':
            commands.add('seek_'+str(labels.index(rule.goal_label)))
        else:
            commands.add(rule.action)
    # Conflicting/unknown alternatives remain alternatives. Choosing the answer
    # that happens to match the expected label would be leakage.
    if len(commands) != 1:
        status, chosen = 'unknown', []
    elif commands == {'baseline'}:
        status, chosen = 'no_personal_reaction', ['baseline']
    else:
        status, chosen = 'supported', sorted(commands)
    return {'status': status, 'commands': chosen, 'possible_commands': sorted(commands),
            'unknown_facts': unknown}


def score(decision, expected_commands):
    # Both authored "unknown" and "baseline" labels disallow asserting a
    # personal action. This is a behavioral criterion, not status-word matching.
    if not expected_commands or expected_commands == ['baseline']:
        return decision['status'] in ('unknown', 'no_personal_reaction')
    return (decision['status'] == 'supported'
            and set(decision['commands']) == set(expected_commands))


def gate(results, expected_ids, repetitions):
    expected = {(item, rep) for item in expected_ids for rep in repetitions}
    actual = [(r['id'], r['rep']) for r in results]
    if len(set(actual)) != len(actual) or set(actual) != expected:
        raise ValueError('incomplete or duplicate denominator')
    total = len(expected)
    passed = sum(r.get('pass') is True for r in results)
    required = ceil(total * .9)
    return {'total': total, 'passed': passed, 'required': required,
            'success_rate': passed / total if total else 0,
            'advance_to_integration': bool(total and passed >= required),
            'interpretation': 'synthetic_behavior_action_agreement_not_location_accuracy',
            'by_action': {action: {'total': sum(r['label'] == action for r in results),
                                  'passed': sum(r.get('pass') is True and r['label'] == action for r in results)}
                          for action in sorted({r['label'] for r in results})},
            'by_repetition': {str(rep): {'total': sum(r['rep'] == rep for r in results),
                                        'passed': sum(r.get('pass') is True and r['rep'] == rep for r in results)}
                              for rep in repetitions},
            'by_person': {pid: {'total': sum(r.get('person_id') == pid for r in results),
                                'passed': sum(r.get('pass') is True and r.get('person_id') == pid for r in results)}
                          for pid in sorted({r['person_id'] for r in results if r.get('person_id')})},
            'errors': dict(Counter(r.get('error_type') for r in results if r.get('error_type')))}
