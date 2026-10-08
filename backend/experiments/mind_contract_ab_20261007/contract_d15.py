"""Compact D12 plus concise source-to-action distinctions; research only."""
from experiments.mind_contract_ab_20261007 import contract_d12 as base, contract_d8 as bounded

VERSION='d15-compact-observed-action-20261008-research'
RELEASE_QUALIFIED=False
SAMPLING=dict(base.SAMPLING)
compile_d15=base.compile_d12
correction=base.correction
trait_accounting=base.trait_accounting


def request(personal,model):
    body=base.request(personal,model)
    body['messages'][0]['content']+='''
관찰된 행동을 설명에만 남기고 실행 규칙에서 빼지 않는다. 특히 대상자 본인이 특정 상황에서 실제로 계속 걸었다면 walk 규칙이다. 기본 보행처럼 보인다는 이유로 생략하지 않는다. 단순히 다른 행동을 안 했다는 부정이나 보행 능력만으로 walk를 만들지는 않는다. 다른 사람 이야기의 정정은 그 사람 정보만 철회하며, 같은 답변에 있는 대상자 본인의 별도 관찰은 남긴다.
짧은 긍정 답변은 연결된 질문 전체의 관찰을 확인한 것이다. 질문의 시작·종료 조건도 condition에 보존한다. 절대 시각 구간은 clock_hour 조건이다. hold_minutes는 원문에 명시된 경과 시간만 쓰며, 시간을 모르면0이다. 가족 귀환 같은 사건 종료를 임의의 분 수로 바꾸지 않는다.
fixed_rules가 같은 근거의 같은 행동과 조건을 이미 처리하면 새 장소 한정 규칙으로 중복하지 않는다. 기존 규칙에 없는 다른 관찰은 별도로 남긴다.
'''
    return bounded._bounded(body)
