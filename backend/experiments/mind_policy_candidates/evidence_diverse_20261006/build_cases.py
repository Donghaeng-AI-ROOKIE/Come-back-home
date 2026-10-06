"""Author-specified synthetic source/scene pairs, never patient ground truth.

Reference rules only check the internal coherence of authored expectations.
They are stored separately from model inputs and never sent to K.
"""
import json,hashlib,sys
from pathlib import Path
D=Path(__file__).resolve().parent
B=D.parents[1]/'개발/cbh-simulation-integration-20261004/backend';sys.path.insert(0,str(B))
from app.llm import mind_policy as m
from experiments.mind_policy_candidates import condition_program as c,note_policy_eval as ev
profiles=[];rows=[];oracles={}
PLACES=[{'label':'느티공원','place_type':'park'},{'label':'해든상가','place_type':'market'},{'label':'솔빛쉼터','place_type':'park'}]

def spec(command,condition,ids=('N1',),labels=(),hold=0):
 return {'command':command,'condition':condition,'note_ids':list(ids),'place_labels':list(labels),'hold_minutes':hold}

def scene(**kw):
 out={k:False for k in m.BOOLEAN_FACTS if '.' not in k}
 out.update(current_action='walk',continuous_walk_minutes=0,distance_since_rest_m=0,clock_hour=11,
            map_distance_m={k:1000 for k in ('market','park','forest','water')},noisy=False,crowded=False,current_place_label='등록 장소 밖')
 out.update(kw);return out

def nearby(feature,**kw):return scene(map_distance_m={**{k:1000 for k in ('market','park','forest','water')},feature:20},**kw)

def case(s,expected,why,status=None,possible=None):
 return {'scene':s,'expected_commands':expected,'expected_status':status or ('supported' if expected and expected!=['baseline'] else 'no_personal_reaction'),
         'expected_possible_commands':possible,'rationale':why}

def add(family,notes,rules,cases,prepared=None):
 pid='P'+str(len(profiles)+1).zfill(2)
 originals=[{'id':'N'+str(i),'text':'질문: '+q+'\n답변: '+a,'provenance':'guardian_original','source_kinds':['guardian_turn'],'recorded_at':['2026-10-01T10:00:00+09:00']} for i,(q,a) in enumerate(notes)]
 personal={'notes':originals,'places':PLACES,'prepared_initial':prepared or {}}
 used={n for r in rules for n in r['note_ids']}
 out={'source_assessment':'연구자가 직접 지정한 참조 규칙. 모델 평가나 임상 근거가 아님.','rules':rules,'non_action_note_ids':[n['id'] for n in originals if n['id'] not in used]}
 policy=c.compile_note(out,personal,'ALL')
 oracles[pid]=policy.model_dump()
 profiles.append({'person_id':pid,'family':family,'personal':personal,'synthetic':True,'language_variant':'individually_authored','prepared_fixture':bool(prepared)})
 assert len(cases)==4
 for i,item in enumerate(cases):
  decision=ev.decide(policy,personal,item['scene'])
  want=item['expected_commands'];assert decision['status']==item['expected_status'] and set(decision['commands'])==set(want),(pid,i,decision,item)
  if item['expected_possible_commands'] is not None:assert set(decision['possible_commands'])==set(item['expected_possible_commands'])
  rows.append({'id':pid+'_S'+str(i+1),'person_id':pid,'family':family,**item})

intro=('등록 장소는 어떤 의미인가요?','느티공원, 해든상가, 솔빛쉼터는 질문에 나온 후보 이름이에요. 그곳을 좋아하거나 실제로 간다는 뜻은 아니에요.')
# A. Environment logic, named/category scope and non-observation.
add('environment',[intro,('해든상가에서는 어떻게 행동했나요?','제가 함께 간 두 번 모두 해든상가에서 사람도 많고 소리도 클 때에만 입구에서 돌아섰어요. 한 가지뿐이면 돌아서지 않았고, 다른 상가는 본 적 없어요.')],
 [spec('avoid_market','market.noisy and market.crowded',labels=['해든상가'])],
 [case(nearby('market',noisy=True,crowded=True,current_place_label='해든상가'),['avoid_market'],'같은 장소 AND 성립'),case(nearby('market',noisy=True,current_place_label='해든상가'),['baseline'],'소음만'),case(nearby('market',crowded=True,current_place_label='해든상가'),['baseline'],'혼잡만'),case(nearby('market',noisy=True,crowded=True,current_place_label='다른 상가'),['baseline'],'이름 범위 밖')])
