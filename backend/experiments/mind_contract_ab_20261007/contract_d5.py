"""Candidate D5 (2026-10-07): D4 with sentence roles, correction and precedence
relations, question context, all-errors-at-once feedback and engine-support
accounting. Not release qualified.

Design: results/d3_dev128_analysis/D5_설계.md, overridden by
D5_설계_수정결정.md (user review 2026-10-07). The decision that governs this
file: a personal trait is never dropped from what the contract can express in
order to match an existing test answer. Concretely:
  - Continuing to walk under fatigue, pain or a walking limit, when the
    guardian saw it, is a walk rule with that condition (the engine already
    lets such a walk override the general fatigue rest:
    person_walk.Population._explicit_physical_walk). 'Did not see a rest' is
    unobserved and makes no rule.
  - rest is NOT required to start while walking. The prompt asks for
    is_walking when the person stopped to rest while walking and for the
    stated situation otherwise; a rest that can start while not walking is
    counted (diagnostic rest_not_while_walking, engine support
    'semantics_incomplete'), never rejected.
  - A rest started by a situation alone, and any behavior started by false
    facts alone (absence conditions, e.g. waiting while no family is near),
    are accepted.
  - No check bans a kind of behavior. Besides D4's checks, D5 rejects only
    what is logically non-executable (a precedence that makes a rule never
    run, a precedence cycle) or inconsistent with the model's own declarations
    (sentence roles, correction relations, override evidence).
The D5_설계.md checks rest_without_is_walking (D5-01), walk_without_event
(D5-02) and situational_only_rest (D5-03) are therefore NOT rejections here;
the latter two remain diagnostics. rule_always_conflicts (D5-08) is a
diagnostic, not a rejection: two overlapping rules without a stated
precedence are executable as an unresolved branch, and 'unknown' can be the
right answer.

Changes on D4 (D5-04 .. D5-12 of the design):
  D5-04 compile_d5 collects every error it can check and reports them at once,
        each with a location and a prescription (<= 200 characters a line,
        <= 800 joined, the run_v2 limit); errors that cite a sentence carry
        its text verbatim. Only shape/type errors stop the checks early. The
        structured list is CompileErrors.items and errors(); run_v2 stores the
        text, so aggregation recomputes the list offline from saved responses.
        correction(): compile errors get the local-fix wording (A-7); the
        completion statuses keep C's wording; incomplete_length returns the
        previous output without its trailing whitespace.
  D5-05 diagnostics(), engine_input_key(), correction_drift(), silent collapse
        and the engine-support split live here as pure functions (run_v2 and
        the scoring modules are frozen by manifest hashes).
  D5-06 sentence_roles: a fixed-key object, one required key per sentence
        ({subject, role}), first in the output; other_sentences is gone;
        behaviors come last.
  D5-07 corrections: [{sentence_id, retracts, amends}], between the roles and
        the behaviors. Deviation from the design, which put retracts/amends
        inside every role value: with those fields every sentence repeats two
        arrays, and the largest eval64 input then exceeds the shared
        40 000-byte input cap (contracts._body; measured 40 846 bytes). One
        list also keeps the ID enum server-enforced. The checks are the
        design's.
  D5-08 behaviors[i].overrides -> Rule.supersedes.
  D5-09 answers_by_turn (question once per answer, structure only).
  D5-10 .. D5-12 prompt paragraphs (PROMPT_CHANGES, applied to SYSTEM_D4 with
        D4's exactly-once _apply).
D4's checks are kept unchanged in meaning and wording. Shared constants and
functions of earlier candidates are not modified.
"""
from __future__ import annotations

import json
import re

from pydantic import Field, StrictFloat, StrictInt, ValidationError

from app.llm import mind_policy as m
from app.llm.initial_behavior import _validate_shape
from experiments.mind_contract_ab_20261007 import contract_c as c
from experiments.mind_contract_ab_20261007 import contract_d as d
from experiments.mind_contract_ab_20261007 import contract_d3 as d3
from experiments.mind_contract_ab_20261007 import contract_d4 as d4
from experiments.mind_contract_ab_20261007 import contracts as ab
from experiments.mind_policy_candidates.condition_program import expression, fixed

RELEASE_QUALIFIED = False
VERSION = 'contract-d5-roles-relations-trait-preserving-20261007-research'
SAMPLING = dict(d4.SAMPLING)
MAX_SENTENCES = d4.MAX_SENTENCES
BEHAVIOR_KINDS = d4.BEHAVIOR_KINDS
OTHER_KINDS = d4.OTHER_KINDS
KINDS = d4.KINDS  # trait_accounting keeps D4's keys
SOURCE_ROLES = ('behavior_source', 'qualifies_behavior')
ROLES = SOURCE_ROLES + ('correction', 'corrected_away', 'capacity_only', 'stated_goal', 'unobserved',
                        'hearsay_or_general', 'other_information', 'not_representable')
LINE_LIMIT = 200   # one error line
ERROR_LIMIT = 800  # run_v2.ERROR_CHARS: every line joined with ' | '
BODY_FACTS = ('pain_observed', 'fatigue_high') + ab.PHYSICAL  # person_walk's physical set plus pain
sentences = d4.sentences
answer_text = d4.answer_text

# Dev128 inputs whose reference has no walk rule although the answer reports
# continued movement under fatigue, pain or a walking limit. Hand-curated by
# reading dev128 (2026-10-07), not computed from text. Their reference answers
# stay as they are; a D5 walk rule there is scored by the existing reference
# and reported separately as disputed (PLAN_d5.md).
DISPUTED_DEV128 = {
    'DEV_P08_original': 'kept going after 12 min and when short of breath; rested only on pain',
    'DEV_P08_preserve': 'kept going past 12 min and when short of breath; rested only on pain',
    'DEV_P08_counterfactual': 'never stopped for shortness of breath alone',
    'DEV_P08_hard': 'corrected to: kept walking when short of breath; past 12 min without pain kept going',
    'DEV_P19_counterfactual': 'did not rest on fatigue alone or on pain alone',
}
# Read the same way but closer to an ability statement; for the human review only.
REVIEW_DEV128 = {'DEV_P06_preserve': "'walks 25 minutes without resting': observed continuation or capacity_only"}


# ------------------------------------------------------------------- input

def turns(personal):
    """answers_by_turn: one entry per note, its chatbot question once, its sentences.

    chatbot_question is the note text before the first '\\n답변: ' (structure
    only; nothing is interpreted). A note without a question has ''.
    """
    by_note = {}
    for s in sentences(personal):
        by_note.setdefault(s['note_id'], []).append({'id': s['id'], 'text': s['text']})
    out = []
    for n in personal['notes']:
        parts = n['text'].split('\n답변: ', 1)
        out.append({'note_id': n['id'], 'chatbot_question': parts[0] if len(parts) == 2 else '',
                    'answer_sentences': by_note.get(n['id'], [])})
    return out


