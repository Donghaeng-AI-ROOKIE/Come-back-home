import copy,json
from pathlib import Path
import pytest
import alignment_contract as c
D=Path(__file__).resolve().parent
ROWS=[json.loads(x) for x in (D/'dataset/development.jsonl').read_text().splitlines()]

@pytest.mark.parametrize('row',ROWS,ids=lambda r:r['id'])
def test_original_person_and_all_facts_preserved(row):
    original=copy.deepcopy(row['context']);packed=c.compact(original)
    assert original==row['context']
    assert packed['person']==original['person']
    assert packed['research']==original['research']
    for f in packed['current_facts']:
        assert json.dumps(json.loads(f['value_json']),ensure_ascii=False,sort_keys=True)==f['value_json']
    assert len({f['fact_id'] for f in packed['current_facts']})==len(packed['current_facts'])
    for arm in ['full','compact','grounded']:
        body=c.payload(original,arm,'offline')
        assert sum(len(m['content'].encode()) for m in body['messages'])+256<=16384
        assert 'expected' not in json.loads(body['messages'][1]['content'])


def grounded():
    r=ROWS[3];answer=copy.deepcopy(r['expected'])
    answer['checks']=[{'source_id':'N1','quote':'공원 소리를 꺼려 돌아가는 분이지만',
       'facts':[{'fact_id':'/environment/observed_signals/park/noisy','value_json':'null'}],
       'relation':'unknown'}]
    return r['context'],answer


def test_unknown_remains_unknown():
    context,answer=grounded()
    assert c.validate(answer,context,'grounded')['status']=='insufficient_information'
    answer['checks'][0]['facts'][0]['value_json']='false'
    with pytest.raises(ValueError,match='fact_changed'):c.validate(answer,context,'grounded')


def test_fabricated_quote_and_injected_observation_fail():
    context,answer=grounded();answer['checks'][0]['quote']='소음은 없다고 확인했다'
    with pytest.raises(ValueError,match='quote_not_verbatim'):c.validate(answer,context,'grounded')
    context,answer=grounded();answer['checks'][0]['facts'][0]['fact_id']='/invented'
    with pytest.raises(ValueError,match='fact_changed'):c.validate(answer,context,'grounded')


def test_valid_references_do_not_certify_relation_semantics():
    context,answer=grounded();answer['checks'][0]['relation']='applies'
    # References are authentic, but the relation is wrong. This MUST remain a separate semantic rubric.
    assert c.validate(answer,context,'grounded')['status']=='insufficient_information'


def test_corrected_same_goal_labels_and_original_files():
    audit=json.loads((D/'data_audit.json').read_text());assert len(audit['corrections'])==4
    rows=[json.loads(x) for x in (D/'dataset/train_corrected.jsonl').read_text().splitlines()]
    for row in rows:
        c.v5.validate(row['expected'],row['context'])
        assert json.loads(row['messages'][-1]['content'])==row['expected']
        s=row['context']['state'];e=row['expected']
        assert not (s['current_action']=='seek' and e['action']=='seek' and s['target_label']==e['goal_label'])
        if row.get('label_revision'):
            assert row['rubric']['allowed_action_goal_feature']==[['continue',None,None]]


@pytest.mark.parametrize('index,text',[(4,'동행자가 없다고 확인됨'),(5,'동행자가 있다고 확인됨'),(7,'동행자가 있는지 미확인')])
def test_companion_presence_and_missing_observation_are_distinct(index,text):
    import next_action_followup as followup
    original=copy.deepcopy(ROWS[index]['context'])
    assert any(text in x for x in followup.render(original)['관측_요약'])
    assert followup.render(original)['보호자_원문과_저장_개인해석']==original['person']
    assert original==ROWS[index]['context']


def test_sources_are_copied_from_original_without_changing_action():
    import next_action_followup as followup
    context=ROWS[0]['context'];output={'next_command_id':'rest','source_ids':['N1'],'reason':'높은 피로의 개인 휴식 조건'}
    decoded=followup.validate(output,context,'next_source_ids')
    assert decoded['action']=='rest'
    linked=followup.attach_original_sources(output,context)
    assert linked[0]['original_text']==context['person']['evidence_notes'][0]['text']
    assert 'server_copied' in linked[0]['provenance']
    # Selecting the wrong action remains wrong: this adapter never replaces it.
    output['next_command_id']='stay'
    assert followup.validate(output,context,'next_source_ids')['action']=='stay'
