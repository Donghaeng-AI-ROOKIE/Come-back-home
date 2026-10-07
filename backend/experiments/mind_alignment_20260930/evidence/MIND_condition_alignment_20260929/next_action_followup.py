"""Next-command probe. Guardian language is never mapped to an action by code."""
import copy,json,importlib.util
from pathlib import Path
import alignment_contract as base
p=base.OLD/'contract_k_v7.py';spec=importlib.util.spec_from_file_location('saved_menu_contract',p);menu=importlib.util.module_from_spec(spec)
# saved menu module imports its frozen v5 dependency as contract
import sys
sys.modules.setdefault('contract',base.v5);spec.loader.exec_module(menu)
SYSTEM='''지금은 가상 보행자의 다음 행동 명령을 새로 결정하는 시점이다. 보호자가 설명한 이 사람의 조건과 현재 관측을 연결해 next_command_id 하나를 선택한다.
직전 실행 명령은 과거부터 지금까지 하던 동작이다. 이번에 유지해야 한다는 지시가 아니다. 걷던 사람도 개인 조건에 따라 지금 쉬거나 피하는 동작으로 전환할 수 있다.
보호자 원문과 저장 해석은 함께 제공된다. 질문·부정·예외·우선순위까지 읽고, 요약이 생략한 조건은 원문을 따른다. 원문에서 관찰하지 않았다는 상황이나 현재 관측 미확인은 사실을 지어내지 말고 defer로 남긴다. 미확인은 false가 아니다.
개인의 반응이 갈라지는 조건을 판별하는 데 필요한 관측이 미확인이면, 이전에 하던 행동을 그대로 고르는 것으로 그 조건이 확인되지는 않는다. 다른 충분한 근거가 없으면 defer로 남긴다. 관련 없는 관측의 미확인만으로 판단을 유보하지 않는다.
가능한 다음 명령 목록은 엔진이 표현할 수 있는 동작일 뿐 추천이 아니다. 현재 사실만으로 판단하며 휴식이 먼저 끝났다고 가정하거나 목적지까지 간 후의 시점을 상상하지 않는다.
입력에 없는 안전성·경로 관련성·동행자·환경을 추가하지 않는다. 치매라는 집단 특성으로 개인 원문을 덮어쓰지 않는다.
결과는 next_command_id, source_ids, reason만 포함한 JSON. source_ids에는 근거로 사용한 보호자 원문 ID만 적는다. 원문 인용문은 서버가 원본에서 연결하므로 다시 작성하지 않는다. reason은 선택한 다음 행동과 개인 조건·현재 관측이 연결되는 공개 설명 1~2문장(한국어)이다. 긴 내부 추론을 쓰지 않는다.'''
LABELS={'continue':'진행하던 이동·목표 유지','rest':'지금 잠시 쉬기','stay':'지금 제자리에서 기다리기','roam':'목표 없이 걷기','defer':'필요한 개인 조건 또는 관측이 없어 판단 유보'}

def render(context):
    facts={f['fact_id']:f['value_json'] for f in base.facts(context)}
    state=context['state'];band=json.loads(facts['/engine_current_facts/fatigue_band'])
    brief=[f"현재 피로: {state['fatigue']}, 엔진 구간: {dict(high='높음',medium='중간',low='낮음')[band]} (임상 측정 아님)",f"직전까지 실행한 명령: {state['current_action']}",f"기억한 목표: {state['target_label']}"]
    yn=lambda value:'미확인' if value is None else '있음' if value is True else '없음' if value is False else str(value)
    for feature,signals in context['environment']['observed_signals'].items():
        name={'park':'공원','market':'시장','forest':'숲','water':'물가'}.get(feature,feature)
        for key,label in [('noisy','소음'),('crowded','혼잡')]:
            if key in signals:brief.append(f'현재 {name} {label}: {yn(signals[key])}')
    events=[(i,e) for i,e in enumerate(state['recent_events']) if e['kind']=='companion_observation']
    if events:
        i,event=max(events,key=lambda pair:pair[1]['elapsed_minutes'])
        presence='동행자가 있다고 확인됨' if event.get('value') is True else '동행자가 없다고 확인됨' if event.get('value') is False else '동행자가 있는지 미확인'
        brief.append(f"{presence}, 관측된 경과시각 {event['elapsed_minutes']}분 (현재 {state['elapsed_minutes']}분)")
    else:brief.append('동행자 관측: 제공되지 않음')
    options=menu.options(context)
    option_list=[]
    for id,command in options.items():
        desc=LABELS.get(id)
        if id.startswith('seek_'):desc='지금 '+command['goal_label']+'로 목표 설정 또는 멈춤 후 재개'
        if id.startswith('avoid_'):desc='지금 '+{'market':'시장','park':'공원','water':'물가','forest':'숲'}[command['avoid_feature']]+' 환경에서 멀어지는 이동'
        option_list.append({'next_command_id':id,'meaning':desc})
    return {'현재_판단_시점':context['clock_time'],'관측_요약':brief,
            '보호자_원문과_저장_개인해석':copy.deepcopy(context['person']),
            '전체_현재사실':base.facts(context),'연구_발췌':copy.deepcopy(context['research']),
            '가능한_다음명령':option_list}


def payload(context,arm,model):
    assert arm=='next_source_ids'
    schema={'type':'object','additionalProperties':False,'required':['next_command_id','source_ids','reason'],'properties':{
        'next_command_id':{'type':'string','enum':list(menu.options(context))},
        'source_ids':{'type':'array','minItems':1,'items':{'type':'string','enum':[n['id'] for n in context['person']['evidence_notes']]}},
        'reason':{'type':'string','minLength':1,'maxLength':400}}}
    return {'model':model,'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(render(context),ensure_ascii=False)}],
        'temperature':1.,'top_p':.95,'max_tokens':6000,'parse_reasoning':True,'chat_template_kwargs':{'enable_thinking':True},
        'response_format':{'type':'json_schema','json_schema':{'schema':schema}}}


def validate(value,context,arm):
    if not isinstance(value,dict) or set(value)!= {'next_command_id','source_ids','reason'}:raise ValueError('fields')
    if value['next_command_id'] not in menu.options(context):raise ValueError('command')
    ids=value['source_ids'];notes={n['id']:n['text'] for n in context['person']['evidence_notes']}
    if not isinstance(ids,list) or not ids or any(not isinstance(i,str) or i not in notes for i in ids):raise ValueError('source_ids')
    decision={**menu.options(context)[value['next_command_id']],'reason':value['reason'],'evidence_ids':list(dict.fromkeys(ids)),'confusion_level':'unknown'}
    return base.v5.validate(decision,context)


def attach_original_sources(value,context):
    validate(value,context,'next_source_ids')
    notes={n['id']:n['text'] for n in context['person']['evidence_notes']}
    return [{'source_id':i,'original_text':notes[i], 'provenance':'server_copied_original_not_model_quote'} for i in value['source_ids']]
