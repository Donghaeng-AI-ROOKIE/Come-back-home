"""Separate locomotion from remembered goal; no guardian text action parser."""
import json
import contrast_candidate
import epistemic_candidate
import unique_command_contract

RULES = '''
행동과 목표 기억은 별개다. next_command_id는 지금 실행할 행동을 선택한다. 목적지를 기억한다는 이유만으로 continue를 고르지 않는다. rest·stay·avoid는 모두 기존 목표를 기억하면서 지금의 동작을 바꾸는 명령이다.
continue는 이전 이동 방식을 계속 실행하는 명령이다. 이전 이동 방식이 seek인 경우에만 같은 목표를 향한 이동 지속을 뜻한다. seek는 다른 목적지로 변경하거나 멈춤·다른 이동 방식에서 목적지를 향해 출발하는 명령이다.
관측은 true=그 조건이 성립함을 확인, false=그 조건이 성립하지 않음을 확인, null=어느 쪽인지 미확인이다. false 자체는 미확인이 아니다. 개인 원문의 조건을 현재 관측에 대입한다. A와 B는 둘 다 true일 때 성립하고, 어느 하나 false면 불성립이다. A 또는 B는 어느 하나 true면 성립하고, 둘 다 false면 불성립이다. 나머지는 미확인이다.
미확인인 관련 조건을 참과 거짓으로 각각 놓았을 때 개인의 행동이 다르면 defer다. 모든 가능한 경우에서 행동이 같으면 그 행동을 선택한다. 관련 없는 관측의 null은 무시한다. 이 가정은 실제 관측을 새로 만들거나 확률을 부여하는 것이 아니다.
defer는 해석의 유보이지 환자가 쉬거나 기다린다는 행동이 아니다. reason은 확인된 조건 또는 필요한 미확인 조건과 선택한 현재 동작을 연결한 한국어 결과 설명 1~2문장, 200자 이내다. JSON 이외의 글과 내부 추론을 쓰지 않는다.
'''

def payload(context, arm, model):
    if arm != 'separate_motion_and_goal':
        raise ValueError(arm)
    body = epistemic_candidate.payload(context, 'explicit_knowledge_state', model)
    # Rebuild the system so the old "goal kept => continue" shortcut is absent.
    body['messages'][0]['content'] = contrast_candidate.SYSTEM + RULES
    data = json.loads(body['messages'][1]['content'])
    commands = unique_command_contract.options(context)
    menu = []
    for command_id, command in commands.items():
        if command_id == 'defer':
            motion = '행동을 확정하지 않음. 환자의 대기·정지와 다름'
        elif command_id == 'continue':
            motion = '기존 이동 방식 그대로 실행: ' + str(context.get('execution', {}).get('previous_travel_action'))
        elif command_id == 'rest':
            motion = '지금 이동을 멈추고 휴식'
        elif command_id == 'stay':
            motion = '지금 제자리에 머물러 대기'
        elif command_id == 'roam':
            motion = '기존 목적지 없이 걷기'
        elif command_id.startswith('seek_'):
            motion = '등록된 목적지를 향해 이동 시작·재개·변경'
        elif command_id.startswith('avoid_'):
            motion = '명시된 환경을 피하는 방향으로 이동'
        else:
            raise ValueError('unknown motion')
        menu.append(dict(next_command_id=command_id, current_motion=motion,
                         **command))
    data['available_commands'] = menu
    data['goal_operation_semantics'] = {
        'keep': '기존 목적지 기억 보존. 해당 목적지로 지금 걷는다는 뜻은 아님',
        'set': '등록된 goal_label로 목적지 설정',
        'clear': '기존 목적지 기억 해제',
        'null': '해석 유보, 실행 동작 미결정',
    }
    body['messages'][1]['content'] = json.dumps(data, ensure_ascii=False)
    return body

validate = unique_command_contract.validate