prep={'scope':{'environment':{'market':{'response':'avoid','scope':'conditional_category','note_ids':['N1'],'condition_clauses':[[{'signal':'noisy','state':'present'}],[{'signal':'crowded','state':'present'}]]}}}}
add('environment',[intro,('서로 다른 상가에서도 같은 반응이었나요?','세 군데를 같이 다녀봤어요. 사람만 몰려도 돌아서고, 조용히 한산해도 소리가 크면 돌아섰어요. 두 자극이 다 없을 때는 안 피했어요.')],[],
 [case(nearby('market',noisy=True),['avoid_market'],'소음만 OR'),case(nearby('market',crowded=True),['avoid_market'],'혼잡만 OR'),case(nearby('market'),['baseline'],'두 자극 없음'),case(nearby('market',noisy=None),[],'소음 미관측',status='unknown',possible=['baseline','avoid_market'])],prep)
add('environment',[intro,('공원에서 피한 상황을 알려주세요.','여러 공원에서 직접 봤는데, 어두우면서 사람까지 붐비면 공원 쪽에서 멀어졌어요. 대낮에 사람이 많은 건 괜찮았고, 어두워도 한산하면 피하지 않았어요.')],
 [spec('avoid_park','dark_observed and park.crowded')],
 [case(nearby('park',dark_observed=True,crowded=True),['avoid_park'],'어둠과 혼잡'),case(nearby('park',crowded=True),['baseline'],'혼잡만'),case(nearby('park',dark_observed=True),['baseline'],'어둠만'),case(scene(dark_observed=True,crowded=True),['baseline'],'공원에서 멂')])
add('environment',[intro,('물가 반응과 주변 사람의 이야기는요?','아버지가 물가를 피하는지는 아직 본 적이 없어요. 시끄러운 하천변에서 되돌아갔다는 사람은 옆집 어르신이에요. 아버지 이야기로 기록하지 말아주세요.')],[],
 [case(nearby('water',noisy=True),['baseline'],'타인의 반응'),case(nearby('water',crowded=True),['baseline'],'본인 관찰 없음'),case(nearby('water',noisy=True,dark_observed=True),['baseline'],'조건 추가도 근거 아님'),case(scene(),['baseline'],'중립')])
# B. Mobility needs versus capacity, limits and recovery.
add('physical_rest',[intro,('보행 후 쉬어야 하나요?','연속 팔 분 정도 걷거나 사백오십 미터쯤 가면 무릎 때문에 앉아 쉬어야 해요. 둘 다 채워야 하는 건 아니고 먼저 힘든 쪽에서 쉬어요.')],
 [spec('rest','is_walking and (continuous_walk_minutes >= 8 or distance_since_rest_m >= 450)')],
 [case(scene(continuous_walk_minutes=8,distance_since_rest_m=200),['rest'],'시간 한계'),case(scene(continuous_walk_minutes=4,distance_since_rest_m=450),['rest'],'거리 한계'),case(scene(continuous_walk_minutes=7,distance_since_rest_m=440),['baseline'],'두 한계 전'),case(scene(current_action='rest',continuous_walk_minutes=8,distance_since_rest_m=450),['baseline'],'이미 휴식 중')])
add('physical_rest',[intro,('어느 정도 보행이 가능한가요?','쉬지 않고 이십오 분은 걸을 수 있어요. 이십오 분에 꼭 쉬었다는 관찰은 아니에요. 쉬는 시점은 제가 확인하지 못했어요.')],[],
 [case(scene(continuous_walk_minutes=24),['baseline'],'능력 전'),case(scene(continuous_walk_minutes=25),['baseline'],'능력 경계'),case(scene(continuous_walk_minutes=30,distance_since_rest_m=1500),['baseline'],'능력을 휴식 명령으로 바꾸지 않음'),case(scene(current_action='rest'),['baseline'],'휴식 관찰 없음')])
