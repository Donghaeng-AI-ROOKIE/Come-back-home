"""Handwritten contract fixtures for candidate D5 (2026-10-07).

They test the compiler, prompt, correction text and accounting only. Passing
them is not evidence of model interpretation quality. The governing decision
(D5_설계_수정결정.md): personal traits are never removed from what the
contract can express to match an existing test answer. Three hand-written
outputs pin that down: continued walking under fatigue as a walk rule, a rest
taken while standing or waiting, and a behavior started by an absence
condition all compile.
"""
import json
import re

import pytest

from app.llm import mind_policy as m
from app.phase2.person_walk import Population
from experiments.mind_contract_ab_20261007 import contract_c, contract_d, contract_d3, run_v2, scoring
from experiments.mind_contract_ab_20261007 import contract_d4 as d4
from experiments.mind_contract_ab_20261007 import contract_d5 as d5
from experiments.mind_policy_candidates import note_policy_eval as ev
from tests.test_mind_contract_ab import D_CORRECT, cl, to_d3
from tests.test_mind_contract_d4 import (
    ANSWERS,
    DEV128,
    DEV128_REFERENCE,
    DEV128_SCENES,
    EVAL64,
    EVAL_TRAIT_WORDS,
    bigrams,
)

PEOPLE, SCENES, REFERENCE = scoring.load()
LINE, TOTAL = 200, run_v2.ERROR_CHARS
assert (d5.LINE_LIMIT, d5.ERROR_LIMIT) == (LINE, TOTAL)
ATOM_OPS = {'gte': '>=', 'gt': '>', 'lte': '<=', 'lt': '<'}


def personal(pid):
    return PEOPLE[pid]['personal']


def behavior(ids, action, start, end=(), kind='observed_response', goal='', scope=(), hold=0, overrides=()):
    return {'sentence_ids': list(ids), 'kind': kind, 'action': action, 'goal_place': goal,
            'applies_only_at': list(scope), 'start_when_any': list(start), 'end_when_any': list(end),
            'hold_minutes': hold, 'overrides': [{'behavior': j, 'sentence_id': s} for j, s in overrides]}


def output(p, behaviors=(), roles=None, corrections=()):
    """Every sentence other_information of the patient unless roles says otherwise;
    a sentence cited by a behavior defaults to behavior_source."""
    roles = roles or {}
    cited = {s for b in behaviors for s in b['sentence_ids']}
    out = {}
    for s in d5.sentences(p):
        role, subject = roles.get(s['id'], ('behavior_source' if s['id'] in cited else 'other_information', 'patient'))
        out[s['id']] = {'subject': subject, 'role': role}
    return {'sentence_roles': out, 'corrections': [{'sentence_id': s, 'retracts': list(r), 'amends': list(a)}
                                                   for s, r, a in corrections],
            'behaviors': list(behaviors)}


def one_note(answer, question='질문: 어떻게 하셨나요?\n'):
    return {'notes': [{'id': 'N0', 'text': question + '답변: ' + answer}],
            'places': [{'label': '솔빛쉼터', 'place_type': 'park'}, {'label': '해든상가', 'place_type': 'market'}],
            'prepared_initial': {}}


def codes(value, p):
    return [e['code'] for e in d5.errors(value, p)]


def feedback(value, p):
    """The text and kind run_v2 stores and feeds back to the correction request."""
    with pytest.raises(d5.CompileErrors) as error:
        d5.compile_d5(value, p)
    return run_v2.describe(error.value)


def walking_facts(**facts):
    base = {f: False for f in m.BOOLEAN_FACTS}
    base.update(continuous_walk_minutes=0.0, distance_since_rest_m=0.0, clock_hour=11.0)
    base.update(facts)
    return base


# ----------------------------------------------- D4 behavior is kept

@pytest.mark.parametrize('pid', sorted(D_CORRECT))
def test_d5_compiles_every_d_fixture_to_the_d4_rules(pid):
    out3 = to_d3(D_CORRECT[pid])
    policy = d5.compile_d5(d5.from_d3(out3, personal(pid)), personal(pid))
    old = d4.compile_d4(out3, personal(pid)).model_dump()
    for r in old['rules']:
        r['id'] = r['id'].replace('d4_', 'd5_')
    assert policy.model_dump()['rules'] == old['rules']
    assert all(scoring.scene_pass(ev.decide(policy, personal(pid), s['scene']), s)
               for s in SCENES if s['person_id'] == pid)
    assert scoring.critical(policy, personal(pid), REFERENCE[pid], pid) == []


def reference_output(p, ref):
    """A D5 output that states the reference policy (the researchers' own rules)."""
    by_note = {}
    for s in d5.sentences(p):
        by_note.setdefault(s['note_id'], []).append(s['id'])
    own = [r for r in ref['rules'] if not r['id'].startswith('initial_')]
    behaviors = []
    for r in own:
        clauses = [{'true': [a['fact'] for a in row if a['op'] == 'eq' and a['value'] is True],
                    'false': [a['fact'] for a in row if a['op'] == 'eq' and a['value'] is False],
                    'numbers': [{'fact': a['fact'], 'op': ATOM_OPS[a['op']], 'value': a['value']}
                                for a in row if a['op'] in ATOM_OPS]} for row in r['when']]
        ids = list(dict.fromkeys(s for e in r['evidence'] for s in by_note[e['note_id']]))[:d5.MAX_SENTENCES]
        action = 'avoid_' + r['feature'] if r['action'] == 'avoid' else r['action']
        behaviors.append(behavior(ids, action, clauses, goal=r['goal_label'] or '', scope=r['place_labels'],
                                  hold=r['hold_minutes'] or 0))
    return output(p, behaviors)


