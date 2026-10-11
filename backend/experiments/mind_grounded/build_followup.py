"""Freeze new compositional evaluation cases; no model or geographic calls."""
import argparse,json,hashlib
from pathlib import Path
from copy import deepcopy
from datetime import datetime
from app.schemas.persona import Persona
from app.schemas.prediction import PriorParams
from experiments.mind_upgrade.contract import State,context_for


def build(previous,out):
    out.mkdir(parents=True,exist_ok=True)
    if (out/'freeze.json').exists():raise ValueError('already frozen')
    old=json.loads((previous/'evaluation.json').read_text());byid={x['id']:x for x in old}
    dev=[deepcopy(byid[f'E{i:02d}']) for i in [3,4,5,6,7,8,9,10,13,14,20,21]]
    for i,c in enumerate(dev):c['original_case']=c['id'];c['id']=f'D{i+1:02d}'
    held=[]
    def add(note,actions,*,fatigue=.2,rest=None,lost=False,events=None,noise=None,crowd=None,
            feature='market',hour=9,target='등록 장소 A',goal=None,arrived=False,
            question='조건에 따라 어떻게 행동하시나요?',summary=None):
        template=deepcopy(old[0]);p=Persona.model_validate(template['persona']);p.id='composite-'+hashlib.sha256(note.encode()).hexdigest()[:12]
        p.onboarding_turns=[{'slot':'behavior','question':question,'answer':note}];p.behavior_notes=[summary or note]
        prior=PriorParams.model_validate(template['prior']);idx=f'S{len(held)+1:02d}'
        history=events if events is not None else ([{'kind':'orientation_lost','elapsed_minutes':59}] if lost else [])
        if rest is not None:history=history+[{'kind':'rest_complete','elapsed_minutes':rest}]
        s=State(elapsed_minutes=60,distance_m=500,fatigue=fatigue,confusion=.9 if lost else .2,
                current_action='seek',target_label=target,target_reached=arrived,
                last_rest_end_minutes=rest,recent_events=history)
        c=context_for(p,prior,s,case_id=idx,started_at=datetime(2026,9,28,hour-1),trigger='state_review',
                      env={feature+'_m':20},observations={feature:{'noisy':noise,'crowded':crowd}})
        held.append({'id':idx,'persona':p.model_dump(mode='json'),'prior':prior.model_dump(mode='json'),'context':c,
                     'rubric':{'actions':actions,'goal':goal,'avoid_feature':feature if 'avoid' in actions else None,
                               'basis':'Prewritten synthetic compositional condition; not clinical ground truth'}})
    n='많이 지쳤을 때는 시장 소리가 커도 먼저 앉아서 쉽니다. 지치지 않았는데 시장 소리가 크면 시장에서 멀어지는 쪽으로 걷습니다.'
    add(n,['rest'],fatigue=.9,noise=True);add(n,['avoid'],fatigue=.1,noise=True)
    n='길을 잃으면 지쳤든 아니든 움직이지 않고 가족을 기다립니다. 가족이 도착했다는 확인이 있으면 등록 장소 B로 다시 갑니다.'
    add(n,['stay'],fatigue=.9,lost=True)
    add(n,['seek'],goal='등록 장소 B',events=[{'kind':'orientation_lost','elapsed_minutes':57},{'kind':'family_arrived','elapsed_minutes':59}])
    n='저녁이면 등록 장소 B로 갑니다. 다만 가는 도중 시장이 시끄러우면 먼저 그 시장에서 멀어지는 길로 돌아갑니다.'
    add(n,['avoid'],hour=19,noise=True);add(n,['seek'],hour=19,noise=False,goal='등록 장소 B')
    n='등록 장소 A에 도착했다면 가족을 기다리며 그 자리에 머뭅니다. 아직 도착하지 않았는데 많이 지쳤다면 먼저 앉아서 쉽니다.'
    add(n,['stay'],arrived=True,fatigue=.9);add(n,['rest'],arrived=False,fatigue=.9)
    n='아무리 피곤해도 걸음을 멈추지 않습니다. 단, 길을 잃어서 어디인지 모를 때만 그 자리에 머무릅니다.'
    add(n,['stay'],fatigue=.9,lost=True);add(n,['continue','seek'],fatigue=.9,lost=False)
    n='공원에 사람이 많고 소리도 큰 것이 둘 다 확인되면 공원에서 멀어집니다. 둘 중 하나라도 확인되지 않았으면 원래 가던 길을 유지합니다.'
    add(n,['continue','seek'],feature='park',noise=True,crowd=None);add(n,['avoid'],feature='park',noise=True,crowd=True)
    n='시장이 지금 시끄러운 동안만 돌아갑니다. 조금 전에 시끄러웠어도 지금 조용하다는 확인이 있으면 원래 방향으로 계속 걷습니다.'
    add(n,['continue','seek'],noise=False,events=[{'kind':'market_noise_detected','elapsed_minutes':50}])
    add(n,['avoid'],noise=True,events=[{'kind':'market_quiet_detected','elapsed_minutes':50}])
    add('예전 기록은 등록 장소 A를 좋아한다고 되어 있지만 지금은 A에 가지 않고 등록 장소 B로 갑니다.',['seek'],goal='등록 장소 B',summary='등록 장소 A를 계속 선호함')
    add('어렸을 때 등록 장소 B를 자주 갔다는 이야기입니다. 요즘 가는 곳은 등록 장소 A이며 B에는 가지 않습니다.',['continue','seek'],goal='등록 장소 A',summary='등록 장소 B로 갈 가능성 높음')
    n='쉬었다는 사실만으로 바로 걷지는 않아요. 쉬고 나서도 많이 피곤하면 더 앉아 있고, 피곤함이 가라앉으면 등록 장소 B로 갑니다.'
    add(n,['rest'],rest=59,fatigue=.9,target='등록 장소 B');add(n,['continue','seek'],rest=59,fatigue=.1,target='등록 장소 B',goal='등록 장소 B')
    n='어디인지 모르게 되면 그 자리에 기다리지만, 다시 방향을 알게 되면 등록 장소 A로 걷습니다.'
    add(n,['continue','seek'],events=[{'kind':'orientation_lost','elapsed_minutes':10},{'kind':'orientation_regained','elapsed_minutes':59}],goal='등록 장소 A')
    add(n,['stay'],lost=True,events=[{'kind':'orientation_regained','elapsed_minutes':10},{'kind':'orientation_lost','elapsed_minutes':59}])
    add('아뇨. 그럴 때는 움직이지 않고 기다려요.',['stay'],lost=True,question='길을 잃었을 때도 계속 걸으시나요?')
    add('아니요. 기다리지 않고 등록 장소 A를 찾아서 걸어요.',['seek'],lost=True,goal='등록 장소 A',question='길을 잃으면 그 자리에 멈춰 기다리시나요?')
    n='등록 장소 B에 도착해도 멈추지 않고 목적지 없이 돌아다닙니다. 다만 어디인지 모르게 되면 제자리에서 기다립니다.'
    add(n,['roam'],target='등록 장소 B',arrived=True);add(n,['stay'],target='등록 장소 B',arrived=True,lost=True)
    manifest={'status':'prepared_pending_new_call_approval','development_cases':12,'evaluation_cases':24,
              'new_model_calls':0,'human_independent_evaluation':False,
              'proposed_development_calls':36,'proposed_evaluation_calls':48,'proposed_total_calls':84,
              'proposed_max_tokens_per_call':6000,'proposed_candidate_cap':3}
    for name,data in [('development',dev),('evaluation',held)]:
        blob=json.dumps(data,ensure_ascii=False,indent=2).encode();(out/(name+'.json')).write_bytes(blob)
        manifest[name+'_sha256']=hashlib.sha256(blob).hexdigest()
    (out/'freeze.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(manifest,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--previous',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();build(a.previous,a.out)