add('physical_rest',[intro,('통증이 나타나면 실제로 어떻게 하셨나요?','걷는 동안 무릎이 아프다고 말씀하신 뒤에는 앉아서 삼 분 정도 쉬셨어요. 통증 없는 때에 어떻게 쉬는지는 모르겠어요.')],
 [spec('rest','is_walking and pain_observed',hold=3)],
 [case(scene(pain_observed=True),['rest'],'보행 중 통증'),case(scene(pain_observed=False),['baseline'],'통증 없음'),case(scene(current_action='rest',pain_observed=True),['baseline'],'새 보행 반응 아님'),case(scene(pain_observed=None),[],'통증 미확인',status='unknown',possible=['baseline','rest'])])
add('physical_rest',[intro,('언제 쉬셨는지 구체적으로 알려주세요.','실제로 같이 걸어 보니 연속 십이 분 걷고 난 뒤에도 계속 가셨어요. 숨이 차 보인다는 것만으로 멈춘 적은 없고, 본인이 무릎 통증을 말할 때만 앉아 쉬셨어요.')],
 [spec('rest','is_walking and pain_observed')],
 [case(scene(continuous_walk_minutes=12,fatigue_high=True),['baseline'],'피로 추정만'),case(scene(continuous_walk_minutes=20,pain_observed=True),['rest'],'본인 통증'),case(scene(continuous_walk_minutes=20,pain_observed=False),['baseline'],'시간만으로 휴식 아님'),case(scene(current_action='rest',pain_observed=True),['baseline'],'휴식 중 보행 조건 거짓')])
# C. Wait onset and release; unknown versus false.
add('waiting',[intro,('길을 놓친 걸 알았을 때 실제로는요?','길을 잃었다고 알아차린 두 번에는 가족이 곁에 없으면 그 자리에서 기다렸어요. 가족이 오자 대기는 끝났고 그 이후 어디로 갔는지는 기억나지 않아요.')],
 [spec('wait','lost_awareness and not family_present')],
 [case(scene(lost_awareness=True,family_present=False),['wait'],'발동'),case(scene(lost_awareness=True,family_present=True),['baseline'],'가족 도착'),case(scene(lost_awareness=False,family_present=False),['baseline'],'부재만으로 발동 안 함'),case(scene(lost_awareness=True,family_present=None),[],'가족 여부 미확인',status='unknown',possible=['baseline','wait'])])
add('waiting',[intro,('길 잃음을 알고 불안해하면 어떻게 하나요?','길을 잃은 걸 알고 불안하다고 표현할 때는 곁에 누가 있든 잠깐 멈춰 기다렸어요. 불안하지 않으면 그렇게 기다리지는 않았어요.')],
 [spec('wait','lost_awareness and anxiety_high')],
 [case(scene(lost_awareness=True,anxiety_high=True),['wait'],'인지와 불안'),case(scene(lost_awareness=True),['baseline'],'불안 없음'),case(scene(anxiety_high=True),['baseline'],'길 잃음 인지 없음'),case(scene(lost_awareness=True,anxiety_high=True,family_present=True),['wait'],'가족을 근거 없이 종료조건으로 추가 금지')])
add('waiting',[intro,('가족이 없을 때 기다리나요?','혼자면 기다려야 한다고 제가 말씀드렸을 뿐이에요. 실제로 기다린 장면은 못 봤고 가족이 있을 때도 모르겠어요.')],[],
 [case(scene(lost_awareness=True,family_present=False),['baseline'],'보호자 권고'),case(scene(lost_awareness=True,family_present=True),['baseline'],'실제 관찰 없음'),case(scene(anxiety_high=True,family_present=False),['baseline'],'불안도 관찰을 만들지 못함'),case(scene(family_present=False),['baseline'],'혼자만으로 반응 확정 금지')])
