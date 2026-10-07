"""Freeze development/evaluation synthetic cases before receiving new outputs."""
import argparse,json,hashlib
from pathlib import Path
from datetime import datetime
from app.geo.roadnet import OSMnxNetwork
from app.geo.h3grid import haversine_km
from app.schemas.common import GeoPoint
from app.schemas.persona import Persona,AttractionPoint
from app.schemas.prediction import PriorParams,LognormalParams
from experiments.mind_upgrade.contract import State,context_for


def build(cache):
    meta=json.loads((cache/'kintex_walk.json').read_text());net=OSMnxNetwork.from_graphml(cache/'kintex_walk.graphml')
    center=GeoPoint(**meta['center']);import networkx as nx
    start=net.nearest_node(center);component=nx.node_connected_component(net.graph.to_undirected(),start)
    candidates=[n for n in component if 250<haversine_km(center,net.node_location(n))*1000<450]
    nodes=[min(candidates,key=lambda n:net.node_location(n).lng),max(candidates,key=lambda n:net.node_location(n).lng)]
    points=[net.node_location(n) for n in nodes];labels=['등록 장소 A','등록 장소 B']
    def make(i,note,actions,*,fatigue=.2,rest_end=None,lost=False,noise=None,crowd=None,feature='market',hour=9,goal=None,arrived=False,summary=None,question='평소 어떤 행동을 보이나요?'):
        persona=Persona(id=f'person-{hashlib.sha256(note.encode()).hexdigest()[:10]}',name='합성 평가',age=78,type='dementia',home=center,
            onboarding_turns=[{'slot':'behavior','question':question,'answer':note}],
            behavior_notes=[summary or note],attraction_points=[AttractionPoint(label=lb,location=point,place_type='registered_synthetic') for lb,point in zip(labels,points)])
        prior=PriorParams(strategy_probs={'random_walk':1},attraction_weights={lb:.5 for lb in labels},radius_lognormal=LognormalParams(mu=0,sigma=1))
        history=([{'kind':'orientation_lost','elapsed_minutes':59}] if lost else [])+([{'kind':'rest_complete','elapsed_minutes':rest_end}] if rest_end is not None else [])
        state=State(elapsed_minutes=60,distance_m=500,fatigue=fatigue,confusion=.9 if lost else .2,
                    current_action='seek',target_label=labels[0],target_reached=arrived,last_rest_end_minutes=rest_end,recent_events=history)
        context=context_for(persona,prior,state,case_id=i,started_at=datetime(2026,9,28,hour-1),trigger='state_review',
                    env={feature+'_m':20},observations={feature:{'noisy':noise,'crowded':crowd}})
        return {'id':i,'persona':persona.model_dump(mode='json'),'prior':prior.model_dump(mode='json'),'context':context,
                'rubric':{'actions':actions,'goal':goal,'avoid_feature':feature if 'avoid' in actions else None,
                          'basis':'prewritten synthetic guardian condition; not clinical ground truth'}}
    n='피곤하지 않으면 등록 장소 A로 계속 걷고, 많이 피곤해지면 잠깐 앉아 쉰 뒤 다시 걷는다.'
    dev=[make('D01',n,['rest'],fatigue=.9),make('D02',n,['continue','seek'],fatigue=.1),
         make('D03','오래 걸어 피곤해지면 쉬고, 충분히 쉬고 나서는 등록 장소 A로 다시 걷는다.',['continue','seek'],rest_end=59),
         make('D04','몸이 지쳐도 앉아서 쉬지 않고 계속 걷는다. 쉬자고 해도 걸음을 멈추지 않는 모습이 반복된다.',['continue','seek','roam'],fatigue=.9),
         make('D05','길을 잃어 어디인지 모르겠으면 그 자리에 머물러 가족을 기다린다.',['stay'],lost=True),
         make('D06','길을 잃어도 한 곳에서 기다리지 않고 가족을 찾으려고 계속 걸어 다닌다.',['continue','seek','roam'],lost=True),
         make('D07','시장 주변이 조용하면 등록 장소 A로 계속 걷지만 시끄러우면 시장에서 멀어지는 길로 돌아간다.',['avoid'],noise=True),
         make('D08','시장 주변이 조용하면 등록 장소 A로 계속 걷지만 시끄러우면 시장에서 멀어지는 길로 돌아간다.',['continue','seek'],noise=False)]
    held=[]
    def add(note,actions,**kw):held.append(make(f'E{len(held)+1:02d}',note,actions,**kw))
    n='기운이 남았을 땐 걷습니다. 지친 날에는 걸음을 끊고 잠시 앉았다가 다시 나섭니다.'
    add(n,['rest'],fatigue=.95);add(n,['continue','seek'],fatigue=.12)
    n='쉬었다고 바로 움직이지는 않아요. 피로가 가라앉은 뒤에야 다시 등록 장소 A 쪽으로 걷고, 여전히 지치면 더 쉬어요.'
    add(n,['continue','seek'],fatigue=.1,rest_end=58);add(n,['rest'],fatigue=.9,rest_end=58)
    add('여기가 어딘지 모르겠다고 할 때는 같은 자리에 서서 아들이 올 때까지 기다려요.',['stay'],lost=True)
    add('여기가 어딘지 모를 때도 누가 올 때까지 서 있지는 않아요. 직접 찾아보겠다며 발길을 옮깁니다.',['continue','seek','roam'],lost=True)
    n='공원에서 큰 소리가 들리면 그쪽에서 멀어집니다. 조용한 공원 옆은 피하지 않고 원래 가던 데로 걷습니다.'
    add(n,['avoid'],feature='park',noise=True);add(n,['continue','seek'],feature='park',noise=False)
    n='시장이 붐비고 소리도 클 때에만 시장 반대쪽으로 갑니다. 사람이 많아도 조용하면 가던 길을 계속 갑니다.'
    add(n,['avoid'],noise=True,crowd=True);add(n,['continue','seek'],noise=False,crowd=True)
    n='시장이 시끄럽다는 것을 확인하면 돌아가고, 그런 확인이 없을 때는 등록 장소 A로 가던 길을 유지합니다.'
    add(n,['continue','seek'],noise=None);add(n,['avoid'],noise=True)
    n='아침에는 등록 장소 A에 가고 저녁에는 등록 장소 B에 가는 일과가 있습니다.'
    add(n,['continue','seek'],hour=8,goal='등록 장소 A');add(n,['seek'],hour=19,goal='등록 장소 B')
    add('많이 지치면 지금 하던 이동을 멈추고 쉬어요. 피곤해도 걷는다는 이전 요약은 잘못됐습니다.',['rest'],fatigue=.9,summary='많이 피곤해도 계속 걷는다')
    add('많이 지쳐도 걸음을 멈추지는 않습니다. 피곤하면 앉는다는 이전 요약은 잘못됐어요.',['continue','seek','roam'],fatigue=.9,summary='많이 피곤하면 반드시 쉰다')
    add('길이 낯설어지면 가족에게 도움을 기다리며 그 자리에 머뭅니다. 가족을 찾아 돌아다니지는 않아요.',['stay'],lost=True)
    add('길이 낯설어지면 기다리는 대신 익숙한 등록 장소 B를 향해 걸어갑니다.',['seek'],lost=True,goal='등록 장소 B')
    add('예전엔 등록 장소 A를 찾았지만 요즘은 거긴 가지 않겠다며 등록 장소 B로 향합니다.',['seek'],goal='등록 장소 B')
    add('등록 장소 A에 이르면 멈춰 서서 기다리고 도착하기 전에는 그곳으로 계속 갑니다.',['stay'],arrived=True)
    add('등록 장소 A에 이르면 멈춰 서서 기다리고 도착하기 전에는 그곳으로 계속 갑니다.',['continue','seek'],arrived=False,goal='등록 장소 A')
    add('그때는 안 걸어요. 잠깐 앉아서 쉽니다.',['rest'],fatigue=.9,question='많이 피곤해졌을 때에도 계속 걷나요?')
    add('아니요. 그래도 계속 걸으세요.',['continue','seek','roam'],fatigue=.9,question='많이 피곤해졌을 때에는 앉아서 쉬나요?')
    add('시장 소리가 크더라도 사람이 드물면 원래 가던 길을 유지하고, 사람이 많아도 조용하면 피하지 않아요. 두 조건이 함께 나타날 때만 돌아갑니다.',['continue','seek'],noise=True,crowd=False)
    return dev,held,meta

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cache',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    out=Path(a.out);out.mkdir(exist_ok=True,parents=True)
    if (out/'freeze.json').exists():raise SystemExit('already frozen; no overwrite')
    dev,held,meta=build(Path(a.cache));manifest={}
    for name,data in [('development',dev),('evaluation',held)]:
        blob=json.dumps(data,ensure_ascii=False,indent=2).encode();(out/(name+'.json')).write_bytes(blob);manifest[name]={'cases':len(data),'sha256':hashlib.sha256(blob).hexdigest()}
    manifest.update(map_sha256=meta['sha256'],human_independent_evaluation=False,model_calls_before_freeze=0,
                    approved_total=112,approved_development=64,approved_evaluation=48,per_model_max=80,
                    max_tokens={'dem5':900,'k':6000},new_embeddings=0,new_maps=0,new_training=0)
    (out/'freeze.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(manifest,ensure_ascii=False))
