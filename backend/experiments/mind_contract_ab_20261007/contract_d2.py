"""Candidate D2 (2026-10-07): D plus review fixes before any wider claim.

Review of D (user-forwarded, 2026-10-07):
  1. D's prompt examples reused development numbers (8 min / 450 m, 08-09 h)
     and the inherited contrasts reused development shapes. A higher dev score
     would then show familiarity, not generalization. D2 examples use numbers
     absent from every dev/eval file (checked) and abstract wording.
  2. Evidence: D accepted up to 8 sentence IDs but stored the first 5. D2
     accepts at most 5 (the Rule limit) and rejects more, so nothing is
     silently dropped; the correction request reports it.
  3. Traits the engine cannot express must surface: D2 adds kind
     hearsay_or_general (guardian's guess, general belief, second-hand) and
     reports per response how many units were observed behavior, functional
     need, not_representable, unobserved, hearsay. not_representable units are
     counted as trait loss, never hidden.
Sampling, schema enforcement, sentence IDs, structured conditions and the one
validator-feedback correction are unchanged from D. Not release qualified.
"""
from __future__ import annotations

from pydantic import Field

from app.llm import mind_policy as m
from app.llm.initial_behavior import _validate_shape
from experiments.mind_contract_ab_20261007 import contract_c as c
from experiments.mind_contract_ab_20261007 import contract_d as d
from experiments.mind_contract_ab_20261007 import contracts as ab
from experiments.mind_policy_candidates.condition_program import expression, fixed

RELEASE_QUALIFIED = False
VERSION = 'contract-d2-neutral-examples-trait-accounting-20261007-research'
SAMPLING = dict(d.SAMPLING)
MAX_SENTENCES = 5  # mind_policy.Rule.evidence max_length
KINDS = ab.BEHAVIOR_KINDS + ('capacity_only', 'stated_goal', 'unobserved', 'corrected_away',
                             'hearsay_or_general', 'other_information', 'not_representable')
sentences = d.sentences

CONDITION_FORMAT = """조건은 문자열이 아니라 구조로 쓴다. start_when_any는 '이 중 하나라도 성립하면 시작'인 분기 목록이고, 각 분기는 true(모두 참이어야 할 사실), false(모두 거짓이어야 할 사실), numbers(모두 만족해야 할 숫자 비교)를 함께 만족해야 성립한다.
형식 예(수치·사실은 형식을 보여 주려는 임의 값이며 실제 사람에게 복사하지 않는다):
- 걷는 중에 한계 A분 또는 B미터에 먼저 닿으면: [{"true":["is_walking"],"false":[],"numbers":[{"fact":"continuous_walk_minutes","op":">=","value":13}]}, {"true":["is_walking"],"false":[],"numbers":[{"fact":"distance_since_rest_m","op":">=","value":730}]}]
- 사실 X가 참이고 사실 Y가 거짓일 때: [{"true":["X"],"false":["Y"],"numbers":[]}]  (X, Y 자리에는 제공된 사실 이름을 쓴다)
- 하루 중 C시부터 D시 전까지(예: 오후 2시~3시 전): [{"true":[],"false":[],"numbers":[{"fact":"clock_hour","op":">=","value":14},{"fact":"clock_hour","op":"<","value":15}]}]
end_when_any는 원문이 '그러면 끝났다'고 말한 종료 조건이며 같은 형식이다. 종료가 원문에 없으면 []. 코드는 (시작 조건) 그리고 (종료 조건이 아님)으로 옮긴다. 숫자는 원문의 수를 아라비아 숫자로 정확히 옮긴다."""

CONTRASTS = """구별 원칙(문장은 원칙을 보이기 위한 추상 예이며 실제 사람의 수치·장소를 복사하지 않는다):
- '오래 걸을 수 있다'는 능력 진술 → capacity_only. 휴식 규칙을 만들지 않는다.
- '얼마쯤 걸으면 아파서 꼭 앉아야 한다'는 신체 필요 → functional_need, rest, 그 한계를 조건으로.
- '어디에 가야 한다고 말만 한다' → stated_goal. 출발 규칙을 만들지 않는다.
- '어떤 장소를 알아보면 그쪽으로 걸어갔다' → observed_response, seek, goal_place=그 등록 장소, applies_only_at=[].
- '어떤 장소 안에서만 어떤 상황이면 돌아섰다' → observed_response, avoid_유형, applies_only_at=[그 등록 장소].
- '그건 다른 사람 이야기였다' → corrected_away 또는 other_person. 그 행동을 본인에게 넣지 않는다.
- '보통 치매 어르신들은 그렇다더라', '그럴 것 같다' → hearsay_or_general. 관찰이 아니므로 행동을 만들지 않는다.
- 본인이 실제로 보인 반응인데 제공된 사실·행동으로 나타낼 수 없는 것(예: 특정 교통수단을 탐, 같은 길을 왕복함) → not_representable. 억지로 가까운 행동에 끼워 넣지 않는다."""

GLOSSARY = c.FACT_GLOSSARY.split('숫자 비교는')[0].strip().replace('(8.5는 오전 8시 30분)', '(13.5는 오후 1시 30분)')
assert '오전 8' not in GLOSSARY

