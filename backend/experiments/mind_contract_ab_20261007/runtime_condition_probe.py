"""Supplemental execution-effect comparison; never replaces original scores.

The continuous walker reevaluates wait every step, so wait.hold_minutes is not
a committed waiting duration. Rest without a stated duration executes for 5
minutes. Report these engine semantics separately from source-contract
fidelity; ignoring an unsupported wait duration here is NOT successful
representation of a guardian's stated duration.
"""
from copy import deepcopy
from experiments.mind_contract_ab_20261007 import condition_probe as probe


def execution_effects(effects):
    result=[]
    for item in effects:
        value=deepcopy(item)
        if value['action']!='baseline':
            if value['action']=='rest':
                value['hold_minutes']=value.get('hold_minutes') or 5.
            elif value['action']=='wait':
                # The maximum clock step is one minute. Sub-minute holds can
                # alter when a condition is reevaluated and are not equivalent.
                if value.get('hold_minutes') is None or value['hold_minutes'] >= 1.:
                    value['hold_minutes']=None
            else:
                value['hold_minutes']=None
        if value not in result:result.append(value)
    return result


def audit(scored,references):
    original=probe.effects
    try:
        probe.effects=lambda *args:execution_effects(original(*args))
        result=probe.audit(scored,references)
    finally:
        probe.effects=original
    result['version']='supplemental-continuous-execution-effects-20261008'
    result['source_fidelity_measured']=False
    result['original_scores_unchanged']=True
    result['release_gate_replaced']=False
    result['engine_limits']=[
        'wait duration >=1 minute is reevaluated each <=1-minute clock step, not implemented as a committed hold; sub-minute values retained',
        'rest duration defaults to 5 minutes when unspecified; provisional engine assumption',
        'current-state effects only; not a complete trajectory-equivalence proof']
    return result
