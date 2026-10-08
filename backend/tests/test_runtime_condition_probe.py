from copy import deepcopy
from experiments.mind_contract_ab_20261007.runtime_condition_probe import execution_effects


def test_wait_duration_difference_is_retained_in_original_but_not_consumed_effect():
    original=[{'action':'wait','goal':None,'feature':None,'hold_minutes':60.}]
    copy=deepcopy(original)
    assert execution_effects(original)==execution_effects([dict(original[0],hold_minutes=None)])
    assert original==copy


def test_rest_duration_is_not_discarded():
    effect={'action':'rest','goal':None,'feature':None,'hold_minutes':10.}
    assert execution_effects([effect])!=execution_effects([dict(effect,hold_minutes=5.)])
    assert execution_effects([dict(effect,hold_minutes=None)])==execution_effects([dict(effect,hold_minutes=5.)])


def test_subminute_wait_can_change_recheck_timing_and_is_not_normalized():
    effect={'action':'wait','goal':None,'feature':None,'hold_minutes':.25}
    assert execution_effects([effect])!=execution_effects([dict(effect,hold_minutes=None)])
