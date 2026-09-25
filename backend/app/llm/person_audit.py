"""Experimental semantic review; not a clinical or factual truth guarantee."""
import json

from app.llm import person_evidence

REVIEW = '''당신은 보호자 기록에서 시뮬레이션 초기 특성을 작성하는 최종 검토자다. draft는 다른 AI의 미검증 초안이며 정답도 개인 관찰도 아니다. 보호자 원문에서 다시 판단하고 초안의 value와 note_ids를 필요한 만큼 수정한다. 단순 JSON 형식 검토가 아니다.
각 항목의 정의에 해당하는 사실이 해당 note_ids에 실제로 있는지 확인한다. 원문이 허용하는 추론과 명시된 관찰을 혼동하지 않는다. 방향 변화는 이동 중 방향을 바꾼 근거가 필요하며 목적지 의도·길 잃음·멈춤만으로 방향을 정할 수 없다. 경로 경험이 없다고 확인한 기록과 경험 여부를 모른다는 기록을 구분한다. 장소를 표현하는 동의어는 문맥으로 해석한다.
각 사람의 목적, 경로 경험, 혼란 시 대처, 몸 능력은 함께 존재할 수 있다. 한 특성을 이유로 다른 특성을 제거하거나 만들어내지 않는다. 말의 주체와 시간도 유지한다. 가려는 말은 도착 관찰이 아니며, 도착을 못 봤다는 말은 도착하지 않았다는 뜻이 아니다. 최근 정정은 반영하되 같은 상황에서 해소되지 않은 두 보호자 관찰은 상충으로 보존한다.
먼저 각 항목에 대해 미확인이라고 명시한 원문이 있는지 확인한다. 이동 여부나 길을 찾는 행동을 설명한 문장으로 방향 선택 미확인이라는 기록을 뒤집지 않는다. 방향은 방위 유지·회전·온 길 재추적을 실제로 서술한 근거가 있어야 한다. 사건 시점에 적용되는 근거와 다른 시간대의 행동도 구분한다.
정의에 맞는 근거가 있는 항목은 보존하고, 확실하지 않다는 이유만으로 전부 unknown으로 지우지 않는다. 관련 근거가 없거나 원문에서 미확인이라고 한 항목은 unknown이다. 판단과 근거 ID는 원문이 뒷받침하는 내용만 사용한다. 개인 관찰 없는 연구 경향을 특정 사람의 행동 사실로 바꾸지 않는다. 최종 스키마에 맞는 전체 core JSON만 반환한다.'''


def request(payload, draft, model):
    body = person_evidence.request(payload, model)
    body['messages'][0]['content'] += '\n최종 검토 과업:\n' + REVIEW
    visible = json.loads(body['messages'][1]['content'])
    compact={k:({name:{'value':v['value'],'note_ids':v['note_ids']} for name,v in values.items()}
               if k in ['goals','routes'] else {'value':values['value'],'note_ids':values['note_ids']})
             for k,values in draft.items() if k!='environment'}
    visible['draft'] = {'status': 'unverified_model_interpretation', 'content': compact}
    body['messages'][0]['content'] += '\n최종 응답에는 설명문 없이 value와 note_ids만 작성한다. 설명은 원문과 연결해 표시하므로 새로 생성하지 않는다.'
    body['messages'][1]['content'] = json.dumps(visible, ensure_ascii=False)
    return body


validate = person_evidence.validate
