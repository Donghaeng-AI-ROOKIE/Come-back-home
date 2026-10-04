"""Source-only behavioral compiler, no constrained generation, strict local validation."""
import json
from app.llm import mind_policy as m
from app.llm.initial_behavior import decode_json_content
SYSTEM='''당신은 보호자 인터뷰에서 실제 관찰된 개인 행동을 추출하는 연구자다. 다음 사람의 조건부 행동을 JSON으로 정리하라.
원문 전체의 의미, 부정, 정정, 예외를 읽는다. 단어 대응표로 해석하지 않는다. 일반적인 치매 지식으로 개인의 행동을 채우지 않는다. 능력/의도/관찰 행동을 구분한다. 후보 장소나 과거 방문, 단순 보행 가능 시간은 자동 행동의 근거가 아니다. 이미 앞단에 저장된 목표와 길 친숙도는 그대로 쓰므로 다시 출력할 필요 없다.
출력은 {"rules":[...],"unused_note_ids":[...]} 하나다. 각 규칙 필드는 다음과 같다.
- id: 짧은 고유 영문 이름
- action: wait(도움 기다림), rest(잠깐 쉬기), walk(걷기), avoid(멀어지기), seek(등록 목적지로 향하기)
- when: 조건 사전. 모든 조건은 AND이다. OR은 규칙 행을 나눈다. boolean 조건은 true/false, 숫자는 {"gte":숫자} 또는 {"lte":숫자}이다. 조건 없는 명확한 행동은 {}.
- target: seek일 때만 등록 장소 이름, 나머지 null
- feature: avoid일 때만 market/park/forest/water, 나머지 null
- places: 특정 장소 한정이면 그 등록 이름 배열, 유형 전체이면 []
- minutes: 실제 관찰된 대기/휴식 지속 시간만 숫자, 없으면 null
- supersedes: 원문이 명시한 우선순위가 있을 때만 다른 규칙 id 배열, 없으면 []
- notes: 근거 note id 배열
boolean 조건 어휘: lost_awareness(길 잃음을 본인이 알아챔), family_present(가족 도착), pain_observed(현재 통증), physical_arrival(좌표 도착), target_recognized(장소 인지), is_walking(현재 걷는 중), dark_observed, rain_observed, fatigue_high, anxiety_high, home_pull_high, market.noisy, market.crowded, park.noisy, park.crowded, forest.noisy, forest.crowded, water.noisy, water.crowded.
숫자 조건 어휘: continuous_walk_minutes(마지막 정지 이후 실제 걷는 시간), distance_since_rest_m(마지막 정지 이후 이동 거리), clock_hour(한국 시각).
보행 후 휴식 조건에는 is_walking=true도 넣는다. 보행 시간과 거리 둘 다 실제 휴식 시점으로 제시되면 각각 반영한다. '한 시간 연속으로 못 걸음'을 60분 휴식으로 바꾸지 않는다. '가족 올 때까지 기다림'은 가족이 없을 때만 성립한다. 실제 관찰하지 않은 대응은 만들지 않는다. 좌표 도착을 장소 인지로 대신하지 않는다. 불확실한 반응은 unused_note_ids에 넣는다.
추가 설명이나 마크다운 없이 완전하고 짧은 JSON만 출력하라.'''
def request(personal,model,draft=None):
 data={'notes':personal['notes'],'places':personal['places']}
 if draft is not None:data['draft_to_review']=draft;data['task']='원문과 다시 대조해 누락·왜곡을 수정한 최종 JSON을 출력한다. 초안을 그대로 유지할 의무는 없다.'
 return {'model':model,'temperature':1.,'top_p':.95,'presence_penalty':0.,'max_tokens':12000,'parse_reasoning':True,'chat_template_kwargs':{'enable_thinking':True},'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(data,ensure_ascii=False)}]}
def compile(value,personal):
 assert set(value)=={'rules','unused_note_ids'}
 rows=[]
 for r in value['rules']:
  assert set(r)=={'id','action','when','target','feature','places','minutes','supersedes','notes'}
  atoms=[]
  for name,v in r['when'].items():
   if type(v) is bool:atoms.append({'fact':name,'op':'eq','value':v})
   else:
    assert type(v) is dict and len(v)==1
    op,n=next(iter(v.items()));atoms.append({'fact':name,'op':op,'value':n})
  rows.append({'id':r['id'],'when':[atoms],'action':r['action'],'goal_label':r['target'],'feature':r['feature'],'place_labels':r['places'],'hold_minutes':r['minutes'],'supersedes':r['supersedes'],'evidence':[{'note_id':n} for n in r['notes']]})
 return m.validate({'rules':rows,'unrepresented':[{'note_id':n,'reason':'원문에서 실행 가능한 반응 미확인'} for n in value['unused_note_ids']]},personal)