def test_every_dev128_reference_policy_is_expressible_and_keeps_its_scenes():
    # No D5 check rejects a behavior the researchers' reference holds (absence
    # conditions, stationary waits, place scopes, time windows past midnight).
    for input_id, ref in DEV128_REFERENCE.items():
        p = DEV128[input_id]['personal']
        policy = d5.compile_d5(reference_output(p, ref), p)
        scenes = [s for s in DEV128_SCENES if s['input_id'] == input_id]
        assert all(scoring.scene_pass(ev.decide(policy, p, s['scene']), s) for s in scenes), input_id


def test_d4_rejections_still_apply_with_locations():
    t = one_note('비가 오면 처마 밑에서 기다리셨어요. 실제로 본 일이에요.')
    cases = [
        ([cl(['is_walking'])], 'rest', 'degenerate_branch_only_is_walking'),
        ([cl(['rain_observed'], numbers=[('clock_hour', '>=', 10), ('clock_hour', '<', 10)])], 'wait', 'unsatisfiable_branch'),
        ([cl(['rain_observed', 'is_walking'])], 'wait', 'wait_cancels_itself_is_walking'),
        ([cl(['rain_observed'], numbers=[('clock_hour', '<', 25)])], 'wait', 'clock_out_of_range'),
        ([cl(['rain_observed'], numbers=[('continuous_walk_minutes', '>=', 27)])], 'rest', 'walking_limited_rest_unguarded'),
        ([cl()], 'wait', 'empty_condition_clause'),
        ([cl(['rain_observed'], numbers=[('distance_since_rest_m', '>=', -3)])], 'wait', 'negative_number'),
    ]
    for start, action, code in cases:
        assert codes(output(t, [behavior(['N0.s1'], action, start)]), t) == [code], code
    assert codes(output(t, [behavior(['N0.s1'], 'wait', [cl(['rain_observed'])], kind='functional_need')]), t) == \
        ['functional_need_not_rest']
    bad = output(t, [behavior(['N0.s1'], 'wait', [cl(['rain_observed'])])])
    bad['behaviors'][0]['start_when_any'][0]['true'] = ['비']
    assert codes(bad, t) == ['schema_mismatch']
    assert d5.errors(bad, t)[0]['where'] == 'behaviors[0].start_when_any[0].true[0]'


# ------------------------- the three trait-preserving decisions

P08 = DEV128['DEV_P08_original']['personal']
P08_OUT = output(P08, [
    # Kept walking past the 12 minute mark and when short of breath, unless in pain.
    behavior(['N1.s1', 'N1.s2'], 'walk', [cl(['is_walking'], ['pain_observed'], [('continuous_walk_minutes', '>=', 12)]),
                                          cl(['is_walking', 'fatigue_high'], ['pain_observed'])]),
    behavior(['N1.s2'], 'rest', [cl(['is_walking', 'pain_observed'])], kind='functional_need'),
])


def test_continued_walking_under_fatigue_is_a_walk_rule_the_engine_lets_override_fatigue_rest():
    policy = d5.compile_d5(P08_OUT, P08)
    walk, rest = policy.rules
    assert (walk.action, rest.action) == ('walk', 'rest')
    # person_walk suppresses the general fatigue rest only for such a walk rule.
    assert Population._explicit_physical_walk(walk, walking_facts(is_walking=True, fatigue_high=True)) is True
    assert Population._explicit_physical_walk(walk, walking_facts(is_walking=True, continuous_walk_minutes=13.0)) is True
    lost_walk = d5.compile_d5(output(P08, [behavior(['N1.s1'], 'walk', [cl(['lost_awareness'])])]), P08).rules[0]
    assert Population._explicit_physical_walk(lost_walk, walking_facts(is_walking=True, lost_awareness=True)) is False
    yes, _ = m.applicable(policy, walking_facts(is_walking=True, pain_observed=True, continuous_walk_minutes=13.0))
    assert [r.action for r in yes] == ['rest']  # in pain the stated rest, not the walk
    assert d5.trait_accounting(P08_OUT)['engine_support']['supported'] == 2
    diag = d5.diagnostics(P08_OUT, P08, DEV128_REFERENCE['DEV_P08_original'])
    assert diag['physical_walk'] == [0] and diag['disputed_physical_walk'] is True and diag['errors'] == []


