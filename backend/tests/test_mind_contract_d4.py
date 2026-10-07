"""Handwritten contract fixtures for candidate D4 (2026-10-07).

They test the compiler, prompt and accounting only. Passing them is not
evidence of model interpretation quality. Each defect from code_review_d3.json
is shown twice where possible: D3 accepts (or wrongly rejects) the case, D4 does
the opposite.
"""
import json
import re
from pathlib import Path

import pytest

from app.llm import mind_policy as m
from experiments.mind_contract_ab_20261007 import contract_c, contract_d, contract_d2, contract_d3, run_candidate, scoring
from experiments.mind_contract_ab_20261007 import contract_d4 as d4
from experiments.mind_policy_candidates import note_policy_eval as ev
from tests.test_mind_contract_ab import D_CORRECT, cl, to_d3

PEOPLE, SCENES, REFERENCE = scoring.load()
DATA = Path(d4.__file__).parent / 'dataset'
LIMIT = 200  # run_candidate.judge keeps the first line, first 200 characters
assert d4.LIMIT == LIMIT


def personal(pid):
    return PEOPLE[pid]['personal']


def scenes_pass(policy, pid):
    return {s['id']: scoring.scene_pass(ev.decide(policy, personal(pid), s['scene']), s)
            for s in SCENES if s['person_id'] == pid}


def inputs(name):
    path = DATA / name / f'{name}_inputs.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {r['id']: r for r in rows}


DEV128, EVAL64 = inputs('dev128'), inputs('eval64')
DEV128_REFERENCE = json.loads((DATA / 'dev128' / 'dev128_reference.NOT_MODEL_INPUT.json').read_text())
DEV128_SCENES = json.loads((DATA / 'dev128' / 'dev128_scenes.NOT_MODEL_INPUT.json').read_text())
ANSWERS = ' '.join(n['text'].split('\n답변: ', 1)[-1] for r in [*DEV128.values(), *EVAL64.values()]
                   for n in r['personal']['notes'])


def behavior(ids, action, start, end=(), kind='observed_response', goal='', scope=(), hold=0):
    return {'sentence_ids': list(ids), 'kind': kind, 'action': action, 'goal_place': goal,
            'applies_only_at': list(scope), 'start_when_any': list(start), 'end_when_any': list(end),
            'hold_minutes': hold}


def other(ids, kind='other_information', subject='patient'):
    return {'sentence_ids': list(ids), 'subject': subject, 'kind': kind}


def one_note(answer, question='질문: 어떻게 하셨나요?\n'):
    return {'notes': [{'id': 'N0', 'text': question + '답변: ' + answer}],
            'places': [{'label': '솔빛쉼터', 'place_type': 'park'}], 'prepared_initial': {}}


TWO = one_note('그때는 그렇게 하셨어요. 실제로 본 일이에요.')


def single(start, end=(), action='wait', scope=(), hold=0, kind='observed_response'):
    """One behavior on N0.s1 of TWO, the other sentence classified."""
    return {'behaviors': [behavior(['N0.s1'], action, start, end, kind=kind, scope=scope, hold=hold)],
            'other_sentences': [other(['N0.s2'])]}


# ------------------------------------------------------------ D3 behavior kept

@pytest.mark.parametrize('pid', sorted(D_CORRECT))
def test_d4_compiles_every_d_fixture_like_d3_and_matches_scenes(pid):
    out = to_d3(D_CORRECT[pid])
    policy = d4.compile_d4(out, personal(pid))
    assert all(scenes_pass(policy, pid).values())
    assert scoring.critical(policy, personal(pid), REFERENCE[pid], pid) == []
    old = contract_d3.compile_d3(out, personal(pid)).model_dump()
    for r in old['rules']:
        r['id'] = r['id'].replace('d3_', 'd4_')
    assert policy.model_dump() == old


