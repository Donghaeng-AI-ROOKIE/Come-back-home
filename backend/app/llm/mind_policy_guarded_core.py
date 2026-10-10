"""Research core: source/actor clarification plus explicit partial recovery.

Recovery never chooses a rule using expected answers, rewrites conditions, or
supplies a destination. Only individually compilable rules survive, with losses
reported separately from interpretation correctness.
"""
from copy import deepcopy
import json
from app.llm import mind_policy as m, mind_policy_compact as compact
from app.llm.initial_behavior import _validate_shape
from app.llm import mind_policy_core as core

VERSION = 'd12-core-actor-guarded-20261009-research'
REVIEW_POLICY = 'on_validation_failure'
RELEASE_QUALIFIED = False


def request(personal, model, draft=None):
    body = core.request(personal, model, draft=draft)
    body['messages'][0]['content'] += '''
규칙의 주체는 어르신이다. 보호자의 질문 답변에서 화자·인용 속 화자·실제 행동 주체를 구별한다. 보호자가 찾으러 간 일이나 함께 귀가시킨 일을 어르신의 독립 이동으로 만들지 않는다. '제가'라는 단어만으로 판단하지 말고 인용과 문장 전체의 주체를 본다. 예: '어머니는 기다렸고 제가 데리러 갔어요'는 어머니의 기다림만, '어머니가 등록된 은행을 알아보고 그쪽으로 먼저 걸어갔어요'는 어머니의 seek이다. 등록 장소가 있어도 가족의 행동에 그 장소를 붙이지 않는다.
is_walking은 모든 행동의 공통 안전 조건이 아니다. 보행 한계에 따른 신체 휴식에는 필요하지만 장소 회피에는 원문이 걷는 중으로 한정할 때만 쓴다. '시끄러우면 피함'은 서 있거나 기다리는 중에도 해당할 수 있으므로 임의로 is_walking을 추가하지 않는다. 원문이 명시적으로 '걷는 중일 때만'이라고 하면 그 한정은 보존한다. 대기에도 스스로 대기를 끝내는 걷기 조건을 넣지 않는다.
source_assessment에는 어르신이 실제로 한 행동을 적고 보호자가 한 후속 조치를 섞지 않는다. 불확실한 정보로 이동 목적지나 후속 행동을 채우지 않는다.'''
    return compact.bounded(body)


def repair_request(personal, model, draft, problem):
    body = request(personal, model)
    payload = json.loads(body['messages'][1]['content'])
    payload.update(previous_public_output=deepcopy(draft), validation_error=problem,
        task='검사 오류를 고친 완전한 JSON을 출력한다. 오류 행동의 주체와 원문 근거부터 재확인한다. 근거 없는 seek를 고치려고 목적지를 임의로 채우지 않는다. 정상적인 규칙의 조건·수치·범위는 보존한다.')
    body['messages'][1]['content'] = json.dumps(payload, ensure_ascii=False)
    return compact.bounded(body)


def compile(value, personal):
    return compact.compile_d12(value, personal)


