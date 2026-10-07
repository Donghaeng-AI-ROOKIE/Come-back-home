"""Eliminate a redundant target SET while preserving real goal changes/restarts."""
import copy,json
import contrast_candidate as candidate
import state_contract as base

def options(context):
    choices=copy.deepcopy(base.original.menu.options(context))
    state=context['state']
    if state['current_action']=='seek' and 'continue' in choices:
        choices={k:v for k,v in choices.items() if not (v['action']=='seek' and v['goal_label']==state.get('target_label'))}
    return choices

def payload(context,arm,model):
    body=candidate.payload(context,arm,model);allowed=options(context)
    data=json.loads(body['messages'][1]['content'])
    data['available_commands']=[c for c in data['available_commands'] if c['next_command_id'] in allowed]
    body['messages'][1]['content']=json.dumps(data,ensure_ascii=False)
    body['response_format']['json_schema']['schema']['properties']['next_command_id']['enum']=list(allowed)
    body['messages'][0]['content']+='\n이미 향하던 같은 목적지를 유지하는 명령은 continue다. seek는 다른 목적지로 변경하거나 멈춤 후 목적지로 재개할 때 사용한다. 필요한 개인 조건의 해석과 행동 선택은 원문·현재 관측에 근거해 수행한다.'
    return body

def validate(value,context):
    if not isinstance(value,dict) or value.get('next_command_id') not in options(context):raise ValueError('command_not_available')
    return base.validate(value,context)