SYSTEM_D2 = '\n'.join([  # noqa: FLY002 - prompt sections
    '보호자 문답을 읽고, 답변의 문장들을 의미 단위로 묶어 판정한다. 코드는 네 판정을 실행 규칙으로 옮길 뿐 단어를 해석하지 않는다. 현재 장면과 정답은 주어지지 않는다.',
    c.PERSON,
    'answer_sentences는 각 답변을 문장으로 나눈 것이다. 각 unit은 근거 문장의 sentence_ids를 1~5개 적는다. 모든 문장은 적어도 하나의 unit에 들어가야 한다. 정정 문장과 대상 어르신 본인의 관찰 문장은 서로 다른 unit이다. 한 문장에 행동이 둘이면 unit을 둘로 만들고 같은 문장을 함께 인용한다.',
    'subject: patient(대상 어르신 본인), other_person(다른 사람), unclear(누구인지 불분명).',
    'kind: observed_response(본인이 실제로 보인 조건부 반응), functional_need(걸은 뒤 쉬어야 하는 신체적 필요), capacity_only(걸을 수 있는 능력뿐), stated_goal(가고 싶다는 발언뿐), unobserved(보지 못함·모름), corrected_away(정정으로 철회된 정보), hearsay_or_general(보호자의 짐작·일반론·남에게 들은 말), other_information(행동이 아닌 정보), not_representable(본인이 실제로 보인 반응이지만 제공된 사실·행동으로 나타낼 수 없음).',
    'observed_response와 functional_need는 subject=patient이고 action과 start_when_any가 반드시 있어야 한다. 그 밖의 kind는 action="none", goal_place="", applies_only_at=[], start_when_any=[], end_when_any=[], hold_minutes=0이다. functional_need의 action은 rest다. 행동의 조건에는 is_walking 말고도 그 반응을 일으키는 사실이 하나 이상 있어야 한다.',
    CONDITION_FORMAT,
    'fixed_rules는 이미 실행 가능하며 그대로 유지된다. 같은 반응을 다시 만들지 말고 그 문장은 other_information으로 둘 수 있다.',
    ab.ACTION_MEANING, GLOSSARY, ab.DISTINCTIONS,
    'hold_minutes는 원문이 말한 휴식·대기 지속 시간만 쓰고 모르면 0이다. 쉬기 전에 걸은 시간이 아니다.',
    'output_schema에 맞는 완전한 JSON 객체 하나를 닫는 괄호까지 출력한다. 설명문·마크다운을 붙이지 않는다.',
    CONTRASTS, ab.SOURCE_RULES])


def schema(personal):
    out = d.schema(personal)
    unit = out['properties']['units']['items']
    unit['properties']['kind'] = {'type': 'string', 'enum': list(KINDS)}
    return out


def request(personal, model, *, thinking=True):
    payload = ab._payload(personal)
    payload['answer_sentences'] = [{'id': s['id'], 'text': s['text']} for s in sentences(personal)]
    payload['output_schema'] = schema(personal)
    body = ab._body(SYSTEM_D2, payload, model, thinking)
    body.update(SAMPLING)
    body['response_format'] = {'type': 'json_schema', 'json_schema': {'schema': schema(personal)}}
    return body


correction = c.correction


class UnitD2(d.UnitD):
    sentence_ids: list[str] = Field(min_length=1, max_length=MAX_SENTENCES)


class OutputD2(m.Strict):
    units: list[UnitD2] = Field(min_length=1, max_length=32)


def compile_d2(value, personal):
    _validate_shape(value, schema(personal))
    for u in value.get('units', []):
        if len(u.get('sentence_ids', [])) > MAX_SENTENCES:
            raise ValueError(f'too_many_sentences_for_one_rule(max {MAX_SENTENCES})')
    parsed = OutputD2.model_validate(value)
    by_id = {s['id']: s for s in sentences(personal)}
    ready = fixed(personal)
    rules, unrepresented = [r.model_dump() for r in ready], []
    cited = set()
    for i, u in enumerate(parsed.units):
        if len(set(u.sentence_ids)) != len(u.sentence_ids):
            raise ValueError('duplicate_sentence_id_in_unit')
        cited.update(u.sentence_ids)
        if u.kind not in ab.BEHAVIOR_KINDS:
            if (u.action != 'none' or u.goal_place or u.applies_only_at or u.start_when_any
                    or u.end_when_any or u.hold_minutes):
                raise ValueError('non_behavior_unit_with_action')
            for n in sorted({by_id[s]['note_id'] for s in u.sentence_ids}):
                unrepresented.append({'note_id': n, 'reason': f'{u.kind}/{u.subject}:' + ','.join(u.sentence_ids)})
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
        start = d.render(u.start_when_any)
        text = f'({start}) and not ({d.render(u.end_when_any)})' if u.end_when_any else start
        when = expression(text)
        action, goal, feature = ab._bind(u.action, u.goal_place, u.applies_only_at, personal)
        ab._guard_walking_rest(action, when)
        rules.append({'id': f'd2_{i}', 'action': action, 'when': when, 'goal_label': goal,
                      'feature': feature, 'place_labels': u.applies_only_at,
                      'hold_minutes': u.hold_minutes or None, 'supersedes': [],
                      'evidence': [{'note_id': by_id[s]['note_id'], 'quote': by_id[s]['text']}
                                   for s in u.sentence_ids]})
    covered_by_fixed = {e.note_id for r in ready for e in r.evidence}
    missing = {s for s in set(by_id) - cited if by_id[s]['note_id'] not in covered_by_fixed}
    if missing:
        raise ValueError('sentence_not_classified:' + ','.join(sorted(missing)))
    return m.validate({'rules': rules, 'unrepresented': unrepresented}, personal)


def trait_accounting(value):
    """Per-response unit counts by kind; not_representable is reported as trait loss."""
    counts = {k: 0 for k in KINDS}
    flagged = []
    for u in (value or {}).get('units', []):
        if u.get('kind') in counts:
            counts[u['kind']] += 1
        if u.get('kind') == 'not_representable':
            flagged.extend(u.get('sentence_ids', []))
    return {'by_kind': counts, 'trait_loss_sentence_ids': flagged,
            'observed_rules': counts['observed_response'] + counts['functional_need']}
