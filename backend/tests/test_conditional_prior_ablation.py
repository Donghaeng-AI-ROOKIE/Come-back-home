from types import SimpleNamespace
from copy import deepcopy
import pytest
from experiments.mind_contract_ab_20261007.conditional_prior import separate_waiting
from app.phase2 import guardrail


class Prior(SimpleNamespace):
    def model_copy(self,update):
        p=deepcopy(self);p.__dict__.update(update);return p


def fixture():
    raw={'route_following':.3,'direction_keeping':.25,'random_walk':.15,'backtracking':.05,'staying_put':.1,'landmark_seeking':.15}
    values=guardrail._boost_strategies(raw,{'staying_put':3.},floor=0)
    values=guardrail._boost_strategies(values,{'landmark_seeking':2.},floor=0)
    p=Prior(strategy_before_behavior=raw,strategy_probs=guardrail.sanitize_strategy_probs(values,raw),
        initial_interpretation={'status':'applied','semantic_contract':{'persistence':{'value':'wait_for_help','note_ids':['N4']}},
        'source_audit':{'evidence_note_ids':['N4']},'projection_trace':[
            {'consumer':'strategy_probs','action':'start_before_legacy_behavior_tilt'},
            {'consumer':'strategy_probs','semantic_evidence':'persistence.wait_for_help','factors':{'staying_put':3.}},
            {'consumer':'strategy_probs','semantic_evidence':'current_destination','factors':{'landmark_seeking':2.}}]})
    rule=SimpleNamespace(id='wait',action='wait',evidence=[SimpleNamespace(note_id='N4')],when=[[SimpleNamespace(fact='lost_awareness')]])
    return p,SimpleNamespace(rules=[rule])


def test_only_duplicate_boost_removed_other_personal_and_population_prior_preserved():
    p,policy=fixture();saved=deepcopy(p.__dict__)
    after,audit=separate_waiting(p,policy)
    assert audit['applied']
    assert after.strategy_probs==guardrail.sanitize_strategy_probs(
        guardrail._boost_strategies(p.strategy_before_behavior,{'landmark_seeking':2.},floor=0),p.strategy_before_behavior)
    assert after.strategy_probs['staying_put']>0
    assert p.__dict__==saved


@pytest.mark.parametrize('defect',['wrong_source','missing_snapshot','changed_trace','wrong_action','missing_original','extra_source'])
def test_unproven_ownership_cannot_change_the_prior(defect):
    p,policy=fixture()
    if defect=='wrong_source':policy.rules[0].evidence[0].note_id='N9'
    if defect=='extra_source':policy.rules[0].evidence.append(SimpleNamespace(note_id='N9'))
    if defect=='missing_snapshot':p.strategy_before_behavior={}
    if defect=='changed_trace':p.strategy_probs['staying_put']+=.01
    if defect=='wrong_action':policy.rules[0].action='walk'
    if defect=='missing_original':p.initial_interpretation['source_audit']['evidence_note_ids']=[]
    after,audit=separate_waiting(p,policy)
    assert after is p and not audit['applied']
