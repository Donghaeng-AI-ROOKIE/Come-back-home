"""D7: always re-read source and a saved D6 draft, including valid drafts.

The review gets no reference policy, expected scene or score. This is model
self-review, not an independent human or clinical validation. D6 outputs and
scores remain untouched. Keep the same D4 compiler to isolate review effect.
"""
import json

from experiments.mind_contract_ab_20261007 import contract_d6 as d6, completion

RELEASE_QUALIFIED = False
VERSION = 'contract-d7-source-review-20261008-research'
SAMPLING = dict(d6.SAMPLING)
schema = d6.schema
compile_d7 = d6.compile_d6
correction = d6.correction
trait_accounting = d6.trait_accounting

REVIEW = '''
이번 작업은 원문과 기존 초안을 대조하여 완성본을 다시 쓰는 것이다.
초안은 같은 모델이 작성했으며, JSON이 맞아도 내용이 틀릴 수 있다. 초안을 정답이나 추가 관찰로 취급하지 않는다.
1. 초안을 먼저 따라 고치지 말고 질문과 답변 전체에서 본인이 실제로 보인 각각의 반응을 먼저 확인한다.
2. 각 반응에 대해 주체, 행동, 시작 조건 모두, 끝나는 조건, 장소 범위, 수치와 단위를 원문과 대조한다. 같은 문장 안의 서로 다른 반응을 하나로 합쳐 하나를 잃지 않는다.
3. 초안의 행동과 조건 각각을 하나씩 제거하거나 반대로 놓아 본다. 그때에도 원문이 같은 행동을 뒷받침하는지 살핀다. 원문이 한정한 상황 밖으로 행동을 넓히거나 근거 없이 좁힌 부분을 수정한다.
4. other_sentences에 들어간 문장도 다시 읽는다. 실제 관찰된 반응을 단순 능력이나 미관찰로 버리지 않는다. 반대로 능력·희망·제삼자의 이야기를 본인의 반응으로 만들지 않는다.
5. 원문이 예외나 배타적 반응을 말하면 함께 읽어 서로 모순되지 않게 조건을 표현한다. 원문이 동시 상황을 말하지 않았다면 임의로 우선순위를 정하지 않는다. 제공된 형식으로 보존할 수 없는 특성은 not_representable로 남기며 없는 것으로 처리하지 않는다.
6. 빠뜨린 반응은 복구하고 근거 없는 반응은 제거한다. 맞았던 행동·조건·장소·숫자를 수정 자체를 위해 바꾸지 않는다.
최종 출력은 기존과 같은 behaviors와 other_sentences 두 목록의 완전한 JSON 하나다. 검토 설명이나 새 필드는 출력하지 않는다.
'''


def request_with_draft(personal, public, model, *, thinking=True):
    body = d6.request(personal, model, thinking=thinking)
    status, value = completion.classify(public)
    payload = json.loads(body['messages'][-1]['content'])
    # Only final content is evidence for review. Never send reasoning, scores,
    # validator feedback, expected rules or evaluator-produced counterexamples.
    payload['untrusted_previous_draft'] = value if status == 'complete_json' else public.get('final_content')
    payload['draft_completion_status'] = status
    body['messages'][0]['content'] += '\n' + REVIEW
    body['messages'][-1]['content'] = json.dumps(payload, ensure_ascii=False)
    if len(json.dumps(body, ensure_ascii=False).encode()) > 40000:
        raise ValueError('input byte cap; original evidence is not truncated')
    return body