def test_interface_matches_d3():
    assert d4.RELEASE_QUALIFIED is False
    assert re.fullmatch(r'contract-d4-[a-z0-9-]+-20261007-research', d4.VERSION)
    assert d4.SAMPLING == contract_d3.SAMPLING and d4.KINDS == contract_d3.KINDS
    assert d4.MAX_SENTENCES == contract_d3.MAX_SENTENCES and d4.correction is contract_c.correction
    body = d4.request(personal('P29'), 'model-x')
    assert body['messages'][0]['content'] == d4.SYSTEM_D4
    assert body['response_format']['json_schema']['schema'] == d4.schema(personal('P29'))
    assert {k: body[k] for k in d4.SAMPLING} == d4.SAMPLING
    user = json.loads(body['messages'][1]['content'])
    assert user['original_notes'] == personal('P29')['notes']
    assert [s['id'] for s in user['answer_sentences']] == ['N0.s1', 'N0.s2', 'N1.s1', 'N2.s1', 'N2.s2']
    for leaked in ('expected', 'reference', 'rationale', '"family": '):
        assert leaked not in json.dumps(body, ensure_ascii=False)


def test_requests_build_for_every_dev128_and_eval64_input():
    for r in [*DEV128.values(), *EVAL64.values()]:
        d4.request(r['personal'], 'model-x')  # raises on the 40 000-byte input cap


def test_d3_rejections_still_apply():
    out = to_d3(D_CORRECT['P21'])
    out['other_sentences'] = [o for o in out['other_sentences'] if o['sentence_ids'] != ['N1.s3']]
    with pytest.raises(ValueError, match='sentence_not_classified:N1.s3'):
        d4.compile_d4(out, personal('P21'))
    out = to_d3(D_CORRECT['P05'])
    out['behaviors'][0]['start_when_any'] = []
    with pytest.raises(ValueError, match='behavior_without_condition'):
        d4.compile_d4(out, personal('P05'))
    out = to_d3(D_CORRECT['P21'])
    out['other_sentences'].append(other(['N1.s1'], 'not_representable', 'other_person'))
    with pytest.raises(ValueError, match='not_representable_must_be_the_person'):
        d4.compile_d4(out, personal('P21'))
    with pytest.raises(ValueError, match='empty_condition_clause'):
        d4.compile_d4(single([cl()]), TWO)
    with pytest.raises(ValueError, match='walking_limited_rest_unguarded'):
        d4.compile_d4(single([cl(['rain_observed'], numbers=[('continuous_walk_minutes', '>=', 27)])],
                             action='rest', kind='functional_need'), TWO)


# ------------------------------------------------- 1. degenerate per branch

P05_EXTRA_BRANCH = [cl(['is_walking']), cl(['is_walking'], numbers=[('continuous_walk_minutes', '>=', 8)]),
                    cl(['is_walking'], numbers=[('distance_since_rest_m', '>=', 450)])]


def test_one_is_walking_only_branch_is_rejected_even_beside_real_branches():
    out = to_d3(D_CORRECT['P05'])
    out['behaviors'][0]['start_when_any'] = P05_EXTRA_BRANCH
    policy = contract_d3.compile_d3(out, personal('P05'))  # the D3 defect: compiles
    assert not scenes_pass(policy, 'P05')['P05_S3']
    with pytest.raises(ValueError, match=r'degenerate_branch_only_is_walking\(behaviors\[0\]\.start_when_any\[0\]\)'):
        d4.compile_d4(out, personal('P05'))


@pytest.mark.parametrize('start', [[cl(['is_walking'])], [cl(false=['is_walking'])],
                                   [cl(['rain_observed']), cl(['is_walking'])]])
def test_branch_without_a_fact_besides_is_walking_is_rejected_without_place_scope(start):
    with pytest.raises(ValueError, match='degenerate_branch_only_is_walking'):
        d4.compile_d4(single(start, action='rest'), TWO)


ALWAYS_TRUE = [('continuous_walk_minutes', '>=', 0), ('distance_since_rest_m', '>=', 0),
               ('clock_hour', '>=', 0), ('clock_hour', '<', 24), ('clock_hour', '<=', 24)]


