"""Typed scene presentation, without guardian word-to-action rules."""
import copy, json, sys
from pathlib import Path

OLD = Path(__file__).resolve().parent.parent/'MIND_condition_alignment_20260929'
sys.path.insert(0,str(OLD))
import next_action_followup as original


def scene(context):
    state = copy.deepcopy(context['state'])
    now = state['elapsed_minutes']
    history = state.pop('recent_events')
    companion = None
    latest_index = None
    for index,event in enumerate(history):
        when = event['elapsed_minutes']
        if not 0 <= when <= now:
            raise ValueError('invalid_event_time')
        event['minutes_before_now'] = now-when
        if event['kind']=='companion_observation' and (companion is None or when >= companion['elapsed_minutes']):
            companion = event
            latest_index = index
    earlier = [e for i,e in enumerate(history) if i != latest_index]
    for event in earlier:
        if event['kind']=='companion_observation':
            event['superseded_by_latest_observation'] = True
    if companion is None:
        companion = dict(value=None,relation='unknown',provenance='no_observation_provided')
    else:
        companion = copy.deepcopy(companion)
        companion.setdefault('relation','unknown')
        if companion.get('value') is not None and type(companion['value']) is not bool:
            raise ValueError('invalid_companion_value')
        if companion.get('relation') not in ('family','non_family','unknown','none'):
            raise ValueError('invalid_companion_relation')
        if companion.get('value') is False and companion['relation'] not in ('none','unknown'):
            raise ValueError('conflicting_companion_observation')
        if companion.get('value') is not True and companion['relation'] in ('family','non_family'):
            raise ValueError('relation_without_present_companion')
    rest = state['last_rest_end_minutes']
    if rest is not None and not 0<=rest<=now:
        raise ValueError('invalid_rest_time')
    state['minutes_since_rest_end'] = None if rest is None else now-rest
    state['fatigue_band'] = 'high' if state['fatigue']>=.7 else 'medium' if state['fatigue']>=.4 else 'low'
    state['fatigue_scale_provenance'] = 'existing_engine_proxy_not_clinical_measurement'
    return dict(clock_time=context['clock_time'],trigger=context['trigger'],
        state=state,latest_companion_observation=companion,earlier_event_history=earlier,
        environment=copy.deepcopy(context['environment']),execution=copy.deepcopy(context['execution']),
        known_places=copy.deepcopy(context['known_places']))


def payload(context,arm,model):
    body = original.payload(context,'next_source_ids',model)
    body['max_tokens'] = 12000
    if arm=='baseline':
        return body
    if arm not in ('scene_v1','scene_evidence_first_v2'):
        raise ValueError('unknown_arm')
    option_list = original.render(context)['가능한_다음명령']
    body['messages'][1]['content'] = json.dumps(dict(
        person=copy.deepcopy(context['person']),research=copy.deepcopy(context['research']),
        current_scene=scene(context),available_commands=option_list),ensure_ascii=False)
    body['messages'][0]['content'] += '''\n입력의 current_scene은 지금 판단할 한 상황이다. earlier_event_history는 과거 이력이며 latest_companion_observation이 현재 동행 관측이다. value는 동행 여부, relation은 관계다. family만 가족으로 확인된 것이며 unknown 관계를 가족으로 추정하지 않는다. null은 미확인이고 false와 다르다. 환경의 provenance와 관측값을 유지한다. 현재 장면의 값과 원문의 조건을 연결한다. 충분한 개인 근거가 있을 때만 등록 장소 목록의 다른 목적지로 변경한다. 최종 응답은 모든 필드를 포함한 완전한 JSON 객체 하나로 끝까지 출력한다.'''
    if arm=='scene_evidence_first_v2':
        props=body['response_format']['json_schema']['schema']['properties']
        body['response_format']['json_schema']['schema']['properties']={k:props[k] for k in ('reason','source_ids','next_command_id')}
        body['messages'][0]['content'] += '\n공개 설명 reason을 먼저 간결하게 적고, 그 설명에 해당하는 명령 하나를 next_command_id로 선택한다. 설명은 원문 조건과 현재 사실을 잇는 짧은 결과 근거이며 긴 내부 추론은 출력하지 않는다.'
    return body


def validate(value,context):
    if not isinstance(value,dict) or not isinstance(value.get('reason'),str) or not 1<=len(value['reason'])<=400:
        raise ValueError('reason')
    return original.validate(value,context,'next_source_ids')


def matches(decision,row):
    triple=[decision['action'],decision['goal_label'],decision['avoid_feature']]
    if decision['status']=='insufficient_information':
        return bool(row['rubric']['abstention_allowed']) and triple==[None,None,None]
    return triple in row['rubric']['allowed_action_goal_feature'] and triple!=[None,None,None]
