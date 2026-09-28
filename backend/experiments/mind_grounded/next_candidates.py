"""Prepared follow-up candidates. No live runner or authorization in this module."""
import json
from .context_view import presentation
from .contract import facts, obj, enum
from .nonthinking import request_spec as previous, validate as validate_previous
from experiments.mind_upgrade.contract import validate_decision
from app.llm.initial_behavior import SOURCE_PRECEDENCE


def request_spec(context, model, variant):
    if variant=='explicit_time':
        body=previous(context,'k',model)
        visible=presentation(context)
        visible['engine_state_facts']={k:v for k,v in facts(context).items() if k in ('fatigue_band','rest_phase')}
        body['messages'][1]['content']=json.dumps(visible,ensure_ascii=False)
        return body
    if variant not in ('minimal','minimal_thinking'):raise ValueError('unknown candidate')
    ids=[n['id'] for n in context['person']['evidence_notes']]
    labels=[x['label'] for x in context['known_places']]
    s=obj({'action':enum(['continue','seek','roam','rest','stay','avoid']),
           'goal_operation':enum(['keep','set','clear']),
           'goal_label':{'enum':labels+[None]},
           'avoid_feature':{'enum':['water','forest','market','park',None]},
           'evidence_ids':{'type':'array','items':enum(ids),'minItems':1},
           'reason':{'type':'string'},
           'confusion_level':enum(['high','medium','low','unknown'])})
    system=SOURCE_PRECEDENCE+'''
온보딩된 특정 치매 어르신의 현재 행동을 해석한다. 한국어로 답한다.
보호자 원문에 나타난 조건·부정·예외를 현재 시뮬레이션 상태와 비교하여 지금 행동을 고른다.
이전 행동과 목적지는 과거 실행 상태이며, 현재 조건에 맞지 않으면 유지할 필요가 없다.
사건의 발생 경과분과 '몇 분 전'을 구분한다. 휴식 완료와 피로 회복은 다른 사실이다.
가까운 지도 시설과 공급된 소음·혼잡 관측은 다르다. unknown을 true/false로 지어내지 않는다.
연구 집단 경향이나 모델의 이전 요약으로 보호자 원문을 덮지 않는다.
continue: 이전 이동 유지, seek: 등록 목적지 지정, roam: 목적 없는 이동,
rest: 잠시 쉬고 재평가, stay: 제자리 머무름, avoid: 해당 환경에서 멀어지는 길 선호.
seek는 set과 등록 goal_label, roam은 clear, continue/rest/stay/avoid는 keep을 쓴다.
set이 아니면 goal_label은 null, avoid가 아니면 avoid_feature는 null이다.
reason은 현재 상태→관련 개인 조건→선택 행동을 연결한 공개 근거 1~2문장(400자 이하)이다.
evidence_ids는 실제 보호자 원문 ID를 참조한다. 원문을 새로 만들어 인용하지 않는다.
JSON 하나만 반환한다. 좌표·확률·보행 속도·휴식 시간을 만들지 않는다.
출력 스키마:
'''+json.dumps(s,ensure_ascii=False)
    body={'model':model,'messages':[{'role':'system','content':system},
            {'role':'user','content':json.dumps(presentation(context),ensure_ascii=False)}],
          'temperature':1.,'top_p':.95,'presence_penalty':0.,'max_tokens':6000,
          'chat_template_kwargs':{'enable_thinking':variant=='minimal_thinking'},'parse_reasoning':True}
    if variant=='minimal':body['response_format']={'type':'json_schema','json_schema':{'schema':s}}
    return body


def validate(value,context,variant):
    if variant=='explicit_time':return validate_previous(value,context)
    d=validate_decision(value,context)
    if d.action in ('stay','avoid') and d.goal_operation!='keep':raise ValueError('preserve goal during stay/avoid')
    notes={n['id'] for n in context['person']['evidence_notes']}
    if not set(d.evidence_ids)<=notes:raise ValueError('guardian evidence required')
    return d
