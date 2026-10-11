"""Separate the latest typed observations from superseded history.

This does not infer an individual's behavior or turn a past event into a new
measurement. Observation ages and original provenance remain present.
"""
import copy,json
import state_contract as base


def scene(context):
    result=base.scene(context)
    now=context['state']['elapsed_minutes']
    events=copy.deepcopy(context['state']['recent_events'])
    latest={}
    for index,event in enumerate(events):
        when=event['elapsed_minutes']
        if not 0<=when<=now:raise ValueError('invalid_event_time')
        event['minutes_before_now']=now-when
        if event['kind'].endswith('_observation'):
            old=latest.get(event['kind'])
            if old is None or when>=events[old]['elapsed_minutes']:
                latest[event['kind']]=index
    active=set(latest.values())
    result.pop('earlier_event_history')
    result['latest_other_observations']={kind:events[index] for kind,index in latest.items() if kind!='companion_observation'}
    result['event_history']=[]
    for index,event in enumerate(events):
        if index in active:continue
        if event['kind'].endswith('_observation'):event['superseded_by_latest_observation']=True
        result['event_history'].append(event)
    result['observation_time_note']='latest는 제공된 기록 중 가장 최근이라는 뜻이며 새 관측이나 영구히 유효한 사실을 뜻하지 않는다. 각 관측의 경과 시간을 보존한다.'
    return result


def payload(context,model):
    body=base.payload(context,'scene_v1',model)
    data=json.loads(body['messages'][1]['content'])
    data['current_scene']=scene(context)
    body['messages'][1]['content']=json.dumps(data,ensure_ascii=False)
    body['messages'][0]['content']=body['messages'][0]['content'].replace('earlier_event_history는 과거 이력이며 latest_companion_observation이 현재 동행 관측이다.','event_history는 대체된 관측 및 동작 이력이다. latest_other_observations와 latest_companion_observation은 각 종류별 가장 최근에 제공된 관측이다. 기록 시각과 관측 유효성을 구분한다.')
    return body
