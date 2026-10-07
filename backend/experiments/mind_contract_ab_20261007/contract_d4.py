"""Candidate D4 (2026-10-07): D3 with branch-level compiler checks and the
prompt lines found to match development or evaluation data neutralised.

Review of D3 (code_review_d3.json, compiler and leakage lenses, reproduced):
  1. The degenerate check took the union of every start branch, so one
     is_walking-only branch beside a real one passed and fired on every step.
     D4 checks each start_when_any branch. A comparison every engine value
     satisfies (>=0 on any numeric fact, clock_hour<24 or <=24) is not a fact
     here, so [is_walking, continuous_walk_minutes>=0] is still is_walking
     only. Such a branch is accepted only when the behavior is limited to a
     registered place (applies_only_at), e.g. a person who sits down whenever
     at one named shelter.
  2. Compiled branches (start AND NOT end) that can never hold were accepted:
     a window past midnight written as clock_hour>=A with end clock_hour>=B,
     the same Boolean fact required true and false, a numeric lower bound at
     or above its upper bound, clock_hour>=24 (the engine clock is [0, 24)).
     D4 rejects them; a clock_hour value outside [0, 24] (e.g. 25 for 1 a.m.)
     is rejected before compilation instead of surfacing as a bare Atom
     validation error. Both errors say how to write a window past midnight
     (two start branches) so the one correction request can act on it.
     Strictness (a choice awaiting the user's decision, both cases are fixed
     in tests): every compiled row must be satisfiable, not merely one row per
     start branch. Kept because it caught a real misread that the scenes did
     not: d3_dev128 DEV_P02_original rep 2 wrote 'crowded or noisy' as start
     (crowded | noisy) and end (crowded & noisy), i.e. exclusive or; the
     fixed prepared_initial rule hides it from the scenes and only its dead
     rows show it. Cost: start [>=23], [<1] with the complementary end
     [>=1 & <23] means the right thing but is rejected; the prompt never asks
     for that form and the error names the accepted one.
  3. A wait whose compiled branch requires is_walking=True switches itself off
     (waiting is not walking). Rejected if any row does. A wait hold_minutes
     is accepted but the engine does not execute it; trait_accounting reports
     it as unexecuted_wait_hold instead of hiding it.
  4. sentences() normalised answers differently from mind_policy.validate, so
     an answer without a question ('답변: ...') kept the prefix in its first
     sentence and every quote of it was rejected. D4 uses validate's rule.
  5. Prompt (every edit is listed in PROMPT_CHANGES; the rest is SYSTEM_D3
     verbatim): the registered-place line is replaced by a general one; the
     not_representable contrast is defined abstractly (its concrete examples
     matched evaluation persona traits); the condition examples use general
     wording and numbers absent from the dev128 and eval64 answers (tested);
     a past-midnight window example is added; the clock range is stated as
     [0, 24); the condition rules changed in 1 and 3 are stated. Not
     changed: the D2 contrast lines (d2.CONTRASTS) kept from D3 for
     comparability still share phrases with dev128 answers ('이야기였다',
     '에 가야 한다고', '그쪽으로 걸어갔다').
Two lists, trait accounting, the five-sentence limit, sampling, schema
enforcement and the one validator-feedback correction are D3's. Not release
qualified.
"""
from __future__ import annotations

from pydantic import Field

from app.llm import mind_policy as m
from app.llm.initial_behavior import _validate_shape
from experiments.mind_contract_ab_20261007 import contract_c as c
from experiments.mind_contract_ab_20261007 import contract_d as d
from experiments.mind_contract_ab_20261007 import contract_d2 as d2
from experiments.mind_contract_ab_20261007 import contract_d3 as d3
from experiments.mind_contract_ab_20261007 import contracts as ab
from experiments.mind_policy_candidates.condition_program import expression, fixed

RELEASE_QUALIFIED = False
VERSION = 'contract-d4-branch-checks-neutral-prompt-20261007-research'
SAMPLING = dict(d3.SAMPLING)
MAX_SENTENCES = d3.MAX_SENTENCES
BEHAVIOR_KINDS = d3.BEHAVIOR_KINDS
OTHER_KINDS = d3.OTHER_KINDS
KINDS = d3.KINDS
# person_walk computes clock_hour = hour + minute/60 + second/3600, so [0, 24).
CLOCK_END = 24


def answer_text(note_text):
    """The answer part exactly as mind_policy.validate compares quotes."""
    answer = note_text.split('\n답변: ', 1)[-1]
    if answer.startswith('답변: '):
        answer = answer[4:]
    return answer