add('waiting',[intro,('가족을 찾을 때 어떤 행동이었나요?','가족이 안 보이고 불안하다고 할 때는 걷지 않고 기다렸어요. 가족을 만나면 기다림은 끝났어요. 그때 길을 잃었다고 생각했는지는 몰라요.')],
 [spec('wait','anxiety_high and not family_present')],
 [case(scene(anxiety_high=True,family_present=False),['wait'],'불안과 부재'),case(scene(anxiety_high=True,family_present=True),['baseline'],'가족 만남'),case(scene(anxiety_high=False,family_present=False),['baseline'],'불안 없음'),case(scene(anxiety_high=True,family_present=False,lost_awareness=None),['wait'],'원문에 없는 길 잃음 인지 조건 추가 금지')])
# D. Goal intent versus observed departure and recognition.
add('destination',[intro,('공원에 가겠다고 하시나요?','느티공원에 가야 한다는 말은 매일 하세요. 실제로 일어나 출발한 적은 확인하지 못했어요. 입구를 알아보는지도 몰라요.')],[],
 [case(scene(clock_hour=9),['baseline'],'발언만'),case(scene(target_recognized=True),['baseline'],'인지가 새 출발 근거 아님'),case(scene(physical_arrival=True,target_recognized=False),['baseline'],'좌표 도착만'),case(scene(home_pull_high=True),['baseline'],'다른 마음 상태가 원문 관찰 아님')])
add('destination',[intro,('익숙한 공원을 알아보면 어떻게 행동했나요?','느티공원 입구를 알아봤다고 직접 말한 두 번 모두 그쪽으로 걸어 출발했어요. 입구를 알아보지 못했을 때의 행동은 아직 본 적 없어요.')],
 [spec('seek_0','target_recognized')],
 [case(scene(target_recognized=True),['seek_0'],'실제 출발'),case(scene(target_recognized=False),['baseline'],'인지 안 됨'),case(scene(physical_arrival=True,target_recognized=False),['baseline'],'물리적 도착과 인지 구분'),case(scene(target_recognized=None),[],'인지 미확인',status='unknown',possible=['baseline','seek_0'])])
add('destination',[intro,('언제 상가로 향하셨나요?','직접 본 세 번에는 오전 열 시부터 열한 시 전까지 가족이 곁에 있으면 해든상가 쪽으로 출발했어요. 다른 시간이나 혼자 있을 때는 출발하지 않았어요.')],
 [spec('seek_1','clock_hour >= 10 and clock_hour < 11 and family_present')],
 [case(scene(clock_hour=10,family_present=True),['seek_1'],'시작 경계'),case(scene(clock_hour=10.5,family_present=False),['baseline'],'혼자'),case(scene(clock_hour=11,family_present=True),['baseline'],'종료 경계'),case(scene(clock_hour=9.9,family_present=True),['baseline'],'시간 전')])
add('destination',[intro,('장소를 알아본 뒤 잠시 멈춘 적이 있나요?','솔빛쉼터에 실제로 도착하고, 거기가 쉼터라는 것도 알아봤다고 말했을 때는 그 자리에서 기다렸어요. 단순히 근처를 지났을 때는 기다리지 않았어요.')],
 [spec('wait','physical_arrival and target_recognized',labels=['솔빛쉼터'])],
 [case(scene(physical_arrival=True,target_recognized=True,current_place_label='솔빛쉼터'),['wait'],'도착과 인지'),case(scene(physical_arrival=True,target_recognized=False,current_place_label='솔빛쉼터'),['baseline'],'도착만'),case(scene(physical_arrival=False,target_recognized=True,current_place_label='솔빛쉼터'),['baseline'],'인지뿐'),case(scene(physical_arrival=True,target_recognized=True,current_place_label='느티공원'),['baseline'],'다른 장소')])
# E. Environmental interaction and physical state, independent of clock inference.
add('external_state',[intro,('비가 오면 어떤 행동을 했나요?','가족과 여러 번 함께 나갔는데 비가 내리는 걸 본인은 알았고 그때마다 걷는 걸 멈추고 기다렸어요. 비가 그치면 대기는 끝났어요.')],
 [spec('wait','rain_observed')],
 [case(scene(rain_observed=True),['wait'],'비 관측'),case(scene(rain_observed=False),['baseline'],'비 그침'),case(scene(rain_observed=None),[],'날씨 미관측',status='unknown',possible=['baseline','wait']),case(scene(clock_hour=23,rain_observed=False),['baseline'],'밤이 비를 뜻하지 않음')])
