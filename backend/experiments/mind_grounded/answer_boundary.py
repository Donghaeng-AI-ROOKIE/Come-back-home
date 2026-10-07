"""Keep c1's evidence-first contract; separate questions from guardian answers."""
import json
from .contract import request_spec as base_request_spec, validate


def request_spec(context, provider, model, variant='answer_boundary'):
    request = base_request_spec(context, provider, model, 'grounded')
    visible = json.loads(request['messages'][1]['content'])
    for note in visible['person']['evidence_notes']:
        original = note.pop('text')
        if '\n답변: ' in original:
            question, answer = original.split('\n답변: ', 1)
            note['question_context'] = question.removeprefix('질문: ')
            note['guardian_answer'] = answer
        else:
            note['question_context'] = ''
            note['guardian_answer'] = original.removeprefix('답변: ')
    request['messages'][1]['content'] = json.dumps(visible, ensure_ascii=False)
    request['messages'][0]['content'] += (
        '\nevidence.quote에는 guardian_answer에 실제 존재하는 연속 구절만 인용한다. '
        'question_context는 짧은 답변을 해석하는 문맥이며 보호자 답변이 아니다. '
        '질문 문장이나 질문/답변 접두어를 인용에 넣지 않는다. '
        '인용과 assessment를 생략하거나 말줄임표·자리표시자로 대체하지 않는다.'
    )
    return request
