from copy import deepcopy
import pytest
from experiments.mind_contract_ab_20261007.bounded_correction import prepare, size


def body():
    return {'messages': [{'role': 'system', 'content': 'output schema'},
                         {'role': 'user', 'content': '원문 문답 전체 ' * 600}], 'max_tokens': 16384}


def test_oversized_incomplete_model_text_removed_but_source_preserved():
    request = body(); before = deepcopy(request)
    public = {'finish_reason': 'length', 'final_content': '잘못 반복된 출력\\"' * 6000}
    raw = deepcopy(public)
    out, audit = prepare(request, public, 'incomplete_length')
    assert out['messages'][:2] == request['messages']
    assert request == before and public == raw
    assert audit['prior_incomplete_output_omitted'] is True
    assert size(out) <= 40000
    assert out['max_tokens'] == request['max_tokens']


def test_small_error_keeps_previous_output_and_other_errors_do_not_get_silently_cut():
    request = body()
    public = {'finish_reason': 'stop', 'final_content': '{}'}
    out, audit = prepare(request, public, 'unknown condition fact')
    assert out['messages'][-2]['content'] == '{}'
    assert audit['prior_incomplete_output_omitted'] is False
    public['final_content'] = '긴 출력' * 20000
    with pytest.raises(ValueError, match='never truncated'):
        prepare(request, public, 'unknown condition fact')


def test_original_source_never_truncated_even_when_it_alone_exceeds_cap():
    request = body(); request['messages'][1]['content'] *= 20
    with pytest.raises(ValueError, match='never truncated'):
        prepare(request, {'finish_reason': 'length', 'final_content': 'x'}, 'incomplete_length')