def schema(personal):
    labels = ab._labels(personal)
    sids = [s['id'] for s in sentences(personal)]
    sid = {'type': 'string', 'enum': list(sids)}
    ids = {'type': 'array', 'items': sid}
    role = ab._obj({'subject': {'type': 'string', 'enum': list(ab.SUBJECTS)},
                    'role': {'type': 'string', 'enum': list(ROLES)}})
    correction_item = ab._obj({'sentence_id': sid, 'retracts': ids, 'amends': ids})
    condition = {'type': 'array', 'items': d._clause_schema()}
    override = ab._obj({'behavior': {'type': 'number'}, 'sentence_id': sid})
    behavior = ab._obj({'sentence_ids': ids,
                        'kind': {'type': 'string', 'enum': list(BEHAVIOR_KINDS)},
                        'action': {'type': 'string', 'enum': list(ab.ACTIONS)},
                        'goal_place': {'type': 'string', 'enum': [''] + labels},
                        'applies_only_at': {'type': 'array', 'items': {'type': 'string', 'enum': labels}},
                        'start_when_any': condition,
                        'end_when_any': condition,
                        'hold_minutes': {'type': 'number'},
                        'overrides': {'type': 'array', 'items': override}})
    return ab._obj({'sentence_roles': ab._obj({s: role for s in sids}),
                    'corrections': {'type': 'array', 'items': correction_item},
                    'behaviors': {'type': 'array', 'items': behavior}})


# ------------------------------------------------------------------- prompt
# Every new text shares no Hangul word pair with any dev128 or eval64 answer
# beyond the D4 text it replaces (tests/test_mind_contract_d5.py).

ANSWER_INPUT = ('answers_by_turn은 문답마다 note_id, chatbot_question(챗봇의 질문), answer_sentences(답변을 문장으로 '
                '나눈 것)를 담는다. 출력은 sentence_roles, corrections, behaviors 순서로 적는다.')

BEHAVIOR_FIELDS = ('각 항목은 근거 문장 1~5개, action, goal_place, applies_only_at, start_when_any(반드시 한 분기 이상), '
                   'end_when_any, hold_minutes, overrides를 적는다. 근거 문장은 behavior_source 문장을 하나 이상 포함하고 '
                   'behavior_source와 qualifies_behavior 문장만 인용한다.')

TWO_RESPONSES = '서로 다른 조건에서 일어난 반응이 둘이면 항목을 둘로 만들고 같은 문장을 함께 인용한다.'

ROLE_TEXT = """sentence_roles: 문장 ID마다 subject(그 문장이 말하는 행동·사실의 주인. patient=대상 어르신 본인, other_person=다른 사람, unclear=불분명)와 role을 적는다. role은 질문과 함께 읽은 뜻으로 정한다.
- behavior_source: 본인이 실제로 한 반응을 말하는 문장. 질문이 물은 행동을 확인하는 짧은 답도 포함한다.
- qualifies_behavior: 다른 문장이나 질문이 말한 본인 반응에 조건(언제 하는지, 하지 않는지, 끝나는지), 범위, 출처, 횟수를 보태거나 확인하는 문장.
- correction: 앞 진술을 거두거나 고치기만 하는 문장. corrected_away: 다른 문장이 거둔 진술.
- capacity_only(걸을 수 있는 능력뿐), stated_goal(바람·싫음·다짐을 말로만 함), unobserved(보지 못함·모름), hearsay_or_general(보호자의 짐작·일반론·남에게 들은 말), other_information(행동이 아닌 정보), not_representable(본인이 실제로 보인 반응이지만 제공된 사실·행동으로 나타낼 수 없음).
역할이 섞이면 behavior_source, qualifies_behavior, 그 밖의 역할 순으로 고른다."""

RELATIONS = """corrections에는 정정을 말한 문장마다 sentence_id, retracts, amends를 하나씩 적는다. 앞 진술 전체를 거두거나 다른 사람의 일로 돌렸으면 그 문장 ID를 retracts에, 수치·조건·대상 하나만 고쳤으면 amends에 넣는다. retracts에 넣은 문장은 corrected_away이며 행동의 근거가 아니다. amends 대상은 바뀐 부분만 정정 문장을 따른다. 정정 문장이 본인에 대해 고친 값을 말하면 그 문장은 behavior_source나 qualifies_behavior다. 정정 대상이 질문 속 말이거나 문답 밖이면 corrections에 적지 않는다.
overrides는 두 반응의 조건이 함께 성립할 때의 우선이다. 항목 i의 overrides에 {behavior: j, sentence_id: s}가 있으면 항목 i의 조건이 참인 동안 항목 j(behaviors에서 0부터 센 위치)는 하지 않는다. 원문이 두 조건이 함께 있던 상황에서 이 반응만 했거나 먼저 했다고 말한 경우에만 적고, 그 문장 s를 이 항목의 sentence_ids에도 넣는다. 겹친 상황을 말하지 않았거나 별개라고만 했거나 모른다고 하면 []이다. 우선만 나타내려고 다른 항목의 조건을 부정해 넣을 필요는 없다. 원문이 그 반응의 조건으로 명시한 부정은 false에 쓴다."""

END_RULE = ('답변이, 또는 답변이 받아들인 질문이 반응이 끝나는 상황을 말하면 그 상황을 end_when_any에 쓴다. '
            '질문이 앞서 말한 반응이 끝나는 때를 묻고 답변이 그때 그 반응을 그쳤다고 하면 '
            '새 행동 대신 그 반응의 end_when_any로 쓴다. 종료가 어디에도 없으면 []이다.')

# D5-10 plus the revised D5-01 (is_walking guidance, never a rejection) and the
# revised walk B decision (observed continued movement is a walk rule).
CONDITION_PRINCIPLES = """조건을 옮기는 원칙:
1. 원문이 반응에 모두 필요하다고 한 조건은 같은 분기에 넣는다. 어느 하나로도 반응했다고 하면 조건마다 분기를 만들고, 공통 조건은 분기마다 반복한다.
2. 원문이 어떤 상태가 아닐 때 반응했다고 하면 그 사실 이름을 false에 넣는다. 참인 사실로 바꿔 적지 않는다. 어떤 상태의 부재만으로 시작된 반응은 false만 있는 분기로 써도 된다.
3. 앉아 있던 시간은 hold_minutes에만 쓴다. continuous_walk_minutes에는 원문이 말한 쉬기 전 보행 시간만 쓴다.
4. 걷던 중에 멈춰 쉰 반응이면 rest의 분기마다 true에 is_walking을 넣는다. 서 있거나 기다리던 중에 쉰 반응이면 원문이 말한 그 상황을 조건으로 쓰고 is_walking은 넣지 않는다.
5. 피로·통증이나 걸은 시간·거리의 한계에 이르렀는데도 멈춤 없이 이동을 이어 간 모습을 보호자가 직접 보았다면 본인의 반응이다. action=walk인 항목으로 만들고 분기마다 true에 is_walking과 그 상태나 한계를 넣는다. 그 상태에서 쉬는 모습을 보지 못했다는 말뿐이면 unobserved이고 규칙이 없다. 보행 능력 진술은 capacity_only다."""

