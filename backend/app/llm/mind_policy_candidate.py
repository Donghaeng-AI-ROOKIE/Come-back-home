"""D12 service candidate with a separately grounded finite-wait continuation.

No clinical release claim. A new contract version requires fresh validation;
frozen D12 results apply only to the base contract.
"""
from copy import deepcopy
import json
from app.llm import mind_policy as m, mind_policy_compact as compact
from app.llm.initial_behavior import _validate_shape

VERSION = m.VERSION
EXTENSION = '''
사건 경계: 보호자와 실제 재회해 안전이 확인되면 실종 사건이 종결된다. 이는 앱의 확인된 종결 처리이며 AI가 도착 시각을 상상하거나 걷기 재개 명령을 만드는 일이 아니다. 과거 관찰의 가족 도착 조건은 역사적 대기 범위를 설명할 뿐 미래 관측으로 넣지 않는다.
각 규칙에 after_wait 배열을 추가한다. 기본은 빈 배열이다. 원문이 '일정 시간 기다린 다음 실제로 걷거나 등록 장소로 출발했다'고 명시한 경우에만 항목 하나를 넣는다. 대기 지속시간 hold_minutes가 있어야 한다. 가족 도착·발견·관찰 종료만으로 후속 행동을 만들지 않는다. 대기 종료 후 행동을 못 봤거나 모르면 빈 배열이다.
after_wait 항목: action=walk 또는 seek, goal_place=seek만 등록 장소 이름(나머지 빈 문자열), note_id=근거 문답, quote=대기 시간과 뒤이은 실제 이동을 뒷받침하는 답변의 연속 인용. 단순 능력·희망을 후속 행동으로 만들지 않는다. after_wait는 대기가 중간에 취소됐을 때가 아니라 정해진 시간이 끝났을 때만 실행한다. 범위가 없는 후속 이동을 새로운 독립 규칙으로 동시에 발동시키지 않는다. 표현할 수 없는 후속 반응은 source_assessment에 명시하고 창작하지 않는다.
'''


def schema(personal):
    out = compact.schema_a(personal)
    labels = [p['label'] for p in personal['places']]
    item = out['properties']['rules']['items']
    item['properties']['after_wait'] = {'type': 'array', 'maxItems': 1, 'items': compact._obj({
        'action': {'type': 'string', 'enum': ['walk', 'seek']},
        'goal_place': {'type': 'string', 'enum': [''] + labels},
        'note_id': {'type': 'string', 'enum': [n['id'] for n in personal['notes']]},
        'quote': {'type': 'string'}})}
    item['required'].append('after_wait')
    return out


def request(personal, model, draft=None):
    body = compact.request(personal, model, allow_finite_wait_entry=True)
    body['messages'][0]['content'] += EXTENSION
    payload = json.loads(body['messages'][1]['content'])
    payload['output_schema'] = schema(personal)
    if draft is not None:
        payload['draft_to_review'] = draft
        payload['task'] = '같은 원문과 다시 대조해 누락·왜곡을 수정한 최종 JSON을 출력한다. 초안을 그대로 유지할 의무는 없다.'
    body['messages'][1]['content'] = json.dumps(payload, ensure_ascii=False)
    body['response_format']['json_schema']['schema'] = schema(personal)
    return compact.bounded(body)


def compile(value, personal):
    _validate_shape(value, schema(personal))
    base = deepcopy(value)
    continuations = [row.pop('after_wait') for row in base['rules']]
    if any(len(rows) > 1 for rows in continuations):
        raise ValueError('one follow-up per finite wait')
    policy = compact.compile_d12(base, personal, allow_finite_wait_entry=True)
    by_id = {r.id: r for r in policy.rules}
    for i, rows in enumerate(continuations):
        if not rows:
            continue
        follow = rows[0]
        rule = by_id['a_' + str(i)]
        if follow['note_id'] not in [e.note_id for e in rule.evidence]:
            raise ValueError('follow-up must share the source of its waiting episode')
        if follow['action'] == 'walk' and follow['goal_place']:
            raise ValueError('walk cannot silently discard a follow-up destination')
        # The common validator verifies the actual quoted source and known goal.
        rule.after_wait = m.AfterWait(action=follow['action'], goal_label=follow['goal_place'] or None,
            evidence=[m.Evidence(note_id=follow['note_id'], quote=follow['quote'])])
    return m.validate(policy.model_dump(mode='json'), personal)