add('external_state',[intro,('어두운 곳과 가족 유무가 영향을 주나요?','여러 산책에서 어둡다고 본인이 느꼈고 가족도 곁에 없을 때만 멈춰 기다렸어요. 가족이 같이 있거나 밝으면 기다리지 않았어요.')],
 [spec('wait','dark_observed and not family_present')],
 [case(scene(dark_observed=True,family_present=False),['wait'],'어둠과 부재'),case(scene(dark_observed=True,family_present=True),['baseline'],'동행 있음'),case(scene(dark_observed=False,family_present=False,clock_hour=23),['baseline'],'밤이어도 관측 밝음'),case(scene(dark_observed=None,family_present=False),[],'밝기 미관측',status='unknown',possible=['baseline','wait'])])
add('external_state',[intro,('피곤하다고 할 때와 아프다고 할 때는요?','실제로 걸어 다닐 때 피곤하다고 하시거나 무릎이 아프다고 하면 어느 하나만 있어도 잠깐 앉아 쉬셨어요. 둘 다 괜찮을 때는 그 이유로 쉬지 않으셨어요.')],
 [spec('rest','is_walking and (fatigue_high or pain_observed)')],
 [case(scene(fatigue_high=True),['rest'],'피로만'),case(scene(pain_observed=True),['rest'],'통증만'),case(scene(),['baseline'],'둘 다 없음'),case(scene(current_action='rest',fatigue_high=True,pain_observed=True),['baseline'],'이미 쉬는 중')])
add('external_state',[intro,('숲길에서 무엇을 피하셨나요?','두 군데 숲길에서 소리가 크면 길 가장자리에서 멀어졌어요. 비가 오느냐, 사람이 많으냐와는 관계없이 소리가 클 때였어요.')],
 [spec('avoid_forest','forest.noisy')],
 [case(nearby('forest',noisy=True),['avoid_forest'],'소음'),case(nearby('forest',crowded=True),['baseline'],'혼잡만'),case(nearby('forest',noisy=True,rain_observed=True),['avoid_forest'],'비는 제한 조건 아님'),case(scene(noisy=True),['baseline'],'숲 근처 아님')])
# F. Negation, explicit correction, third party and short answers.
add('source_fidelity',[intro,('전에 기다린다고 하셨는데 맞나요?','지난번 기다린다는 설명은 어머니가 아니라 아버지 이야기였어요. 어머니가 길을 잃었다고 알아차리면 실제로 멈추지 않고 계속 걸었어요. 기다리는지는 어머니에게서 본 적 없어요.')],
 [spec('walk','lost_awareness')],
 [case(scene(lost_awareness=True),['walk'],'수정 후 본인 반응'),case(scene(lost_awareness=False),['baseline'],'인지 없음'),case(scene(lost_awareness=True,family_present=False),['walk'],'아버지 대기를 가져오지 않음'),case(scene(lost_awareness=None),[],'인지 미확인',status='unknown',possible=['baseline','walk'])])
add('source_fidelity',[intro,('예전에 공원을 피한다고 했던 기록은요?','제가 잘못 말했어요. 공원이 아니라 사람이 붐비는 물가를 피했어요. 세 하천변에서 직접 본 거예요. 한산한 물가에서는 피하지 않았어요.')],
 [spec('avoid_water','water.crowded')],
 [case(nearby('water',crowded=True),['avoid_water'],'수정된 유형'),case(nearby('park',crowded=True),['baseline'],'철회된 공원'),case(nearby('water'),['baseline'],'한산함'),case(nearby('water',crowded=True,noisy=False),['avoid_water'],'소음 추가 조건 금지')])
add('source_fidelity',[intro,('길을 잃은 걸 알면 가족이 올 때까지 기다리는 모습을 직접 보셨나요?','네, 두 번 다 제가 봤어요.')],
 [spec('wait','lost_awareness and not family_present')],
 [case(scene(lost_awareness=True,family_present=False),['wait'],'짧은 답은 질문 문맥과 해석'),case(scene(lost_awareness=True,family_present=True),['baseline'],'가족 도착'),case(scene(lost_awareness=False,family_present=False),['baseline'],'질문을 무조건 행동으로 바꾸지 않음'),case(scene(lost_awareness=True,family_present=None),[],'가족 미확인',status='unknown',possible=['baseline','wait'])])
