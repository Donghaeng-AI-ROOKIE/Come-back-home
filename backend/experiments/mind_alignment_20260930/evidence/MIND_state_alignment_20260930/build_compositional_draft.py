"""Create auditable synthetic drafts, not clinical observations or training approval.

The formal policy is an AUTHORING oracle. It is never used to parse guardian
words at inference, and must never be included in the model's user message.
"""
import copy,hashlib,itertools,json,random
from pathlib import Path

D=Path(__file__).resolve().parent
FEATURES={'park':'공원','market':'시장','forest':'숲길','water':'물가'}
ATOMS=[]
for feature,label in FEATURES.items():
    for signal,phrase in [('noisy','소음이 들리는'),('crowded','사람이 붐비는')]:
        ATOMS.append(dict(id=f'{feature}_{signal}',phrase=f'{label}에서 {phrase} 상황',
            kind='environment',feature=feature,signal=signal,action='avoid_'+feature))
for name,phrase,action in [
    ('reported_tiredness','본인이 많이 지쳤다고 말하는 상황','rest'),
    ('heavy_legs','본인이 다리가 무겁다고 말하는 상황','rest'),
    ('self_lost_awareness','본인이 길을 잃었다고 알아차린 상황','stay'),
    ('reported_thirst','본인이 목마르다고 말하는 상황','seek_1'),
    ('reported_hunger','본인이 배고프다고 말하는 상황','seek_1'),
    ('reported_toilet_need','본인이 화장실에 가고 싶다고 말하는 상황','seek_1'),
    ('familiar_place_recognition','본인이 주변 장소를 익숙한 곳으로 알아보는 상황','seek_1'),
    ('reported_anxiety','본인이 불안하다고 말하는 상황','stay'),
    ('reported_pain','본인이 몸이 아프다고 말하는 상황','rest'),
    ('reported_cold','본인이 춥다고 말하는 상황','seek_1'),
    ('approaching_stranger','낯선 사람이 다가오는 상황','stay'),
]:
    ATOMS.append(dict(id=name,phrase=phrase,kind='event',action=action))
ATOMS.append(dict(id='family_companion',phrase='가족이 곁에서 동행하는 상황',kind='family',action='continue'))
STATES=[(False,False),(False,True),(True,False),(True,True),(False,None),(True,None),(None,False),(None,True)]


def action_text(action):
    if action.startswith('avoid_'):return FEATURES[action[6:]]+'에서 멀어지는 쪽으로 돌아간다'
    return {'rest':'잠시 앉아서 쉰다','stay':'그 자리에 서서 기다린다','seek_1':'등록 장소 B로 목표를 바꾸어 간다','continue':'원래 가던 길과 목표를 유지한다'}[action]


def narrative(first,second,variant):
    a,b=first['phrase'],second['phrase'];x,y=action_text(first['action']),action_text(second['action'])
    if variant==0:
        return f'여러 번 관찰한 이분의 반응을 적습니다. {a}이면 먼저 {x}. 그 상황이 아니고 {b}일 때에는 {y}. 두 상황 모두 아니면 원래 가던 길과 목표를 유지한다. 두 상황이 겹쳐도 첫 번째 반응이 우선입니다.'
    if variant==1:
        return f'질문: 상황이 겹치면 어떻게 하시나요? 답변: {a}일 때는 {x}는 반응이 가장 먼저예요. 질문: 그 상황이 아니라면요? 답변: {b}라면 {y}. 둘 다 아닐 때는 원래 목표대로 가요. 첫 번째 상황 없이 두 번째 상황만 있을 때의 반응과 우선순위를 구분해서 말씀드린 거예요.'
    return f'돌봄 기록: {a}을 확인했던 날에는 {x}. {b}이 함께 생겨도 그 첫 반응은 같았다. 첫 상황이 아니면서 두 번째 상황에 해당한 날에는 {y}. 어느 쪽도 해당하지 않은 때에는 기존 목표를 향한 이동을 이어갔다.'


def possible_commands(first,second,values):
    possibilities=[]
    for a,b in itertools.product(*[(False,True) if v is None else (v,) for v in values]):
        possibilities.append(first['action'] if a else second['action'] if b else 'continue')
    commands=set(possibilities)
    return sorted(commands),next(iter(commands)) if len(commands)==1 else 'defer'


