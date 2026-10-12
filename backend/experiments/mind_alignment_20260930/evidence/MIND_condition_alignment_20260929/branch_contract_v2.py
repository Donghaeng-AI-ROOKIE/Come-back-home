"""Unexecuted candidate: explicit hypothesis labels, observation age, no-op-free menu."""
import copy,json
import branch_contract as previous
SYSTEM_SUFFIX='''\n각 가정 분기의 확정 가정값은 가정_분기_읽기에 있다. 전체_현재사실의 null은 원래 관측을 모른다는 뜻이며, 해당 분기에 지정한 가정값과 혼동하지 않는다. 다른 분기의 설명을 복사하면서 가정값을 바꾸지 않는 오류를 피한다.\n관측의 경과시각은 시뮬레이션 시작 후의 시각이며 현재부터 몇 분 전인지는 별도로 계산되어 있다. 두 숫자의 뜻을 뒤바꾸지 않는다. 설명에는 선택에 실제로 관련되는 개인 조건과 사실만 적는다. 관련 없는 가정은 행동의 원인처럼 나열하지 않는다.\n가능한 다음 명령 목록에 없는 명령을 생성하지 않는다. 이미 향하던 같은 목적지를 유지할 때는 continue를 사용한다. 이 목록 정리는 개인의 행동을 정해 주는 것이 아니며, 필요한 개인 조건 해석은 원문을 읽어 수행한다.'''

def options(context):
    values=copy.deepcopy(previous.original.menu.options(context))
    state=context['state']
    # Remove only the redundant SET of the same target while already travelling.
    # Resuming after rest/stay or selecting a different target is still expressible.
    if state['current_action']=='seek' and 'continue' in values:
        values={k:v for k,v in values.items() if not (v['action']=='seek' and v['goal_label']==state.get('target_label'))}
    return values

def readable_worlds(context):
    result={}
    for key,world in previous.worlds(context).items():
        facts=[]
        for path,value in world.items():
            if path.startswith('/environment/observed_signals/'):
                feature,signal=path.split('/')[-2:]
                subject={'park':'공원','market':'시장','water':'물가','forest':'숲'}[feature]+' '+{'noisy':'소음','crowded':'혼잡'}[signal]
            else:subject='동행자'
            facts.append({'fact_id':path,'hypothetical_value':value,'text':subject+(' 있음' if value else ' 없음'),'is_observed':False})
        result[key]=facts
    return result

def payload(context,arm,model):
    assert arm=='branch_explicit_facts_v2'
    body=previous.payload(context,'branch_thinking',model)
    body['max_tokens']=12000
    body['messages'][0]['content']+=SYSTEM_SUFFIX
    data=json.loads(body['messages'][1]['content'])
    data['가정_분기_읽기']={key:[fact['text'] for fact in facts] for key,facts in readable_worlds(context).items()}
    data['가정_분기_읽기_주의']='각 값은 실제 관측이 아니라 이 분기에만 적용하는 가정이다. 정확한 Boolean과 원본 경로는 가정_분기에 보존.'
    allowed=options(context)
    data['가능한_다음명령']=[x for x in data['가능한_다음명령'] if x['next_command_id'] in allowed]
    events=[(i,e) for i,e in enumerate(context['state']['recent_events']) if e['kind']=='companion_observation']
    if events:
        i,event=max(events,key=lambda pair:pair[1]['elapsed_minutes'])
        when=event['elapsed_minutes'];now=context['state']['elapsed_minutes'];age=now-when
        label='동행자가 있다고 확인됨' if event.get('value') is True else '동행자가 없다고 확인됨' if event.get('value') is False else '동행자가 있는지 미확인'
        data['관측_요약'][-1]=f'{label}. 관측은 현재로부터 {age}분 전. 시작 후 {when}분에 관측했고 현재는 시작 후 {now}분이다.'
    body['messages'][1]['content']=json.dumps(data,ensure_ascii=False)
    for schema in body['response_format']['json_schema']['schema']['properties'].values():
        schema['properties']['next_command_id']['enum']=list(allowed)
    return body

def validate(value,context,arm):
    if not isinstance(value,dict):raise ValueError('branches')
    for branch in value.values():
        if not isinstance(branch,dict) or branch.get('next_command_id') not in options(context):raise ValueError('command_not_available')
    return previous.validate(value,context,'branch_thinking')

attach_original_sources=previous.attach_original_sources
