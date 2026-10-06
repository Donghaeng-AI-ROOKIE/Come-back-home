"""Candidate D (2026-10-07): no free text in the model's structured answer.

c_dev8 (temperature 1.0) removed reasoning loops but the model rewrote quotes
(words dropped, 이백팔십 -> 이백오십) and corrupted condition strings
('is_walking (...' with no operator, '거리_since_rest_m'). D removes every
free-text field the compiler depends on:
  - evidence: code splits each answer into sentences at sentence-final
    punctuation (no word interpretation) and the model cites sentence IDs from
    a schema enum; every sentence must be cited by at least one unit
  - conditions: a disjunction of clauses, each clause = facts that must be
    true, facts that must be false, numeric comparisons; fact names and
    operators are schema enums. Code renders the clauses to the existing
    whitelist expression and compiles it with the same AST compiler.
  - a behavior whose condition uses no fact other than is_walking is rejected
    (it would fire on every step)
Everything else follows C (official sampling, response_format, one
validator-feedback correction). Not release qualified.
"""
from __future__ import annotations

import re

from pydantic import Field, StrictFloat, StrictInt

from app.llm import mind_policy as m
from app.llm.initial_behavior import _validate_shape
from experiments.mind_contract_ab_20261007 import contract_c as c
from experiments.mind_contract_ab_20261007 import contracts as ab
from experiments.mind_policy_candidates.condition_program import expression, fixed

RELEASE_QUALIFIED = False
VERSION = 'contract-d-sentence-ids-structured-conditions-20261007-research'
SAMPLING = dict(c.SAMPLING)
BOOL = [f for f in m.BOOLEAN_FACTS]
NUM = list(m.NUMERIC_FACTS)
OPS = {'>=': '>=', '>': '>', '<=': '<=', '<': '<'}
SENTENCE_END = re.compile(r'(?<=[.?!。])\s+')


def sentences(personal):
    """Deterministic sentence split of each answer; IDs like N1.s2."""
    out = []
    for n in personal['notes']:
        answer = n['text'].split('\n답변: ', 1)[-1].strip()
        parts = [p.strip() for p in SENTENCE_END.split(answer) if p.strip()]
        for k, text in enumerate(parts or [answer], 1):
            out.append({'id': f"{n['id']}.s{k}", 'note_id': n['id'], 'text': text})
    return out


def _clause_schema():
    return ab._obj({'true': {'type': 'array', 'items': {'type': 'string', 'enum': BOOL}},
                    'false': {'type': 'array', 'items': {'type': 'string', 'enum': BOOL}},
                    'numbers': {'type': 'array', 'items': ab._obj({
                        'fact': {'type': 'string', 'enum': NUM},
                        'op': {'type': 'string', 'enum': list(OPS)},
                        'value': {'type': 'number'}})}})


def schema(personal):
    labels = ab._labels(personal)
    condition = {'type': 'array', 'items': _clause_schema()}
    unit = ab._obj({'sentence_ids': {'type': 'array', 'items': {'type': 'string', 'enum': [s['id'] for s in sentences(personal)]}},
                    'subject': {'type': 'string', 'enum': list(ab.SUBJECTS)},
                    'kind': {'type': 'string', 'enum': list(ab.BEHAVIOR_KINDS + ab.OTHER_KINDS)},
                    'action': {'type': 'string', 'enum': ['none'] + list(ab.ACTIONS)},
                    'goal_place': {'type': 'string', 'enum': [''] + labels},
                    'applies_only_at': {'type': 'array', 'items': {'type': 'string', 'enum': labels}},
                    'start_when_any': condition,
                    'end_when_any': condition,
                    'hold_minutes': {'type': 'number'}})
    return ab._obj({'units': {'type': 'array', 'items': unit}})