add('source_fidelity',[intro,('길을 잃은 걸 알면 기다리나요?','아니요. 기다리는 모습은 관찰하지 못했어요. 이 질문에 네라고 답한 것은 다른 가족이 돌보는 분 이야기였어요.')],[],
 [case(scene(lost_awareness=True,family_present=False),['baseline'],'부정 답변'),case(scene(lost_awareness=True,family_present=True),['baseline'],'질문 자체를 근거로 쓰지 않음'),case(scene(anxiety_high=True),['baseline'],'타인 사례 제외'),case(scene(lost_awareness=None),['baseline'],'개인 반응 근거 없음')])
# G. Absolute clock, midnight and observed darkness independence.
add('time_context',[intro,('아침과 낮에 다른 반응을 봤나요?','가족이 곁에 없을 때 오전 여덟 시부터 아홉 시 전까지는 현관에서 기다렸어요. 아홉 시가 되면 그 기다림은 끝났어요. 그 다음 행동은 기록하지 못했어요.')],
 [spec('wait','clock_hour >= 8 and clock_hour < 9 and not family_present')],
 [case(scene(clock_hour=8,family_present=False),['wait'],'시작 경계'),case(scene(clock_hour=8.5,family_present=True),['baseline'],'가족 있음'),case(scene(clock_hour=9,family_present=False),['baseline'],'종료 경계'),case(scene(clock_hour=7.9,family_present=False),['baseline'],'시작 전')])
add('time_context',[intro,('늦은 밤에도 시간에 따른 차이가 있나요?','밤 열한 시부터 자정을 지나 새벽 한 시 전까지는 가족이 안 보이면 기다렸어요. 새벽 한 시에는 그 기다림이 끝났어요. 실제 관찰한 시간 기록이에요.')],
 [spec('wait','(clock_hour >= 23 or clock_hour < 1) and not family_present')],
 [case(scene(clock_hour=23.5,family_present=False),['wait'],'자정 전'),case(scene(clock_hour=.5,family_present=False),['wait'],'자정 후'),case(scene(clock_hour=1,family_present=False),['baseline'],'종료 경계'),case(scene(clock_hour=22.5,family_present=False),['baseline'],'시간 전')])
add('time_context',[intro,('낮에도 어두우면 멈추셨나요?','시각은 관계없어요. 지하 통로처럼 본인이 어둡다고 말한 곳에서는 기다리고, 밝은 곳에서는 그 기다림이 끝났어요. 밤이라고 무조건 기다리지는 않았어요.')],
 [spec('wait','dark_observed')],
 [case(scene(clock_hour=12,dark_observed=True),['wait'],'낮의 어둠'),case(scene(clock_hour=23,dark_observed=False),['baseline'],'밝은 밤'),case(scene(clock_hour=23,dark_observed=None),[],'시각으로 밝기 추정 금지',status='unknown',possible=['baseline','wait']),case(scene(clock_hour=6,dark_observed=False),['baseline'],'명시적으로 밝음')])
add('time_context',[intro,('연속 보행 시간과 하루 시각 중 무엇이 중요했나요?','몇 시든 실제로 십 분 연속 걸은 뒤에는 앉아서 쉬어야 했어요. 시계가 열 시가 된다는 뜻은 아니에요. 이미 앉아서 쉬고 있으면 새로 걷고 있다는 뜻도 아니고요.')],
 [spec('rest','is_walking and continuous_walk_minutes >= 10')],
 [case(scene(clock_hour=8,continuous_walk_minutes=10),['rest'],'오전 연속 보행'),case(scene(clock_hour=20,continuous_walk_minutes=10),['rest'],'저녁 같은 보행'),case(scene(clock_hour=10,continuous_walk_minutes=0),['baseline'],'시각과 지속시간 구분'),case(scene(current_action='rest',clock_hour=10,continuous_walk_minutes=10),['baseline'],'휴식 중')])