# D5-11 (A-5) and D5-12 (A-6).
SCOPE_AND_SOURCE = """반응의 조건과 범위:
1. 보호자가 계기로 한 조건절에 묶어 말한 상황은 모두 같은 분기에 넣는다. 짧은 답이라 질문이 계기를 정했다면 질문 속 상황도 넣는다.
2. 관찰 경위(누구와 함께였는지, 횟수, 확인 방법)는 조건이 아니다. 그 경위 밖에서는 하지 않았다거나 보지 못했다고 따로 말했을 때만 조건이다.
3. 반응의 범위를 넓히거나 좁히는 문장(그 상황이 아닐 때의 무반응, 늘 있던 상황이 빠졌을 때의 미관찰, 다른 장소의 관찰 여부)은 qualifies_behavior로 그 반응에 인용하고 조건이나 applies_only_at에 반영한다.
4. 관찰 당시 어떤 사실이 있었는지 모른다는 문장과 두 반응이 겹친 때를 보지 못했다는 문장은 unobserved이며 규칙을 바꾸지 않는다.
5. applies_only_at: 답변이 반응을 특정 등록 장소에서 봤다고 하면 그 장소로 한정하고, 같은 유형의 여러 곳이나 장소와 상관없이 같았다고 하면 []이다. 등록 장소 목록의 이름·개수·유형은 범위의 근거가 아니다.
근거의 출처:
- 조건(시작·종료)에는 반응이 시작되거나 끝날 때 원문이 말하거나 관찰한 상황만 넣는다. 그 순간 관찰된 상황은 어떤 연결 표현으로 이어지든 조건이다.
- 반응의 배경으로 든 지속적 이유(몸 상태, 병력, 성격)는 조건이 아니다. 통증·피로는 원문이 그 순간 말하거나 보였다고 할 때만 조건이다.
- 다른 사람의 행동, 보호자의 짐작, 전해 들은 말, 거둔 진술은 조건의 근거가 아니다. 보호자·가족의 동행이나 도착은 대상 어르신 반응의 조건이다.
- 본인이 실제로 보인 반응이나 보호자가 판단한 신체 한계를 알려 주는 문장은 behavior_source이고, 나타낼 수 없으면 not_representable이다.
- stated_goal은 그 조건에서 행동으로 옮기는 것을 보호자가 보지 못한 발언이다. 휴식을 바란다는 발언만 있는 것도 stated_goal이다."""

# D5-09 (A-8), replacing the inherited question sentence of SOURCE_RULES.
QUESTION_CONTEXT = ("질문은 챗봇의 말이라 인용할 수 없지만 답의 뜻은 질문에 기댄다. "
                    "(가) 예/아니오 질문을 답이 긍정하면 질문이 물은 상황·행동·종료 조건 전체를 보호자가 진술한 것이다. "
                    "(나) 질문이 제시한 상황에서의 행동을 답이 말하면 그 상황은 행동의 조건이다. "
                    "(다) 답이 조건을 덧붙이거나 좁히면 질문의 조건에 더해 쓴다. 답이 일부만 다시 말해도 부정하지 않은 상황은 남는다. "
                    "(라) 답이 질문의 일부를 부정·정정하거나 상관없다고 하면 그 부분은 답을 따른다. "
                    "뒤 문답이 앞 답을 거두면 앞 답은 corrected_away다. "
                    "(마) 그렇게 하라고 권했다거나 짐작한다는 답은 관찰이 아니며, 질문의 상황만으로 행동을 만들지 않는다. "
                    "주어가 없는 문장의 주어는 같은 답의 앞 문장이 정한 사람, 그다음 질문이 묻는 사람이고, "
                    "그것도 없으면 대상 어르신이다.")

_OTHER_LINE = next(x for x in d4.SYSTEM_D4.split('\n') if x.startswith('other_sentences:'))
_HOLD_LINE = 'hold_minutes는 원문이 말한 휴식·대기 지속 시간만 쓰고 모르면 0이다. 쉬기 전에 걸은 시간이 아니다.'
_NUMBERS_LINE = '숫자는 원문의 수를 아라비아 숫자로 정확히 옮긴다.'

# (D4 text, D5 text). Each D4 text occurs exactly once in SYSTEM_D4.
PROMPT_CHANGES = (
    ('질문은 챗봇이 한 말이고 답변만 보호자의 진술이다.', '답변은 보호자의 진술이다.'),
    ('answer_sentences는 각 답변을 문장으로 나눈 것이다. 출력은 두 목록이다.', ANSWER_INPUT),
    ('각 항목은 근거 문장 1~5개, action, goal_place, applies_only_at, start_when_any(반드시 한 분기 이상), '
     'end_when_any, hold_minutes를 적는다.', BEHAVIOR_FIELDS),
    ('한 문장에 행동이 둘이면 항목을 둘로 만들고 같은 문장을 함께 인용한다.', TWO_RESPONSES),
    (_OTHER_LINE, ROLE_TEXT),
    ('모든 문장은 behaviors나 other_sentences 중 적어도 한 곳에 나와야 한다. 행동이 없는 문장도 other_sentences에 넣는다. '
     '정정된 다른 사람 이야기와 본인의 관찰은 서로 다른 항목이다.', RELATIONS),
    ('종료가 원문에 없으면 [].', END_RULE),
    (_NUMBERS_LINE, _NUMBERS_LINE + '\n' + CONDITION_PRINCIPLES),
    ('그 문장은 other_sentences(other_information)에 둘 수 있다.', '그 문장의 role은 other_information으로 둘 수 있다.'),
    ('- rest: 보행을 멈추고 앉아서 쉰다. 신체 회복이다.',
     '- rest: 앉아서 쉰다. 신체 회복이다. 걷던 중에 쉬었는지 서 있거나 기다리던 중에 쉬었는지는 조건으로 나타낸다(조건을 옮기는 원칙 4).'),
    (_HOLD_LINE, _HOLD_LINE + '\n' + SCOPE_AND_SOURCE),
    ("- '그건 다른 사람 이야기였다' → corrected_away 또는 other_person. 그 행동을 본인에게 넣지 않는다.",
     '- 앞 진술을 다른 사람의 일로 돌린 문장 → role=correction이고 corrections에서 거둔 문장 ID를 retracts에 적는다. '
     '거둔 문장은 corrected_away이며 그 행동을 본인에게 넣지 않는다.'),
    ("text가 '질문: …/답변: …' 형식이면 질문은 챗봇이 한 말이고 보호자 진술이 아니다. "
     "답변만 보호자 진술이며, 짧은 답은 그 질문의 맥락으로 해석한다.", QUESTION_CONTEXT),
)

SYSTEM_D5 = d4._apply(d4.SYSTEM_D4, PROMPT_CHANGES)


def request(personal, model, *, thinking=True):
    payload = ab._payload(personal)
    payload['answers_by_turn'] = turns(personal)
    payload['output_schema'] = schema(personal)
    body = ab._body(SYSTEM_D5, payload, model, thinking)
    body.update(SAMPLING)
    body['response_format'] = {'type': 'json_schema', 'json_schema': {'schema': schema(personal)}}
    return body


# ------------------------------------------------------------- correction
# D5-04 (A-7): for compile errors only. The completion statuses (no parseable
# JSON) keep C's wording, which allows a reinterpretation.
LOCAL_FIX = ('오류가 요구하는 부분만 고친다. 이전 출력의 나머지 값은, 같은 항목 안의 다른 숫자·사실·장소 한정까지 '
             '포함해 그대로 옮겨 적는다. 원문을 다시 읽어 이전 값이 원문과 다르다고 확인한 경우에만 그 값을 고친다.')
