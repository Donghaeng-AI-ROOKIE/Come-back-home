"""c1 with exact source selection instead of free-form source quotation.

The model still interprets the original and chooses its action. Enumerating source
text is not a word-to-behavior mapping and does not constrain which action wins.
"""
import json
from .contract import request_spec as base_request_spec, validate


def request_spec(context, provider, model, variant='source_enum'):
    request=base_request_spec(context,provider,model,'grounded')
    s=request.get('guided_json') if provider=='dem5' else request['response_format']['json_schema']['schema']
    answers=[n['text'].split('\n답변: ',1)[-1] for n in context['person']['evidence_notes']]
    s['properties']['evidence']['items']['properties']['quote']={'type':'string','enum':list(dict.fromkeys(answers))}
    request['messages'][0]['content']=request['messages'][0]['content'].split('\n출력 스키마:\n')[0]
    request['messages'][0]['content'] += (
        '\nevidence.quote는 스키마 enum에서 해당 note_id의 보호자 답변 원문을 선택한다. '
        '질문이나 접두어를 섞지 않는다. 한국어 assessment 1~2문장으로 현재 선택의 근거를 요약한다. '
        '출처 선택과 현재 행동 선택은 별개다. 원문의 조건을 현재 상태와 대조하여 행동을 결정한다.'
    )
    if provider=='k':request['messages'][0]['content']+='\n출력 스키마:\n'+json.dumps(s,ensure_ascii=False)
    return request