def sentences(personal):
    """Deterministic sentence split of each answer; IDs like N1.s2.

    Same split as D3 (sentence-final punctuation only, no word interpretation);
    only the answer normalisation follows validate so every sentence is a
    verbatim span of the text validate checks.
    """
    out = []
    for n in personal['notes']:
        answer = answer_text(n['text']).strip()
        parts = [p.strip() for p in d.SENTENCE_END.split(answer) if p.strip()]
        for k, text in enumerate(parts or [answer], 1):
            out.append({'id': f"{n['id']}.s{k}", 'note_id': n['id'], 'text': text})
    return out


def schema(personal):
    """D3's schema with sentence IDs from D4 sentences()."""
    out = d3.schema(personal)
    ids = [s['id'] for s in sentences(personal)]
    for part in ('behaviors', 'other_sentences'):
        out['properties'][part]['items']['properties']['sentence_ids']['items']['enum'] = list(ids)
    return out


# ------------------------------------------------------------------- prompt
# Example numbers (27 min, 730 m, clock 14 / 14.5 / 20.5 / 2.5) do not occur in
# any dev128 or eval64 answer, in digits or Korean (tests/test_mind_contract_d4).
CONDITION_FORMAT = """조건은 문자열이 아니라 구조로 쓴다. start_when_any는 '이 중 하나라도 성립하면 시작'인 분기 목록이고, 각 분기는 true(모두 참이어야 할 사실), false(모두 거짓이어야 할 사실), numbers(모두 만족해야 할 숫자 비교)를 함께 만족해야 성립한다.
형식 예(수치·사실은 형식을 보여 주려는 임의 값이며 실제 사람에게 복사하지 않는다):
- 걷는 중에 한계 A분 또는 B미터 중 하나에 이르면: [{"true":["is_walking"],"false":[],"numbers":[{"fact":"continuous_walk_minutes","op":">=","value":27}]}, {"true":["is_walking"],"false":[],"numbers":[{"fact":"distance_since_rest_m","op":">=","value":730}]}]
- 사실 X가 참이고 사실 Y가 거짓일 때: [{"true":["X"],"false":["Y"],"numbers":[]}]  (X, Y 자리에는 제공된 사실 이름을 쓴다)
- 하루 중 C시부터 D시 전까지(예: 오후 2시~2시 반 전): [{"true":[],"false":[],"numbers":[{"fact":"clock_hour","op":">=","value":14},{"fact":"clock_hour","op":"<","value":14.5}]}]
- 자정을 넘어 E시부터 다음 날 F시 전까지(예: 밤 8시 반~새벽 2시 반 전)는 분기 둘이다: [{"true":[],"false":[],"numbers":[{"fact":"clock_hour","op":">=","value":20.5}]}, {"true":[],"false":[],"numbers":[{"fact":"clock_hour","op":"<","value":2.5}]}]  (함께 필요한 사실은 두 분기에 모두 넣는다)
end_when_any는 원문이 '그러면 끝났다'고 말한 종료 조건이며 같은 형식이다. 종료가 원문에 없으면 []. 코드는 (시작 조건) 그리고 (종료 조건이 아님)으로 옮기며, 옮긴 뒤 분기마다 모든 조건이 동시에 성립할 수 있어야 한다. 자정을 넘는 시간대의 끝 시각은 end_when_any나 24보다 큰 수로 쓰지 않고 위처럼 start_when_any의 둘째 분기로 쓴다. 숫자는 원문의 수를 아라비아 숫자로 정확히 옮긴다."""


def _apply(text, changes):
    """Replace each old text that occurs exactly once; fail loudly otherwise."""
    for old, new in changes:
        if text.count(old) != 1:
            raise RuntimeError('D3 prompt text changed; re-review the D4 prompt edits')
        text = text.replace(old, new)
    return text


# The C glossary said '0~24' while the clock is [0, 24); D4 states the range.
GLOSSARY = _apply(c.FACT_GLOSSARY.split('숫자 비교는')[0].strip(), (
    ('하루 중 시각 0~24 (8.5는 오전 8시 30분)', '하루 중 시각 0 이상 24 미만, 자정은 0 (14.5는 오후 2시 30분)'),))

_NOT_REPRESENTABLE_D3 = ('- 본인이 실제로 보인 반응인데 제공된 사실·행동으로 나타낼 수 없는 것'
                         '(예: 특정 교통수단을 탐, 같은 길을 왕복함) → not_representable. '
                         '억지로 가까운 행동에 끼워 넣지 않는다.')
_NOT_REPRESENTABLE_D4 = ('- 본인이 실제로 보인 반응이지만 그 반응이나 그것을 일으킨 조건이 제공된 '
                         '사실·행동 목록에 없는 것 → not_representable. 억지로 가까운 행동에 끼워 넣지 않는다.')

