import json,sys
from experiments.mind_contract_ab_20261007 import run_staged9 as runner,run_repair8,contract_d8,contract_d9,run_v2


def test_interpretation_failure_counts_both_repeats_without_compiler_calls(tmp_path,monkeypatch):
    original=run_repair8.repair_dataset()
    inputs,scenes,refs,files=original
    first=inputs[0]
    monkeypatch.setattr(run_repair8,'repair_dataset',lambda:([first],[s for s in scenes if s['input_id']==first['id']],{first['id']:refs[first['id']]},files))
    calls=[]
    def invoke(body,job,**kw):
        calls.append(job)
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'observed_behaviors':[],'other_information':[]})}}]}
    monkeypatch.setattr(run_v2.transport,'invoke',invoke)
    monkeypatch.setenv('CBH_K_BRIDGE_SSH','fake-no-network')
    monkeypatch.setattr(sys,'argv',['run_staged9','--out',str(tmp_path),'--ledger',str(tmp_path/'ledger.jsonl'),'--execute'])
    (tmp_path/'ledger.jsonl').write_text('')
    runner.main()
    value=json.loads((tmp_path/'scored.json').read_text())
    assert len(calls)==2 and all(x.endswith('_interpret') for x in calls)
    assert value['summary']['complete'] and value['summary']['responses']==2
    assert value['summary']['final_valid']==0
    assert all(r['pipeline_failure']['error']=='source_note_omitted' for r in value['rows'])
    assert all(r['policy'] is None for r in value['rows'])


def test_source_cards_and_original_both_reach_compiler(tmp_path,monkeypatch):
    inputs,scenes,refs,files=run_repair8.repair_dataset();first=inputs[0]
    monkeypatch.setattr(run_repair8,'repair_dataset',lambda:([first],[s for s in scenes if s['input_id']==first['id']],{first['id']:refs[first['id']]},files))
    calls=[]
    def invoke(body,job,**kw):
        calls.append((job,body))
        if job.endswith('_interpret'):
            value={'observed_behaviors':[],'other_information':[{'note_ids':[n['id']],'content':n['text'],'reason_not_behavior':'fake test artifact'} for n in first['personal']['notes']]}
        else:
            schema=contract_d8.schema(first['personal'])
            ids=schema['properties']['other_sentences']['items']['properties']['sentence_ids']['items']['enum']
            value={'behaviors':[],'other_sentences':[{'sentence_ids':[i],'subject':'patient','kind':'other_information'} for i in ids]}
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}]}
    monkeypatch.setattr(run_v2.transport,'invoke',invoke)
    monkeypatch.setenv('CBH_K_BRIDGE_SSH','fake-no-network')
    monkeypatch.setattr(sys,'argv',['run_staged9','--out',str(tmp_path),'--ledger',str(tmp_path/'ledger.jsonl'),'--execute'])
    (tmp_path/'ledger.jsonl').write_text('')
    runner.main()
    assert len(calls)==4
    for job,body in calls:
        if not job.endswith('_interpret'):
            payload=json.loads(body['messages'][-1]['content'])
            assert payload['original_notes']==first['personal']['notes']
            assert payload['untrusted_source_interpretation']['other_information']
            assert not {'reference','scenes','expected_commands'} & payload.keys()
    result=json.loads((tmp_path/'scored.json').read_text())
    assert result['summary']['complete'] and result['summary']['final_valid']==2
    # Valid empty output is still penalized for losing the stated walking-rest behavior.
    assert result['summary']['passed'] < result['summary']['decisions']