@pytest.mark.parametrize('numbers', [[a] for a in ALWAYS_TRUE] + [[('clock_hour', '>=', 0), ('clock_hour', '<', 24)]])
def test_a_comparison_every_value_satisfies_does_not_make_a_branch_real(numbers):
    # Review probe5: [is_walking, continuous_walk_minutes>=0] is is_walking only.
    out = to_d3(D_CORRECT['P05'])
    # to_d3 copies shallowly; build a new list so D_CORRECT stays intact.
    out['behaviors'][0]['start_when_any'] = out['behaviors'][0]['start_when_any'] + [cl(['is_walking'], numbers=numbers)]
    assert not scenes_pass(contract_d3.compile_d3(out, personal('P05')), 'P05')['P05_S3']  # fires at 7 min, 440 m
    with pytest.raises(ValueError) as error:
        d4.compile_d4(out, personal('P05'))
    text = str(error.value)
    assert text.startswith('degenerate_branch_only_is_walking(behaviors[0].start_when_any[2]): ')
    assert '\n' not in text and len(text) <= LIMIT


@pytest.mark.parametrize('fact,op,value,always', [
    ('continuous_walk_minutes', '>=', 0, True), ('continuous_walk_minutes', '>=', 0.5, False),
    ('continuous_walk_minutes', '>', 0, False),  # false at the first step after a rest
    ('distance_since_rest_m', '<=', 100000, False), ('distance_since_rest_m', '<', 24, False),
    ('clock_hour', '<', 24, True), ('clock_hour', '<=', 24, True), ('clock_hour', '<', 23.5, False),
    ('clock_hour', '>=', 0, True), ('clock_hour', '>', 0, False),
])
def test_always_true_is_exactly_the_engine_domain(fact, op, value, always):
    assert d4._always_true(contract_d.Number(fact=fact, op=op, value=value)) is always


def test_place_limited_is_walking_branch_is_a_legitimate_rule():
    p = one_note('솔빛쉼터에 가시면 늘 앉아 쉬셨어요.')
    out = {'behaviors': [behavior(['N0.s1'], 'rest', [cl(['is_walking'])], scope=['솔빛쉼터'])],
           'other_sentences': []}
    with pytest.raises(ValueError, match='degenerate_condition_only_is_walking'):
        contract_d3.compile_d3(out, p)  # the D3 defect: rejected
    rule = d4.compile_d4(out, p).rules[0]
    assert (rule.action, rule.place_labels) == ('rest', ['솔빛쉼터'])
    assert [[a.model_dump() for a in row] for row in rule.when] == [[{'fact': 'is_walking', 'op': 'eq', 'value': True}]]


# ------------------------------------------- 2. unsatisfiable compiled branch

P26 = DEV128['DEV_P26_original']['personal']
P26_OTHERS = [other(['N0.s1', 'N0.s2']), other(['N1.s3'])]


def p26(start, end=()):
    return {'behaviors': [behavior(['N1.s1', 'N1.s2'], 'wait', start, end)], 'other_sentences': P26_OTHERS}


def test_window_past_midnight_closed_by_end_condition_is_rejected_with_the_two_branch_form():
    # The DEV_P26 pattern from the review: start 23 h, end 1 h -> [[23 <= x < 1]].
    out = p26([cl(false=['family_present'], numbers=[('clock_hour', '>=', 23)])],
              [cl(numbers=[('clock_hour', '>=', 1)])])
    contract_d3.compile_d3(out, P26)  # the D3 defect: compiles a rule that never fires
    with pytest.raises(ValueError) as error:
        d4.compile_d4(out, P26)
    text = str(error.value)
    assert text.startswith('unsatisfiable_branch(behaviors[0] clock_hour>=23 & <1)')
    assert '[clock_hour>=A], [clock_hour<B]' in text and 'end_when_any' in text
    assert '\n' not in text and len(text) <= LIMIT


def test_the_two_branch_form_passes_every_dev128_p26_scene():
    start = [cl(false=['family_present'], numbers=[('clock_hour', '>=', 23)]),
             cl(false=['family_present'], numbers=[('clock_hour', '<', 1)])]
    policy = d4.compile_d4(p26(start), P26)
    scenes = [s for s in DEV128_SCENES if s['input_id'] == 'DEV_P26_original']
    assert len(scenes) == 4
    assert all(scoring.scene_pass(ev.decide(policy, P26, s['scene']), s) for s in scenes)
    assert scoring.critical(policy, P26, DEV128_REFERENCE['DEV_P26_original'], 'P26') == []


