import json
import pytest
from experiments.mind_contract_ab_20261007 import contract_d9 as d9, run_repair8, transport


def sample():
    personal=run_repair8.repair_dataset()[0][0]['personal']
    cards={'observed_behaviors':[],'other_information':[{'note_ids':[n['id']],'content':n['text'],'reason_not_behavior':'test only'} for n in personal['notes']]}
    return personal,cards


def test_both_requests_preserve_original_without_grades():
    p,c=sample()
    for req in [d9.interpretation_request(p,transport.MODEL),d9.request_with_cards(p,c,transport.MODEL)]:
        payload=json.loads(req['messages'][-1]['content'])
        assert payload['original_notes']==p['notes']
        assert not {'scenes','expected_commands','reference_policies','score'} & payload.keys()
        assert len(json.dumps(req,ensure_ascii=False).encode())<=40000


def test_omitted_note_and_fabricated_quote_rejected():
    p,c=sample();c['other_information'].pop()
    with pytest.raises(ValueError,match='source_note_omitted'):d9.validate_cards(c,p)
    p,c=sample()
    c['observed_behaviors']=[{'note_ids':[p['notes'][0]['id']],'source_quote':'this is not in the original',**{k:'' for k in ['subject','action','starts_when','ends_when','place_scope','quantity_and_unit','uncertainty']}}]
    with pytest.raises(ValueError,match='card_quote_not_in_original'):d9.validate_cards(c,p)