def test_the_existing_answer_is_kept_and_the_disagreement_is_reported_as_disputed():
    policy = d5.compile_d5(P08_OUT, P08)
    reference = DEV128_REFERENCE['DEV_P08_original']
    assert [r['action'] for r in reference['rules']] == ['rest']  # unchanged: no walk rule
    scenes = {s['id']: s for s in DEV128_SCENES if s['input_id'] == 'DEV_P08_original'}
    passed = {k: scoring.scene_pass(ev.decide(policy, P08, s['scene']), s) for k, s in scenes.items()}
    failed = sorted(k for k, ok in passed.items() if not ok)
    assert failed == ['DEV_P08_original_S1', 'DEV_P08_original_S3']  # scored as failures by the existing reference
    assert all(ev.decide(policy, P08, scenes[k]['scene'])['commands'] == ['walk'] for k in failed)
    assert d5.disputed('DEV_P08_original', policy, reference) == {
        'input_id': 'DEV_P08_original', 'listed': True, 'physical_walk_rules': ['d5_0'], 'reference_has_walk': False}


def test_disputed_list_names_dev128_inputs_whose_reference_has_no_walk_rule():
    for input_id in [*d5.DISPUTED_DEV128, *d5.REVIEW_DEV128]:
        assert input_id in DEV128
        assert not any(r['action'] == 'walk' for r in DEV128_REFERENCE[input_id]['rules'])


def test_not_having_seen_a_rest_is_unobserved_and_makes_no_rule():
    p = one_note('힘들어 보이셨지만 그때 쉬는 모습은 못 봤어요.')
    out = output(p, roles={'N0.s1': ('unobserved', 'patient')})
    policy = d5.compile_d5(out, p)
    assert policy.rules == [] and policy.unrepresented[0].reason == 'unobserved/patient:N0.s1'
    acct = d5.trait_accounting(out)
    assert acct['by_kind']['unobserved'] == 1 and acct['trait_loss_sentence_ids'] == []
    assert d5.diagnostics(out, p)['silent_collapse'] is None  # undefined without a reference


STANDING = one_note('기다리시다가 비가 오면 그 자리에 앉아 쉬셨어요. 걷다가 그러신 적은 없어요.')


@pytest.mark.parametrize('start', [
    [cl(['rain_observed'], ['is_walking'])],          # while standing or waiting, a situation
    [cl(['fatigue_high'], ['is_walking'])],           # while standing, a body state
    [cl(['rain_observed'])],                          # the situation alone
])
def test_a_rest_taken_while_standing_or_waiting_compiles_and_is_only_counted(start):
    out = output(STANDING, [behavior(['N0.s1', 'N0.s2'], 'rest', start)])
    rule = d5.compile_d5(out, STANDING).rules[0]
    assert rule.action == 'rest'
    assert m.truth(rule.when, walking_facts(rain_observed=True, fatigue_high=True)) is True  # not walking
    diag = d5.diagnostics(out, STANDING)
    assert diag['rest_not_while_walking'] == [0] and diag['errors'] == []
    support = d5.trait_accounting(out)['engine_support']
    assert support['semantics_incomplete'] == 1
    assert support['semantics_incomplete_behaviors'] == {'0': ['rest_not_while_walking']}


def test_situational_rest_is_a_diagnostic_never_a_rejection():
    out = output(STANDING, [behavior(['N0.s1', 'N0.s2'], 'rest', [cl(['is_walking', 'rain_observed'])])])
    d5.compile_d5(out, STANDING)
    assert d5.diagnostics(out, STANDING)['situational_only_rest'] == [0]


ABSENT = one_note('가족이 곁에 없을 때는 그 자리에서 기다리셨어요. 가족이 오면 같이 가셨어요.')


@pytest.mark.parametrize('action', ['wait', 'walk', 'rest', 'avoid_market'])
def test_a_behavior_started_by_an_absence_condition_compiles(action):
    out = output(ABSENT, [behavior(['N0.s1', 'N0.s2'], action, [cl(false=['family_present'])])])
    rule = d5.compile_d5(out, ABSENT).rules[0]
    assert m.truth(rule.when, {'family_present': False}) is True
    assert m.truth(rule.when, {'family_present': True}) is False  # 'absent' is not read as 'present'
    diag = d5.diagnostics(out, ABSENT)
    assert diag['absence_only_branches'] == [0]
    assert diag['walk_without_true_event'] == ([0] if action == 'walk' else [])


SHAPES = {'absence': [cl(false=['family_present'])], 'situation': [cl(['rain_observed'])],
          'standing': [cl(['dark_observed'], ['is_walking'])], 'body': [cl(['fatigue_high'], ['pain_observed'])],
          'walking_body': [cl(['is_walking', 'fatigue_high'], ['pain_observed'])],
          'walking_limit': [cl(['is_walking'], numbers=[('continuous_walk_minutes', '>=', 27)])]}


@pytest.mark.parametrize('action', [a for a in d5.ab.ACTIONS])
@pytest.mark.parametrize('shape', sorted(SHAPES))
def test_no_check_bans_a_kind_of_behavior(action, shape):
    # The only refusals left are D4's logical ones: a wait that needs walking
    # switches itself off the moment it starts.
    out = output(STANDING, [behavior(['N0.s1'], action, SHAPES[shape], goal='솔빛쉼터' if action == 'seek' else '')])
    found = codes(out, STANDING)
    if action == 'wait' and shape.startswith('walking'):
        assert found == ['wait_cancels_itself_is_walking']
    else:
        assert found == []