def judged(out, p, compile_fn):
    """The feedback text run_candidate.judge would send to the correction request."""
    public = {'finish_reason': 'stop', 'final_content': json.dumps(out, ensure_ascii=False)}
    return run_candidate.judge(public, p, compile_fn)[0]


NIGHT = cl(false=['family_present'], numbers=[('clock_hour', '>=', 23)])


ATOM_ERROR = '1 validation error for Atom'


@pytest.mark.parametrize('start,end,where,d3_feedback', [
    # 1 a.m. written as 25: as an upper bound, as the end, as a second branch
    ([cl(false=['family_present'], numbers=[('clock_hour', '>=', 23), ('clock_hour', '<', 25)])], [],
     'start_when_any[0] <25', ATOM_ERROR),
    ([NIGHT], [cl(numbers=[('clock_hour', '>=', 25)])], 'end_when_any[0] >=25', ATOM_ERROR),
    ([NIGHT, cl(false=['family_present'], numbers=[('clock_hour', '<', 25)])], [], 'start_when_any[1] <25', ATOM_ERROR),
    ([cl(false=['family_present'], numbers=[('clock_hour', '>=', 24.5)])], [], 'start_when_any[0] >=24.5', ATOM_ERROR),
    ([cl(false=['family_present'], numbers=[('clock_hour', '>=', -1)])], [], 'start_when_any[0] >=-1',
     'only Boolean and numeric literals are allowed'),  # '-1' renders as a unary minus
])
def test_clock_value_outside_the_day_gets_the_midnight_help_not_an_atom_error(start, end, where, d3_feedback):
    out = p26(start, end)
    assert judged(out, P26, contract_d3.compile_d3) == d3_feedback  # the D3 feedback: no help at all
    text = judged(out, P26, d4.compile_d4)
    assert text == f'clock_out_of_range(behaviors[0].{where}): {d4.CLOCK_HELP}'  # whole help survives the cut
    assert '[clock_hour>=A], [clock_hour<B]' in text


def test_clock_bound_24_itself_is_handled_by_the_domain():
    assert judged(p26([cl(false=['family_present'], numbers=[('clock_hour', '>=', 24)])]), P26, d4.compile_d4) == \
        f'unsatisfiable_branch(behaviors[0] clock_hour>=24 & <24): {d4.CLOCK_HELP}'
    d4.compile_d4(p26([cl(false=['family_present'], numbers=[('clock_hour', '>=', 23), ('clock_hour', '<=', 24)])]), P26)


# Strictness: every compiled row must be satisfiable. This is a design choice
# awaiting the user's decision; both of its consequences are fixed here.

def test_strict_rows_reject_the_complementary_end_form_a_documented_cost():
    out = p26([NIGHT, cl(false=['family_present'], numbers=[('clock_hour', '<', 1)])],
              [cl(numbers=[('clock_hour', '>=', 1), ('clock_hour', '<', 23)])])
    policy = contract_d3.compile_d3(out, P26)  # means the right thing: every DEV_P26 scene passes
    scenes = [s for s in DEV128_SCENES if s['input_id'] == 'DEV_P26_original']
    assert all(scoring.scene_pass(ev.decide(policy, P26, s['scene']), s) for s in scenes)
    with pytest.raises(ValueError) as error:
        d4.compile_d4(out, P26)
    assert str(error.value) == f'unsatisfiable_branch(behaviors[0] clock_hour>=23 & <1): {d4.CLOCK_HELP}'


