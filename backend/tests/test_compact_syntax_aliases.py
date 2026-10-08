import pytest
from experiments.mind_contract_ab_20261007 import compact_syntax as c
from experiments.mind_policy_candidates.condition_program import expression


@pytest.mark.parametrize('upper,lower',[
 ('is_walking AND (continuous_walk_minutes >= 8 OR distance_since_rest_m >= 450)',
  'is_walking and (continuous_walk_minutes >= 8 or distance_since_rest_m >= 450)'),
 ('NOT family_present AND lost_awareness','not family_present and lost_awareness'),
 ('family_present == FALSE OR market.noisy == TRUE','family_present == False or market.noisy == True'),
])
def test_lexical_aliases_preserve_complete_logic(upper,lower):
    normalized,changes=c.normalize(upper)
    assert changes
    assert expression(normalized)==expression(lower)


@pytest.mark.parametrize('text',[
 'distance_since_rest_m >= 28물이 280',
 '__import__("os").system("false")',
 'AND_feature', 'IS_WALKING', 'family_present = False',
])
def test_ambiguous_numbers_unknown_names_and_execution_stay_rejected(text):
    normalized,_=c.normalize(text)
    with pytest.raises((ValueError,SyntaxError)):
        expression(normalized)


def test_quotes_numbers_and_guardian_source_are_not_rewritten():
    text='unknown("AND", 280)'
    assert c.normalize(text)==(text,[])
    value={'source_assessment':'보호자 원문 AND 28물이 280',
           'rules':[{'condition':'is_walking AND pain_observed'}]}
    normalized,audit=c.prepare(value)
    assert normalized['source_assessment']==value['source_assessment']
    assert value['rules'][0]['condition']=='is_walking AND pain_observed'
    assert audit[0]['before']!=audit[0]['after']