def test_the_prompt_asks_for_the_three_decisions_and_drops_the_withdrawn_rules():
    text = d5.SYSTEM_D5
    assert '걷던 중에 멈춰 쉰 반응이면 rest의 분기마다 true에 is_walking을 넣는다.' in text
    assert '서 있거나 기다리던 중에 쉰 반응이면 원문이 말한 그 상황을 조건으로 쓰고 is_walking은 넣지 않는다.' in text
    assert 'action=walk인 항목으로 만들고' in text and '쉬는 모습을 보지 못했다는 말뿐이면 unobserved' in text
    assert '부재만으로 시작된 반응은 false만 있는 분기로 써도 된다' in text
    for withdrawn in ('원인과 상관없이 start_when_any의 모든 분기 true에 is_walking을 넣는다',  # design A-1
                      'walk 항목은 두 경우가 모두 성립할 때만 만든다',  # design A-2
                      '- rest: 보행을 멈추고'):
        assert withdrawn not in text


# --------------------------------------------- D5-04 errors and correction

def test_every_error_is_reported_at_once_with_location_and_fits_the_feedback():
    p = DEV128['DEV_P08_hard']['personal']
    out = output(p, [behavior(['N1.s1'], 'rest', [cl(['is_walking'])]),
                     behavior(['N2.s1'], 'wait', [cl(['is_walking', 'fatigue_high'])]),
                     behavior(['N3.s1'], 'walk', [cl(['fatigue_high'])], overrides=[(0, 'N2.s1')])],
                 roles={'N1.s1': ('behavior_source', 'patient'), 'N0.s1': ('qualifies_behavior', 'patient')})
    found = d5.errors(out, p)
    assert [e['code'] for e in found] == ['role_not_cited', 'degenerate_branch_only_is_walking',
                                          'wait_cancels_itself_is_walking', 'override_evidence_not_cited']
    text, kind = feedback(out, p)
    assert kind == 'role_not_cited' and len(text) <= TOTAL
    assert text.count(' | ') == 3 and all(len(x) <= LINE for x in text.split(' | '))
    # A sentence-located error carries the sentence verbatim (no interpretation).
    quote = next(s['text'] for s in d5.sentences(p) if s['id'] == 'N0.s1')
    assert f'원문 "{quote}"' in text.split(' | ')[0]


def test_many_errors_are_cut_with_a_count_and_still_fit():
    p = one_note(' '.join(f'문장{i}이에요.' for i in range(16)))
    out = output(p, [behavior([f'N0.s{i}'], 'rest', [cl(['is_walking'])]) for i in range(1, 17)])
    text, kind = feedback(out, p)
    assert kind == 'degenerate_branch_only_is_walking' and len(text) <= TOTAL
    assert text.split(' | ')[-1].startswith('more_errors: 외 ')
    assert len(d5.errors(out, p)) == 16


def test_shape_errors_stop_early_but_name_their_paths():
    p = one_note('비가 오면 기다리셨어요.')
    out = output(p, [behavior(['N0.s1'], 'wait', [cl(['rain_observed'])])])
    del out['sentence_roles']['N0.s1']
    out['behaviors'][0]['hold_minutes'] = 'ten'
    found = d5.errors(out, p)
    assert [(e['code'], e['where']) for e in found] == [('schema_mismatch', 'sentence_roles'),
                                                        ('schema_mismatch', 'behaviors[0].hold_minutes')]
    assert '빠짐: N0.s1' in found[0]['text']


def body_for(p):
    return d5.request(p, 'model-x')


def test_correction_uses_the_local_fix_wording_only_for_compile_errors():
    p = personal('P29')
    first = body_for(p)
    fix = d5.correction(first, {'final_content': '{"a": 1}'}, 'override_self(behaviors[0].overrides[0]): …')
    assert fix['messages'][:2] == first['messages'] and fix['messages'][2]['content'] == '{"a": 1}'
    assert d5.LOCAL_FIX in fix['messages'][3]['content'] and d5.REINTERPRET not in fix['messages'][3]['content']
    status = d5.correction(first, {'final_content': '{"a": [1'}, 'invalid_json')
    assert d5.REINTERPRET in status['messages'][3]['content'] and d5.LOCAL_FIX not in status['messages'][3]['content']
    assert status == contract_c.correction(first, {'final_content': '{"a": [1'}, 'invalid_json')
    assert d4.correction is contract_c.correction  # D4's frozen correction is untouched


@pytest.mark.parametrize('content,returned', [('{"sentence_roles": {   \n\n   ', '{"sentence_roles": {'),
                                              ('   \n  ', '(최종 출력 없음)'), ('', '(최종 출력 없음)')])
def test_incomplete_length_returns_the_output_without_its_trailing_whitespace(content, returned):
    first = body_for(personal('P29'))
    fix = d5.correction(first, {'final_content': content}, 'incomplete_length')
    assert fix['messages'][2]['content'] == returned
    assert contract_c.ERROR_HELP['incomplete_length'] in fix['messages'][3]['content']
    assert d5.REINTERPRET in fix['messages'][3]['content']


# ----------------------------------------------------- D5-06 roles

P21 = personal('P21')  # N1.s1 correction, N1.s2 walk when lost, N1.s3 unobserved


