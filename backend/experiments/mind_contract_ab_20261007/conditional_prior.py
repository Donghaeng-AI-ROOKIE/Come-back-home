"""Research-only ablation of a duplicated personal waiting contribution.

Preserve the population prior and all other documented boosts. Remove only
the recorded persistence.wait_for_help boost when the SAME original note set
is represented by an executable conditional waiting rule. No source parsing,
no inferred duration/probability, no changes to the original saved prior.
This is not wired into the production engine.
"""
from copy import deepcopy
import math

from app.phase2 import guardrail


def separate_waiting(prior, policy):
    info = prior.initial_interpretation or {}
    audit = {'applied':False, 'reason':'no_matching_sourced_conditional_wait',
             'before':dict(prior.strategy_probs), 'new_model_calls':0}
    semantic = info.get('semantic_contract', {}).get('persistence', {})
    notes = set(semantic.get('note_ids', []))
    original = set(info.get('source_audit', {}).get('evidence_note_ids', []))
    if (info.get('status') != 'applied' or semantic.get('value') != 'wait_for_help'
            or not notes or not notes <= original):
        return prior, audit
    matches = [r for r in policy.rules if r.action == 'wait'
        and {e.note_id for e in r.evidence} == notes and r.when and all(r.when)
        and any(a.fact != 'is_walking' for clause in r.when for a in clause)]
    if not matches:
        return prior, audit
    trace = [x for x in info.get('projection_trace', []) if x.get('consumer') == 'strategy_probs']
    if (not prior.strategy_before_behavior or not trace
            or trace[0].get('action') != 'start_before_legacy_behavior_tilt'):
        return prior, audit | {'reason':'missing_exact_pre_projection_snapshot'}
    events = trace[1:]
    if any(not isinstance(x.get('factors'),dict) or not x.get('semantic_evidence') for x in events):
        return prior, audit | {'reason':'unreplayable_strategy_trace'}
    matched = [x for x in events if x['semantic_evidence'] == 'persistence.wait_for_help']
    if len(matched) != 1:
        return prior, audit | {'reason':'no_unique_recorded_wait_boost'}

    def replay(remove):
        value = dict(prior.strategy_before_behavior)
        for x in events:
            if remove and x['semantic_evidence'] == 'persistence.wait_for_help':
                continue
            if not all(isinstance(v,(int,float)) and math.isfinite(v) and v > 0 for v in x['factors'].values()):
                raise ValueError('invalid recorded factor')
            value = guardrail._boost_strategies(value,x['factors'],floor=0)
        return guardrail.sanitize_strategy_probs(value,prior.strategy_before_behavior)

    try:
        existing, adjusted = replay(False), replay(True)
    except (ValueError,TypeError):
        return prior, audit | {'reason':'invalid_recorded_strategy_trace'}
    if set(existing) != set(prior.strategy_probs) or any(
            abs(existing[k]-prior.strategy_probs[k]) > 1e-10 for k in existing):
        return prior, audit | {'reason':'recorded_trace_does_not_reproduce_current_prior'}
    audit.update(applied=True,reason='same_source_wait_delegated_to_conditional_policy',after=adjusted,
        source_note_ids=sorted(notes),rule_ids=[r.id for r in matches],removed_boost=deepcopy(matched[0]),
        remaining_boosts=deepcopy([x for x in events if x not in matched]),
        limitations='note-level match is not sentence-level proof; ablation only, not a clinical calibration')
    copy = deepcopy(info)
    copy['conditional_wait_ablation'] = audit
    return prior.model_copy(update={'strategy_probs':adjusted,'initial_interpretation':copy}),audit