def add_fact(context,atom,value):
    provenance='synthetic_authored_observation_not_patient_or_sensor_data'
    if atom['kind']=='environment':
        context['environment']['map_proximity_m'][atom['feature']]=20
        context['environment']['observed_signals'].setdefault(atom['feature'],{})[atom['signal']]=value
        return '/environment/observed_signals/'+atom['feature']+'/'+atom['signal']
    if atom['kind']=='family':
        event=dict(kind='companion_observation',value=value,relation='family' if value is True else 'none' if value is False else 'unknown',elapsed_minutes=60,provenance=provenance)
    else:
        event=dict(kind=atom['id']+'_observation',value=value,elapsed_minutes=60,provenance=provenance,
            meaning=atom['phrase']+'임을 확인했는지 여부; null은 미확인')
    index=len(context['state']['recent_events'])
    context['state']['recent_events'].append(event)
    if atom['id']=='reported_tiredness':
        context['state']['fatigue']=.9 if value is True else .1 if value is False else .5
    return f'/state/recent_events/{index}/value'


def build():
    out=D/'expanded_draft';out.mkdir(exist_ok=False)
    base=json.loads((D/'dataset/development.jsonl').read_text().splitlines()[0])['context']
    pairs=[(a,b) for a,b in itertools.combinations(ATOMS,2) if a['action']!=b['action']]
    random.Random(930).shuffle(pairs)
    assert len(pairs)>=140
    splits={'train':[],'development':[],'evaluation':[]};policies=[];raw_counts={k:0 for k in splits}
    for i,(first,second) in enumerate(pairs[:140]):
        split='train' if i<80 else 'development' if i<100 else 'evaluation'
        # Priority is part of the authored person's definition, not a population rule.
        if i%2:first,second=second,first
        family=f'CP{i+1:03}'
        fingerprint=hashlib.sha256(json.dumps([first['id'],second['id'],first['action'],second['action'],'continue']).encode()).hexdigest()
        policies.append(dict(family_id=family,split=split,formal_policy_hash=fingerprint,
            first=first,second=second,default_command='continue',
            clinical_evidence=False,source='AI-authored compositional draft; not extracted from a paper or caregiver'))
        for j,values in enumerate(STATES):
            for variant in range(3 if split=='train' else 1):
                context=copy.deepcopy(base);cid=f'{family}_S{j+1}_V{variant}'
                context.update(case_id=cid,person_id='draft-'+family,person_revision='compositional-draft-v1')
                context['person'].update(evidence_notes=[dict(id='N1',text=narrative(first,second,variant))],prepared_person_interpretation={},initial_interpretation={},preparation_status='synthetic_draft_original_only',initial_interpretation_status='not_generated')
                context['environment'].update(map_proximity_m={f:None for f in FEATURES},observed_signals={},provenance='synthetic state composition, not measured at KINTEX')
                context['state'].update(fatigue=.2,current_action='seek',target_label='등록 장소 A',recent_events=[],elapsed_minutes=60,last_rest_end_minutes=None)
                context['execution']['previous_travel_action']='seek'
                fact_paths=[add_fact(context,atom,value) for atom,value in zip((first,second),values)]
                possible,command=possible_commands(first,second,values)
                states=' / '.join(atom['phrase']+': '+('미확인' if val is None else '확인됨' if val else '아님이 확인됨') for atom,val in zip((first,second),values))
                reason=states+('. 가능한 개인 반응이 달라 판단 유보.' if command=='defer' else '. 원문 조건과 우선순위에 따라 '+action_text(command)+'.')
                assert len(reason)<=400
                row=dict(id=cid,split=split,family_id=family,lineage_id=f'{family}_S{j+1}',variant=variant,
                    context=context,authoring_oracle=dict(first_atom=first['id'],second_atom=second['id'],values=list(values),fact_paths=fact_paths,possible_commands=possible,expected_command=command,formal_policy_hash=fingerprint),
                    expected_output=dict(next_command_id=command,source_ids=['N1'],reason=reason),
                    quality=dict(status='draft_needs_semantic_and_domain_review',clinical_observations=0,real_frontend_output=False,not_for_training_until_reviewed=True))
                splits[split].append(row)
                if variant==0:raw_counts[split]+=1
    hashes={}
    for split,rows in splits.items():
        path=out/(split+'.jsonl');path.write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows))
        hashes[split]=hashlib.sha256(path.read_bytes()).hexdigest()
    (out/'policies.json').write_text(json.dumps(policies,ensure_ascii=False,indent=2)+'\n')
    manifest=dict(status='draft_not_training_ready',raw_counts=raw_counts,counts={k:len(v) for k,v in splits.items()},
        family_counts={'train':80,'development':20,'evaluation':40},hashes=hashes,
        narrative_template_count=3,observation_atom_count=len(ATOMS),clinical_patient_count=0,
        new_independent_caregiver_sources=0,paper_derived_behavior_labels=False,
        synthetic_policy_groups_are_not_independent_patients=True,new_model_calls=0,new_training_runs=0)
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__':build()