def p21(roles=None, behaviors=None, corrections=()):
    base = {'N1.s1': ('correction', 'patient'), 'N1.s3': ('unobserved', 'patient')}
    base.update(roles or {})
    return output(P21, behaviors if behaviors is not None else
                  [behavior(['N1.s2'], 'walk', [cl(['lost_awareness'])])], base, corrections)


def test_p21_with_roles_compiles_and_matches_the_scenes():
    policy = d5.compile_d5(p21(), P21)
    assert all(scoring.scene_pass(ev.decide(policy, P21, s['scene']), s) for s in SCENES if s['person_id'] == 'P21')


@pytest.mark.parametrize('change,code', [
    (dict(roles={'N1.s3': ('qualifies_behavior', 'patient')}), 'role_not_cited'),
    (dict(roles={'N1.s2': ('qualifies_behavior', 'patient')}), 'behavior_without_source'),
    (dict(behaviors=[behavior(['N1.s2', 'N1.s3'], 'walk', [cl(['lost_awareness'])])]), 'behavior_cites_other_role'),
    (dict(roles={'N1.s2': ('behavior_source', 'other_person')}), 'behavior_source_not_patient'),
    (dict(roles={'N1.s3': ('not_representable', 'other_person')}), 'not_representable_must_be_the_person'),
])
def test_role_cross_checks(change, code):
    assert code in codes(p21(**change), P21)


def test_sentences_of_a_fixed_rule_note_need_not_be_cited():
    p = DEV128['DEV_P02_original']['personal']
    assert [r.id for r in m.fixed_rules(p)] == ['initial_env_market']
    out = output(p, roles={'N1.s1': ('behavior_source', 'patient')})
    assert codes(out, p) == [] and [r.id for r in d5.compile_d5(out, p).rules] == ['initial_env_market']


# ------------------------------------------------ D5-07 corrections

P04 = one_note('어두우면 멈춰 서 계셨어요. 아니요, 그건 옆집 어르신 얘기예요. 어머니는 어두워도 그냥 걸으셨어요.')


def p04(roles, corrections, behaviors=None):
    return output(P04, behaviors if behaviors is not None else
                  [behavior(['N0.s3'], 'walk', [cl(['dark_observed'])])], roles, corrections)


def test_a_retracted_sentence_is_corrected_away_and_cannot_be_evidence():
    ok = p04({'N0.s1': ('corrected_away', 'other_person'), 'N0.s2': ('correction', 'patient')},
             [('N0.s2', ['N0.s1'], [])])
    assert codes(ok, P04) == []
    used = p04({'N0.s1': ('corrected_away', 'other_person'), 'N0.s2': ('correction', 'patient')},
               [('N0.s2', ['N0.s1'], [])], [behavior(['N0.s1'], 'wait', [cl(['dark_observed'])]),
                                            behavior(['N0.s3'], 'walk', [cl(['dark_observed'])])])
    assert 'withdrawn_sentence_used' in codes(used, P04)
    assert 'behavior_cites_other_role' not in codes(used, P04)  # one error per cause


@pytest.mark.parametrize('roles,corrections,code', [
    ({'N0.s1': ('other_information', 'patient'), 'N0.s2': ('correction', 'patient')}, [('N0.s2', ['N0.s1'], [])],
     'retract_target_not_corrected_away'),
    ({'N0.s1': ('corrected_away', 'other_person'), 'N0.s2': ('correction', 'patient')}, [],
     'corrected_away_without_relation'),
    ({'N0.s2': ('correction', 'patient')}, [('N0.s2', ['N0.s2'], [])], 'correction_self_reference'),
    ({'N0.s1': ('corrected_away', 'other_person'), 'N0.s2': ('correction', 'patient')},
     [('N0.s2', ['N0.s1'], ['N0.s1'])], 'retracts_and_amends_same'),
    ({'N0.s1': ('corrected_away', 'other_person'), 'N0.s2': ('correction', 'patient')},
     [('N0.s2', ['N0.s1'], []), ('N0.s2', [], [])], 'duplicate_correction_entry'),
])
def test_correction_relation_checks(roles, corrections, code):
    assert code in codes(p04(roles, corrections), P04)


def test_an_amended_sentence_cited_without_its_correction_is_a_diagnostic_only():
    p = one_note('연속 이십 분 걸으면 쉬셨어요. 아니, 십오 분이었어요.')
    walking = [cl(['is_walking'], numbers=[('continuous_walk_minutes', '>=', 15)])]
    out = output(p, [behavior(['N0.s1'], 'rest', walking, kind='functional_need')],
                 {'N0.s2': ('qualifies_behavior', 'patient')}, [('N0.s2', [], ['N0.s1'])])
    assert codes(out, p) == ['role_not_cited']  # N0.s2 qualifies the rest and must be cited
    out['behaviors'][0]['sentence_ids'] = ['N0.s1', 'N0.s2']
    assert codes(out, p) == []
    out2 = output(p, [behavior(['N0.s1'], 'rest', walking, kind='functional_need')],
                  {'N0.s2': ('correction', 'patient')}, [('N0.s2', [], ['N0.s1'])])
    assert codes(out2, p) == [] and d5.diagnostics(out2, p)['amends_without_correction_cited'] == [[0, 'N0.s1', 'N0.s2']]


