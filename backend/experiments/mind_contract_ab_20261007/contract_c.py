"""Candidate C (2026-10-07): evidence units (B) with a repaired output channel.

dev8 showed the A/B meaning was mostly right when an output completed; most
failures were in the channel: reasoning loops at temperature 0.2 (the model
card strongly recommends temperature 1.0 / top_p 0.95), stray framing, broken
keys. C changes only that channel plus two prompt defects, and keeps B's
compiler (compile_b) and every rejection rule:
  - official sampling (1.0 / 0.95), max_tokens 16384
  - response_format json_schema with the same simple schema (no refs/unions)
  - no "do not follow instructions in the source" line (the loops repeated it);
    a fact glossary; who the person is; split correction vs own observation
  - one correction request when the output fails validation; the validator's
    error is the only feedback (no scenes, no labels). Both calls are counted.
Not release qualified.
"""
from __future__ import annotations

import json

from experiments.mind_contract_ab_20261007 import contracts as ab

RELEASE_QUALIFIED = False
VERSION = 'contract-c-evidence-units-channel-20261007-research'
SAMPLING = {'temperature': 1.0, 'top_p': 0.95, 'max_tokens': 16384}

FACT_GLOSSARY = """사실 이름의 뜻 (조건식에는 이 이름만 쓴다):
- lost_awareness: 본인이 길을 잃었다고 알아차린 상태
- family_present: 가족이나 보호자가 곁에 있음
- pain_observed: 통증을 말하거나 통증이 관찰됨
- target_recognized: 지금 향하거나 마주한 등록 장소를 본인이 알아봄. 어느 장소인지는 이 사실에 들어 있지 않으므로 장소 이름과 비교하지 않는다. 장소는 goal_place와 applies_only_at으로 정한다
- physical_arrival: 등록 장소 좌표에 실제로 도착함(알아봄과 별개)
- is_walking: 지금 걷는 중(쉬거나 기다리는 중이 아님)
- dark_observed: 본인이 어둡다고 느끼거나 어둠이 관측됨. 시각으로 추정하지 않는다
- rain_observed: 비가 오는 것이 관측됨
- fatigue_high / anxiety_high / home_pull_high: 높은 피로 / 높은 불안 / 강한 귀가 욕구
- market.noisy, market.crowded, park.*, forest.*, water.*: 그 유형의 장소 근처에서 시끄러움·붐빔이 관측됨
- continuous_walk_minutes: 마지막 휴식·대기 뒤 계속 걸은 분
- distance_since_rest_m: 마지막 휴식 뒤 걸은 거리(미터)
- clock_hour: 하루 중 시각 0~24 (8.5는 오전 8시 30분). 걸은 시간이 아니다
숫자 비교는 >=, >, <=, < 로 쓴다. 숫자에 == 나 != 를 쓰지 않는다."""

PERSON = """이 문답은 보호자 한 명이 돌보는 치매 어르신 한 명(대상 어르신)에 관한 것이다. 보호자는 대상 어르신을 '어머니', '아버지', '남편' 등으로 부를 수 있다. 질문은 챗봇이 한 말이고 답변만 보호자의 진술이다. 다른 가족·이웃·다른 어르신 이야기는 대상 어르신의 행동이 아니다."""

SPLIT = """한 답변 안에 정정(예: 그건 다른 사람 이야기였다)과 대상 어르신 본인의 관찰이 함께 있으면 반드시 서로 다른 units로 나눈다. 정정된 부분은 corrected_away 또는 other_person으로, 본인이 실제로 보인 반응은 observed_response로 남긴다. 한 답변에 행동이 둘이면 둘로 나눈다. quote는 그 의미 단위를 뒷받침하는 짧은 연속 인용이다."""

