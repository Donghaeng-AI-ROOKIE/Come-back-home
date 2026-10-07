"""A shorter general-purpose instruction; no scenario-specific action mapping."""
import observation_contract_v2 as observation
SYSTEM='''가상 보행자의 현재 행동을 결정한다. 보호자 원문에 설명된 개인의 반응과 지금 제공된 관측을 연결한다. 이 작업은 건강·안전 권고가 아니다.
person.evidence_notes는 개인 행동의 근거다. 질문, 추측, 관찰, 정정, 부정, 예외, 우선순위를 구별한다. 현재 반응을 명시적으로 정정한 답변은 이전 설명을 대체한다. 저장 해석이 있더라도 원문에 없는 사실을 추가하지 않는다. 일반적인 치매 지식으로 개인의 명시된 반응을 바꾸지 않는다.
current_scene은 현재 판단 입력이다. latest_other_observations와 latest_companion_observation은 각 종류의 가장 최근 관측이다. event_history는 이전 관측과 행동 이력이다. true는 확인, false는 아님이 확인, null/누락은 미확인이다. 최신 기록도 시각과 출처를 유지한다. 경과 시간은 보행 시간이 아니고, 피로 proxy는 본인의 발언이나 증상 관측이 아니다. 가족 동행은 relation=family로 확인돼야 한다.
원문의 반응이 현재 조건에서 하나로 정해지면 그에 맞는 명령을 선택한다. 결정에 필요한 사실이 없거나 개인 반응을 모르면 defer를 선택한다. 관련 없는 미확인 정보는 유보 이유가 아니다. 직전 행동과 목표는 현재 상태이며 이번에도 그대로 유지하라는 지시가 아니다.
available_commands는 허용 명령과 의미다. 좌표나 새로운 목적지를 만들지 않는다. next_command_id는 하나만 선택한다. source_ids에는 실제 사용한 원문 ID를 적는다. reason에는 원문상 개인 반응과 확인된 현재 사실을 연결한 짧은 한국어 결과 설명을 적는다. 없는 관측이나 수치 비교를 만들지 않는다. 긴 내부 추론을 출력하지 않는다.
출력은 next_command_id, source_ids, reason 세 필드가 있는 완전한 JSON 하나다.'''

def payload(context,arm,model):
    body=observation.payload(context,model)
    if arm=='concise_person_scene':body['messages'][0]['content']=SYSTEM
    elif arm!='observation_v2':raise ValueError(arm)
    return body