def test_strict_rows_catch_the_stored_exclusive_or_misread():
    # Shape of the stored d3_dev128 DEV_P02_original rep 2 first response:
    # 'crowded or noisy' as start (crowded | noisy), end (crowded & noisy).
    p = DEV128['DEV_P02_original']['personal']
    out = {'behaviors': [behavior(['N1.s2', 'N1.s3'], 'avoid_market', [cl(['market.crowded']), cl(['market.noisy'])],
                                  [cl(['market.crowded', 'market.noisy'])])],
           'other_sentences': [other(['N0.s1', 'N0.s2', 'N1.s1'])]}
    policy = contract_d3.compile_d3(out, p)
    # The fixed prepared_initial rule avoids the market on either stimulus, so
    # the scenes cannot see the model's own rule; only its dead rows show it.
    assert [r.id for r in policy.rules] == ['initial_env_market', 'd3_0']
    scenes = [s for s in DEV128_SCENES if s['input_id'] == 'DEV_P02_original']
    assert scenes and all(scoring.scene_pass(ev.decide(policy, p, s['scene']), s) for s in scenes)
    both = {'market.crowded': True, 'market.noisy': True}
    reference = [[m.Atom(**a) for a in row] for row in DEV128_REFERENCE['DEV_P02_original']['rules'][0]['when']]
    assert (m.truth(policy.rules[1].when, both), m.truth(reference, both)) == (False, True)  # exclusive or
    with pytest.raises(ValueError, match=r'^unsatisfiable_branch\(behaviors\[0\] market\.crowded 참·거짓 동시\)'):
        d4.compile_d4(out, p)


def test_same_fact_true_and_false_is_rejected():
    # The stored d_dev8 P29 shape: start family present, end family present.
    out = to_d3(D_CORRECT['P29'])
    out['behaviors'][1]['start_when_any'] = [cl(['lost_awareness', 'family_present'])]
    contract_d3.compile_d3(out, personal('P29'))  # the D3 defect: compiles
    with pytest.raises(ValueError, match=r'unsatisfiable_branch\(behaviors\[1\] family_present 참·거짓 동시\)'):
        d4.compile_d4(out, personal('P29'))


@pytest.mark.parametrize('numbers,ok', [
    ([('clock_hour', '>=', 24)], False),            # the engine clock is [0, 24)
    ([('clock_hour', '>', 23.5), ('clock_hour', '<=', 23.5)], False),
    ([('clock_hour', '>=', 10), ('clock_hour', '<', 10)], False),
    ([('clock_hour', '>=', 10), ('clock_hour', '<=', 10)], True),  # both inclusive: x == 10 holds
    ([('clock_hour', '>=', 23)], True),
    ([('clock_hour', '<=', 24)], True),
    ([('continuous_walk_minutes', '>=', 5), ('continuous_walk_minutes', '>=', 9),
      ('continuous_walk_minutes', '<', 7)], False),  # the tighter lower bound decides
    ([('distance_since_rest_m', '<', 0)], False),   # numeric facts are never negative
    ([('distance_since_rest_m', '<=', 0)], True),
])
def test_numeric_bounds_respect_strictness_and_domain(numbers, ok):
    out = single([cl(['rain_observed'], numbers=numbers)])
    if ok:
        d4.compile_d4(out, TWO)
    else:
        with pytest.raises(ValueError, match='unsatisfiable_branch'):
            d4.compile_d4(out, TWO)


def test_every_rejection_message_fits_the_correction_feedback():
    worst = [[{'fact': 'clock_hour', 'op': 'gte', 'value': 23.99}, {'fact': 'clock_hour', 'op': 'lte', 'value': 1.25}],
             [{'fact': 'distance_since_rest_m', 'op': 'gt', 'value': 123456.75},
              {'fact': 'distance_since_rest_m', 'op': 'lt', 'value': 1000.25}],
             [{'fact': 'forest.crowded', 'op': 'eq', 'value': True}, {'fact': 'forest.crowded', 'op': 'eq', 'value': False}]]
    for row in worst:
        why = d4.dead_branch(row)
        help_text = d4.CLOCK_HELP if why.startswith('clock_hour') else d4.COMBINED_HELP
        assert len(f'unsatisfiable_branch(behaviors[15] {why}): {help_text}') <= LIMIT
    p = one_note(' '.join(f'문장{i}이에요.' for i in range(16)))
    walking = {'behaviors': [behavior([f'N0.s{i}'], 'wait', [cl(['rain_observed'])]) for i in range(1, 16)]
               + [behavior(['N0.s16'], 'wait', [cl(['is_walking', 'rain_observed'])])], 'other_sentences': []}
    degenerate = {'behaviors': [behavior([f'N0.s{i}'], 'wait', [cl(['rain_observed'])]) for i in range(1, 16)]
                  + [behavior(['N0.s16'], 'rest', [cl(['rain_observed'])] * 5 + [cl(['is_walking'])])],
                  'other_sentences': []}
    clock = {'behaviors': [behavior([f'N0.s{i}'], 'wait', [cl(['rain_observed'])]) for i in range(1, 16)]
             + [behavior(['N0.s16'], 'wait', [cl(['rain_observed'])] * 5
                         + [cl(['rain_observed'], numbers=[('clock_hour', '>=', 123456789.25)])])],
             'other_sentences': []}
    for out in (walking, degenerate, clock):
        with pytest.raises(ValueError) as error:
            d4.compile_d4(out, p)
        text = str(error.value)
        assert 'behaviors[15]' in text and len(text) <= LIMIT and '\n' not in text
    assert text == f'clock_out_of_range(behaviors[15].start_when_any[5] >=1234567…): {d4.CLOCK_HELP}'


