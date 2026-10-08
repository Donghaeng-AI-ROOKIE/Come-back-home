"""D12 representation, tighter cross-note condition composition; development only."""
from experiments.mind_contract_ab_20261007 import contract_d12 as base
from experiments.mind_contract_ab_20261007 import contract_d8 as bounded
VERSION='d13-compact-composed-conditions-20261008-research'
RELEASE_QUALIFIED=False
SAMPLING=dict(base.SAMPLING)
correction=base.correction
compile_d13=base.compile_d12
trait_accounting=base.trait_accounting


def request(personal,model):
    body=base.request(personal,model)
    body['messages'][0]['content'] += """
서로 다른 질문의 답변이 같은 행동의 시작·끝·예외를 설명하면, 모두 합친 최종 조건을 한 규칙으로 만든다. 뒤의 종료·예외 문장을 별도 규칙으로 덧붙이면서 앞의 넓은 규칙을 남겨 두지 않는다. OR로 합쳐진 규칙에서는 넓은 규칙 하나가 제한 전체를 무효로 만들기 때문이다. 같은 action이어도 실제로 서로 다른 관찰이면 합치지 않는다.
장소 범위(place_labels), 그 장소에 실제로 도착함(physical_arrival), 장소를 알아봄(target_recognized)은 서로 다르다. 원문이 도착과 인지를 모두 행동의 전제로 삼는다면 둘 다 condition에 남긴다. 그 장소 근처라는 범위만으로 도착을 증명하지 않는다. 반대로 단지 근처에서 반응한 경우에는 도착 조건을 새로 추가하지 않는다.
휴식은 시작과 지속이 분리된다. 걸음에서 멈추어 쉬는 관찰이면 시작 조건에 is_walking을 남긴다. 대기 중에도 통증 때문에 앉아 쉬었다고 관찰했다면 걷기를 필수 조건으로 넣지 않는다. 휴식 종료 뒤에도 같은 조건만으로 재시작하는지, 원문이 그 반복을 지지하는지 점검한다.
질문·답변과 조건식이 일치하는지 마지막으로 검토하되 검사 설명을 새 JSON 필드로 추가하지 않는다. 관찰되지 않은 이후 행동을 walk나wait로 보충하지 않는다. 숫자·목적지·공간 범위는 원문과 등록 목록에서만 가져온다.
"""
    return bounded._bounded(body)
