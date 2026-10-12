from copy import deepcopy
import pytest
from experiments.mind_grounded.contract import validate,facts,schema


def context():
 return {'person':{'evidence_notes':[{'id':'N0','text':'질문: 많이 피곤해도 계속 걷나요?\n답변: 많이 지치면 잠깐 앉아서 쉬어요.'}]},
         'state':{'fatigue':.9,'current_action':'seek','last_rest_end_minutes':None,'target_label':'A'},
         'clock_time':'2026-09-28T09:00:00','known_places':[{'label':'A'}],'research':[],
         'environment':{'map_proximity_m':{'market':20,'water':None}}}


def answer():
 return {'evidence':[{'note_id':'N0','quote':'많이 지치면 잠깐 앉아서 쉬어요.'}],
         'state_check':{'fatigue_band':'high','rest_phase':'not_recorded'},
         'assessment':'현재 피로가 높고 보호자에게 보고된 휴식 조건에 해당한다.',
         'confusion_level':'unknown','decision':{'action':'rest'}}


def test_temporal_rest_and_goal_are_not_erased():
 d=validate(answer(),context());assert d.action=='rest' and d.goal_operation=='keep'
 c=context();c['state']['last_rest_end_minutes']=59
 assert facts(c)['rest_phase']=='completed'
 assert facts(c)['fatigue_band']=='high' # completed rest does not imply recovery


def test_question_is_not_treated_as_guardian_evidence():
 a=answer();a['evidence'][0]['quote']='많이 피곤해도 계속 걷나요?'
 with pytest.raises(ValueError,match='quote_not_in_guardian_answer'):validate(a,context())


def test_fabricated_or_reversed_quotes_are_rejected():
 a=answer();a['evidence'][0]['quote']='많이 지쳐도 계속 걸어요.'
 with pytest.raises(ValueError):validate(a,context())


def test_current_state_cannot_be_overwritten_by_model():
 a=answer();a['state_check']['fatigue_band']='low'
 with pytest.raises(ValueError,match='state_fact_mismatch'):validate(a,context())


def test_unmapped_avoidance_and_unregistered_goal_rejected():
 for d in [{'action':'seek','goal_label':'unregistered'},{'action':'avoid','avoid_feature':'water'}, {'action':'rest','goal_label':'A'}]:
  a=answer();a['decision']=d
  with pytest.raises(ValueError):validate(a,context())


def test_evidence_and_assessment_are_not_repeated_per_action_branch():
 s=schema(context());assert list(s['properties'])[-1]=='decision'
 for branch in s['properties']['decision']['anyOf']:
  assert 'assessment' not in branch['properties'] and 'evidence' not in branch['properties']


def test_prepared_nonthinking_candidate_preserves_input_and_action_choices():
 import json
 from experiments.mind_grounded.source_enum import request_spec as previous
 from experiments.mind_grounded.nonthinking import request_spec as prepared
 c=context();a=previous(c,'k','test');b=prepared(c,'k','test')
 assert json.loads(a['messages'][1]['content'])==json.loads(b['messages'][1]['content'])
 assert b['chat_template_kwargs']['enable_thinking'] is False
 x=a['response_format']['json_schema']['schema'];y=b['response_format']['json_schema']['schema']
 assert x['properties']['decision']==y['properties']['decision']
 assert y['properties']['evidence']['items']['properties']['quote']['enum']==['많이 지치면 잠깐 앉아서 쉬어요.']
 # The application still enforces the bound omitted from the API decoder schema.
 value=answer();value['evidence']*=5
 with pytest.raises(ValueError,match='missing_evidence'):validate(value,c)
