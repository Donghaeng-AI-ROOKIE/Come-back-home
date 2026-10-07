"""Diagnose actual condition losses without parsing or rewriting the source."""
from copy import deepcopy
import json

from app.llm.mind_policy import Policy
from experiments.mind_contract_ab_20261007.condition_probe import compare, audit
from experiments.mind_contract_ab_20261007.run_v2 import DEV128
from tests.test_mind_upgrade import geography
from tests.test_person_policy import population, obs, rule, policy

REF = json.loads((DEV128 / 'dev128_reference.NOT_MODEL_INPUT.json').read_text())


def pair(key):
    ref = Policy.model_validate(REF[key])
    return deepcopy(ref), ref


def test_lost_walking_precondition_has_stationary_counterexample():
    # The saved D3 P30 response passed all four authored scenes with precisely
    # this omission; its long walk then accumulated much more personal rest.
    candidate, ref = pair('DEV_P30_original')
    rest = next(r for r in candidate.rules if r.action == 'rest')
    rest.when = [[a for a in clause if a.fact != 'is_walking'] for clause in rest.when]
    r = compare(candidate, ref)
    assert r['status'] == 'difference'
    assert r['counterexample']['facts']['is_walking'] is False
    assert r['counterexample']['facts']['pain_observed'] is True


def test_preserved_or_reordered_rules_do_not_require_literal_equality():
    candidate, ref = pair('DEV_P30_original')
    candidate.rules.reverse()
    for rule in candidate.rules:
        rule.id += '_renamed'
        rule.when = list(reversed([list(reversed(c)) for c in rule.when]))
        rule.when.append(list(rule.when[0]))  # logically redundant OR branch
    assert compare(candidate, ref)['status'] == 'no_difference_in_probes'


def test_arrival_and_recognition_are_separate_conditions():
    candidate, ref = pair('DEV_P16_preserve')
    wait = next(r for r in candidate.rules if r.action == 'wait')
    wait.when = [[a for a in c if a.fact != 'physical_arrival'] for c in wait.when]
    result = compare(candidate, ref)
    assert result['status'] == 'difference'
    assert result['counterexample']['facts']['physical_arrival'] is False


def test_named_scope_cannot_be_widened_to_every_market():
    candidate, ref = pair('DEV_P30_original')
    next(r for r in candidate.rules if r.action == 'avoid').place_labels = []
    assert compare(candidate, ref)['status'] == 'difference'


def test_hold_duration_is_an_effect_even_if_action_name_stays_rest():
    candidate, ref = pair('DEV_P07_original')
    next(r for r in candidate.rules if r.action == 'rest').hold_minutes = 30
    assert compare(candidate, ref)['status'] == 'difference'


def test_probe_exhaustion_is_not_a_pass():
    candidate, ref = pair('DEV_P30_original')
    assert compare(candidate, ref, max_worlds=1)['status'] == 'incomplete'


def test_common_condition_loss_is_found_even_when_family_is_absent():
    candidate, ref = pair('DEV_P31_original')
    for r in candidate.rules:
        r.when = [[a for a in c if a.fact != 'anxiety_high'] for c in r.when]
    result = compare(candidate, ref)
    assert result['status'] == 'difference'
    assert result['counterexample']['facts']['anxiety_high'] is False


def test_missing_start_condition_retriggers_rest_in_real_walker(geography):
    # Mechanism reproduction, not a claim that the reference is clinically
    # correct. Use the existing KINTEX fixture and a synthetic pain observation.
    proper = rule('rest', when=[[dict(fact='is_walking', op='eq', value=True),
                                dict(fact='pain_observed', op='eq', value=True)]])
    omitted = deepcopy(proper)
    omitted['when'][0] = omitted['when'][0][1:]
    populations = [population(geography, policy(r), behavior_observations=[obs('pain_observed', True)])
                   for r in (proper, omitted)]
    for pop in populations:
        for particle in pop.particles:
            particle.mode = 'rest'
            particle.hold_until = 5.0
        pop.advance_to(12)
    assert all(p.walking > 0 for p in populations[0].particles)
    assert all(p.walking == 0 and p.rest == 12 for p in populations[1].particles)


def test_unusable_responses_remain_in_denominator_and_scores_stay_unchanged():
    scored = {'rows': [{'input_id': 'P', 'rep': 1, 'family': 'test', 'policy': None,
                       'scenes': [{'pass': False}]}]}
    frozen = deepcopy(scored)
    result = audit(scored, {})
    assert result['summary']['responses'] == 1
    assert result['summary']['status'] == {'unusable_output': 1}
    assert scored == frozen