REINTERPRET = '형식 문제만이 아니라 해석이 틀렸다면 바로잡아도 된다.'


def correction(first_body, first_public, problem):
    """Second call: same input, the previous final answer and the validator error only."""
    body = c.correction(first_body, first_public, problem)
    previous = (first_public or {}).get('final_content') or ''
    if problem == 'incomplete_length':
        # The cut-off output without its trailing whitespace run; an output of
        # whitespace only gets C's wording for an empty output.
        body['messages'][-2]['content'] = previous.rstrip()[:20000] or '(최종 출력 없음)'
    if problem not in c.ERROR_HELP:  # a compile error, not a completion status
        text = body['messages'][-1]['content']
        if text.count(REINTERPRET) != 1:
            raise RuntimeError('C correction text changed; re-review the D5 correction wording')
        body['messages'][-1]['content'] = text.replace(REINTERPRET, LOCAL_FIX)
    return body


# ----------------------------------------------------------------- models

class Override(m.Strict):
    behavior: StrictInt | StrictFloat
    sentence_id: str


class BehaviorD5(d3.Behavior):
    overrides: list[Override] = Field(max_length=8)


class Role(m.Strict):
    subject: str
    role: str


class Correction(m.Strict):
    sentence_id: str
    retracts: list[str] = Field(max_length=32)
    amends: list[str] = Field(max_length=32)


class OutputD5(m.Strict):
    sentence_roles: dict[str, Role]
    corrections: list[Correction] = Field(max_length=32)
    behaviors: list[BehaviorD5] = Field(max_length=16)


# ------------------------------------------------------------- error lines

class CompileErrors(ValueError):
    """Every error found, one line each; items keep code/where/text/quote for aggregation."""

    def __init__(self, items):
        self.items = items
        super().__init__(compose(items))


def _error(code, where, text, quote=None):
    return {'code': code, 'where': where, 'text': text, 'quote': quote}


def _line(e):
    head = f"{e['code']}({e['where']}): " if e['where'] else f"{e['code']}: "
    body = e['text']
    if e['quote'] is not None:
        room = LINE_LIMIT - len(head) - len(body) - len(' 원문 ""')
        if room > 1:
            quote = e['quote'] if len(e['quote']) <= room else e['quote'][:room - 1] + '…'
            body = f'{body} 원문 "{quote}"'
    line = head + body
    return line if len(line) <= LINE_LIMIT else line[:LINE_LIMIT - 1] + '…'


def compose(items):
    """Error lines joined by newlines; joined by ' | ' (run_v2.describe) they fit ERROR_LIMIT."""
    lines = list(dict.fromkeys(_line(e) for e in items))
    out, used = [], 0
    for k, line in enumerate(lines):
        sep = 3 if out else 0
        tail = 3 + 60 if k < len(lines) - 1 else 0
        if used + sep + len(line) + tail > ERROR_LIMIT:
            left = lines[k:]
            codes = ','.join(dict.fromkeys(x.split('(', 1)[0].split(':', 1)[0] for x in left))
            more = f'more_errors: 외 {len(left)}건 ({codes})'
            room = ERROR_LIMIT - used - sep
            out.append(more if len(more) <= room else more[:max(room - 1, 0)] + '…')
            break
        out.append(line)
        used += sep + len(line)
    return '\n'.join(out)


def _path(parts):
    text = ''
    for p in parts:
        if isinstance(p, int):
            text += f'[{p}]'
        elif re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', str(p)):
            text += ('.' if text else '') + str(p)
        else:
            text += f'["{p}"]'
    return text or '(최상위)'


# ------------------------------------------------------------------ shape

SHAPE_LIMIT = 6


def _shape(value, sch, parts, out):
    """Like initial_behavior._validate_shape but collects located errors (up to SHAPE_LIMIT)."""
    if len(out) >= SHAPE_LIMIT:
        return
    kind = sch['type']
    where = _path(parts)
    if kind == 'object':
        if not isinstance(value, dict):
            out.append(_error('schema_mismatch', where, '객체여야 한다. output_schema를 따른다.'))
            return
        missing = [k for k in sch['properties'] if k not in value]
        extra = sorted(k for k in value if k not in sch['properties'])
        if missing or extra:
            out.append(_error('schema_mismatch', where, f"키가 다르다(빠짐: {','.join(missing)[:50] or '-'} / "
                                                       f"남음: {','.join(extra)[:50] or '-'}). 정해진 키를 하나씩만 쓴다."))
        for k, child in sch['properties'].items():
            if k in value:
                _shape(value[k], child, parts + [k], out)
    elif kind == 'array':
        if not isinstance(value, list):
            out.append(_error('schema_mismatch', where, '배열이어야 한다.'))
            return
        for i, child in enumerate(value):
            _shape(child, sch['items'], parts + [i], out)
    elif kind == 'string':
        if not isinstance(value, str):
            out.append(_error('schema_mismatch', where, '문자열이어야 한다.'))
        elif 'enum' in sch and value not in sch['enum']:
            out.append(_error('schema_mismatch', where, f'허용되지 않은 값 "{value[:30]}". output_schema의 목록에서 고른다.'))
    elif kind == 'number':
        if type(value) not in (float, int) or value != value or value in (float('inf'), float('-inf')):
            out.append(_error('schema_mismatch', where, '유한한 숫자여야 한다.'))


def _pydantic_errors(error, skip):
    out = []
    for e in error.errors(include_url=False):
        loc = tuple(e.get('loc', ()))
        if any(loc[:len(s)] == s for s in skip):
            continue
        out.append(_error('invalid_value', _path(list(loc)), str(e.get('msg', ''))[:120]))
    return out


# --------------------------------------------------------- logic on rows

def _constraints(row):
    """(truth, low, high) of a compiled AND row that can hold, or None if it never holds.

    Same domain as d4.dead_branch: numeric facts >= 0, clock_hour < 24.
    Bounds are (value, strict).
    """
    if d4.dead_branch(row) is not None:
        return None
    truth, low, high = {}, {}, {'clock_hour': (d4.CLOCK_END, True)}
    for a in row:
        fact, op, value = a['fact'], a['op'], a['value']
        if fact in m.BOOLEAN_FACTS:
            truth[fact] = value
            continue
        low.setdefault(fact, (0, False))
        if op in ('gte', 'gt', 'eq'):
            low[fact] = max(low[fact], (value, op == 'gt'))
        if op in ('lte', 'lt', 'eq'):
            bound = (value, op == 'lt')
            high[fact] = min(high.get(fact, bound), bound, key=lambda b: (b[0], not b[1]))
    return truth, low, high


def _implied(cons, atom):
    truth, low, high = cons
    fact, op, value = atom['fact'], atom['op'], atom['value']
    if fact in m.BOOLEAN_FACTS:
        return truth.get(fact) is value
    lo, hi = low.get(fact, (0, False)), high.get(fact)
    if op == 'gte':
        return lo[0] >= value
    if op == 'gt':
        return lo[0] > value or (lo[0] == value and lo[1])
    if op == 'lte':
        return hi is not None and hi[0] <= value
    if op == 'lt':
        return hi is not None and (hi[0] < value or (hi[0] == value and hi[1]))
    return hi is not None and lo == (value, False) and hi == (value, False)  # numeric eq