CONDITION_FORMAT = """조건은 문자열이 아니라 구조로 쓴다. start_when_any는 '이 중 하나라도 성립하면 시작'인 분기 목록이고, 각 분기는 true(모두 참이어야 할 사실), false(모두 거짓이어야 할 사실), numbers(모두 만족해야 할 숫자 비교)를 함께 만족해야 성립한다.
예: 걷는 중에 연속 8분 또는 450미터에 도달하면 → [{"true":["is_walking"],"false":[],"numbers":[{"fact":"continuous_walk_minutes","op":">=","value":8}]}, {"true":["is_walking"],"false":[],"numbers":[{"fact":"distance_since_rest_m","op":">=","value":450}]}]
예: 길을 잃었다고 알아차렸고 가족이 곁에 없을 때 → [{"true":["lost_awareness"],"false":["family_present"],"numbers":[]}]
예: 오전 8시부터 9시 전까지 → [{"true":[],"false":[],"numbers":[{"fact":"clock_hour","op":">=","value":8},{"fact":"clock_hour","op":"<","value":9}]}]
end_when_any는 원문이 '그러면 끝났다'고 말한 종료 조건이며 같은 형식이다. 종료가 원문에 없으면 []. 코드는 (시작 조건) 그리고 (종료 조건이 아님)으로 옮긴다. 숫자는 원문의 수를 아라비아 숫자로 정확히 옮긴다(예: 이백팔십 → 280)."""

SYSTEM_D = '\n'.join([  # noqa: FLY002 - prompt sections
    '보호자 문답을 읽고, 답변의 문장들을 의미 단위로 묶어 판정한다. 코드는 네 판정을 실행 규칙으로 옮길 뿐 단어를 해석하지 않는다. 현재 장면과 정답은 주어지지 않는다.',
    c.PERSON,
    'answer_sentences는 각 답변을 문장으로 나눈 것이다. 각 unit은 근거 문장의 sentence_ids를 적는다. 모든 문장은 적어도 하나의 unit에 들어가야 한다. 정정 문장과 대상 어르신 본인의 관찰 문장은 서로 다른 unit이다. 한 문장에 행동이 둘이면 unit을 둘로 만들고 같은 문장을 함께 인용한다.',
    'subject: patient(대상 어르신 본인), other_person(다른 사람), unclear(누구인지 불분명).',
    'kind: observed_response(본인이 실제로 보인 조건부 반응), functional_need(걸은 뒤 쉬어야 하는 신체적 필요), capacity_only(걸을 수 있는 능력뿐), stated_goal(가고 싶다는 발언뿐), unobserved(보지 못함·모름), corrected_away(정정으로 철회된 정보), other_information(행동이 아닌 정보), not_representable(본인의 실제 반응이지만 제공된 사실·행동으로 표현할 수 없음).',
    'observed_response와 functional_need는 subject=patient이고 action과 start_when_any가 반드시 있어야 한다. 그 밖의 kind는 action="none", goal_place="", applies_only_at=[], start_when_any=[], end_when_any=[], hold_minutes=0이다. functional_need의 action은 rest다. 행동의 조건에는 is_walking 말고도 그 반응을 일으키는 사실이 하나 이상 있어야 한다.',
    CONDITION_FORMAT,
    'fixed_rules는 이미 실행 가능하며 그대로 유지된다. 같은 반응을 다시 만들지 말고 그 문장은 other_information으로 둘 수 있다.',
    ab.ACTION_MEANING, c.FACT_GLOSSARY.split('숫자 비교는')[0].strip(), ab.DISTINCTIONS,
    'hold_minutes는 원문이 말한 휴식·대기 지속 시간만 쓰고 모르면 0이다. 쉬기 전에 걸은 시간이 아니다.',
    'output_schema에 맞는 완전한 JSON 객체 하나를 닫는 괄호까지 출력한다. 설명문·마크다운을 붙이지 않는다.',
    ab.CONTRASTS, ab.SOURCE_RULES])


def request(personal, model, *, thinking=True):
    payload = ab._payload(personal)
    payload['answer_sentences'] = [{'id': s['id'], 'text': s['text']} for s in sentences(personal)]
    payload['output_schema'] = schema(personal)
    body = ab._body(SYSTEM_D, payload, model, thinking)
    body.update(SAMPLING)
    body['response_format'] = {'type': 'json_schema', 'json_schema': {'schema': schema(personal)}}
    return body


