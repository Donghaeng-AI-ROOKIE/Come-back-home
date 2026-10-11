"""Authored contrast dataset; never a production rule parser or clinical dataset.

The counterfactual pair and every state/wording derivative stay in one split.
Oracle fields are separate from context and may not enter model messages.
"""
import collections, copy, hashlib, itertools, json, random
from pathlib import Path
from build_compositional_draft import ATOMS, FEATURES, add_fact, action_text

D=Path(__file__).resolve().parent
KINDS=('single','and','or','unless','priority','correction','latest_observation')
VALUES=(False,True,None)
STATES=list(itertools.product(VALUES, repeat=2))

def policy_results(kind, values, main, second):
    possible=set()
    for a,b in itertools.product(*[(False,True) if v is None else (v,) for v in values]):
        if kind in ('single','correction','latest_observation'):result=main if a else 'continue'
        elif kind=='and':result=main if a and b else 'continue'
        elif kind=='or':result=main if a or b else 'continue'
        elif kind=='unless':result=main if a and not b else 'continue'
        elif kind=='priority':result=main if a else second if b else 'continue'
        else:raise ValueError(kind)
        possible.add(result)
    return sorted(possible), next(iter(possible)) if len(possible)==1 else 'defer'

def clauses(kind,a,b,main,second):
    x=action_text(main)
    if kind in ('single','correction','latest_observation'):
        return f'{a}에는 {x}. 이 상황이 아니면 원래 하던 이동과 목표를 유지한다. {b}만으로는 그 반응이 달라지지 않는다.'
    if kind=='and':return f'{a}, 그리고 {b}이 모두 해당할 때만 {x}. 둘 중 하나라도 아니면 원래 하던 이동과 목표를 유지한다.'
    if kind=='or':return f'{a}, 또는 {b} 중 하나 이상에 해당하면 {x}. 둘 다 아니면 원래 하던 이동과 목표를 유지한다.'
    if kind=='unless':return f'{a}에는 {x}. 다만 {b}이면 앞의 반응 대신 원래 하던 이동과 목표를 유지한다. 첫 상황이 아닐 때도 기존 이동을 유지한다.'
    if kind=='priority':return f'{a}에는 먼저 {x}. 첫 상황이 아니면서 {b}일 때는 {action_text(second)}. 둘 다 아니면 기존 이동과 목표를 유지한다. 두 상황이 겹칠 때는 첫 번째 반응이 우선이다.'
    raise ValueError(kind)

def notes(kind,first,second,main,other,variant):
    body=clauses(kind,first['phrase'],second['phrase'],main,other)
    prefixes=[
        '제가 여러 번 함께 걸으며 본 반응은 이렇습니다. ',
        '질문: 실제로 지켜본 평소 반응을 알려 주세요. 답변: ',
        '돌봄 기록에서 반복해서 확인한 모습. ',
        '한 번만 있었던 일이 아니라, 같이 외출할 때 반복해서 봤어요. 구체적으로 적으면 ',
        '가족끼리 이야기하다가 이분의 반응을 정리해 봤어요. 제가 직접 본 내용은 ',
    ]
    if kind=='correction':
        old='continue' if main!='continue' else first['action']
        return [dict(id='N1',text='앞서 전달한 설명: '+clauses('single',first['phrase'],second['phrase'],old,other)),
                dict(id='N2',text=prefixes[variant]+'앞선 N1은 현재 반응을 잘못 설명한 것이어서 정정합니다. '+body)]
    return [dict(id='N1',text=prefixes[variant]+body)]

def alternative(atom,index):
    original=atom['action']
    if original=='continue':return 'stay'
    if original=='stay':return 'roam'
    if index%2==0:return 'continue'
    if original=='rest':return 'stay'
    if original=='seek_1':return 'continue'
    return 'stay'

def describe_action(command):
    return '목표 없이 주변을 걷는다' if command=='roam' else action_text(command)

# Extending the authoring vocabulary does not add a runtime word/action rule.
_action_text=action_text
def action_text(command):
    return '목표 없이 주변을 걷는다' if command=='roam' else _action_text(command)

