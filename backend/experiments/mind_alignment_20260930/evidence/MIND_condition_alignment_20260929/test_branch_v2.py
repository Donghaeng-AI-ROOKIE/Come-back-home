import copy,json
from pathlib import Path
import branch_contract_v2 as c
D=Path(__file__).resolve().parent
ROWS=list(map(json.loads,(D/'dataset/development.jsonl').read_text().splitlines()))
def test_current_target_set_removed_but_alternatives_and_rest_resume_retained():
 ctx=copy.deepcopy(ROWS[0]['context']);choices=c.options(ctx)
 assert 'continue' in choices and 'seek_0' not in choices and 'seek_1' in choices
 assert 'rest' in choices and 'avoid_park' in choices
 ctx['state']['current_action']='rest'
 assert 'seek_0' in c.options(ctx)
def test_observation_age_not_elapsed_timestamp():
 ctx=ROWS[4]['context'];body=c.payload(ctx,'branch_explicit_facts_v2','offline');data=json.loads(body['messages'][1]['content'])
 assert '현재로부터 1분 전' in data['관측_요약'][-1]
 assert '시작 후 59분' in data['관측_요약'][-1]
 assert data['보호자_원문과_저장_개인해석']==ctx['person']
def test_each_hypothetical_fact_remains_distinct_and_not_observed():
 ctx=ROWS[-1]['context'];original=copy.deepcopy(ctx)
 descriptions=c.readable_worlds(ctx)
 assert len(descriptions)==4
 assert any(x['text']=='동행자 있음' for x in descriptions['b1'])
 assert any(x['text']=='동행자 없음' for x in descriptions['b0'])
 assert all(x['is_observed'] is False for facts in descriptions.values() for x in facts)
 assert ctx==original
