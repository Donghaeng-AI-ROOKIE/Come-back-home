"""Persistent unknown-fact hypotheses; opt-in research executor.

The hypotheses are not observations or calibrated patient probabilities. No
unobserved transition rate or personal waiting duration is invented here.
"""
import hashlib
import json
import math

from app.llm import mind_policy as m
from app.phase2.place_bound_walk import PlaceBoundPopulation

VERSION = 'persistent-context-v6-known-environment-sequence'
# An executor fix must invalidate old checkpoints without changing the paired
# walkers' uncertainty hypotheses or action ties as an unrelated side effect.
HYPOTHESIS_NAMESPACE = 'persistent-context-v2-sourced-followup'
SELF_TRIGGER_FACTS = ('is_walking', 'continuous_walk_minutes', 'distance_since_rest_m')


class PersistentContextPopulation(PlaceBoundPopulation):
    CHECKPOINT_FAMILY = VERSION
    def __init__(self, *args, unknown_true_weights=None, **kwargs):
        self.unknown_true_weights = dict(unknown_true_weights or {})
        for fact, weight in self.unknown_true_weights.items():
            if fact not in m.BOOLEAN_FACTS or type(weight) not in (int, float) or not math.isfinite(weight) or not 0 <= weight <= 1:
                raise ValueError('invalid explicit uncertainty assumption')
        context = {'version': VERSION, 'weights': self.unknown_true_weights}
        self.context_digest = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
        checkpoint = kwargs.get('checkpoint')
        if checkpoint and checkpoint.get('context_digest') != self.context_digest:
            raise ValueError('persistent context assumptions changed')
        super().__init__(*args, **kwargs)

    def checkpoint(self):
        return super().checkpoint() | {'context_digest': self.context_digest}

    def _uniform(self, p, key):
        raw = json.dumps([HYPOTHESIS_NAMESPACE, p.seed, key], ensure_ascii=False, sort_keys=True)
        return int.from_bytes(hashlib.sha256(raw.encode()).digest()[:8], 'big') / 2**64

    def _value(self, p, key, fact, actual):
        previous = p.context_assumptions.get(key)
        if actual is not None:
            # Keep the source fact separate. Known -> unknown opens a new
            # uncertainty episode, never silently extends an expired observation.
            if previous is not None:
                previous['state'] = 'known'
                previous['last_known'] = actual
            return actual
        if fact not in m.BOOLEAN_FACTS and not fact.startswith('spatial_scope:'):
            raise ValueError('unknown numeric duration/state needs an explicit model')
        if previous is None or previous['state'] == 'known':
            generation = 0 if previous is None else previous['generation'] + 1
            value = self._uniform(p, [key, generation]) < self.unknown_true_weights.get(fact, .5)
            previous = {'value': value, 'generation': generation, 'state': 'unknown',
                        'source': 'unvalidated_scenario_hypothesis'}
            p.context_assumptions[key] = previous
            self._event(p, 'context_assumption', fact_key=key, value=value,
                        generation=generation, source=previous['source'])
        return previous['value']

    def _fact_key(self, p, rule, fact, bindings, labels):
        if fact in bindings.get(rule.id, {}):
            return bindings[rule.id][fact][0]
        if '.' in fact:
            # A place-type signal ("market.noisy") is observed near a place of
            # that type. A named site's unknown signal is not shared with other
            # sites. Without any known site nearby (registered place, bounded
            # report, or map layer) there is nothing to perceive: the
            # environment information is insufficient, so no hypothesis is drawn.
            named = sorted(set(rule.place_labels) & set(labels))
            if named:
                return json.dumps(['environment', fact, ['places', named]], ensure_ascii=False)
            sites = self.known_sites(p, fact.split('.', 1)[0])
            if not sites:
                return None
            return json.dumps(['environment', fact, ['sites', sites]], ensure_ascii=False)
        if fact == 'target_recognized':
            return json.dumps([fact, p.target], ensure_ascii=False)
        return 'global:' + fact

    def _select_rule(self, p, rng, facts, labels, features):
        possible, unknown = self._policy_options(p, facts, labels, features)
        finite_waits = any(r.action == 'wait' and r.hold_minutes is not None for r in self.policy.rules)
        bindings = self.place_bindings(p)
        active = []
        for rule in self.policy.rules:
            key, spatial = m.spatial_scope(rule, labels, features)
            if spatial is False:
                if rule.id in p.completed_waits:
                    p.completed_waits.remove(rule.id)
                continue
            insufficient = spatial is None
            local = dict(facts)
            for clause in rule.when:
                for atom in clause:
                    actual = bindings.get(rule.id, {}).get(atom.fact, (None, facts.get(atom.fact)))[1]
                    variable = self._fact_key(p, rule, atom.fact, bindings, labels)
                    if variable is None and actual is None:
                        local[atom.fact] = None; insufficient = True
                        continue
                    local[atom.fact] = self._value(p, variable, atom.fact, actual)
            if insufficient:
                # Category scope or signal without any known location: not a
                # fact, not absence. Keep the rule, do not execute it here, and
                # disclose the time it could not be checked.
                if m.truth([[a for a in clause if '.' not in a.fact] for clause in rule.when], local) is not False:
                    if rule.id not in p.env_insufficient_rules:
                        p.env_insufficient_rules.append(rule.id)
                if rule.id in p.completed_waits and spatial is None:
                    p.completed_waits.remove(rule.id)
                continue
            continuing = p.mode == 'wait' and p.hold_rule_id == rule.id and rule.hold_minutes is not None
            if continuing:
                # Waiting itself stops walking and resets its counters. Those
                # consequences are not evidence that the initiating episode
                # ended, including at the exact duration boundary. External
                # facts and spatial scope still use their current values.
                local.update(p.wait_start_facts)
            if (continuing and p.minute >= p.hold_until - 1e-8
                    and spatial and m.truth(rule.when, local) is True):
                if rule.id not in p.completed_waits:
                    p.completed_waits.append(rule.id)
                    self._event(p, 'sourced_wait_complete', rule_id=rule.id,
                                duration_minutes=rule.hold_minutes)
                    if rule.after_wait is not None:
                        eligible, follow_unknown = self._followup_at_completion(p, rule, facts, labels)
                        p.followup_rule_id = rule.id if eligible else None
                        self._event(p, 'sourced_wait_followup' if eligible else 'sourced_wait_followup_withheld',
                                    rule_id=rule.id, action=rule.after_wait.action,
                                    goal=rule.after_wait.goal_label, unknown_facts=follow_unknown,
                                    condition_time='wait_completion')
            if rule.id in p.completed_waits:
                # A walking guard qualifies entry; an intervening wait/rest
                # must not invent a new lost/noisy/etc. episode. Numeric walking
                # thresholds remain live so a newly accumulated bout can rearm.
                rearm_when = [[a for a in clause if a.fact != 'is_walking']
                              for clause in rule.when]
                if m.truth(rearm_when, local) is False:
                    p.completed_waits.remove(rule.id)
                # Completing an episode cannot immediately restart the same wait.
                continue
            if spatial and m.truth(rule.when, local) is True:
                active.append(rule)
        removed = {rid for r in active for rid in r.supersedes}
        active = [r for r in active if r.id not in removed
                  and not (r.action == 'seek' and r.goal_label in p.completed_goals)]
        if not unknown and not finite_waits:
            # Update known/expired evidence state above before preserving the
            # fully known component checks and their original walk RNG.
            return super()._select_rule(p, rng, facts, labels, features)

        def action_key(rule):
            return json.dumps([rule.action, rule.goal_label, rule.feature,
                               sorted(rule.place_labels), rule.hold_minutes], ensure_ascii=False)
        # Conflicting supported actions have no clinical priority unless supplied
        # by supersedes. Stable keyed ranks expose a tie assumption without
        # allowing unrelated action changes to redraw every unresolved fact.
        rule = min(active, key=lambda r: (self._uniform(p, ['action_tie', action_key(r)]), action_key(r))) if active else None
        if rule is not None and rule.action != 'rest':
            # A later explicit intention replaces the previous continuation.
            # A temporary physical rest pauses it instead.
            p.followup_rule_id = None
        if rule is None and p.followup_rule_id is not None:
            parent = next(r for r in self.policy.rules if r.id == p.followup_rule_id)
            follow = parent.after_wait
            if follow.action == 'seek' and follow.goal_label in p.completed_goals:
                p.followup_rule_id = None
            else:
                # The guard qualified departure at the completion boundary.
                # A later rest pauses that intention; a new explicit response
                # replaces it. Do not invent a delayed departure if it failed.
                rule = m.Rule(id=parent.id + '::after_wait', when=follow.when,
                    action=follow.action, goal_label=follow.goal_label, feature=None,
                    place_labels=[], hold_minutes=None, supersedes=[], evidence=follow.evidence)
        if rule is not None and rule.action == 'wait' and rule.hold_minutes is not None:
            if p.mode != 'wait' or p.hold_rule_id != rule.id:
                p.wait_start_facts = {k: facts[k] for k in SELF_TRIGGER_FACTS if k in facts}
        return rule, len(possible) > 1 or len(active) > 1, unknown

    def _followup_at_completion(self, p, parent, facts, labels):
        follow = parent.after_wait
        candidate = m.Rule(id=parent.id + '::after_wait', when=follow.when,
            action=follow.action, goal_label=follow.goal_label, feature=None,
            place_labels=[], hold_minutes=None, supersedes=[], evidence=follow.evidence)
        bindings = self.place_bindings(p, rules=[candidate])
        local = dict(facts); unknown = []
        for clause in follow.when:
            for atom in clause:
                actual = bindings.get(candidate.id, {}).get(atom.fact, (None, facts.get(atom.fact)))[1]
                variable = self._fact_key(p, candidate, atom.fact, bindings, labels)
                if variable is None and actual is None:
                    local[atom.fact] = None; continue
                if actual is None: unknown.append(variable)
                local[atom.fact] = self._value(p, variable, atom.fact, actual)
        return m.truth(follow.when, local) is True, sorted(set(unknown))

    def _hold_deadline(self, p, rule, mode, hold, old_mode):
        if rule is not None and mode == 'wait' and rule.hold_minutes is not None:
            if old_mode == 'wait' and p.hold_rule_id == rule.id:
                return p.hold_until
        return super()._hold_deadline(p, rule, mode, hold, old_mode)

    def distribution(self, minute):
        out = super().distribution(minute)
        out['quality'].update(
            context_executor=VERSION,
            unknown_branch_weighting='persistent_boolean_hypotheses_not_calibrated',
            unknown_true_weights={'default': .5, **self.unknown_true_weights},
            unknown_transition='stable_while_unobserved; new_episode_after_observation_expiry',
            conflicting_action_tie='legacy_when_known; stable_hash_when_unknown; not_clinical_priority',
            explicit_wait_duration='episode_from_entry; no_refresh; rearm_after_non_walking_guard_false',
            unreported_wait_duration='not_inferred; conditional_wait_may_persist',
            after_wait_action='only_explicit_source; guard_at_timed_completion_only; no_deferred_departure; unknowns_are_hypotheses',
            environment_signal_scope='known_sites_only; no_hypothesis_without_registered_place_report_or_layer',
            context_assumption_count=sum(len(p.context_assumptions) for p in self.particles),
            sourced_wait_completions=sum(e['kind'] == 'sourced_wait_complete' for p in self.particles for e in p.events))
        return out
