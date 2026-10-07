"""Regression checks for the frozen JSON-only comparison; no network calls."""
import copy,json
from pathlib import Path
import pytest
import branch_contract_v2 as previous
import branch_json_completion_v3 as candidate
D=Path(__file__).resolve().parent
ROWS={r['id']:r for r in map(json.loads,(D/'dataset/development.jsonl').read_text().splitlines())}
REQUESTS=list(map(json.loads,(D/'json_completion_requests.jsonl').read_text().splitlines()))
@pytest.mark.parametrize('staged',REQUESTS,ids=lambda r:r['id']+'_r'+str(r['repeat']))
def test_frozen_request_changes_only_output_instruction(staged):
    request=staged
    context=ROWS[request['id']]['context']; before=copy.deepcopy(context)
    old=previous.payload(context,'branch_explicit_facts_v2',request['body']['model'])
    new=candidate.payload(context,request['arm'],request['body']['model'])
    assert new==request['body']
    assert context==before
    assert new['messages'][0]['content'].endswith(candidate.JSON_INSTRUCTION)
    new['messages'][0]['content']=new['messages'][0]['content'][:-len(candidate.JSON_INSTRUCTION)]
    assert new==old

def test_one_missing_branch_cannot_be_repaired_or_scored_as_complete():
    request=REQUESTS[1];context=ROWS[request['id']]['context']
    branches=json.loads(request['body']['messages'][1]['content'])['가정_분기']
    response={key:dict(next_command_id='continue',source_ids=['N1'],reason='검증용 설명') for key in branches}
    response.pop(next(iter(response)))
    with pytest.raises(ValueError,match='branch_coverage'):
        candidate.validate(response,context,request['arm'])

def test_valid_structure_does_not_imply_correct_personal_behavior():
    request=REQUESTS[1];context=ROWS[request['id']]['context']
    branches=json.loads(request['body']['messages'][1]['content'])['가정_분기']
    response={key:dict(next_command_id='continue',source_ids=['N1'],reason='검증용 설명') for key in branches}
    decision=candidate.validate(response,context,request['arm'])
    assert decision['action']=='continue'
    assert decision['status']!=ROWS[request['id']]['expected']['status']
