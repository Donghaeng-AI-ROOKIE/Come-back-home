"""Isolation and provenance checks, not model-quality evidence."""
import json

import pytest

from experiments.mind_contract_ab_20261007 import contract_d7 as d7, run_repair8, run_source_review8 as runner


def test_review_gets_only_source_and_final_draft_not_grading_or_reasoning():
    inputs, _, _, _ = run_repair8.repair_dataset()
    public = {'finish_reason': 'stop', 'final_content': '{"behaviors":[],"other_sentences":[]}',
              'reasoning_content': 'SECRET_REASONING', 'score': 'GOLD_SCORE',
              'reference_policy': 'GOLD_POLICY', 'scene': 'GOLD_SCENE'}
    body = d7.request_with_draft(inputs[0]['personal'], public, 'test-model')
    text = json.dumps(body, ensure_ascii=False)
    assert not any(x in text for x in ('SECRET_REASONING', 'GOLD_SCORE', 'GOLD_POLICY', 'GOLD_SCENE'))
    payload = json.loads(body['messages'][-1]['content'])
    assert payload['original_notes'] == inputs[0]['personal']['notes']
    assert payload['untrusted_previous_draft'] == json.loads(public['final_content'])
    assert set(payload['output_schema']['properties']) == {'behaviors', 'other_sentences'}


def test_invalid_or_truncated_draft_is_not_repaired_locally_or_dropped():
    inputs, _, _, _ = run_repair8.repair_dataset()
    broken = '{"behaviors":['
    body = d7.request_with_draft(inputs[0]['personal'],
                                 {'finish_reason': 'length', 'final_content': broken}, 'test-model')
    payload = json.loads(body['messages'][-1]['content'])
    assert payload['draft_completion_status'] == 'incomplete_length'
    assert payload['untrusted_previous_draft'] == broken


def test_pair_freeze_keeps_all_final_drafts_and_rejects_postfreeze_changes(tmp_path):
    source = tmp_path / 'd6_dev8'
    rows = []
    for key in run_repair8.IDS:
        for rep in (1, 2):
            corrected = rep == 2
            rows.append({'input_id': key, 'rep': rep, 'corrected': corrected})
            folder = source / key / str(rep) / ('fix' if corrected else 'first')
            runner.run_v2.write(folder / 'response.public.json',
                                {'finish_reason': 'stop', 'final_content': '{}', 'score': 'NEVER_COPY'})
    runner.run_v2.write(source / 'scored.json', {'summary': {'complete': True}, 'rows': rows})
    target = tmp_path / 'drafts.json'
    frozen = runner.freeze_drafts(source, target)
    assert len(frozen['drafts']) == 16
    assert all('/fix/' in r['source'] for r in frozen['drafts'] if r['rep'] == 2)
    assert 'NEVER_COPY' not in target.read_text()
    assert runner.freeze_drafts(source, target) == frozen
    path = source / run_repair8.IDS[0] / '1' / 'first' / 'response.public.json'
    path.write_text('{"finish_reason":"length","final_content":"changed"}')
    with pytest.raises(ValueError, match='frozen drafts differ'):
        runner.freeze_drafts(source, target)


def test_incomplete_batch_cannot_start_source_review(tmp_path):
    runner.run_v2.write(tmp_path / 'scored.json', {'summary': {'complete': False}})
    with pytest.raises(ValueError, match='must finish'):
        runner.freeze_drafts(tmp_path, tmp_path / 'drafts.json')