def row_implies(a, b):
    """True if every state satisfying row a satisfies row b (a row that never holds implies anything)."""
    cons = _constraints(a)
    return cons is None or all(_implied(cons, atom) for atom in b)


def when_implies(a, b):
    """Sufficient test that DNF a implies DNF b: each live row of a implies one row of b."""
    return all(any(row_implies(ra, rb) for rb in b) for ra in a if _constraints(ra) is not None)


def can_co_hold(a, b):
    return any(d4.dead_branch(ra + rb) is None for ra in a for rb in b)


def scope_within(inner, outer):
    """True if inner's spatial scope is provably inside outer's (dicts with place_labels, feature)."""
    if not outer['place_labels'] and not outer['feature']:
        return True
    if outer['place_labels']:
        return bool(inner['place_labels']) and set(inner['place_labels']) <= set(outer['place_labels'])
    return not inner['place_labels'] and inner['feature'] == outer['feature']


def _command(rule):
    return (rule['action'], rule['goal_label'], rule['feature'])


def _cycle(edges, n):
    """One precedence cycle as a list of behavior indexes, or None."""
    state = [0] * n

    def visit(i, stack):
        state[i] = 1
        for j in sorted(edges.get(i, ())):
            if state[j] == 1:
                return stack[stack.index(j):] + [j]
            if state[j] == 0:
                found = visit(j, stack + [j])
                if found:
                    return found
        state[i] = 2
        return None
    for i in range(n):
        if state[i] == 0:
            found = visit(i, [i])
            if found:
                return found
    return None


# ------------------------------------------------------------------ checks

