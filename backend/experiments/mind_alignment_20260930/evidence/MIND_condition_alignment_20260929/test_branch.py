import copy,json
from pathlib import Path
import pytest
import branch_contract as c
D=Path(__file__).resolve().parent
ROWS=[json.loads(x) for x in (D/'dataset/development.jsonl').read_text().splitlines()]
def test_worlds_preserve_input_and_cover_unknown_values():
 context=copy.deepcopy(ROWS[-1]['context']);before=copy.deepcopy(context)
 worlds=c.worlds(context)
 assert len(worlds)==4
 assert {r['/state/recent_events/1/value'] for r in worlds.values()}=={False,True}
 assert context==before
 assert all('/environment/observed_signals/market/noisy' not in r for r in worlds.values())
def test_differing_actions_retained_as_uncertainty_not_silent_repair():
 context=ROWS[-1]['context']
 answers={k:{'next_command_id':'continue' if w['/state/recent_events/1/value'] else 'avoid_market','source_ids':['N1'],'reason':'가정별 개인 조건 적용'} for k,w in c.worlds(context).items()}
 assert c.validate(answers,context,'branch_thinking')['status']=='insufficient_information'
 assert {r['next_command_id'] for r in answers.values()}=={'continue','avoid_market'}
 # All branches can still be wrong. Aggregation is not a semantic correctness guarantee.
 for r in answers.values():r['next_command_id']='continue'
 assert c.validate(answers,context,'branch_thinking')['action']=='continue'
def test_irrelevant_unknown_does_not_force_abstention():
 context=ROWS[0]['context'];answers={k:{'next_command_id':'rest','source_ids':['N1'],'reason':'많이 지치면 우선 휴식'} for k in c.worlds(context)}
 assert c.validate(answers,context,'branch_thinking')['action']=='rest'
 answers.pop(next(iter(answers)))
 with pytest.raises(ValueError,match='branch_coverage'):c.validate(answers,context,'branch_thinking')