# ----------------------------------------------------- D5-08 overrides

TWO_RULES = one_note('비가 오면 기다리셨어요. 길을 잃은 걸 아시면 계속 걸으셨어요. 비 오는데 길을 잃으셨을 땐 기다리셨어요.')


def two(overrides=(), wait=None, walk=None):
    return output(TWO_RULES, [behavior(['N0.s1', 'N0.s3'], 'wait', wait or [cl(['rain_observed'])], overrides=overrides),
                              behavior(['N0.s2'], 'walk', walk or [cl(['lost_awareness'])])])


def test_a_sourced_precedence_compiles_to_supersedes_and_the_engine_applies_it():
    policy = d5.compile_d5(two([(1, 'N0.s3')]), TWO_RULES)
    assert [r.supersedes for r in policy.rules] == [['d5_1'], []]
    yes, maybe = m.applicable(policy, {'rain_observed': True, 'lost_awareness': True})
    assert [r.action for r in yes] == ['wait'] and maybe == []
    none = d5.compile_d5(two(), TWO_RULES)
    assert {r.action for r in m.applicable(none, {'rain_observed': True, 'lost_awareness': True})[0]} == {'wait', 'walk'}


@pytest.mark.parametrize('overrides,code', [
    ([(2, 'N0.s3')], 'override_out_of_range'), ([(0.5, 'N0.s3')], 'override_out_of_range'),
    ([(0, 'N0.s3')], 'override_self'), ([(1, 'N0.s3'), (1, 'N0.s3')], 'override_duplicate'),
    ([(1, 'N0.s2')], 'override_evidence_not_cited'),
])
def test_override_reference_checks(overrides, code):
    assert codes(two(overrides), TWO_RULES) == [code]


def test_a_precedence_cycle_is_rejected_in_korean():
    out = two([(1, 'N0.s3')])
    out['behaviors'][1]['overrides'] = [{'behavior': 0, 'sentence_id': 'N0.s2'}]
    found = d5.errors(out, TWO_RULES)
    assert [e['code'] for e in found] == ['override_cycle']
    assert found[0]['where'] == 'behaviors[0]→behaviors[1]→behaviors[0]' and '돌고 돈다' in found[0]['text']


def test_a_precedence_that_makes_a_rule_never_run_is_rejected():
    # walk needs lost_awareness and rain, wait needs rain: wait always holds with walk.
    out = two([(1, 'N0.s3')], walk=[cl(['lost_awareness', 'rain_observed'])])
    assert codes(out, TWO_RULES) == ['over_never_runs']
    scoped = output(TWO_RULES, [
        behavior(['N0.s1', 'N0.s3'], 'wait', [cl(['rain_observed'])], scope=['솔빛쉼터'], overrides=[(1, 'N0.s3')]),
        behavior(['N0.s2'], 'walk', [cl(['lost_awareness', 'rain_observed'])])])
    assert codes(scoped, TWO_RULES) == []  # the winner holds only at one place, so the loser still runs elsewhere


def test_overlap_without_precedence_and_noop_precedence_are_diagnostics():
    out = two(walk=[cl(['lost_awareness', 'rain_observed'])])
    assert codes(out, TWO_RULES) == []  # executable as an unresolved branch; 'unknown' can be right
    assert d5.diagnostics(out, TWO_RULES)['rule_always_conflicts'] == [[1, 0]]
    noop = two([(1, 'N0.s3')], wait=[cl(['rain_observed'], ['lost_awareness'])])
    assert codes(noop, TWO_RULES) == [] and d5.diagnostics(noop, TWO_RULES)['noop_override'] == [[0, 1]]
    same = output(TWO_RULES, [behavior(['N0.s1'], 'wait', [cl(['rain_observed'])]),
                              behavior(['N0.s3'], 'wait', [cl(['rain_observed', 'lost_awareness'])])])
    assert d5.diagnostics(same, TWO_RULES)['redundant_rule'] == [[1, 0]]


def test_implication_respects_bounds_and_domain():
    def row(*atoms):
        return [{'fact': f, 'op': o, 'value': v} for f, o, v in atoms]
    assert d5.row_implies(row(('clock_hour', 'gte', 23)), row(('clock_hour', 'gte', 20)))
    assert not d5.row_implies(row(('clock_hour', 'gte', 20)), row(('clock_hour', 'gte', 23)))
    assert d5.row_implies(row(('clock_hour', 'gte', 1)), row(('clock_hour', 'lt', 24)))  # the clock domain
    assert d5.row_implies(row(('continuous_walk_minutes', 'gt', 5)), row(('continuous_walk_minutes', 'gte', 5)))
    assert not d5.row_implies(row(('continuous_walk_minutes', 'gte', 5)), row(('continuous_walk_minutes', 'gt', 5)))
    assert d5.row_implies(row(('rain_observed', 'eq', True), ('rain_observed', 'eq', False)), row(('dark_observed', 'eq', True)))
    assert not d5.can_co_hold([row(('rain_observed', 'eq', True))], [row(('rain_observed', 'eq', False))])


# --------------------------------------------------- D5-09 input, schema

