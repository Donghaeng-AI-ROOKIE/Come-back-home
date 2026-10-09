"""D12 core contract through the service lifecycle, with conditional correction.

This experiment does not qualify finite-wait continuations. Their absence must
remain an explicit representation limit; no post-wait movement is invented.
"""
from copy import deepcopy
import json
from app.llm import mind_policy_compact as compact

VERSION = 'd12-core-conditional-correction-20261009-research'
REVIEW_POLICY = 'on_validation_failure'
RELEASE_QUALIFIED = False


def request(personal, model, draft=None):
    if draft is not None:
        raise ValueError('use repair_request with the recorded validation error')
    body = compact.request(personal, model)
    body['messages'][0]['content'] += '''
실종 사건의 종료는 앱에서 확인된 발견·재회로 처리한다. 과거의 가족 도착을 미래에 반드시 발생할 관측으로 상상하지 않는다.
이 계약에는 대기 이후의 순차 행동을 표현하는 필드가 없다. 원문에 대기 이후의 실제 출발이 있다면 source_assessment에 표현 불가 한계를 명시한다. 그 후속 행동을 대기와 동시에 켜지는 독립 walk/seek 규칙으로 바꾸지 않는다. 현재 검증 범위는 휴식·대기·장소 회피이며 이것을 개인의 모든 특성 보존으로 주장하지 않는다.'''
    return compact.bounded(body)


def repair_request(personal, model, draft, problem):
    body = request(personal, model)
    payload = json.loads(body['messages'][1]['content'])
    payload.update(previous_public_output=deepcopy(draft), validation_error=problem,
        task='검사 오류를 수정한 완전한 JSON을 출력한다. 원문에 맞는 조건·수치·행동·장소 범위는 그대로 보존한다. 정답이나 현재 장면은 제공되지 않는다.')
    body['messages'][1]['content'] = json.dumps(payload, ensure_ascii=False)
    return compact.bounded(body)


def compile(value, personal):
    return compact.compile_d12(value, personal)