def _analyse(value, personal):
    """(errors, parsed, compiled). compiled[i] holds the rule fields of behavior i, or None.

    Shape and type errors stop the analysis (later checks need the parsed
    structure); every other error is collected.
    """
    errors = []
    _shape(value, schema(personal), [], errors)
    if errors:
        return errors, None, None
    try:
        _validate_shape(value, schema(personal))
    except ValueError as error:  # a disagreement with the shared validator is reported, never ignored
        return [_error('schema_mismatch', '(최상위)', str(error)[:120])], None, None
    skip = []
    for i, b in enumerate(value['behaviors']):
        n = len(b['sentence_ids'])
        if n > MAX_SENTENCES:
            errors.append(_error('too_many_sentences_for_one_rule', f'behaviors[{i}]',
                                 f'근거 문장은 항목마다 {MAX_SENTENCES}개까지다. 꼭 필요한 문장만 남긴다.'))
            skip.append(('behaviors', i, 'sentence_ids'))
        if not n:
            errors.append(_error('item_without_sentence_ids', f'behaviors[{i}]', '근거 문장을 1개 이상 적는다.'))
            skip.append(('behaviors', i, 'sentence_ids'))
        if not b['start_when_any']:
            errors.append(_error('behavior_without_condition', f'behaviors[{i}]',
                                 'start_when_any에 분기를 1개 이상 적는다.'))
            skip.append(('behaviors', i, 'start_when_any'))
    try:
        parsed = OutputD5.model_validate(value)
    except ValidationError as error:
        return errors + _pydantic_errors(error, skip), None, None
    if errors:
        return errors, None, None

    by_id = {s['id']: s for s in sentences(personal)}
    roles = parsed.sentence_roles
    fixed_notes = {e.note_id for r in fixed(personal) for e in r.evidence}
    cited_by = {}
    for i, b in enumerate(parsed.behaviors):
        for s in b.sentence_ids:
            cited_by.setdefault(s, []).append(i)

    def quote(sid):
        return by_id[sid]['text'] if sid in by_id else None

    # D5-06 roles, with D3/D4's subject rule for not_representable
    for sid, r in roles.items():
        if r.role == 'not_representable' and r.subject != 'patient':
            errors.append(_error('not_representable_must_be_the_person', sid,
                                 'not_representable은 대상 어르신 본인의 반응에만 쓴다. subject나 role을 고친다.', quote(sid)))
        if r.role == 'behavior_source' and r.subject != 'patient':
            errors.append(_error('behavior_source_not_patient', sid,
                                 'subject는 그 행동의 주인이다. 대상 어르신의 행동이 아니면 role을 바꾼다.', quote(sid)))
        if r.role in SOURCE_ROLES and sid not in cited_by and by_id[sid]['note_id'] not in fixed_notes:
            errors.append(_error('role_not_cited', f'{sid}={r.role}',
                                 '이 문장이 말하거나 한정하는 행동의 sentence_ids에 넣거나, 행동과 무관하면 role을 바꾼다.',
                                 quote(sid)))
    # D5-07 correction relations
    retracted_by, seen = {}, set()
    for k, x in enumerate(parsed.corrections):
        here = f'corrections[{k}] {x.sentence_id}'
        if x.sentence_id in seen:
            errors.append(_error('duplicate_correction_entry', here, '정정 문장마다 항목은 하나다. 같은 sentence_id의 항목을 합친다.'))
        seen.add(x.sentence_id)
        if x.sentence_id in x.retracts or x.sentence_id in x.amends:
            errors.append(_error('correction_self_reference', here, '자기 자신을 정정할 수 없다. retracts·amends에서 자기 ID를 뺀다.'))
        for t in sorted(set(x.retracts) & set(x.amends)):
            errors.append(_error('retracts_and_amends_same', f'{here}→{t}',
                                 '한 대상을 retracts와 amends에 함께 넣지 않는다. 전부 거뒀으면 retracts, 일부만 고쳤으면 amends.'))
        for t in dict.fromkeys(x.retracts):
            if t == x.sentence_id:
                continue
            retracted_by.setdefault(t, []).append(x.sentence_id)
            if roles[t].role != 'corrected_away':
                errors.append(_error('retract_target_not_corrected_away', f'{t}←{x.sentence_id}',
                                     '거둔 문장의 role은 corrected_away다. 일부만 고쳤다면 amends로 옮긴다.', quote(t)))
    for sid, r in roles.items():
        if r.role == 'corrected_away' and not retracted_by.get(sid):
            errors.append(_error('corrected_away_without_relation', sid,
                                 '거둔 정정 문장의 corrections 항목 retracts에 이 ID를 적거나, 정정이 아니면 다른 role로 바꾼다.',
                                 quote(sid)))

    compiled = [None] * len(parsed.behaviors)
    for i, b in enumerate(parsed.behaviors):
        here = f'behaviors[{i}]'
        if len(set(b.sentence_ids)) != len(b.sentence_ids):
            errors.append(_error('duplicate_sentence_id_in_item', here, '같은 문장 ID를 한 항목에 두 번 적지 않는다.'))
        if not any(roles[s].role == 'behavior_source' for s in b.sentence_ids):
            errors.append(_error('behavior_without_source', here,
                                 '근거 문장에 role=behavior_source 문장이 하나 이상 있어야 한다. 그 반응을 말한 문장의 role을 확인한다.'))
        for s in dict.fromkeys(b.sentence_ids):
            if retracted_by.get(s):
                errors.append(_error('withdrawn_sentence_used', f'{here} {s}←{retracted_by[s][0]}',
                                     '전부 거둔 문장은 근거가 아니다. 그 행동을 지우거나, 일부만 고쳤다면 amends로 옮긴다.', quote(s)))
            elif roles[s].role not in SOURCE_ROLES:
                errors.append(_error('behavior_cites_other_role', f'{here} {s}={roles[s].role}',
                                     '행동 근거는 behavior_source나 qualifies_behavior 문장만 된다. role을 고치거나 인용을 뺀다.',
                                     quote(s)))
        if b.kind == 'functional_need' and b.action != 'rest':
            errors.append(_error('functional_need_not_rest', here,
                                 'kind=functional_need의 action은 rest다. 쉼이 아니면 kind=observed_response로 쓴다.'))
        ok = True
        for part in ('start_when_any', 'end_when_any'):
            for k, clause in enumerate(getattr(b, part)):
                if not (clause.true or clause.false or clause.numbers):
                    ok = False
                    errors.append(_error('empty_condition_clause', f'{here}.{part}[{k}]',
                                         '빈 분기다. true, false, numbers 중 하나 이상을 채우거나 그 분기를 지운다.'))
                for n in clause.numbers:
                    if n.fact == 'clock_hour' and not 0 <= n.value <= d4.CLOCK_END:
                        ok = False
                        shown = d4._num(n.value)
                        shown = shown if len(shown) <= 7 else shown[:7] + '…'
                        errors.append(_error('clock_out_of_range', f'{here}.{part}[{k}] {n.op}{shown}', d4.CLOCK_HELP))
                    elif n.value < 0:
                        ok = False
                        errors.append(_error('negative_number', f'{here}.{part}[{k}] {n.fact}',
                                             '숫자 사실은 0 이상이다. 원문의 수를 그대로 옮긴다.'))
        if not b.applies_only_at:
            for k, clause in enumerate(b.start_when_any):
                # An empty branch is reported once, as empty_condition_clause.
                if (clause.true or clause.false or clause.numbers) and d4._walking_only(clause):
                    errors.append(_error(
                        'degenerate_branch_only_is_walking', f'{here}.start_when_any[{k}]',
                        '분기마다 is_walking 말고도 반응을 일으키는 사실이 있어야 한다(늘 참인 >=0, clock_hour<24는 '
                        '사실로 치지 않는다. 특정 등록 장소에서만 보인 반응은 applies_only_at으로 한정한다).'))
        try:
            action, goal, feature = ab._bind(b.action, b.goal_place, b.applies_only_at, personal)
        except ValueError as error:
            ok = False
            help_text = {'seek_without_registered_goal': 'seek의 goal_place에는 등록 장소 이름을 쓴다.',
                         'goal_on_non_seek': 'seek가 아니면 goal_place는 빈 문자열이다.',
                         'goal_used_as_scope': '목표 장소를 applies_only_at에 넣지 않는다.'}.get(str(error))
            errors.append(_error(str(error), here, help_text or '행동 필드를 확인한다.'))
        if not ok:
            continue
        start = d.render(b.start_when_any)
        text = f'({start}) and not ({d.render(b.end_when_any)})' if b.end_when_any else start
        try:
            when = expression(text)
        except Exception as error:  # noqa: BLE001 - reported with its location, never repaired
            errors.append(_error('invalid_condition', here, f'조건을 옮길 수 없다: {str(error)[:80]}'))
            continue
        for why in dict.fromkeys(why for why in map(d4.dead_branch, when) if why):
            help_text = d4.CLOCK_HELP if why.startswith('clock_hour') else d4.COMBINED_HELP
            errors.append(_error('unsatisfiable_branch', f'{here} {why}', help_text))
        try:
            ab._guard_walking_rest(action, when)
        except ValueError:
            errors.append(_error('walking_limited_rest_unguarded', here,
                                 '걸은 시간·거리 한계로 쉬는 rest는 그 분기마다 true에 is_walking을 넣는다.'))
        if action == 'wait' and any(d4._requires_walking(row) for row in when):
            errors.append(_error(
                'wait_cancels_itself_is_walking', here,
                '기다리기 시작하면 is_walking이 거짓이 되어 대기가 바로 꺼진다. wait 조건에 is_walking=참을 넣지 않는다'
                '(종료 조건의 is_walking 거짓 포함).'))
        compiled[i] = {'action': action, 'goal_label': goal, 'feature': feature, 'when': when,
                       'place_labels': list(b.applies_only_at)}

    # D5-08 overrides
    edges, total = {}, len(parsed.behaviors)
    for i, b in enumerate(parsed.behaviors):
        targets = set()
        for k, o in enumerate(b.overrides):
            here = f'behaviors[{i}].overrides[{k}]'
            j = o.behavior
            if j != int(j) or not 0 <= j < total:
                errors.append(_error('override_out_of_range', here, 'behavior는 behaviors 배열에서 0부터 센 위치(정수)다.'))
                continue
            j = int(j)
            if j == i:
                errors.append(_error('override_self', here, '자기 자신을 우선할 수 없다.'))
                continue
            if j in targets:
                errors.append(_error('override_duplicate', here, '같은 항목을 두 번 적지 않는다.'))
                continue
            targets.add(j)
            edges.setdefault(i, set()).add(j)
            if o.sentence_id not in b.sentence_ids:
                errors.append(_error('override_evidence_not_cited', f'{here} {o.sentence_id}',
                                     '우선을 말한 문장을 이 항목의 sentence_ids에도 넣는다.', quote(o.sentence_id)))
            win, lose = compiled[i], compiled[j]
            if win and lose and when_implies(lose['when'], win['when']) and scope_within(lose, win):
                errors.append(_error('over_never_runs', f'behaviors[{j}]←behaviors[{i}]',
                                     f'[{j}]의 조건이 성립할 때마다 [{i}]도 성립해 [{j}]는 실행되지 않는다. '
                                     '원문 근거가 없으면 overrides를 지우고, 거둔 내용이면 retracts로 옮긴다.'))
    loop = _cycle(edges, total)
    if loop:
        errors.append(_error('override_cycle', '→'.join(f'behaviors[{x}]' for x in loop),
                             '우선 관계가 돌고 돈다. 원문이 겹친 상황에서 한 쪽을 했다고 말한 방향 하나만 남긴다.'))
    return errors, parsed, compiled


