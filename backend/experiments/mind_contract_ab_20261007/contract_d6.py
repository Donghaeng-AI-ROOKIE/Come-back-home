"""Prepared, untested candidate: retain D3/D4 output, improve source context.

D5 dev8 already produced two unusable final outputs, so its 58/64 stage gate
cannot be reached. The extra per-sentence role labels introduced conflicts
between a declared behavior and its source metadata. D6 removes that extra
output task. It does NOT turn an invalid D5 output into an accepted response.
It keeps D4's schema/compiler, supplies full question context, and asks for
condition preservation before producing a new output. No quality claim yet.
"""
from experiments.mind_contract_ab_20261007 import contracts as ab, contract_d3 as d3, contract_d4 as d4, contract_d5 as d5

RELEASE_QUALIFIED = False
VERSION = 'contract-d6-context-without-role-matrix-20261007-research'
SAMPLING = dict(d4.SAMPLING)
schema = d4.schema
compile_d6 = d4.compile_d4
correction = d4.correction
trait_accounting = d4.trait_accounting

OLD_QUESTION = ("text가 '질문: …/답변: …' 형식이면 질문은 챗봇이 한 말이고 보호자 진술이 아니다. "
                "답변만 보호자 진술이며, 짧은 답은 그 질문의 맥락으로 해석한다.")
assert d4.SYSTEM_D4.count(OLD_QUESTION) == 1
SYSTEM_D6 = d4.SYSTEM_D4.replace(OLD_QUESTION, d5.QUESTION_CONTEXT).replace(
    'answer_sentences는 각 답변을 문장으로 나눈 것이다. 출력은 두 목록이다.',
    'answers_by_turn은 질문과 그 질문에 대한 답변 문장을 한 묶음으로 준다. '
    'chatbot_question은 실제 주어진 질문이며 answer_sentences는 답변 문장과 인용 ID다. 출력은 두 목록이다.').replace(
    '- rest: 보행을 멈추고 앉아서 쉰다. 신체 회복이다.',
    '- rest: 앉아서 쉰다. 신체 회복이다. 걷다가 쉬는지 기다리다가 쉬는지는 원문의 조건으로 구분한다.')
SYSTEM_D6 += '\n' + d5.CONDITION_PRINCIPLES + '''
조건 보존 확인:
- 행동의 주인, 시작 조건, 종료 조건, 장소 한정, 시간·거리·지속시간을 원문과 각각 대조한다. 출력 필드를 새로 만들지는 않는다.
- 필요한 조건 하나를 빼거나 뒤집었을 때에도 원문이 그 행동을 뒷받침하는지 확인한다. 뒷받침하지 않는다면 그 조건을 빠뜨리지 않는다. 관찰되지 않은 상태를 채우지는 않는다.
- 장소에 실제 도착하는 일과 그 장소를 알아보는 일은 다르다. 원문이 두 가지를 모두 말하면 두 조건 모두 필요하다.
- 보호자가 관찰한 특정 장소의 반응을 다른 장소나 같은 유형 전체로 넓히지 않는다. 장소와 무관하다는 직접 진술이 있을 때만 넓힌다.
- 같은 반응을 여러 문장이 한정하면 sentence_ids에 함께 넣는다. 행동 관찰이 없다는 문장은 억지로 행동에 인용하지 않고 other_sentences에 unobserved로 남긴다.
- 신체 한계와 현재 통증 관찰은 다르다. 무릎 병력이 이유로 언급됐다는 이유만으로 pain_observed를 새 발동 조건으로 추가하지 않는다.
- 시간대와 지속 시간을 바꾸지 않는다. 시각 범위에서만 기다린다는 말은 clock_hour 조건이며, 그 차이를 hold_minutes로 계산해서 추가하지 않는다.
'''


def request(personal, model, *, thinking=True):
    payload = ab._payload(personal)
    payload['answers_by_turn'] = d5.turns(personal)
    payload['output_schema'] = schema(personal)
    body = ab._body(SYSTEM_D6, payload, model, thinking)
    body.update(SAMPLING)
    body['response_format'] = {'type': 'json_schema', 'json_schema': {'schema': schema(personal)}}
    return body
