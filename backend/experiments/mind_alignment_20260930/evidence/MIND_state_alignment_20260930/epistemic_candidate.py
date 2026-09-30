"""Expose observation knowledge states; no guardian parsing or action oracle."""
import json
import unique_command_contract as base

def fact(path,value,age=None):
    if value is not None and type(value) is not bool:raise ValueError('only_boolean_observation')
    return dict(path=path,original_value=value,
        knowledge_state='참으로 확인' if value is True else '거짓으로 확인' if value is False else '참인지 거짓인지 미확인',
        possible_values_not_new_observations=[False,True] if value is None else [value],
        age_minutes=age)

def payload(context,arm,model):
    if arm!='explicit_knowledge_state':raise ValueError(arm)
    body=base.payload(context,'concise_person_scene',model)
    data=json.loads(body['messages'][1]['content']);scene=data['current_scene'];table=[]
    for feature,signals in scene['environment']['observed_signals'].items():
        for signal,value in signals.items():
            if value is None or type(value) is bool:
                table.append(fact('/environment/observed_signals/'+feature+'/'+signal,value))
    observations=dict(scene['latest_other_observations'],companion_observation=scene['latest_companion_observation'])
    for name,event in observations.items():
        if 'value' in event and (event['value'] is None or type(event['value']) is bool):
            table.append(fact('/latest_observations/'+name,event['value'],event.get('minutes_before_now')))
    data['observation_knowledge_states']=table
    data['knowledge_state_note']='possible_values는 미확인 사실의 가능성만 표시한다. 실제 관측·정답 행동·발생 확률이 아니다. 개인 원문을 읽어 각각 가능한 행동이 같은지 판단한다.'
    body['messages'][1]['content']=json.dumps(data,ensure_ascii=False)
    body['messages'][0]['content']+='''\n조건 추론에서 참·거짓·미확인을 구별한다. "A이면 X, A가 아니면 Y"에서 A가 미확인이면 X와 Y 양쪽 가능성이 남는다. 미확인을 A가 거짓인 경우로 넣지 않는다. "A와 B"에서 A가 참이고 B가 미확인이면 결합 조건도 미확인이다. "A 또는 B"에서 A가 참이면 B가 미확인이어도 결합 조건은 참이다. 원문상 가능한 모든 경우의 행동이 같을 때만 그 행동을 확정한다. 가능한 행동이 다르면 defer다. X/Y는 일반 논리 설명이며 특정 개인의 정답이나 행동 지시가 아니다. 공개 설명에 미확인 사실을 없음·거짓으로 바꾸어 쓰지 않는다.'''
    return body

validate=base.validate