ATOM_OPS = {'gte': '>=', 'gt': '>', 'lte': '<=', 'lt': '<'}


def test_new_checks_accept_every_development_reference_rule():
    for ref in [*DEV128_REFERENCE.values(), *REFERENCE.values()]:
        for rule in ref['rules']:
            for row in rule['when']:
                assert d4.dead_branch(row) is None
                assert not (rule['action'] == 'wait' and d4._requires_walking(row))
                assert all(0 <= a['value'] <= d4.CLOCK_END for a in row if a['fact'] == 'clock_hour')
                if row:  # an empty (always) row has no D3/D4 encoding at all
                    real = [a for a in row if a['fact'] != 'is_walking' and not (
                        a['op'] in ATOM_OPS and d4._always_true(
                            contract_d.Number(fact=a['fact'], op=ATOM_OPS[a['op']], value=a['value'])))]
                    assert real or rule['place_labels']


# ------------------------------------------------------------------ 3. wait

def test_wait_requiring_walking_switches_itself_off_and_is_rejected():
    out = to_d3(D_CORRECT['P29'])
    out['behaviors'][1]['start_when_any'] = [cl(['is_walking', 'lost_awareness'], ['family_present'])]
    policy = contract_d3.compile_d3(out, personal('P29'))  # the D3 defect: compiles and passes the scenes
    assert all(scenes_pass(policy, 'P29').values())
    with pytest.raises(ValueError, match=r'wait_cancels_itself_is_walking\(behaviors\[1\]\)'):
        d4.compile_d4(out, personal('P29'))


def test_wait_with_one_walking_branch_among_others_is_rejected():
    # Any compiled row that requires walking cancels itself when it fires.
    out = single([cl(['rain_observed']), cl(['is_walking', 'dark_observed'])])
    contract_d3.compile_d3(out, TWO)  # the D3 defect: compiles
    with pytest.raises(ValueError, match=r'wait_cancels_itself_is_walking\(behaviors\[0\]\)'):
        d4.compile_d4(out, TWO)


def test_wait_ended_by_not_walking_is_the_same_defect_after_compilation():
    with pytest.raises(ValueError, match='wait_cancels_itself_is_walking'):
        d4.compile_d4(single([cl(['rain_observed'])], [cl(false=['is_walking'])]), TWO)


def test_wait_on_not_walking_and_rest_on_walking_are_kept():
    rule = d4.compile_d4(single([cl(['rain_observed'], ['is_walking'])]), TWO).rules[0]
    assert rule.action == 'wait'
    rest = d4.compile_d4(to_d3(D_CORRECT['P05']), personal('P05')).rules
    assert [r.action for r in rest] == ['rest']


