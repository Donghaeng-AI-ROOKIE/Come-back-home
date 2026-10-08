"""Retry an overlong *incomplete output*, never truncate guardian evidence.

Research transport repair. Original candidate scores/requests are immutable.
One separately metered regeneration may be run; there is no recursive retry.
"""
import hashlib
import json
from experiments.mind_contract_ab_20261007 import contract_c

CAP = 40000


def size(body):
    return len(json.dumps(body, ensure_ascii=False).encode())


def prepare(first_body, first_public, problem):
    body = contract_c.correction(first_body, first_public, problem)
    before = size(body)
    raw = (first_public or {}).get('final_content') or ''
    audit = {'original_request_unchanged': True, 'original_response_unchanged': True,
             'original_response_sha256': hashlib.sha256(raw.encode()).hexdigest(),
             'original_correction_bytes': before, 'prior_incomplete_output_omitted': False}
    if before > CAP and problem == 'incomplete_length':
        if first_public.get('finish_reason') != 'length':
            raise ValueError('incomplete_length requires recorded length finish')
        body['messages'][-2]['content'] = '(이전 최종 응답은 출력 길이 한도에서 끊겼다. 미완성 본문은 별도 보존하고 이 요청에서는 생략한다.)'
        body['messages'][-1]['content'] += ' 앞의 보호자 원문과 출력 스키마는 모두 그대로다. 완전한 JSON을 처음부터 다시 생성하라.'
        audit['prior_incomplete_output_omitted'] = True
    if size(body) > CAP:
        raise ValueError('correction exceeds cap; source evidence is never truncated')
    assert body['messages'][:len(first_body['messages'])] == first_body['messages']
    audit['new_correction_bytes'] = size(body)
    return body, audit
