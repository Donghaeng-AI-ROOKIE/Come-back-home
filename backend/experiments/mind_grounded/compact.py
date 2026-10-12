"""Same behavioral contract, clearer guardian-answer boundary and string-first output."""
import json
from copy import deepcopy
from .contract import request_spec as base_request_spec, validate


def request_spec(context, provider, model, variant='compact'):
    request=base_request_spec(context,provider,model,'grounded')
    visible=json.loads(request['messages'][1]['content'])
    for note in visible['person']['evidence_notes']:
        text=note.pop('text')
        if '\n답변: ' in text:
            question,answer=text.split('\n답변: ',1)
            note['question_context']=question.removeprefix('질문: ')
            note['guardian_answer']=answer
        else:
            note['question_context']=''
            note['guardian_answer']=text.removeprefix('답변: ')
    request['messages'][1]['content']=json.dumps(visible,ensure_ascii=False)
    s=request.get('guided_json') if provider=='dem5' else request['response_format']['json_schema']['schema']
    properties=s['properties'];s['properties']={'assessment':properties['assessment'],**{k:v for k,v in properties.items() if k!='assessment'}}
    request['messages'][0]['content']=request['messages'][0]['content'].replace('evidence→state_check→assessment→confusion_level→decision','assessment→evidence→state_check→confusion_level→decision')
    # The K prompt contains its schema; regenerate it so prompt and actual decoder agree.
    request['messages'][0]['content']=request['messages'][0]['content'].split('\n출력 스키마:\n')[0]
    request['messages'][0]['content']+='\nevidence.quote는 guardian_answer에서 연속한 구절을 정확히 인용한다. question_context와 질문/답변 접두어를 인용에 넣지 않는다. 질문은 짧은 답변의 의미를 이해할 때만 사용한다. JSON은 불필요한 공백과 줄바꿈 없이 한 줄로 작성한다.\n'
    if provider=='k':request['messages'][0]['content']+='\n출력 스키마:\n'+json.dumps(s,ensure_ascii=False)
    return request
