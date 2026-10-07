"""Candidate D3 (2026-10-07): D2 with the answer split into two lists.

d_dev8 (56/64) showed two remaining channel failures: non-behavior units
carried an empty condition clause ({"true":[],"false":[],"numbers":[]}) that
the compiler rightly rejected, and units/sentences went missing. D3 removes
the fields that invite them:
  behaviors        the person's own conditional responses / functional needs
                   only; no subject field (always the person), action and
                   start conditions required
  other_sentences  every remaining sentence with subject and kind only; no
                   action or condition fields exist, so none can be filled
Every sentence must appear in one of the two lists. D2's neutral examples,
trait accounting (hearsay_or_general, not_representable = trait loss), the
five-sentence evidence limit, structured conditions, sampling, schema
enforcement and the one validator-feedback correction are unchanged.
Not release qualified.
"""
from __future__ import annotations

from pydantic import Field, StrictFloat, StrictInt

from app.llm import mind_policy as m
from app.llm.initial_behavior import _validate_shape
from experiments.mind_contract_ab_20261007 import contract_c as c
from experiments.mind_contract_ab_20261007 import contract_d as d
from experiments.mind_contract_ab_20261007 import contract_d2 as d2
from experiments.mind_contract_ab_20261007 import contracts as ab
from experiments.mind_policy_candidates.condition_program import expression, fixed

RELEASE_QUALIFIED = False
VERSION = 'contract-d3-split-behaviors-others-20261007-research'
SAMPLING = dict(d2.SAMPLING)
MAX_SENTENCES = d2.MAX_SENTENCES
BEHAVIOR_KINDS = ab.BEHAVIOR_KINDS
OTHER_KINDS = ('capacity_only', 'stated_goal', 'unobserved', 'corrected_away',
               'hearsay_or_general', 'other_information', 'not_representable')
KINDS = BEHAVIOR_KINDS + OTHER_KINDS
sentences = d.sentences


def schema(personal):
    labels = ab._labels(personal)
    ids = {'type': 'array', 'items': {'type': 'string', 'enum': [s['id'] for s in sentences(personal)]}}
    condition = {'type': 'array', 'items': d._clause_schema()}
    behavior = ab._obj({'sentence_ids': ids,
                        'kind': {'type': 'string', 'enum': list(BEHAVIOR_KINDS)},
                        'action': {'type': 'string', 'enum': list(ab.ACTIONS)},
                        'goal_place': {'type': 'string', 'enum': [''] + labels},
                        'applies_only_at': {'type': 'array', 'items': {'type': 'string', 'enum': labels}},
                        'start_when_any': condition,
                        'end_when_any': condition,
                        'hold_minutes': {'type': 'number'}})
    other = ab._obj({'sentence_ids': ids,
                     'subject': {'type': 'string', 'enum': list(ab.SUBJECTS)},
                     'kind': {'type': 'string', 'enum': list(OTHER_KINDS)}})
    return ab._obj({'behaviors': {'type': 'array', 'items': behavior},
                    'other_sentences': {'type': 'array', 'items': other}})


SYSTEM_D3 = '\n'.join([  # noqa: FLY002 - prompt sections
    '보호자 문답을 읽고 답변의 문장들을 판정한다. 코드는 네 판정을 실행 규칙으로 옮길 뿐 단어를 해석하지 않는다. 현재 장면과 정답은 주어지지 않는다.',
    c.PERSON,
    'answer_sentences는 각 답변을 문장으로 나눈 것이다. 출력은 두 목록이다.',
    'behaviors: 대상 어르신 본인이 실제로 보인 조건부 반응(kind=observed_response)과 걸은 뒤 쉬어야 하는 신체적 필요(kind=functional_need)만 넣는다. 각 항목은 근거 문장 1~5개, action, goal_place, applies_only_at, start_when_any(반드시 한 분기 이상), end_when_any, hold_minutes를 적는다. functional_need의 action은 rest다. 조건에는 is_walking 말고도 그 반응을 일으키는 사실이 하나 이상 있어야 한다. 한 문장에 행동이 둘이면 항목을 둘로 만들고 같은 문장을 함께 인용한다.',
    'other_sentences: behaviors의 근거가 아닌 나머지 문장을 빠짐없이 넣는다. 각 항목은 문장 ID 1~5개, subject(patient=대상 어르신 본인, other_person=다른 사람, unclear=불분명), kind를 적는다. kind: capacity_only(걸을 수 있는 능력뿐), stated_goal(가고 싶다는 발언뿐), unobserved(보지 못함·모름), corrected_away(정정으로 철회된 정보), hearsay_or_general(보호자의 짐작·일반론·남에게 들은 말), other_information(행동이 아닌 정보), not_representable(본인이 실제로 보인 반응이지만 제공된 사실·행동으로 나타낼 수 없음).',
    '모든 문장은 behaviors나 other_sentences 중 적어도 한 곳에 나와야 한다. 등록 장소 설명 같은 문장도 other_sentences에 넣는다. 정정된 다른 사람 이야기와 본인의 관찰은 서로 다른 항목이다.',
    d2.CONDITION_FORMAT,
    'fixed_rules는 이미 실행 가능하며 그대로 유지된다. 같은 반응을 behaviors에 다시 만들지 말고 그 문장은 other_sentences(other_information)에 둘 수 있다.',
    ab.ACTION_MEANING, d2.GLOSSARY, ab.DISTINCTIONS,
    'hold_minutes는 원문이 말한 휴식·대기 지속 시간만 쓰고 모르면 0이다. 쉬기 전에 걸은 시간이 아니다.',
    'output_schema에 맞는 완전한 JSON 객체 하나를 닫는 괄호까지 출력한다. 설명문·마크다운을 붙이지 않는다.',
    d2.CONTRASTS, ab.SOURCE_RULES])


