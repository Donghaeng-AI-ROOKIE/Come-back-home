"""Compact executable expressions with the structured channel and D4 safety checks.

Tests whether nested condition output is a source of loss. Not release qualified:
note-level accounting does not prove that every meaning in a note was retained.
"""
import json
from experiments.mind_contract_ab_20261007 import contracts as ab, contract_d4 as d4, contract_d8 as d8
from app.llm import mind_policy as m

RELEASE_QUALIFIED = False
VERSION = 'd12-compact-expressions-structured-thinking-20261008-research'
SAMPLING = dict(d4.SAMPLING, presence_penalty=0.0, repetition_penalty=1.0)
correction = d8.correction


def request(personal, model):
    body = ab.request_a(personal, model, thinking=True)
    body['messages'][0]['content'] += '\n' + d4.GLOSSARY + '''
condition에는 최종 실행 조건 전체를 쓴다. 종료 조건이 있다면 시작 조건 and not (종료 조건)으로 보존한다. 자정을 넘는 시각 구간은 clock_hour >= 시작 or clock_hour < 끝이며, 공통 조건은 괄호 밖에서 and로 연결한다.
대기 조건에 is_walking을 넣으면 멈추자마자 대기가 끝나므로 넣지 않는다. 시작 조건만 걷기인 휴식에는 is_walking을 보존한다. 관찰된 피로·통증에도 계속 걸은 반응은 walk로 표현할 수 있다. 조건이 없다는 이유로 행동이나 반대 행동을 창작하지 않는다.'''
    body.update(SAMPLING)
    body['response_format'] = {'type': 'json_schema', 'json_schema': {'schema': ab.schema_a(personal)}}
    return d8._bounded(body)


def meaningful(atom):
    if atom['fact'] == 'is_walking': return False
    if atom['fact'] in m.BOOLEAN_FACTS: return True
    if atom['op'] == 'gte' and atom['value'] <= 0: return False
    if atom['fact'] == 'clock_hour' and atom['op'] == 'lt' and atom['value'] >= 24: return False
    if atom['fact'] == 'clock_hour' and atom['op'] == 'lte' and atom['value'] >= 24: return False
    return True


def compile_d12(value, personal):
    policy = ab.compile_a(value, personal)
    for rule in policy.rules:
        for clause in rule.when:
            row = [a.model_dump() for a in clause]
            problem = d4.dead_branch(row)
            if problem: raise ValueError('unsatisfiable branch: ' + problem)
            if rule.action == 'wait' and d4._requires_walking(row):
                raise ValueError('waiting must remain active after walking stops')
            if not any(map(meaningful, row)) and not rule.place_labels:
                raise ValueError('branch has no specific trigger or place scope')
    return policy


def trait_accounting(value):
    # Explicitly record that this simpler contract cannot count per-sentence loss.
    return {'available': False, 'reason': 'note-level compact contract; sentence-level loss requires separate review'}
