"""D15 with concise source condition closure and actionable coverage feedback.

Never fills actions, conditions, evidence or source classifications in code.
Coverage feedback is a set difference of typed note IDs, not language parsing.
"""
from experiments.mind_contract_ab_20261007 import contract_d15 as base, contracts

VERSION = 'd16-condition-closure-coverage-feedback-20261008-research'
RELEASE_QUALIFIED = False
SAMPLING = dict(base.SAMPLING)
correction = base.correction
trait_accounting = base.trait_accounting


def request(personal, model):
    body = base.request(personal, model)
    body['messages'][0]['content'] += '''
source_assessment는 짧은 근거 요약이다. 실제 반응마다 근거 문답 ID와 함께 시작 조건, 종료·예외 조건(관찰 없으면 없음)을 한 줄로 먼저 적고, rules의 condition에 그 조건 전체를 보존한다. 질문의 상황을 짧은 답이 확인한 경우 질문과 답을 한 근거로 읽는다.
applies_only_at은 현재 그 장소 주변에 있다는 공간 범위이며 도착 사건이나 알아봄의 대체 조건이 아니다. 실제 도착과 장소 인지가 함께 관찰된 반응에는 physical_arrival과 target_recognized를 각각 보존한다. 근거에 없는 도착·인지 조건을 추가하지 않는다.
'''
    return base.bounded._bounded(body)


def compile_d16(value, personal):
    try:
        return base.compile_d15(value, personal)
    except ValueError as error:
        if str(error) != 'source_omitted_without_classification':
            raise
        parsed = contracts.OutputA.model_validate(value)
        covered = set(parsed.non_action_note_ids)
        covered.update(n for row in parsed.rules for n in row.note_ids)
        covered.update(e.note_id for row in contracts.fixed(personal) for e in row.evidence)
        missing = sorted({n['id'] for n in personal['notes']} - covered)
        raise ValueError('source_omitted_without_classification: missing note IDs ' + ', '.join(missing)
                         + '. 원문을 다시 읽고 각 ID가 실행 규칙 근거인지 비행동 정보인지 판정하라. '
                           '누락을 없애려고 무조건 non_action으로 넣지 말라.') from error