# (D3 text, D4 text). Each D3 text occurs exactly once in SYSTEM_D3.
PROMPT_CHANGES = (
    (d2.CONDITION_FORMAT, CONDITION_FORMAT),
    (d2.GLOSSARY, GLOSSARY),
    (_NOT_REPRESENTABLE_D3, _NOT_REPRESENTABLE_D4),
    ('등록 장소 설명 같은 문장도 other_sentences에 넣는다.', '행동이 없는 문장도 other_sentences에 넣는다.'),
    ('조건에는 is_walking 말고도 그 반응을 일으키는 사실이 하나 이상 있어야 한다.',
     'start_when_any의 분기마다 is_walking 말고도 그 반응을 일으키는 사실이 하나 이상 있어야 한다. '
     '특정 등록 장소에서만 보인 반응이면 applies_only_at이 그 사실을 대신할 수 있다. '
     'wait의 조건에는 is_walking=참을 넣지 않는다. 기다리기 시작하면 걷기가 멈춰 그 조건이 꺼진다.'),
)


SYSTEM_D4 = _apply(d3.SYSTEM_D3, PROMPT_CHANGES)


def request(personal, model, *, thinking=True):
    payload = ab._payload(personal)
    payload['answer_sentences'] = [{'id': s['id'], 'text': s['text']} for s in sentences(personal)]
    payload['output_schema'] = schema(personal)
    body = ab._body(SYSTEM_D4, payload, model, thinking)
    body.update(SAMPLING)
    body['response_format'] = {'type': 'json_schema', 'json_schema': {'schema': schema(personal)}}
    return body


correction = c.correction


class OutputD4(m.Strict):
    behaviors: list[d3.Behavior] = Field(max_length=16)
    other_sentences: list[d3.Other] = Field(max_length=32)


# ----------------------------------------------------------- branch checks
# Error texts are one line and stay within the LIMIT characters run_candidate.judge
# keeps, because they are the only feedback of the correction request.
LIMIT = 200
CLOCK_HELP = ('시각은 0 이상 24 미만. 자정을 넘는 A~B시는 start_when_any 두 분기 [clock_hour>=A], '
              '[clock_hour<B]로 쓰고 B를 end_when_any에 쓰지 않는다. 자정에 끝나면 [clock_hour>=A]만.')
COMBINED_HELP = '합친 분기의 조건이 동시에 참일 수 없다. 코드는 (시작) 그리고 (종료 아님)으로 합친다. 시작·종료 조건을 다시 확인한다.'


def _num(v):
    text = str(round(v, 2))
    return text[:-2] if text.endswith('.0') else text


def dead_branch(row):
    """Why a compiled AND branch (list of atom dicts) can never hold, or None.

    Pure logic on typed atoms: the same Boolean fact required true and false,
    or a numeric fact whose lower bound is not below its upper bound (equal
    bounds hold only when both are inclusive). Every numeric fact is >= 0 and
    clock_hour < 24, as the engine computes them.
    """
    # Bounds are (value, strict). At the same value the strict bound is tighter:
    # the larger lower bound wins with strict > inclusive; the smaller upper
    # bound wins with strict before inclusive.
    truth, low, high = {}, {}, {'clock_hour': (CLOCK_END, True)}
    for a in row:
        fact, op, value = a['fact'], a['op'], a['value']
        if fact in m.BOOLEAN_FACTS:
            if truth.setdefault(fact, value) is not value:
                return f'{fact} 참·거짓 동시'
            continue
        low.setdefault(fact, (0, False))
        if op in ('gte', 'gt', 'eq'):
            low[fact] = max(low[fact], (value, op == 'gt'))
        if op in ('lte', 'lt', 'eq'):
            bound = (value, op == 'lt')
            high[fact] = min(high.get(fact, bound), bound, key=lambda b: (b[0], not b[1]))
    for fact in sorted(low):
        lo, hi = low[fact], high.get(fact)
        if hi is None:
            continue
        if lo[0] > hi[0] or (lo[0] == hi[0] and (lo[1] or hi[1])):
            return (f"{fact}{'>' if lo[1] else '>='}{_num(lo[0])} & "
                    f"{'<' if hi[1] else '<='}{_num(hi[0])}")
    return None


def _always_true(number):
    """A typed comparison every engine value satisfies (numeric facts >= 0, clock_hour < 24)."""
    if number.op == '>=':
        return number.value <= 0
    if number.op == '>':
        return number.value < 0
    return number.fact == 'clock_hour' and number.value >= CLOCK_END  # '<' or '<='