def _build(parsed, compiled, personal):
    by_id = {s['id']: s for s in sentences(personal)}
    rules = [r.model_dump() for r in fixed(personal)]
    for i, (b, rule) in enumerate(zip(parsed.behaviors, compiled)):
        rules.append({'id': f'd5_{i}', 'action': rule['action'], 'when': rule['when'],
                      'goal_label': rule['goal_label'], 'feature': rule['feature'],
                      'place_labels': rule['place_labels'], 'hold_minutes': b.hold_minutes or None,
                      'supersedes': [f'd5_{int(o.behavior)}' for o in b.overrides],
                      'evidence': [{'note_id': by_id[s]['note_id'], 'quote': by_id[s]['text']}
                                   for s in b.sentence_ids]})
    cited = {s for b in parsed.behaviors for s in b.sentence_ids}
    per_note = {}
    for sid, r in parsed.sentence_roles.items():
        if sid not in cited:
            per_note.setdefault(by_id[sid]['note_id'], {}).setdefault(f'{r.role}/{r.subject}', []).append(sid)
    # One entry per note: Policy.unrepresented holds at most 24.
    unrepresented = [{'note_id': n, 'reason': '; '.join(f"{k}:{','.join(v)}" for k, v in groups.items())[:1200]}
                     for n, groups in per_note.items()]
    return m.validate({'rules': rules, 'unrepresented': unrepresented}, personal)


def errors(value, personal):
    """Every error of an output as dicts (code, where, text, quote); [] if it compiles."""
    found, parsed, compiled = _analyse(value, personal)
    if found:
        return found
    try:
        _build(parsed, compiled, personal)
    except Exception as error:  # noqa: BLE001 - surfaced, never hidden
        return [_error(type(error).__name__, '', str(error)[:160])]
    return []


def compile_d5(value, personal):
    found, parsed, compiled = _analyse(value, personal)
    if found:
        raise CompileErrors(found)
    return _build(parsed, compiled, personal)


# ------------------------------------------------------------- accounting

def _has_walking(clause):
    return 'is_walking' in (clause.get('true') or [])


def _facts(clause):
    return set(clause.get('true') or []) | set(clause.get('false') or []) | {
        n.get('fact') for n in clause.get('numbers') or [] if isinstance(n, dict)}


def _engine_support(behaviors, roles):
    supported, incomplete = [], {}
    for i, b in enumerate(behaviors):
        why = []
        if b.get('action') == 'rest' and any(isinstance(cl, dict) and not _has_walking(cl)
                                             for cl in b.get('start_when_any') or []):
            # person_walk holds a rest for hold_minutes and then re-evaluates: a rest
            # whose condition holds while not walking repeats for as long as it holds.
            why.append('rest_not_while_walking')
        if b.get('action') == 'wait' and d4._positive(b.get('hold_minutes')):
            why.append('unexecuted_wait_hold')  # a wait lasts while its condition holds
        if why:
            incomplete[str(i)] = why
        else:
            supported.append(i)
    lost = [sid for sid, r in roles.items() if isinstance(r, dict) and r.get('role') == 'not_representable']
    return {'supported': len(supported), 'semantics_incomplete': len(incomplete), 'not_representable': len(lost),
            'supported_behaviors': supported, 'semantics_incomplete_behaviors': incomplete,
            'not_representable_sentence_ids': lost}


def trait_accounting(value):
    """D4's keys (by_kind over KINDS, trait loss, observed rules, wait hold) plus D5 additions.

    by_kind counts behaviors by kind and sentences by role for the roles that
    share a D4 kind name; D4 counted other_sentences items, so these counts
    are per sentence (not item for item comparable with D3/D4). by_role counts
    every role. engine_support splits the person's traits three ways:
    supported by contract and engine; sourced but with an incomplete engine
    meaning (a rest that can start while not walking repeats while its
    condition holds; a wait duration is not executed); not representable
    (trait loss).
    """
    value = value if isinstance(value, dict) else {}
    behaviors = [b for b in value.get('behaviors') or [] if isinstance(b, dict)]
    roles = value.get('sentence_roles') if isinstance(value.get('sentence_roles'), dict) else {}
    counts = {k: 0 for k in KINDS}
    by_role = {k: 0 for k in ROLES}
    for b in behaviors:
        if b.get('kind') in counts:
            counts[b['kind']] += 1
    for r in roles.values():
        role = r.get('role') if isinstance(r, dict) else None
        if role in by_role:
            by_role[role] += 1
        if role in counts and role not in BEHAVIOR_KINDS:
            counts[role] += 1
    held = [b for b in behaviors if b.get('action') == 'wait' and d4._positive(b.get('hold_minutes'))]
    support = _engine_support(behaviors, roles)
    return {'by_kind': counts, 'trait_loss_sentence_ids': support['not_representable_sentence_ids'],
            'observed_rules': counts['observed_response'] + counts['functional_need'],
            'unexecuted_wait_hold': len(held),
            'unexecuted_wait_hold_sentence_ids': [s for b in held for s in b.get('sentence_ids', [])],
            'by_role': by_role, 'engine_support': support}


# ------------------------------------------------------------ diagnostics
# D5-05: counted, never rejected. They need a parseable output; a behavior
# whose condition does not compile is left out of the rule-pair diagnostics.

def diagnostics(value, personal, reference=None):
    found, parsed, compiled = _analyse(value, personal)
    if parsed is None:
        return {'readable': False, 'errors': [e['code'] for e in found]}
    roles = parsed.sentence_roles
    out = {'readable': True, 'errors': [e['code'] for e in found],
           'rest_not_while_walking': [], 'situational_only_rest': [], 'functional_need_without_body': [],
           'walk_without_true_event': [], 'absence_only_branches': [], 'physical_walk': [],
           'noop_override': [], 'rule_always_conflicts': [], 'redundant_rule': [],
           'amends_without_correction_cited': [], 'overrides': 0}
    amended = {t: x.sentence_id for x in parsed.corrections for t in x.amends}
    for i, b in enumerate(parsed.behaviors):
        clauses = [cl.model_dump() for cl in b.start_when_any]
        if b.action == 'rest' and any(not _has_walking(cl) for cl in clauses):
            out['rest_not_while_walking'].append(i)
        if b.action == 'rest' and any(
                (set(cl['true']) | set(cl['false'])) - {'is_walking', 'pain_observed', 'fatigue_high'}
                and not (_facts(cl) & set(BODY_FACTS)) for cl in clauses):
            out['situational_only_rest'].append(i)
        if b.kind == 'functional_need' and not any(_facts(cl) & set(BODY_FACTS) for cl in clauses):
            out['functional_need_without_body'].append(i)
        if b.action == 'walk' and any(
                not (set(cl['true']) - {'is_walking'})
                and not any(n['fact'] == 'clock_hour' and not d4._always_true(d.Number(**n)) for n in cl['numbers'])
                for cl in clauses):
            out['walk_without_true_event'].append(i)  # absence or a walking limit alone: accepted
        if any(cl['false'] and not cl['true'] and not cl['numbers'] for cl in clauses):
            out['absence_only_branches'].append(i)
        if b.action == 'walk' and any(_facts(cl) & set(BODY_FACTS) for cl in clauses):
            out['physical_walk'].append(i)
        out['overrides'] += len(b.overrides)
        for s in b.sentence_ids:
            if s in amended and amended[s] not in b.sentence_ids:
                out['amends_without_correction_cited'].append([i, s, amended[s]])
    rules = compiled or []
    for i, b in enumerate(parsed.behaviors):
        for o in b.overrides:
            j = o.behavior
            if j == int(j) and 0 <= j < len(rules) and j != i and rules[i] and rules[int(j)]:
                if not can_co_hold(rules[i]['when'], rules[int(j)]['when']):
                    out['noop_override'].append([i, int(j)])
    linked = {(i, int(o.behavior)) for i, b in enumerate(parsed.behaviors) for o in b.overrides
              if o.behavior == int(o.behavior)}
    for a, ra in enumerate(rules):
        for b_, rb in enumerate(rules):
            if a == b_ or not ra or not rb:
                continue
            if not (when_implies(ra['when'], rb['when']) and scope_within(ra, rb)):
                continue
            if (_command(ra) == _command(rb) and ra['place_labels'] == rb['place_labels']
                    and parsed.behaviors[a].hold_minutes == parsed.behaviors[b_].hold_minutes):
                out['redundant_rule'].append([a, b_])
            elif (_command(ra) != _command(rb) and not (ra['action'] == rb['action'] == 'seek')
                  and (a, b_) not in linked and (b_, a) not in linked):
                out['rule_always_conflicts'].append([a, b_])
    sources = sum(r.role == 'behavior_source' for r in roles.values())
    out['behavior_source_sentences'] = sources
    # Silent collapse: the reference has rules of its own but the output has no
    # behavior_source at all. Undefined without a reference (an input of
    # unobserved statements only rightly has none).
    out['silent_collapse'] = None
    if reference is not None:
        own = [r for r in reference.get('rules', []) if not str(r.get('id', '')).startswith('initial_')]
        out['silent_collapse'] = sources == 0 and not parsed.behaviors and bool(own)
        out['disputed_physical_walk'] = bool(out['physical_walk']) and not any(
            r.get('action') == 'walk' for r in reference.get('rules', []))
    return out