def test_request_carries_questions_once_per_answer_and_no_labels():
    p = personal('P29')
    body = d5.request(p, 'model-x')
    assert body['messages'][0]['content'] == d5.SYSTEM_D5
    assert body['response_format']['json_schema']['schema'] == d5.schema(p)
    assert {k: body[k] for k in d5.SAMPLING} == d5.SAMPLING == d4.SAMPLING
    user = json.loads(body['messages'][1]['content'])
    assert user['original_notes'] == p['notes'] and 'answer_sentences' not in user
    assert [t['note_id'] for t in user['answers_by_turn']] == [n['id'] for n in p['notes']]
    for turn, note in zip(user['answers_by_turn'], p['notes']):
        assert turn['chatbot_question'] == note['text'].split('\n답변: ', 1)[0]
        assert [s['id'] for s in turn['answer_sentences']] == [s['id'] for s in d4.sentences(p)
                                                              if s['note_id'] == note['id']]
    for leaked in ('expected', 'reference', 'rationale', '"family": '):
        assert leaked not in json.dumps(body, ensure_ascii=False)
    assert d5.turns(one_note('비가 오면 기다리셨어요.', question=''))[0]['chatbot_question'] == ''


def test_requests_build_for_every_dev128_and_eval64_input():
    for r in [*DEV128.values(), *EVAL64.values()]:
        d5.request(r['personal'], 'model-x')  # raises on the 40 000-byte input cap


def test_schema_puts_roles_first_one_fixed_key_per_sentence_and_behaviors_last():
    p = personal('P29')
    s = d5.schema(p)
    assert list(s['properties']) == ['sentence_roles', 'corrections', 'behaviors']
    roles = s['properties']['sentence_roles']
    ids = [x['id'] for x in d4.sentences(p)]
    assert roles['required'] == ids and roles['additionalProperties'] is False
    assert list(roles['properties'][ids[0]]['properties']) == ['subject', 'role']
    item = s['properties']['behaviors']['items']
    assert list(item['properties'])[-1] == 'overrides'
    assert item['properties']['sentence_ids']['items']['enum'] == ids


def test_interface():
    assert d5.RELEASE_QUALIFIED is False
    assert re.fullmatch(r'contract-d5-[a-z0-9-]+-20261007-research', d5.VERSION)
    assert d5.KINDS == d4.KINDS and d5.MAX_SENTENCES == d4.MAX_SENTENCES
    every = [r['personal'] for r in [*DEV128.values(), *EVAL64.values()]] + [personal(p) for p in PEOPLE]
    assert all(d5.sentences(p) == d4.sentences(p) for p in every)


# ---------------------------------------------------------- prompt

def test_prompt_differs_from_d4_only_by_the_listed_changes():
    restored = d5.SYSTEM_D5
    for old, new in reversed(d5.PROMPT_CHANGES):
        assert d4.SYSTEM_D4.count(old) == 1 and restored.count(new) == 1
        restored = restored.replace(new, old)
    assert restored == d4.SYSTEM_D4
    assert 'other_sentences' not in d5.SYSTEM_D5
    assert '질문은 챗봇이 한 말이고' not in d5.SYSTEM_D5


def test_prompt_names_no_evaluation_trait_and_adds_no_example_value():
    assert [w for w in EVAL_TRAIT_WORDS if w in d5.SYSTEM_D5] == []
    values = sorted(re.findall(r'"value":(\d+(?:\.\d+)?)', d5.SYSTEM_D5))
    assert values == sorted(re.findall(r'"value":(\d+(?:\.\d+)?)', d4.SYSTEM_D4))


def test_prompt_text_written_for_d5_shares_no_word_pair_with_any_answer():
    # Word pairs already in the replaced D4 text are inherited, not written for D5.
    shared = bigrams(ANSWERS)
    for old, new in d5.PROMPT_CHANGES:
        own = bigrams(new) - bigrams(old)
        assert not own & shared, (new[:30], sorted(own & shared))


# ---------------------------------------------- D5-05 accounting

def test_trait_accounting_keeps_d4_keys_and_adds_engine_support():
    out = d5.from_d3(to_d3(D_CORRECT['P29']), personal('P29'))
    acct = d5.trait_accounting(out)
    d4_keys = set(d4.trait_accounting(to_d3(D_CORRECT['P29'])))
    assert d4_keys < set(acct) and set(acct) - d4_keys == {'by_role', 'engine_support'}
    assert list(acct['by_kind']) == list(d4.KINDS)
    assert acct['engine_support']['supported'] == 2 and acct['observed_rules'] == 2
    lost = output(P21, [behavior(['N1.s2'], 'walk', [cl(['lost_awareness'])])],
                  {'N1.s1': ('correction', 'patient'), 'N1.s3': ('not_representable', 'patient')})
    support = d5.trait_accounting(lost)['engine_support']
    assert support['not_representable'] == 1 and support['not_representable_sentence_ids'] == ['N1.s3']
    held = output(ABSENT, [behavior(['N0.s1', 'N0.s2'], 'wait', [cl(false=['family_present'])], hold=10)])
    acct = d5.trait_accounting(held)
    assert acct['unexecuted_wait_hold'] == 1
    assert acct['engine_support']['semantics_incomplete_behaviors'] == {'0': ['unexecuted_wait_hold']}
    assert d5.trait_accounting(None)['by_kind'] == {k: 0 for k in d4.KINDS}


