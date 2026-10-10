"""Research executor binding arrival/recognition to a particular place.

Used by the staging persistent executor. Arrival means the current snapped road node, not an
indoor entrance or a clinical observation. Visit history remains independent.
Legacy recognition without a place label cannot establish named recognition.
"""
from datetime import timedelta
from itertools import product
import hashlib
import json
import math
from typing import Literal

from pydantic import ConfigDict, Field
from app.llm import mind_policy as m
from app.phase2.person_walk import Population
from app.schemas.environment import BehaviorObservation

VERSION = 'place-bound-conditions-v1-research'
RELEASE_QUALIFIED = False
PLACE_FACTS = {'physical_arrival', 'target_recognized'}


class PlaceRecognition(BehaviorObservation):
    model_config = ConfigDict(extra='forbid')
    fact: Literal['target_recognized']
    place_label: str = Field(min_length=1)


def bound_possibilities(policy, facts, bindings, *, near_places, near_features):
    """bindings[rule_id][fact] = (shared variable id, bool/None).

    The variable id keeps unknowns correlated across rules for the SAME place,
    while different places have different unknowns. It is not an LLM judgment.
    """
    variables = {}
    def context(rule, assigned):
        local = dict(facts)
        for clause in rule.when:
            for atom in clause:
                name, value = bindings.get(rule.id, {}).get(atom.fact, ('global:'+atom.fact, facts.get(atom.fact)))
                local[atom.fact] = assigned.get(name, value)
        return local
    candidates = []
    for rule in policy.rules:
        key, spatial = m.spatial_scope(rule, near_places, near_features)
        truth = m.truth(rule.when, context(rule, {}))
        if spatial is False or truth is False: continue
        candidates.append((rule, spatial, truth))
    removed = {rid for rule, spatial, truth in candidates if spatial is True and truth is True
               for rid in rule.supersedes}
    possible = [rule for rule, _, _ in candidates if rule.id not in removed]
    for rule in possible:
        key, spatial = m.spatial_scope(rule, near_places, near_features)
        if spatial is None: variables[key] = [False, True]
        for clause in rule.when:
            for atom in clause:
                name, value = bindings.get(rule.id, {}).get(atom.fact, ('global:'+atom.fact, facts.get(atom.fact)))
                if value is not None: continue
                if atom.fact in m.BOOLEAN_FACTS:
                    variables[name] = [False, True]
                else:
                    values = set(variables.get(name, [0.0]))
                    x = float(atom.value); values.update((max(0., x-1e-6), x, x+1e-6))
                    variables[name] = sorted(values)
    if math.prod(len(v) for v in variables.values()) > 256:
        raise ValueError('too many unresolved policy conditions')
    outcomes = {}
    for values in product(*variables.values()):
        assigned = dict(zip(variables, values)); chosen = []
        for rule in possible:
            key, spatial = m.spatial_scope(rule, near_places, near_features)
            if spatial is None: spatial = assigned[key]
            if spatial and m.truth(rule.when, context(rule, assigned)) is True: chosen.append(rule)
        removed = {rid for rule in chosen for rid in rule.supersedes}
        chosen = [rule for rule in chosen if rule.id not in removed]
        for rule in chosen or [None]:
            key = 'baseline' if rule is None else json.dumps(
                [rule.action, rule.goal_label, rule.feature, rule.place_labels, rule.hold_minutes], ensure_ascii=False)
            outcomes.setdefault(key, rule)
    return list(outcomes.values()), sorted(variables)


class PlaceBoundPopulation(Population):
    def __init__(self, *args, place_recognitions=(), **kwargs):
        self.place_recognitions = [PlaceRecognition.model_validate(x) for x in place_recognitions]
        if any(x.fact != 'target_recognized' for x in self.place_recognitions):
            raise ValueError('place recognition accepts only target_recognized')
        signature = json.dumps({'version': VERSION, 'observations':
            [x.model_dump(mode='json') for x in self.place_recognitions]}, sort_keys=True, ensure_ascii=False)
        self.place_binding_digest = hashlib.sha256(signature.encode()).hexdigest()
        checkpoint = kwargs.get('checkpoint')
        if checkpoint and checkpoint.get('place_binding_digest') != self.place_binding_digest:
            raise ValueError('stale place recognition checkpoint')
        super().__init__(*args, **kwargs)
        if any(x.place_label not in self.goals for x in self.place_recognitions):
            raise ValueError('recognition refers to an unregistered place')
        for rule in self.policy.rules:
            if len(rule.place_labels)>1 and any(a.fact in PLACE_FACTS for c in rule.when for a in c):
                raise ValueError('place-bound fact requires one named place per rule')
        # Recognition changes can interrupt a wait at their exact expiry, even
        # between minute boundaries. The observations are not globalized.
        self.observation_boundaries = sorted(set(self.observation_boundaries) | {
            (t-self.started_at).total_seconds()/60 for x in self.place_recognitions
            for t in (x.valid_from, x.valid_until) if t > self.started_at})

    def checkpoint(self):
        return super().checkpoint() | {'place_binding_digest': self.place_binding_digest}

    def place_bindings(self, p):
        now = self.started_at + timedelta(minutes=p.minute)
        known = {}
        for observation in self.place_recognitions:
            if observation.valid_from <= now < observation.valid_until:
                known.setdefault(observation.place_label, set()).add(observation.value)
        result = {}
        for rule in self.policy.rules:
            if not any(a.fact in PLACE_FACTS for c in rule.when for a in c): continue
            label = rule.place_labels[0] if rule.place_labels else rule.goal_label or p.target
            values = known.get(label, set())
            recognized = next(iter(values)) if len(values)==1 else None
            arrived = (p.edge_to is None and p.node == self.goals[label]) if label in self.goals else None
            result[rule.id] = {fact: (json.dumps([fact, label], ensure_ascii=False), value)
                               for fact, value in (('physical_arrival', arrived), ('target_recognized', recognized))}
        return result

    def _policy_options(self, p, facts, labels, features):
        bindings = self.place_bindings(p)
        states = []
        for rule in self.policy.rules:
            local = facts | {fact: value for fact, (_, value) in bindings.get(rule.id, {}).items()}
            states.append([m.atom_value(atom, local) for clause in rule.when for atom in clause])
        key = json.dumps([states, bindings, labels, features], ensure_ascii=False, sort_keys=True)
        if key not in self._policy_cache:
            self._policy_cache[key] = bound_possibilities(self.policy, facts, bindings,
                near_places=labels, near_features=features)
        return self._policy_cache[key]
