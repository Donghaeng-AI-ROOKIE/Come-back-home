"""Review a frozen D12 draft against source only; no gold/scene feedback."""
import json
from experiments.mind_contract_ab_20261007 import contract_d12 as base, contract_d8 as bounded
VERSION='d14-compact-source-review-20261008-research'
RELEASE_QUALIFIED=False
SAMPLING=dict(base.SAMPLING)
correction=base.correction
compile_d14=base.compile_d12
trait_accounting=base.trait_accounting


def request_review(personal,model,draft):
    body=base.request(personal,model)
    body['messages'][0]['content'] += """
이번 요청은 기존 후보 규칙을 원문과 대조하는 재검토다. candidate_to_review는 틀릴 수 있는 이전 해석이며 근거가 아니다. 보호자 원문 전체와 질문 문맥이 우선이다.
각 행동의 주체·발동 조건·끝나는 조건·목적지·적용 장소·수치·예외를 원문과 대조하라. 여러 문답이 같은 행동을 설명하면 전체를 반영한 최종 조건으로 만들어라. 원문이 요구하는 조건을 빼거나 관찰하지 않은 사실을 추가한 부분만 고쳐라. 맞는 규칙을 임의로 바꾸지 말라. 방문·범위와 도착·인지는 서로 다르다. 시작·종료를 따로 적어 넓은 규칙이 제한을 무효로 만들지 않게 하라.
수정 여부에 상관없이 완전한 최종 JSON 하나를 같은 스키마로 출력한다. 검토 설명·새 필드는 추가하지 않는다. condition은 지정된 소문자 and/or/not 및 사실 이름과 숫자의 문법만 사용한다.
"""
    payload=json.loads(body['messages'][1]['content'])
    payload['candidate_to_review']=draft
    body['messages'][1]['content']=json.dumps(payload,ensure_ascii=False)
    return bounded._bounded(body)
