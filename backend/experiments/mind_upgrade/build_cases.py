"""Freeze development cases and paired requests; no network, no model output."""
from pathlib import Path
from datetime import datetime
import json,random,hashlib,argparse
from app.schemas.persona import Persona,AttractionPoint
from app.schemas.common import GeoPoint
from app.schemas.prediction import PriorParams,LognormalParams
from app.llm import mind_v2
from .contract import State,context_for,request_spec


def build(center):
    labels=['합성 목적지 A','합성 목적지 B']
    prior=PriorParams(strategy_probs={'random_walk':1},attraction_weights={s:.5 for s in labels},
                      radius_lognormal=LognormalParams(mu=.095,sigma=1.48))
    # Contrasts are synthetic observations, not general statements about dementia.
    definitions=[
      ('fatigue_low','피로','피곤하지 않으면 A로 계속 걷고, 많이 피곤해지면 잠깐 앉아 쉰 뒤 다시 걷는다.',.1,.2,{},8,[],['continue','seek'],False),
      ('fatigue_high','피로','피곤하지 않으면 A로 계속 걷고, 많이 피곤해지면 잠깐 앉아 쉰 뒤 다시 걷는다.',.9,.2,{},8,[],['rest'],False),
      ('lost_wait','개인차','길을 잃어 어디인지 모르겠으면 돌아다니지 않고 그 자리에 머물러 가족을 기다린다.',.2,.9,{},8,[{'kind':'orientation_lost','elapsed_minutes':59}],['stay'],False),
      ('lost_walk','개인차','길을 잃어도 한 곳에서 기다리지 않고 가족을 찾으려고 계속 걸어 다닌다.',.2,.9,{},8,[{'kind':'orientation_lost','elapsed_minutes':59}],['continue','seek','roam'],False),
      ('quiet_market','환경','시장 주변이 조용하면 A로 계속 걷지만 시끄러우면 시장에서 멀어지는 길로 돌아간다.',.2,.2,{'market':{'noisy':False}},8,[],['continue','seek'],False),
      ('noisy_market','환경','시장 주변이 조용하면 A로 계속 걷지만 시끄러우면 시장에서 멀어지는 길로 돌아간다.',.2,.2,{'market':{'noisy':True}},8,[],['avoid'],False),
      ('known_not_seen','장소인식','평소 합성 목적지 A에 가고 싶다고 말한다. A가 눈앞에 보인다는 관찰은 아직 없다.',.2,.2,{},8,[],['continue','seek','roam','stay'],False),
      ('known_seen','장소인식','평소 합성 목적지 A에 가고 싶다고 말한다.',.2,.2,{},8,[],['continue','seek'],True),
      ('before_rest','이력','오래 걸어 피곤해지면 쉬고, 충분히 쉬고 나서는 A로 다시 걷는다.',.9,.2,{},8,[],['rest'],False),
      ('after_rest','이력','오래 걸어 피곤해지면 쉬고, 충분히 쉬고 나서는 A로 다시 걷는다.',.2,.2,{},8,[{'kind':'rest_complete','elapsed_minutes':59}],['continue','seek'],False),
      ('morning','시각','아침에는 합성 목적지 A에 가고 저녁에는 합성 목적지 B로 가는 습관이 있다.',.2,.2,{},7,[],['seek'],False),
      ('evening','시각','아침에는 합성 목적지 A에 가고 저녁에는 합성 목적지 B로 가는 습관이 있다.',.2,.2,{},17,[],['seek'],False),
    ]
    cases=[]
    for cid,pair,note,fatigue,confusion,obs,hour,history,allowed,visible in definitions:
        persona=Persona(id='synthetic-'+cid,name='합성',age=78,type='dementia',home=GeoPoint(**center),
            behavior_notes=[note],onboarding_turns=[{'slot':'behavior','question':'평소 행동은 어떤가요?','answer':note}],
            attraction_points=[AttractionPoint(label=lb,location=GeoPoint(**center),weight=.5,evidence='mention_only') for lb in labels])
        st=State(elapsed_minutes=60,distance_m=500,fatigue=fatigue,confusion=confusion,
                 current_action='seek',target_label=labels[0],recent_events=history,
                 last_rest_end_minutes=59 if cid=='after_rest' else None)
        c=context_for(persona,prior,st,case_id='pilot-'+pair,started_at=datetime(2026,9,28,hour),
                      trigger='diagnostic',env={'market_m':20},observations=obs,
                      observed_place_labels=[labels[0]] if visible else [])
        grade=lambda v:'높음' if v>=.7 else '중간' if v>=.4 else '낮음'
        report=f'집을 나선 지 60분 경과. 피로도: {grade(fatigue)}, 혼란도: {grade(confusion)}, 귀소 충동: 낮음, 불안: 낮음.'
        # A preserves the current production input boundary; B explicitly adds the
        # information it previously dropped. This is a system comparison, not a
        # claim that the same model's intrinsic reasoning became stronger.
        legacy=[{'role':'system','content':mind_v2.system_for(persona.type)},
                {'role':'user','content':mind_v2.build_input(persona,report,labels,prior,'시장 20m, 도로',random.Random(42))}]
        expectation={'allowed_actions':allowed,'goal':labels[0] if cid=='morning' else labels[1] if cid=='evening' else None,
                     'forbidden_invention':'A is visible' if cid=='known_not_seen' else None,
                     'source':'synthetic guardian statement; engineering rubric, not clinical truth'}
        cases.append({'id':cid,'pair':pair,'persona':persona.model_dump(mode='json'),'context':c,
                      'expectation':expectation,'legacy_request':{'model':'exaone-mind-dem5','messages':legacy,
                      'temperature':.3,'max_tokens':500,'guided_json':mind_v2.GUIDED_JSON,
                      'chat_template_kwargs':{'enable_thinking':False},'repetition_penalty':1.05},
                      'candidate_request':request_spec(c,'exaone-mind-dem5')})
    return cases

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--map-manifest',required=True);parser.add_argument('--out',required=True)
    a=parser.parse_args();meta=json.loads(Path(a.map_manifest).read_text());assert meta['region']=='KINTEX, Goyang'
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    data=build(meta['center']);blob=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
    (out/'cases.json').write_text(blob)
    (out/'preregistration.json').write_text(json.dumps({'status':'prepared','cases':12,'arms':['legacy','candidate'],
        'repeats':2,'inference_limit':48,'automatic_retries':0,'max_output_tokens_legacy':500,
        'max_output_tokens_candidate':700,'max_output_tokens_total':28800,
        'map_sha256':meta['sha256'],'cases_sha256':hashlib.sha256(blob.encode()).hexdigest(),
        'actual_cost':None,'support_round':None,'gpu_billed_hours':None,'new_embeddings':0,'new_K_calls':0,
        'heldout_usage':'none; these are development cases','clinical_accuracy_claim':False,
        'limitations':['synthetic environmental annotations, not current KINTEX sound measurements',
                      'previous-rest pair also changes fatigue; not a pure history-effect attribution',
                      'model+input+contract system comparison, not model-only attribution',
                      'places A/B are synthetic; direct-response tests do not execute destination paths']},ensure_ascii=False,indent=2)+'\n')
    print('frozen 12 synthetic development cases; 48 requests prepared, no calls')
