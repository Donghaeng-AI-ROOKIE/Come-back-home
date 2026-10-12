"""Candidate B: final public evidence before the command, explicit uncertainty logic."""
import state_contract as base

SUFFIX='''
판단 유보와 기존 행동 유지를 구분한다. 알려진 개인 조건 C일 때 A, C가 아닐 때 B인데 C를 모르면 A 또는 B를 확정할 수 없다. 다른 확인된 근거만으로 같은 결론이 나오는 경우에는 불필요하게 유보하지 않는다.
‘혼자인지 확인되지 않음’은 ‘동행함이 확인됨’이 아니며, 그 반대도 성립하지 않는다. 개인 반응을 관찰하지 못했다는 답변이나 질문 자체는 어떤 행동을 지지하는 관찰이 아니다. 과거부터 하던 이동이 있다는 사실만으로 지금 계속하는 것이 개인 조건에 맞는다고 확정하지 않는다.
공개 설명에서 행동을 결정할 개인 근거가 부족하다고 판단했다면 next_command_id는 defer여야 한다. 설명에서 기존 목표 유지라고 했으면 새 목표 설정 명령을 선택하지 않는다. 확인된 개인 조건이 충분한 경우에는 그 조건에 해당하는 구체 행동을 고른다. 불확실성을 무조건 행동 정지나 현재 동작 유지로 바꾸지 않는다.
응답은 reason, source_ids, next_command_id의 순서로 완성한다. reason은 관련 개인 조건과 현재 관측이 연결되는 짧은 최종 근거이며 장문의 내부 사고 과정을 쓰지 않는다.
'''


def payload(context,model):
    body=base.payload(context,'scene_evidence_first_v2',model)
    body['messages'][0]['content']+=SUFFIX
    return body