def _walking_only(clause):
    facts = {*clause.true, *clause.false} | {n.fact for n in clause.numbers if not _always_true(n)}
    return not facts - {'is_walking'}


def _check_clock_range(i, b):
    """Reject clock_hour values outside [0, 24] (e.g. 25 for 1 a.m.) with CLOCK_HELP.

    m.Atom rejects them too, but its message ('1 validation error for Atom')
    would be the only feedback of the correction request. The echoed value is
    cut to 7 characters so the message stays within LIMIT.
    """
    for part in ('start_when_any', 'end_when_any'):
        for k, clause in enumerate(getattr(b, part)):
            for n in clause.numbers:
                if n.fact == 'clock_hour' and not 0 <= n.value <= CLOCK_END:
                    shown = _num(n.value)
                    shown = shown if len(shown) <= 7 else shown[:7] + '…'
                    raise ValueError(f'clock_out_of_range(behaviors[{i}].{part}[{k}] {n.op}{shown}): {CLOCK_HELP}')


def _requires_walking(row):
    return any(a['fact'] == 'is_walking' and a['op'] == 'eq' and a['value'] is True for a in row)


def compile_d4(value, personal):
    _validate_shape(value, schema(personal))
    for item in value.get('behaviors', []) + value.get('other_sentences', []):
        if len(item.get('sentence_ids', [])) > MAX_SENTENCES:
            raise ValueError(f'too_many_sentences_for_one_rule(max {MAX_SENTENCES})')
        if not item.get('sentence_ids'):
            raise ValueError('item_without_sentence_ids')
    for b in value.get('behaviors', []):
        if not b.get('start_when_any'):
            raise ValueError('behavior_without_condition')
    parsed = OutputD4.model_validate(value)
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
        start = d.render(b.start_when_any)  # an empty clause is rejected here first
        _check_clock_range(i, b)
        if not b.applies_only_at:
            for k, clause in enumerate(b.start_when_any):
                if _walking_only(clause):
                    raise ValueError(
                        f'degenerate_branch_only_is_walking(behaviors[{i}].start_when_any[{k}]): '
                        '분기마다 is_walking 말고도 반응을 일으키는 사실이 있어야 한다'
                        '(늘 참인 >=0, clock_hour<24는 사실로 치지 않는다. '
                        '특정 등록 장소에서만 보인 반응은 applies_only_at으로 한정한다).')
        text = f'({start}) and not ({d.render(b.end_when_any)})' if b.end_when_any else start
        when = expression(text)
        for row in when:
            why = dead_branch(row)
            if why:
                help_text = CLOCK_HELP if why.startswith('clock_hour') else COMBINED_HELP
                raise ValueError(f'unsatisfiable_branch(behaviors[{i}] {why}): {help_text}')
        action, goal, feature = ab._bind(b.action, b.goal_place, b.applies_only_at, personal)
        ab._guard_walking_rest(action, when)
        if action == 'wait' and any(_requires_walking(row) for row in when):
            raise ValueError(
                f'wait_cancels_itself_is_walking(behaviors[{i}]): 기다리기 시작하면 is_walking이 거짓이 되어 '
                '대기가 바로 꺼진다. wait 조건에 is_walking=참을 넣지 않는다(종료 조건의 is_walking 거짓 포함).')
        rules.append({'id': f'd4_{i}', 'action': action, 'when': when, 'goal_label': goal,
                      'feature': feature, 'place_labels': b.applies_only_at,
                      'hold_minutes': b.hold_minutes or None, 'supersedes': [],
                      'evidence': [{'note_id': by_id[s]['note_id'], 'quote': by_id[s]['text']}
                                   for s in b.sentence_ids]})
    covered_by_fixed = {e.note_id for r in ready for e in r.evidence}
    missing = {s for s in set(by_id) - cited if by_id[s]['note_id'] not in covered_by_fixed}
    if missing:
        raise ValueError('sentence_not_classified:' + ','.join(sorted(missing)))
    return m.validate({'rules': rules, 'unrepresented': unrepresented}, personal)


def _positive(x):
    return type(x) in (int, float) and x > 0


def trait_accounting(value):
    """D3's counts plus wait durations the engine does not execute.

    person_walk holds only rest until hold_until; a wait lasts while its
    condition holds, so a sourced wait duration is reported, never dropped
    silently and never turned into another rule.
    """
    out = d3.trait_accounting(value)
    held = [b for b in (value or {}).get('behaviors', [])
            if b.get('action') == 'wait' and _positive(b.get('hold_minutes'))]
    out['unexecuted_wait_hold'] = len(held)
    out['unexecuted_wait_hold_sentence_ids'] = [s for b in held for s in b.get('sentence_ids', [])]
    return out
