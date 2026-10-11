"""Historical c5 non-thinking prompt builder; this module makes no live calls."""
import json
from .source_enum import request_spec as source_request_spec, validate


def request_spec(context, provider, model, variant='nonthinking'):
    if provider!='k':raise ValueError('This diagnostic candidate is K-only')
    request=source_request_spec(context,provider,model)
    request['chat_template_kwargs']['enable_thinking']=False
    s=request['response_format']['json_schema']['schema']
    # Friendli's documented decoder subset lists minItems 0/1 but not maxItems.
    # Keep the 1..4 limit in application validation; don't rely on ignored fields.
    s['properties']['evidence'].pop('maxItems',None)
    request['messages'][0]['content']=request['messages'][0]['content'].split('\n출력 스키마:\n')[0]
    request['messages'][0]['content']+='\n출력 스키마:\n'+json.dumps(s,ensure_ascii=False)
    return request