correction = c.correction


class Number(m.Strict):
    fact: str
    op: str
    value: StrictFloat | StrictInt


class Clause(m.Strict):
    true: list[str] = Field(max_length=8)
    false: list[str] = Field(max_length=8)
    numbers: list[Number] = Field(max_length=8)


class UnitD(m.Strict):
    sentence_ids: list[str] = Field(min_length=1, max_length=8)
    subject: str
    kind: str
    action: str
    goal_place: str
    applies_only_at: list[str] = Field(max_length=6)
    start_when_any: list[Clause] = Field(max_length=6)
    end_when_any: list[Clause] = Field(max_length=6)
    hold_minutes: StrictFloat | StrictInt = Field(ge=0, le=360)


class OutputD(m.Strict):
    units: list[UnitD] = Field(min_length=1, max_length=32)


def render(clauses):
    """Typed clauses -> the whitelist expression consumed by the AST compiler."""
    parts = []
    for cl in clauses:
        atoms = ([f for f in cl.true] + ['not ' + f for f in cl.false]
                 + [f'{n.fact} {OPS[n.op]} {n.value!r}' for n in cl.numbers])
        if not atoms:
            raise ValueError('empty_condition_clause')
        parts.append('(' + ' and '.join(atoms) + ')')
    return ' or '.join(parts)


def compile_d(value, personal):
    _validate_shape(value, schema(personal))
    parsed = OutputD.model_validate(value)
    by_id = {s['id']: s for s in sentences(personal)}
    ready = fixed(personal)
    rules, unrepresented = [r.model_dump() for r in ready], []
    cited = set()
    for i, u in enumerate(parsed.units):
        if len(set(u.sentence_ids)) != len(u.sentence_ids):
            raise ValueError('duplicate_sentence_id_in_unit')
        cited.update(u.sentence_ids)
        notes = sorted({by_id[s]['note_id'] for s in u.sentence_ids})
        if u.kind not in ab.BEHAVIOR_KINDS:
            if (u.action != 'none' or u.goal_place or u.applies_only_at or u.start_when_any
                    or u.end_when_any or u.hold_minutes):
                raise ValueError('non_behavior_unit_with_action')
            unrepresented.extend({'note_id': n, 'reason': u.kind + '/' + u.subject} for n in notes)
            continue
        if u.subject != 'patient':
            raise ValueError('behavior_unit_not_about_patient')
        if u.action == 'none':
            raise ValueError('behavior_unit_without_action')
        if not u.start_when_any:
            raise ValueError('behavior_unit_without_condition')
        if u.kind == 'functional_need' and u.action != 'rest':
            raise ValueError('functional_need_not_rest')
        used = {f for cl in u.start_when_any for f in cl.true + cl.false} | {
            n.fact for cl in u.start_when_any for n in cl.numbers}
        if not used - {'is_walking'}:
            raise ValueError('degenerate_condition_only_is_walking')
        start = render(u.start_when_any)
        text = f'({start}) and not ({render(u.end_when_any)})' if u.end_when_any else start
        when = expression(text)
        action, goal, feature = ab._bind(u.action, u.goal_place, u.applies_only_at, personal)
        ab._guard_walking_rest(action, when)
        # One entry per cited sentence: each sentence is a verbatim span of its answer.
        evidence = [{'note_id': by_id[s]['note_id'], 'quote': by_id[s]['text']} for s in u.sentence_ids]
        rules.append({'id': f'd_{i}', 'action': action, 'when': when, 'goal_label': goal,
                      'feature': feature, 'place_labels': u.applies_only_at,
                      'hold_minutes': u.hold_minutes or None, 'supersedes': [],
                      'evidence': evidence[:5]})
    missing = set(by_id) - cited
    covered_by_fixed = {e.note_id for r in ready for e in r.evidence}
    missing = {s for s in missing if by_id[s]['note_id'] not in covered_by_fixed}
    if missing:
        raise ValueError('sentence_not_classified:' + ','.join(sorted(missing)))
    return m.validate({'rules': rules, 'unrepresented': unrepresented}, personal)