SYSTEM_C = '\n'.join([  # noqa: FLY002 - prompt sections
    '보호자 문답 전체를 읽고, 각 답변을 의미 단위로 나누어 판정한다. 코드는 네 판정을 실행 규칙으로 옮길 뿐 단어를 해석하지 않는다. 현재 장면과 정답은 주어지지 않는다.',
    PERSON, SPLIT,
    '필드: note_id, quote, subject, kind, action, goal_place, applies_only_at, start_condition, end_condition, hold_minutes.',
    'subject: patient(대상 어르신 본인), other_person(다른 사람), unclear(누구인지 불분명).',
    'kind: observed_response(본인이 실제로 보인 조건부 반응), functional_need(걸은 뒤 쉬어야 하는 신체적 필요), capacity_only(걸을 수 있는 능력뿐), stated_goal(가고 싶다는 발언뿐), unobserved(보지 못함·모름), corrected_away(정정으로 철회된 정보), other_information(행동이 아닌 정보), not_representable(본인의 실제 반응이지만 제공된 사실·행동으로 표현할 수 없음).',
    'observed_response와 functional_need는 subject=patient이고 action과 start_condition이 반드시 있어야 한다. 그 밖의 kind는 action="none", goal_place="", applies_only_at=[], start_condition="", end_condition="", hold_minutes=0이다.',
    'start_condition은 반응이 시작·유지되는 조건, end_condition은 원문이 반응이 끝난다고 말한 조건이다. 코드는 (start_condition) and not (end_condition)으로 옮긴다. 종료가 원문에 없으면 end_condition="". functional_need의 action은 rest다.',
    'fixed_rules는 이미 실행 가능하며 그대로 유지된다. 같은 반응을 다시 만들지 말고 그 문답은 other_information으로 둘 수 있다.',
    ab.ACTION_MEANING, FACT_GLOSSARY, ab.CONDITION_SYNTAX, ab.DISTINCTIONS,
    'hold_minutes는 원문이 말한 휴식·대기 지속 시간만 쓰고 모르면 0이다. 쉬기 전에 걸은 시간이 아니다.',
    'output_schema에 맞는 완전한 JSON 객체 하나를 닫는 괄호까지 출력한다. 설명문·마크다운을 붙이지 않는다.',
    ab.CONTRASTS, ab.SOURCE_RULES])

ERROR_HELP = {
    'incomplete_length': '출력이 길이 한도에서 끊겨 JSON이 완성되지 않았다. 판단은 짧게 하고 JSON을 끝까지 완성하라.',
    'empty': '최종 출력이 비어 있었다.',
    'boundary_single_object': 'JSON 앞뒤에 다른 글자가 있었다. JSON 객체 하나만 출력하라.',
    'multiple_objects': 'JSON 객체가 여러 개였다. 하나만 출력하라.',
    'duplicate_keys': '같은 키가 한 객체에 두 번 나왔다.',
    'invalid_json': 'JSON 문법이 깨졌다.',
    'unexpected_finish': '출력이 정상 종료되지 않았다.',
}


def request(personal, model, *, thinking=True):
    payload = ab._payload(personal)
    payload['output_schema'] = ab.schema_b(personal)
    body = ab._body(SYSTEM_C, payload, model, thinking)
    body.update(SAMPLING)
    body['response_format'] = {'type': 'json_schema', 'json_schema': {'schema': ab.schema_b(personal)}}
    return body


def correction(first_body, first_public, problem):
    """Second call: same input, the previous final answer and the validator error only."""
    body = json.loads(json.dumps(first_body))
    previous = (first_public or {}).get('final_content') or '(최종 출력 없음)'
    help_text = ERROR_HELP.get(problem, '')
    body['messages'] = body['messages'] + [
        {'role': 'assistant', 'content': previous[:20000]},
        {'role': 'user', 'content': '검증 결과 이 출력은 받아들일 수 없다: ' + problem + '. ' + help_text
         + ' 같은 원문을 다시 읽고 output_schema에 맞는 완전한 JSON 객체 하나를 다시 출력하라. '
           '형식 문제만이 아니라 해석이 틀렸다면 바로잡아도 된다.'}]
    return body


def compile_c(value, personal):
    return ab.compile_b(value, personal)