def test_engine_input_key_preserves_rule_order_and_normalizes_equivalent_conditions():
    base = d5.compile_d5(two([(1, 'N0.s3')]), TWO_RULES)
    swapped = output(TWO_RULES, [
        behavior(['N0.s2'], 'walk', [cl(['lost_awareness']), cl(['lost_awareness', 'dark_observed'])]),
        behavior(['N0.s3', 'N0.s1'], 'wait', [cl(['rain_observed'])], overrides=[(0, 'N0.s3')])])
    assert not d5.same_engine_input(base, d5.compile_d5(swapped, TWO_RULES))
    same_order = two([(1, 'N0.s3')], walk=[cl(['lost_awareness']),
                                           cl(['lost_awareness', 'dark_observed'])])
    assert d5.same_engine_input(base, d5.compile_d5(same_order, TWO_RULES))
    other = d5.compile_d5(two([(1, 'N0.s3')], wait=[cl(['rain_observed'], ['family_present'])]), TWO_RULES)
    assert not d5.same_engine_input(base, other)


def test_reordering_conflicting_actions_is_not_identical_engine_input():
    base = d5.compile_d5(two(), TWO_RULES)
    reversed_policy = base.model_copy(update={'rules': list(reversed(base.rules))})
    facts = {'rain_observed': True, 'lost_awareness': True}
    first, _ = m.applicable(base, facts)
    second, _ = m.applicable(reversed_policy, facts)
    # Population uses options[selected_index]; the same index now executes a
    # different action even though the unordered collection of rules is equal.
    assert first[0].action != second[0].action
    assert not d5.same_engine_input(base, reversed_policy)


def test_correction_drift_counts_changes_inside_and_outside_the_located_errors():
    first = two(walk=[cl(['is_walking'])])
    assert codes(first, TWO_RULES) == ['degenerate_branch_only_is_walking']
    fix = two(walk=[cl(['lost_awareness'])], wait=[cl(['dark_observed'])])
    drift = d5.correction_drift(first, fix, TWO_RULES)
    assert (drift['inside'], drift['outside']) == (1, 1)
    assert drift['changed'] == ['behaviors[0].start_when_any', 'behaviors[1].start_when_any']


# ---------------------------------------------- replay and runner

def test_from_d3_maps_roles_by_the_documented_rule():
    out3 = to_d3(D_CORRECT['P21'])
    out3['other_sentences'].append({'sentence_ids': ['N1.s2'], 'subject': 'patient', 'kind': 'unobserved'})
    out5 = d5.from_d3(out3, P21)
    assert out5['sentence_roles']['N1.s1'] == {'subject': 'other_person', 'role': 'correction'}
    assert out5['sentence_roles']['N1.s2'] == {'subject': 'patient', 'role': 'behavior_source'}  # cited wins
    assert out5['corrections'] == [] and all(b['overrides'] == [] for b in out5['behaviors'])
    d5.compile_d5(out5, P21)


def test_runner_can_load_score_and_account_d5_without_running_anything(monkeypatch):
    expected = ('contract_d5', 'compile_d5', 'PLAN_d5.md')
    if 'd5' in run_v2.CANDIDATES:  # registered by the one-line run_v2 change
        assert run_v2.CANDIDATES['d5'] == expected
    monkeypatch.setitem(run_v2.CANDIDATES, 'd5', expected)
    module, compile_fn, plan = run_v2.load_candidate('d5')
    assert (module, compile_fn, plan) == (d5, d5.compile_d5, 'PLAN_d5.md')
    names = {p.name for p in run_v2.sources('d5')}
    assert {'PLAN_d5.md', 'contract_d5.py', 'contract_d4.py', 'run_v2.py'} <= names
    p = personal('P21')
    public = {'finish_reason': 'stop', 'final_content': json.dumps(p21(), ensure_ascii=False)}
    problem, kind, policy = run_v2.judge(public, p, compile_fn)
    assert problem is None and [r.action for r in policy.rules] == ['walk']
    bad = {'finish_reason': 'stop', 'final_content': json.dumps(p21(roles={'N1.s3': ('qualifies_behavior', 'patient')}),
                                                                ensure_ascii=False)}
    problem, kind, policy = run_v2.judge(bad, p, compile_fn)
    assert kind == 'role_not_cited' and policy is None and len(problem) <= TOTAL
    traits = run_v2.traits(module, bad, compiled=False)
    assert traits['compiled'] is False and set(traits['by_kind']) == set(d5.KINDS)
    assert run_v2.jobs_for('d5_dev8', module, [{'id': 'P21', 'personal': p}])[0]['body']['messages'][0]['content'] \
        == d5.SYSTEM_D5


def test_shared_modules_are_not_modified_by_d5():
    assert contract_d.SENTENCE_END.pattern == r'(?<=[.?!。])\s+'
    assert contract_d3.compile_d3 is not d5.compile_d5 and d4.SYSTEM_D4 != d5.SYSTEM_D5
    assert d5.ab.ACTION_MEANING.count('- rest: 보행을 멈추고 앉아서 쉰다. 신체 회복이다.') == 1