def recover(value, personal):
    """After the one correction fails: quarantine invalid rules, never repair.

    Malformed envelopes, unclassified source notes, invalid fixed rules and no
    surviving rule remain failures. A partial note stays visibly unrepresented
    even when another rule grounded in the same note survives.
    """
    _validate_shape(value, compact.schema_a(personal))
    parsed = compact.OutputA.model_validate(value)
    ids = {n['id'] for n in personal['notes']}
    fixed = compact.fixed(personal)
    covered = ({e.note_id for r in fixed for e in r.evidence}
               | set(parsed.non_action_note_ids)
               | {n for r in parsed.rules for n in r.note_ids})
    if covered != ids:
        raise ValueError('source_omitted_without_classification')
    # Check fixed rules once before isolating any generated rule.
    skeleton = {'source_assessment': parsed.source_assessment,
                'rules': [], 'non_action_note_ids': sorted(ids)}
    baseline = compact.compile_d12(skeleton, personal)
    rules = list(baseline.rules)
    quarantined = []
    for index, item in enumerate(parsed.rules):
        single = {**skeleton, 'rules': [item.model_dump()],
                  'non_action_note_ids': sorted(ids - set(item.note_ids))}
        try:
            compiled = compact.compile_d12(single, personal)
        except (ValueError, TypeError, KeyError, AssertionError, AttributeError, SyntaxError) as error:
            quarantined.append({'rule_index': index, 'note_ids': item.note_ids,
                                'reason': type(error).__name__ + ': ' + str(error)[:240]})
            continue
        generated = [r for r in compiled.rules if r.id == 'a_0']
        if len(generated) != 1:
            raise ValueError('unexpected isolated rule count')
        rules.append(generated[0].model_copy(update={'id': 'a_'+str(index)}))
    if not quarantined or not rules:
        raise ValueError('no usable partial recovery')
    lost = {n for q in quarantined for n in q['note_ids']}
    missing = [{'note_id': n, 'reason': 'partial_rule_quarantine: invalid rule withheld; source meaning not fully verified'}
               for n in sorted(lost)]
    missing += [{'note_id': n, 'reason': parsed.source_assessment[:1200]}
                for n in parsed.non_action_note_ids if n not in lost]
    policy = m.validate({'rules': [r.model_dump() for r in rules], 'unrepresented': missing}, personal)
    return policy, {'status': 'partial', 'quarantined_rules': quarantined,
                    'quarantined_rule_count': len(quarantined),
                    'retained_rule_count': len(rules),
                    'partially_unrepresented_note_ids': sorted(lost),
                    'semantic_correctness_claimed': False}


def _rule_signature(rule):
    when = sorted(sorted((a.fact, a.op, str(a.value)) for a in clause) for clause in rule.when)
    return (rule.action, rule.feature, rule.goal_label, rule.hold_minutes,
            tuple(sorted({e.note_id for e in rule.evidence})), json.dumps(when))


def restore_draft_scope(draft_value, policy, personal):
    """A correction must not silently widen a place-limited rule.

    The correction request asks to keep valid rules' scope. When a draft rule
    that compiles on its own is repeated in the correction with identical
    action, target, duration, condition and source, but its place limit was
    dropped, the draft's place limit is restored. Added limits and condition
    changes are accepted as legitimate corrections. Nothing else is altered.
    """
    if not isinstance(draft_value, dict):
        return policy, []
    try:
        _validate_shape(draft_value, compact.schema_a(personal))
        parsed = compact.OutputA.model_validate(draft_value)
    except Exception:
        return policy, []
    ids = {n['id'] for n in personal['notes']}
    standalone = []
    for item in parsed.rules:
        if not item.applies_only_at:
            continue
        single = {'source_assessment': parsed.source_assessment, 'rules': [item.model_dump()],
                  'non_action_note_ids': sorted(ids - set(item.note_ids))}
        try:
            compiled = compact.compile_d12(single, personal)
        except (ValueError, TypeError, KeyError, AssertionError, AttributeError, SyntaxError):
            continue
        standalone += [r for r in compiled.rules if r.id == 'a_0']
    by_signature = {}
    for rule in standalone:
        by_signature.setdefault(_rule_signature(rule), []).append(rule)
    restored = []; rules = []
    for rule in policy.rules:
        match = by_signature.get(_rule_signature(rule), []) if not rule.place_labels else []
        scopes = {tuple(r.place_labels) for r in match}
        if len(scopes) == 1:
            scope = list(next(iter(scopes)))
            restored.append({'rule_id': rule.id, 'restored_place_labels': scope})
            rule = rule.model_copy(update={'place_labels': scope})
        rules.append(rule)
    if not restored:
        return policy, []
    out = m.validate({'rules': [r.model_dump() for r in rules],
                      'unrepresented': [u.model_dump() for u in policy.unrepresented]}, personal)
    return out, restored
