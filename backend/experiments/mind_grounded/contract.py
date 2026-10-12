"""Ground evidence and state before selecting an executable action.

Personal-language interpretation belongs to the model. Code only validates source
quotes, typed state facts, and the action interface; it never keyword-maps a person.
"""
import json
from copy import deepcopy
from app.llm.initial_behavior import SOURCE_PRECEDENCE
from experiments.mind_upgrade.contract import validate_decision


def obj(props):
    return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}

def enum(values): return {'type':'string','enum':list(values)}

def facts(context):
    s=context['state']
    fatigue=s['fatigue']
    return {'fatigue_band':'high' if fatigue>=.7 else 'medium' if fatigue>=.4 else 'low',
            'rest_phase':'resting' if s['current_action']=='rest' else 'completed' if s['last_rest_end_minutes'] is not None else 'not_recorded',
            'clock_time':context['clock_time'], 'current_action':s['current_action'],
            'current_target':s['target_label'],
            'note':'Engine categories, not clinical measurements. Rest completed does not by itself prove full recovery.'}


def schema(context):
    quote=obj({'note_id':enum(n['id'] for n in context['person']['evidence_notes']),
               'quote':{'type':'string'}})
    common={'evidence':{'type':'array','items':quote,'minItems':1,'maxItems':4},
            'state_check':obj({'fatigue_band':enum(['low','medium','high']),
                               'rest_phase':enum(['resting','completed','not_recorded'])}),
            'assessment':{'type':'string'},
            'confusion_level':enum(['high','medium','low','unknown'])}
    branches=[]
    for action in ['continue','seek','roam','rest','stay','avoid']:
        props={'action':enum([action])}
        if action=='seek': props['goal_label']=enum(p['label'] for p in context['known_places'])
        if action=='avoid':props['avoid_feature']=enum(['water','forest','market','park'])
        # A person without registered destinations cannot seek a fabricated label.
        if action=='seek' and not context['known_places']:continue
        branches.append(obj(props))
    common['decision']={'anyOf':branches}
    return obj(common)

SYSTEM=SOURCE_PRECEDENCE+'''
너는 치매 어르신 보행 시뮬레이션의 현재 행동을 결정한다. 개인 진술, 엔진 상태, 실제 관측, 연구를 구분한다.
원문의 특정 단어만 보고 행동을 정하지 않는다. 조건·부정·예외를 문맥으로 해석한다.
보호자 진술의 관련 짧은 구절을 evidence에 정확히 인용하고, 현재 상태가 그 조건에 맞는지 assessment에 1~2문장으로 요약한 뒤 decision을 낸다.
assessment는 공개 가능한 근거 요약이다. 내적 추론 과정을 장황하게 쓰지 않는다.
현재 피로가 높아도 무조건 쉬게 하지 않는다. 그 사람이 피곤할 때 실제로 어떻게 한다는 기록인지 확인한다.
반대로 '피곤하지 않으면 걷고 피곤하면 쉰다'를 '피곤해도 걷는다'로 바꾸지 않는다.
휴식 후 걸을 계획과 지금 휴식을 선택하는 것은 다르다. 이미 휴식이 끝났는지 현재 기록을 확인한다.
현재 행동은 이전 상태이며 정답 행동이 아니다. 조건이 바뀌었다면 새 행동을 선택할 수 있다.
지도상 가까운 장소는 실제로 보이거나 시끄럽다는 관측이 아니다. null은 미확인이며 false와 다르다.
불명확한 조건을 관측됐다고 단정하지 않는다. 문헌의 집단 경향을 개인 사실로 만들지 않는다.
행동: continue=이전 이동과 목적지 유지, seek=등록 목적지로 향함, roam=목적지 없는 이동,
rest=잠시 쉬고 재평가(목적지 보존), stay=그 자리에 머물고 재평가, avoid=특정 환경을 피하는 방향 선호(목적지 보존).
사람이나 가족을 기다리는 것은 그들을 찾으러 이동하는 행동과 다르다.
출력은 스키마에 맞는 JSON 하나. evidence→state_check→assessment→confusion_level→decision 순서.
속도·좌표·확률·휴식 시간을 생성하지 않는다. assessment는 400자 이내, 원문에 없는 확정적 관찰을 넣지 않는다.
'''


def request_spec(context, provider, model, variant='grounded'):
    visible=deepcopy(context);visible['engine_state_facts']=facts(context)
    instruction=SYSTEM
    if variant=='first_person':
        instruction+='\nassessment는 그 사람의 관점에서 지금 느낄 법한 짧은 근거 요약으로 쓰되, 주어지지 않은 감정·관찰을 확정하지 않는다.\n'
    body={'model':model,'messages':[{'role':'system','content':instruction},{'role':'user','content':json.dumps(visible,ensure_ascii=False)}]}
    s=schema(context)
    if provider=='dem5':
        body.update(temperature=.3,max_tokens=900,repetition_penalty=1.05,
                    chat_template_kwargs={'enable_thinking':False},guided_json=s)
    else:
        body.update(temperature=1.,top_p=.95,presence_penalty=0.,max_tokens=6000,parse_reasoning=True,
                    chat_template_kwargs={'enable_thinking':True},
                    response_format={'type':'json_schema','json_schema':{'schema':s}})
        body['messages'][0]['content']+='\n출력 스키마:\n'+json.dumps(s,ensure_ascii=False)
    return body


def validate(value, context):
    if not isinstance(value,dict) or set(value)!= {'evidence','state_check','assessment','confusion_level','decision'}:
        raise ValueError('wrong_envelope')
    notes={n['id']:n['text'] for n in context['person']['evidence_notes']}
    evidence=value['evidence']
    if not isinstance(evidence,list) or not 1<=len(evidence)<=4:raise ValueError('missing_evidence')
    ids=[]
    for e in evidence:
        if not isinstance(e,dict) or set(e)!= {'note_id','quote'}:raise ValueError('wrong_evidence')
        original=notes.get(e['note_id'],'')
        # The question supplies context but is not itself a guardian observation.
        answer=original.split('\n답변: ',1)[-1]
        if not isinstance(e['quote'],str) or not e['quote'].strip() or e['quote'] not in answer:
            raise ValueError('quote_not_in_guardian_answer')
        ids.append(e['note_id'])
    expected=facts(context)
    if value['state_check']!= {k:expected[k] for k in ['fatigue_band','rest_phase']}:
        raise ValueError('state_fact_mismatch')
    d=value['decision'];action=d.get('action') if isinstance(d,dict) else None
    keys={'action','goal_label'} if action=='seek' else {'action','avoid_feature'} if action=='avoid' else {'action'}
    if not isinstance(d,dict) or set(d)!=keys:raise ValueError('incompatible_action_fields')
    canonical={'action':action,'goal_operation':'set' if action=='seek' else 'clear' if action=='roam' else 'keep',
               'goal_label':d.get('goal_label'),'avoid_feature':d.get('avoid_feature'),
               'evidence_ids':ids,'reason':value['assessment'],'confusion_level':value['confusion_level']}
    return validate_decision(canonical,context)