def make():
    out=D/'personal_contrasts_v3';out.mkdir(exist_ok=False)
    base=json.loads((D/'dataset/development.jsonl').read_text().splitlines()[0])['context']
    # Grouping is by atom pair, so near-identical reversed profiles cannot leak.
    # Balance the leading observation across splits. combinations() alone
    # would always put environment atoms first and hide personal body states.
    rng=random.Random(93003);seen=set();pairs=[]
    dev_ids=['park_noisy','market_noisy','forest_noisy','water_noisy','reported_tiredness',
             'heavy_legs','self_lost_awareness','reported_thirst','reported_anxiety','family_companion']
    by_id={a['id']:a for a in ATOMS}
    leading=list(ATOMS)*2+[by_id[x] for x in dev_ids]+list(ATOMS)
    for first in leading:
        candidates=[a for a in ATOMS if a['id']!=first['id'] and tuple(sorted((a['id'],first['id']))) not in seen]
        rng.shuffle(candidates);second=candidates[0]
        seen.add(tuple(sorted((first['id'],second['id']))));pairs.append((first,second))
    splits={k:[] for k in ('train','development','evaluation')};policies=[]
    for i,(first,second) in enumerate(pairs[:70]):
        split='train' if i<40 else 'development' if i<50 else 'evaluation'
        group=f'PC{i+1:03}';kind=KINDS[i%len(KINDS)]
        mains=(first['action'],alternative(first,i))
        assert mains[0]!=mains[1]
        pair_key='|'.join(sorted((first['id'],second['id'])))
        policies.append(dict(group_id=group,split=split,kind=kind,first=first,second=second,
            main_commands=mains,second_command=second['action'],pair_key=pair_key,
            source='AI-authored hypothetical caregiver account, no actual observation',clinical_evidence=False))
        for person,main in enumerate(mains):
            for j,values in enumerate(STATES):
                variants=range(3) if split=='train' else [3 if split=='development' else 4]
                for variant in variants:
                    cid=f'{group}_P{person}_S{j}_V{variant}';context=copy.deepcopy(base)
                    context.update(case_id=cid,person_id=f'{group}_P{person}',person_revision='synthetic-personal-contrasts-v3')
                    context['person'].update(evidence_notes=notes(kind,first,second,main,second['action'],variant),
                        compiled_environment_responses=[],prepared_person_interpretation={},initial_interpretation={},
                        preparation_status='synthetic_original_only',initial_interpretation_status='not_generated')
                    context['environment'].update(map_proximity_m={f:None for f in FEATURES},observed_signals={},
                        provenance='hypothetical scene for language evaluation; not real KINTEX measurements')
                    context['state'].update(fatigue=.2,current_action='seek',target_label='등록 장소 A',recent_events=[],
                        elapsed_minutes=60,last_rest_end_minutes=None)
                    context['execution']['previous_travel_action']='seek'
                    if kind=='latest_observation':
                        for atom,val in zip((first,second),values):
                            if atom['kind']!='environment':
                                add_fact(context,atom,not val if val is not None else True)
                                context['state']['recent_events'][-1]['elapsed_minutes']=15
                    fact_paths=[add_fact(context,atom,val) for atom,val in zip((first,second),values)]
                    possible,command=policy_results(kind,values,main,second['action'])
                    state_text='; '.join(a['phrase']+' '+('미확인' if v is None else '확인' if v else '아님이 확인') for a,v in zip((first,second),values))
                    reason=state_text+'. '+('가능한 개인 반응이 서로 달라 판단 유보.' if command=='defer' else '현재 조건에서 원문의 개인 반응은 '+action_text(command)+'.')
                    source='N2' if kind=='correction' else 'N1'
                    row=dict(id=cid,split=split,group_id=group,person_id=f'{group}_P{person}',
                        lineage_id=f'{group}_P{person}_S{j}',contrast_id=f'{group}_S{j}_V{variant}',variant=variant,
                        context=context,authoring_oracle=dict(kind=kind,first_atom=first['id'],second_atom=second['id'],
                            values=list(values),fact_paths=fact_paths,possible_commands=possible,expected_command=command,pair_key=pair_key),
                        expected_output=dict(next_command_id=command,source_ids=[source],reason=reason),
                        quality=dict(status='synthetic_authoring_review_pending',clinical_observations=0,real_frontend_output=False,
                            not_for_training_until_reviewed=True))
                    splits[split].append(row)
    files={}
    for split,rows in splits.items():
        p=out/(split+'.jsonl');p.write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows))
        files[p.name]=dict(rows=len(rows),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
            base_states=len({r['lineage_id'] for r in rows}),paired_source_groups=len({r['group_id'] for r in rows}),
            synthetic_person_profiles=len({r['person_id'] for r in rows}),
            action_counts=dict(collections.Counter(r['expected_output']['next_command_id'] for r in rows)))
    (out/'policies.json').write_text(json.dumps(policies,ensure_ascii=False,indent=2)+'\n')
    manifest=dict(status='draft_pending_audit',files=files,clinical_patient_count=0,independent_caregiver_sources=0,
        training_run_count=0,model_call_count=0,source_group_unit='paired authored profiles sharing an observation pair',
        templates='train prefix 0/1/2; development prefix 3; evaluation prefix 4; rule clauses shared across splits',
        limits=['Rule clauses are templated, not natural conversational diversity.',
                'Specific actions are hypothetical personal preferences, not population rules or safety recommendations.',
                'No actual K onboarding interpretation in this dataset.',
                'No direct evidence of real dementia behavior validity.'])
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))
if __name__=='__main__':make()