def test_wait_hold_is_compiled_unchanged_and_reported_as_unexecuted():
    out = single([cl(['rain_observed'])], hold=10)
    assert d4.compile_d4(out, TWO).rules[0].hold_minutes == 10
    acct = d4.trait_accounting(out)
    assert acct['unexecuted_wait_hold'] == 1 and acct['unexecuted_wait_hold_sentence_ids'] == ['N0.s1']
    rest = single([cl(['pain_observed'])], action='rest', hold=10)
    assert d4.trait_accounting(rest)['unexecuted_wait_hold'] == 0
    base = d4.trait_accounting(to_d3(D_CORRECT['P29']))
    assert base['unexecuted_wait_hold'] == 0 and base['unexecuted_wait_hold_sentence_ids'] == []
    assert {k: base[k] for k in ('by_kind', 'trait_loss_sentence_ids', 'observed_rules')} == \
        contract_d3.trait_accounting(to_d3(D_CORRECT['P29']))
    assert d4.trait_accounting(None)['unexecuted_wait_hold'] == 0


# ------------------------------------------------------------- 4. sentences

def test_answer_without_question_is_split_without_the_prefix():
    p = one_note('길을 잃은 걸 알면 가족이 올 때까지 그 자리에서 기다렸어요. 가족이 오면 끝났어요.', question='')
    assert [s['text'] for s in d4.sentences(p)] == ['길을 잃은 걸 알면 가족이 올 때까지 그 자리에서 기다렸어요.',
                                                    '가족이 오면 끝났어요.']
    out = {'behaviors': [behavior(['N0.s1', 'N0.s2'], 'wait', [cl(['lost_awareness'], ['family_present'])],
                                  [cl(['family_present'])])], 'other_sentences': []}
    with pytest.raises(ValueError, match='quote not in original answer'):
        contract_d3.compile_d3(out, p)  # the D3 defect
    assert d4.compile_d4(out, p).rules[0].action == 'wait'
    single_sentence = one_note('길을 잃은 걸 알면 그 자리에서 기다렸어요.', question='')
    out = {'behaviors': [behavior(['N0.s1'], 'wait', [cl(['lost_awareness'])])], 'other_sentences': []}
    assert d4.compile_d4(out, single_sentence).rules[0].evidence[0].quote == '길을 잃은 걸 알면 그 자리에서 기다렸어요.'


def test_sentence_normalisation_is_the_validate_rule():
    p = one_note('답변: 비가 오면 처마 밑에서 기다리셨어요.', question='질문: q\n')
    assert [s['text'] for s in d4.sentences(p)] == ['비가 오면 처마 밑에서 기다리셨어요.']
    d4.compile_d4({'behaviors': [behavior(['N0.s1'], 'wait', [cl(['rain_observed'])])], 'other_sentences': []}, p)


def test_sentences_and_schema_are_unchanged_on_every_existing_input():
    every = [r['personal'] for r in [*DEV128.values(), *EVAL64.values()]] + [personal(p) for p in PEOPLE]
    for p in every:
        assert d4.sentences(p) == contract_d3.sentences(p)
        assert d4.schema(p) == contract_d3.schema(p)


# ---------------------------------------------------------------- 5. prompt

def test_prompt_differs_from_d3_only_by_the_listed_changes():
    restored = d4.SYSTEM_D4
    for old, new in reversed(d4.PROMPT_CHANGES):
        assert restored.count(new) == 1
        restored = restored.replace(new, old)
    assert restored == contract_d3.SYSTEM_D3
    assert '등록 장소 설명' not in d4.SYSTEM_D4


# Trait categories of the eval64 expected_trait_loss sentences (eval64_review,
# 2026-10-07). The prompt must define not_representable without naming them.
EVAL_TRAIT_WORDS = ('교통수단', '버스', '열차', '지하철', '전철', '정류장', '역무원', '개찰구', '택시', '왕복',
                    '되돌아', '왔던 길', '같은 길', '되짚', '바퀴', '빙빙', '맴돌', '지팡이', '보행기', '큰길',
                    '골목', '가로등', '처음 잡은 방향', '막다른', '끊긴', '따라가', '따라오', '앞장', '길을 물',
                    '물어', '전화', '숨어', '눈에 안 띄', '대답', '걸음이 빠르', '걸음이 느리', '열쇠', '좌우',
                    '오르막', '혼잣말', '들락날락', '숨이 차', '눌러앉')


def test_prompt_names_no_evaluation_trait():
    assert [w for w in EVAL_TRAIT_WORDS if w in d4.SYSTEM_D4] == []
    assert '교통수단' in contract_d3.SYSTEM_D3  # the leak this candidate removes


