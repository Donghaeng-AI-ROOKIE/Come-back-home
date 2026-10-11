"""Only add the missing explicit final-JSON instruction; no other candidate edits."""
import branch_contract_v2 as previous
JSON_INSTRUCTION='''\n최종 응답은 모든 가정 분기 키를 빠짐없이 포함한 유효하고 완전한 JSON 객체 단 한 개로 출력한다. 각 분기 값에는 next_command_id, source_ids, reason을 모두 포함한다. JSON 객체 바깥에 설명이나 마크다운을 출력하지 않는다. 불필요한 공백·줄바꿈을 반복하지 말고 모든 분기와 최상위 객체의 닫는 중괄호까지 완성한 후 종료한다.'''
def payload(context,arm,model):
    assert arm=='branch_json_completion_v3'
    body=previous.payload(context,'branch_explicit_facts_v2',model)
    body['messages'][0]['content']+=JSON_INSTRUCTION
    return body
validate=previous.validate
attach_original_sources=previous.attach_original_sources