def disputed(input_id, policy, reference):
    """A physical walk rule where the reference has no walk rule (scores unchanged, reported apart)."""
    walks = [r for r in (policy.rules if policy else []) if r.action == 'walk'
             and any(a.fact in BODY_FACTS for row in r.when for a in row)]
    return {'input_id': input_id, 'listed': input_id in DISPUTED_DEV128,
            'physical_walk_rules': [r.id for r in walks],
            'reference_has_walk': any(r.get('action') == 'walk' for r in reference.get('rules', []))}


# ------------------------------------------------- engine-input identity

def _row_key(row):
    atoms = (a if isinstance(a, dict) else a.model_dump() for a in row)
    return tuple(sorted({(a['fact'], a['op'], a['value']) for a in atoms}, key=repr))


def _normal_when(when):
    rows = sorted(set(map(_row_key, when)), key=repr)
    # Absorption: a row holding every atom of another row adds nothing to the OR.
    return [r for r in rows if not any(o != r and set(o) <= set(r) for o in rows)]


def engine_input_key(policy):
    """Ordered rules as the engine reads them; ids/evidence are normalized away.

    DNF rows are deduplicated and absorbed. Rule order is retained because
    Population selects an index from the applicable rules with its seeded RNG.
    Sorting that list can label different same-seed actions as identical.
    Supersedes uses the target rule's content; this is not semantic equivalence.
    """
    rules = policy.rules if hasattr(policy, 'rules') else policy['rules']
    rules = [r.model_dump() if hasattr(r, 'model_dump') else r for r in rules]

    def base(r):
        return [r['action'], r['goal_label'], r['feature'], sorted(r['place_labels']), r['hold_minutes'],
                [list(x) for x in _normal_when(r['when'])]]
    by_id = {r['id']: base(r) for r in rules}
    keys = [base(r) + [sorted((by_id[s] for s in r['supersedes'] if s in by_id), key=repr)] for r in rules]
    return json.dumps(keys, ensure_ascii=False, default=str)


def same_engine_input(a, b):
    return engine_input_key(a) == engine_input_key(b)


# --------------------------------------------------------- correction drift

def correction_drift(first_value, fix_value, personal):
    """Values a correction changed, inside vs outside what the first output's errors located.

    An error locates behaviors[i] and every sentence ID it names. Behaviors are
    compared by position (an added or removed behavior counts once), roles by
    sentence ID, corrections by their sentence_id.
    """
    flagged_b, flagged_s = set(), set()
    sids = {s['id'] for s in sentences(personal)}
    for e in errors(first_value, personal):
        where = e['where'] or ''
        flagged_b |= {int(x) for x in re.findall(r'behaviors\[(\d+)\]', where)}
        flagged_s |= {x for x in re.findall(r'N\d+\.s\d+', where) if x in sids}
    count = {'inside': 0, 'outside': 0}
    changed = []

    def note(name, inside):
        changed.append(name)
        count['inside' if inside else 'outside'] += 1
    first, fix = first_value or {}, fix_value or {}
    fb, xb = first.get('behaviors') or [], fix.get('behaviors') or []
    for i in range(max(len(fb), len(xb))):
        if i >= len(fb) or i >= len(xb):
            note(f'behaviors[{i}]', i in flagged_b)
            continue
        for k in sorted(set(fb[i]) | set(xb[i])):
            if fb[i].get(k) != xb[i].get(k):
                note(f'behaviors[{i}].{k}', i in flagged_b)
    fr, xr = first.get('sentence_roles') or {}, fix.get('sentence_roles') or {}
    for sid in sorted(set(fr) | set(xr)):
        a, b = fr.get(sid) or {}, xr.get(sid) or {}
        for k in sorted(set(a) | set(b)):
            if a.get(k) != b.get(k):
                note(f'{sid}.{k}', sid in flagged_s)
    fc = {x.get('sentence_id'): x for x in first.get('corrections') or [] if isinstance(x, dict)}
    xc = {x.get('sentence_id'): x for x in fix.get('corrections') or [] if isinstance(x, dict)}
    for sid in sorted(set(fc) | set(xc), key=str):
        if fc.get(sid) != xc.get(sid):
            note(f'corrections[{sid}]', sid in flagged_s)
    return dict(count, changed=changed)


# ---------------------------------------------------------------- replay

def from_d3(value, personal):
    """A D3/D4 output in D5 shape, for replaying saved responses through compile_d5.

    D3 had no relation, precedence or role fields, so the mapping is fixed:
    a sentence cited by a behavior is behavior_source of the patient (D5's
    role priority); any other sentence takes its other_sentences kind and
    subject, except corrected_away, which becomes 'correction' (D3 cannot say
    which sentence withdrew which, so the relation checks are not replayable);
    a sentence D3 left out (allowed for fixed-rule notes) is
    other_information. corrections and overrides are empty.
    """
    ids = [s['id'] for s in sentences(personal)]
    behaviors = value['behaviors']
    cited = {s for b in behaviors for s in b.get('sentence_ids', [])}
    roles = {sid: {'subject': 'patient', 'role': 'behavior_source'} for sid in ids if sid in cited}
    for o in value['other_sentences']:
        for sid in o.get('sentence_ids', []):
            if sid in ids and sid not in roles:
                kind = o.get('kind')
                roles[sid] = {'subject': o.get('subject'), 'role': 'correction' if kind == 'corrected_away' else kind}
    for sid in ids:
        roles.setdefault(sid, {'subject': 'patient', 'role': 'other_information'})
    return {'sentence_roles': {sid: roles[sid] for sid in ids}, 'corrections': [],
            'behaviors': [dict(b, overrides=[]) for b in behaviors]}