# H. Multiple independent behaviors, competing evidence and uncertainty.
add('multiple_behaviors',[intro,('보행 후 휴식은요?','무릎 때문에 육 분 걷거나 이백팔십 미터 가면 먼저 도달한 쪽에서 쉬어야 해요.'),('길을 잃은 걸 알면 어떻게 하나요?','두 번 모두 길을 잃었다는 걸 알고 가족이 없으면 그 자리에서 기다렸어요. 가족이 오면 기다림은 끝났어요.')],
 [spec('rest','is_walking and (continuous_walk_minutes >= 6 or distance_since_rest_m >= 280)',ids=['N1']),spec('wait','lost_awareness and not family_present',ids=['N2'])],
 [case(scene(continuous_walk_minutes=6,family_present=True),['rest'],'휴식 시간'),case(scene(distance_since_rest_m=280,family_present=True),['rest'],'휴식 거리'),case(scene(lost_awareness=True,family_present=False),['wait'],'별개 기다림'),case(scene(lost_awareness=True,family_present=True),['baseline'],'가족 도착')])
add('multiple_behaviors',[intro,('상가 반응은요?','해든상가에서 시끄러우면 피했어요. 다른 상가는 모르겠어요.'),('통증 반응은요?','걷다가 아프다고 말하면 앉아서 쉬었어요. 소음 반응과는 별개예요.')],
 [spec('avoid_market','market.noisy',ids=['N1'],labels=['해든상가']),spec('rest','is_walking and pain_observed',ids=['N2'])],
 [case(nearby('market',noisy=True,current_place_label='해든상가'),['avoid_market'],'소음 반응'),case(scene(pain_observed=True),['rest'],'통증 반응'),case(nearby('market',noisy=True,pain_observed=True,current_place_label='해든상가'),[],'두 유효 반응 우선순위 미제공',status='unknown',possible=['avoid_market','rest']),case(scene(),['baseline'],'둘 다 없음')])
add('multiple_behaviors',[intro,('공원 반응은요?','공원 여러 곳에서 사람이 붐비면 공원 쪽에서 멀어졌어요.'),('가족이 없을 때 불안하면요?','불안하다고 하면서 가족이 안 보이면 기다렸어요. 가족이 보이면 대기는 끝났어요.')],
 [spec('avoid_park','park.crowded',ids=['N1']),spec('wait','anxiety_high and not family_present',ids=['N2'])],
 [case(nearby('park',crowded=True,family_present=True),['avoid_park'],'회피만'),case(scene(anxiety_high=True,family_present=False),['wait'],'기다림만'),case(nearby('park',crowded=True,anxiety_high=True,family_present=False),[],'우선순위 미제공',status='unknown',possible=['avoid_park','wait']),case(nearby('park',crowded=False,anxiety_high=True,family_present=True),['baseline'],'두 조건 해제')])
add('multiple_behaviors',[intro,('상가를 알아보면요?','해든상가를 알아봤다고 말하면 실제로 그쪽으로 출발했어요. 그냥 근처에 도착했다는 것과는 달라요.'),('비가 내릴 때는요?','비가 오는 걸 알고는 그 자리에서 기다렸어요. 상가 출발과 비 대기가 겹쳤을 때는 못 봤어요.')],
 [spec('seek_1','target_recognized',ids=['N1']),spec('wait','rain_observed',ids=['N2'])],
 [case(scene(target_recognized=True),['seek_1'],'출발만'),case(scene(rain_observed=True),['wait'],'대기만'),case(scene(target_recognized=True,rain_observed=True),[],'겹침 미관찰',status='unknown',possible=['seek_1','wait']),case(scene(physical_arrival=True,target_recognized=False),['baseline'],'좌표 도착이 인지 아님')])

assert len(profiles)==32 and len(rows)==128
for name,value in [('profiles.json',profiles),('scenes.json',rows),('reference_policies.NOT_MODEL_INPUT.json',oracles)]:
 (D/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'synthetic_profiles':len(profiles),'families':8,'authored_scenes':len(rows),'reference_consistency':'128/128; handwritten references only','model_calls':0},ensure_ascii=False))
