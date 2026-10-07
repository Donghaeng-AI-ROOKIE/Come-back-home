import copy
import json

import pytest

from experiments.mind_contract_ab_20261007 import contract_d8 as d8, contract_d8plain, contract_d4, run_repair8
from experiments.mind_contract_ab_20261007 import condition_probe, scoring
from app.llm.mind_policy import Policy
from tests.test_mind_contract_ab import D_CORRECT, to_d3


def test_non_temporal_fixture_compilation_is_unchanged_and_input_not_mutated():
    people, _, _ = scoring.load()
    for key, old in D_CORRECT.items():
        old = to_d3(old)
        if any(n['fact'] == 'clock_hour' for b in old['behaviors']
               for k in ('start_when_any', 'end_when_any') for c in b[k] for n in c['numbers']):
            continue  # Temporal shape deliberately changes; exercised below.
        new = copy.deepcopy(old)
        for b in new['behaviors']:
            b['daily_time_windows'] = []
        before = copy.deepcopy(new)
        assert d8.compile_d8(new, people[key]['personal']) == contract_d4.compile_d4(old, people[key]['personal'])
        assert new == before


def test_midnight_interval_preserves_family_condition_on_both_sides():
    inputs, _, refs, _ = run_repair8.repair_dataset()
    row = next(r for r in inputs if r['id'] == 'DEV_P26_hard')
    value = {'behaviors': [{'sentence_ids':['N1.s1','N2.s1','N3.s1'], 'kind':'observed_response',
        'action':'wait','goal_place':'','applies_only_at':[],
        'start_when_any':[{'true':[],'false':['family_present'],'numbers':[]}], 'end_when_any':[],
        'hold_minutes':0,'daily_time_windows':[{'start_hour':23,'end_hour':1}]}],
        'other_sentences':[{'sentence_ids':['N0.s1','N0.s2','N2.s2'],'subject':'patient','kind':'unobserved'}]}
    out = d8.compile_d8(value,row['personal'])
    assert condition_probe.compare(out,Policy.model_validate(refs[row['id']]))['status'] == 'no_difference_in_probes'
    for h, active in [(0,True),(.5,True),(1,False),(12,False),(22.999,False),(23,True),(23.999,True)]:
        for present in (False,True):
            actions=condition_probe.effects(out,{'clock_hour':h,'family_present':present},[],{})
            assert any(a['action']=='wait' for a in actions) is (active and not present)


@pytest.mark.parametrize('start,end',[(0,0),(24,1),(-1,1),(23,25),(True,1),(23,float('nan'))])
def test_ambiguous_or_invalid_time_is_rejected_not_silently_repaired(start,end):
    with pytest.raises(ValueError):
        d8.clock_branches(start,end)


def test_midnight_endpoint_and_schema_plain_only_difference():
    assert d8.clock_branches(21,0) == [[{'fact':'clock_hour','op':'>=','value':21}]]
    inputs,_,_,_=run_repair8.repair_dataset()
    for r in inputs:
        body=d8.request(r['personal'],'test-model')
        plain=contract_d8plain.request(r['personal'],'test-model')
        body.pop('response_format')
        assert body==plain
        assert len(json.dumps(body,ensure_ascii=False).encode())<40000
        schema=d8.schema(r['personal'])
        for key in ('start_when_any','end_when_any'):
            assert 'clock_hour' not in schema['properties']['behaviors']['items']['properties'][key]['items']['properties']['numbers']['items']['properties']['fact']['enum']