def bigrams(text):
    words = re.findall(r'[가-힣]+', text)
    return {' '.join(words[i:i + 2]) for i in range(len(words) - 1)}


# Hangul word pairs of the past-midnight and afternoon examples ('밤 8시 반' ->
# '밤 시', '시 반'); a clock example cannot avoid them.
CLOCK_READINGS = {'다음 날', '밤 시', '새벽 시', '시 반', '시 전까지', '시부터 다음', '오후 시'}


def test_prompt_text_written_for_d4_shares_only_clock_readings_with_answers():
    shared = bigrams(ANSWERS)
    for old, new in d4.PROMPT_CHANGES:
        # The glossary's fact definitions are C's, shared by every candidate;
        # only D4's edit of it is checked. Every other new text is checked whole.
        own = bigrams(new) - (bigrams(old) if old == contract_d2.GLOSSARY else set())
        assert own & shared <= CLOCK_READINGS, (new[:30], sorted(own & shared - CLOCK_READINGS))
    assert '먼저 닿' in ANSWERS and '먼저 닿' not in d4.SYSTEM_D4  # the D2 wording the review found


def test_prompt_states_the_clock_range_once_and_consistently():
    assert '0~24' not in d4.SYSTEM_D4 and '0~24' in contract_d3.SYSTEM_D3
    assert d4.SYSTEM_D4.count('0 이상 24 미만') == 1 and '0 이상 24 미만' in d4.CLOCK_HELP


# Each example value with the ways an answer could state it (digits, Korean
# numerals, 12-hour clock readings); '시간' is a duration, not a clock time.
EXAMPLE_FORMS = {
    '27': [r'이십칠', r'스물일곱'],
    '730': [r'칠백 ?삼십'],
    '14': [r'(?<!\d)2 ?시(?!간)', r'두 ?시(?!간)', r'14 ?시'],
    '14.5': [r'(?<!\d)2 ?시 ?(반|30)', r'두 ?시 ?(반|삼십)'],
    '20.5': [r'(?<!\d)8 ?시 ?(반|30)', r'여덟 ?시 ?(반|삼십)', r'20 ?시'],
    '2.5': [r'(?<!\d)2 ?시 ?(반|30)', r'두 ?시 ?(반|삼십)'],
}


def test_prompt_example_numbers_occur_in_no_dev128_or_eval64_answer():
    values = set(re.findall(r'"value":(\d+(?:\.\d+)?)', d4.SYSTEM_D4))
    values |= set(re.findall(r'\((\d+(?:\.\d+)?)는 ', d4.GLOSSARY))
    assert values == set(EXAMPLE_FORMS)
    for value, forms in EXAMPLE_FORMS.items():
        assert not re.search(rf'(?<![\d.]){re.escape(value)}(?!\d)', ANSWERS), value
        for form in forms:
            assert not re.search(form, ANSWERS), (value, form)
    used = {float(a['value']) for ref in [*DEV128_REFERENCE.values(), *REFERENCE.values()]
            for rule in ref['rules'] for row in rule['when'] for a in row if a['fact'] in m.NUMERIC_FACTS}
    assert not {float(v) for v in values} & used


def test_prompt_condition_examples_pass_the_d4_branch_checks():
    from experiments.mind_policy_candidates.condition_program import expression
    examples = re.findall(r'^- .*?: (\[.*\])', d4.CONDITION_FORMAT, flags=re.M)
    compiled = []
    for text in examples:
        clauses = [contract_d.Clause.model_validate(x) for x in json.loads(text)]
        if any(f in ('X', 'Y') for x in clauses for f in x.true + x.false):
            continue  # placeholder fact names
        assert not any(d4._walking_only(x) for x in clauses)
        compiled.append(expression(contract_d.render(clauses)))
    assert len(compiled) == 3
    assert all(d4.dead_branch(row) is None for when in compiled for row in when)
    night = [[m.Atom(**a) for a in row] for row in compiled[-1]]
    assert m.truth(night, {'clock_hour': 23.0}) is True and m.truth(night, {'clock_hour': 1.0}) is True
    assert m.truth(night, {'clock_hour': 12.0}) is False
