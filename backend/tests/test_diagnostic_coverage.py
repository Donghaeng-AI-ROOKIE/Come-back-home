from copy import deepcopy
import pytest
from experiments.mind_contract_ab_20261007.diagnostic_coverage import compile_for_diagnosis


def sample():
    personal={'notes':[{'id':'N0','text':'길을 잃으면 기다렸어요.','provenance':'guardian_original'},
        {'id':'N1','text':'함께 있는 동안에는 기다리지 않았어요.','provenance':'guardian_original'}],
        'places':[],'prepared_initial':{}}
    raw={'source_assessment':'관찰된 기다림','rules':[{'action':'wait','goal_place':'','applies_only_at':[],
        'condition':'lost_awareness and not family_present','hold_minutes':0,'note_ids':['N0']}],
        'non_action_note_ids':[]}
    return raw,personal


def test_missing_source_is_flagged_not_silently_called_irrelevant():
    raw,personal=sample();before=deepcopy(raw)
    policy,audit=compile_for_diagnosis(raw,personal)
    assert raw==before
    assert audit['unclassified_note_ids']==['N1']
    assert audit['source_accounting_complete'] is False
    assert audit['eligible_for_release'] is False
    assert policy.rules[0].action=='wait'
    assert policy.unrepresented[0].note_id=='N1'
    assert '비행동 정보라는 판정이 아님' in policy.unrepresented[0].reason


def test_other_invalid_conditions_still_rejected():
    raw,personal=sample();raw['rules'][0]['condition']='made_up_fact'
    with pytest.raises(ValueError):compile_for_diagnosis(raw,personal)