def request(personal, model, *, thinking=True):
    payload = ab._payload(personal)
    payload['answer_sentences'] = [{'id': s['id'], 'text': s['text']} for s in sentences(personal)]
    payload['output_schema'] = schema(personal)
    body = ab._body(SYSTEM_D3, payload, model, thinking)
    body.update(SAMPLING)
    body['response_format'] = {'type': 'json_schema', 'json_schema': {'schema': schema(personal)}}
    return body


correction = c.correction


class Behavior(m.Strict):
    sentence_ids: list[str] = Field(min_length=1, max_length=MAX_SENTENCES)
    kind: str
    action: str
    goal_place: str
    applies_only_at: list[str] = Field(max_length=6)
    start_when_any: list[d.Clause] = Field(min_length=1, max_length=6)
    end_when_any: list[d.Clause] = Field(max_length=6)
    hold_minutes: StrictFloat | StrictInt = Field(ge=0, le=360)


class Other(m.Strict):
    sentence_ids: list[str] = Field(min_length=1, max_length=MAX_SENTENCES)
    subject: str
    kind: str


class OutputD3(m.Strict):
    behaviors: list[Behavior] = Field(max_length=16)
    other_sentences: list[Other] = Field(max_length=32)


def compile_d3(value, personal):
    _validate_shape(value, schema(personal))
    for item in value.get('behaviors', []) + value.get('other_sentences', []):
        if len(item.get('sentence_ids', [])) > MAX_SENTENCES:
            raise ValueError(f'too_many_sentences_for_one_rule(max {MAX_SENTENCES})')
        if not item.get('sentence_ids'):
            raise ValueError('item_without_sentence_ids')
    for b in value.get('behaviors', []):
        if not b.get('start_when_any'):
            raise ValueError('behavior_without_condition')
    parsed = OutputD3.model_validate(value)
    by_id = {s['id']: s for s in sentences(personal)}
    ready = fixed(personal)
    rules, unrepresented, cited = [r.model_dump() for r in ready], [], set()
    for item in parsed.behaviors + parsed.other_sentences:
        if len(set(item.sentence_ids)) != len(item.sentence_ids):
            raise ValueError('duplicate_sentence_id_in_item')
        cited.update(item.sentence_ids)
    for o in parsed.other_sentences:
        if o.kind == 'not_representable' and o.subject != 'patient':
            raise ValueError('not_representable_must_be_the_person')
        for n in sorted({by_id[s]['note_id'] for s in o.sentence_ids}):
            unrepresented.append({'note_id': n, 'reason': f'{o.kind}/{o.subject}:' + ','.join(o.sentence_ids)})
    for i, b in enumerate(parsed.behaviors):
        if b.kind == 'functional_need' and b.action != 'rest':
            raise ValueError('functional_need_not_rest')
        used = {f for cl in b.start_when_any for f in cl.true + cl.false} | {
            n.fact for cl in b.start_when_any for n in cl.numbers}
        if not used - {'is_walking'}:
            raise ValueError('degenerate_condition_only_is_walking')
        start = d.render(b.start_when_any)
        text = f'({start}) and not ({d.render(b.end_when_any)})' if b.end_when_any else start
        when = expression(text)
        action, goal, feature = ab._bind(b.action, b.goal_place, b.applies_only_at, personal)
        ab._guard_walking_rest(action, when)
        rules.append({'id': f'd3_{i}', 'action': action, 'when': when, 'goal_label': goal,
                      'feature': feature, 'place_labels': b.applies_only_at,
                      'hold_minutes': b.hold_minutes or None, 'supersedes': [],
                      'evidence': [{'note_id': by_id[s]['note_id'], 'quote': by_id[s]['text']}
                                   for s in b.sentence_ids]})
    covered_by_fixed = {e.note_id for r in ready for e in r.evidence}
    missing = {s for s in set(by_id) - cited if by_id[s]['note_id'] not in covered_by_fixed}
    if missing:
        raise ValueError('sentence_not_classified:' + ','.join(sorted(missing)))
    return m.validate({'rules': rules, 'unrepresented': unrepresented}, personal)


def trait_accounting(value):
    counts = {k: 0 for k in KINDS}
    flagged = []
    for b in (value or {}).get('behaviors', []):
        if b.get('kind') in counts:
            counts[b['kind']] += 1
    for o in (value or {}).get('other_sentences', []):
        if o.get('kind') in counts:
            counts[o['kind']] += 1
        if o.get('kind') == 'not_representable':
            flagged.extend(o.get('sentence_ids', []))
    return {'by_kind': counts, 'trait_loss_sentence_ids': flagged,
            'observed_rules': counts['observed_response'] + counts['functional_need']}
