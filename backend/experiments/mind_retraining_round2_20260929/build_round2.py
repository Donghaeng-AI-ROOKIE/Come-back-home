"""Offline author-labelled contrasts. No model calls or production word mapping."""
from pathlib import Path
import hashlib,json
from collections import Counter
import authoring_base as base
from audit import audit

ROOT=Path(__file__).resolve().parent
PREVIOUS=ROOT.parent/'mind_retraining_20260928'/'lora'/'dataset_v2'

def supplements():
    return [
    ('T19','train','ACOUSTIC','개인별 소음 반응과 관측',
     '어머니는 시장 소리가 크면 그쪽에서 멀어져요. 사람이 없어도 소리가 크면 돌아가고, 소리가 작다고 확인되면 사람이 많아도 원래 길을 가세요. 소리를 확인 못 한 때는 어떻게 하실지 본 적 없어요.',[
      ({'noise':True,'crowd':False},'avoid','사람은 적지만 시장 소음이 확인됐고, 어머니의 회피 조건은 소음이다.'),
      ({'noise':True,'crowd':None},'avoid','혼잡은 미확인이지만 소음이 확인되어 이 사람의 회피 조건은 충분하다.'),
      ({'noise':False,'crowd':True},'continue','시장은 혼잡하지만 조용하다는 확인이 있고, 그때는 이동을 유지한 개인 기록이다.'),
      ({'noise':False,'crowd':None},'continue','혼잡은 미확인이며 조용한 시장에서는 계속 간다는 개인 조건을 적용한다.'),
      ({'noise':None,'crowd':False},'defer','사람이 적다는 사실은 조용하다는 뜻이 아니다. 소음 관측과 그 상황의 반응을 확인해야 한다.'),
      ({'noise':None,'crowd':True},'defer','혼잡만 확인되어 소음에 반응하는 이 사람의 행동을 구분할 수 없다.')]),
    ('T20','train','ACOUSTIC','복합 조건의 부정과 미확인',
     '아버지는 시장에 사람이 몰려 있으면서 소리까지 클 때에만 돌아가세요. 둘 중 하나라도 아니라는 걸 알면 그대로 가세요. 둘 다 확인 안 된 상황은 모르겠어요.',[
      ({'noise':True,'crowd':True},'avoid','소음과 혼잡이 모두 확인되어 아버지의 두 조건이 함께 충족됐다.'),
      ({'noise':True,'crowd':True,'hour':15},'avoid','오후에도 소음과 혼잡이 모두 관측됐으므로 같은 개인 회피 조건이 성립한다.'),
      ({'noise':False,'crowd':None},'continue','혼잡은 미확인이지만 소음이 없다고 확인되어 두 조건의 동시 성립은 아니다.'),
      ({'noise':None,'crowd':False},'continue','소음은 미확인이지만 사람이 몰리지 않았다는 관측 때문에 복합 회피 조건이 성립하지 않는다.'),
      ({'noise':True,'crowd':None},'defer','소음만 확인됐고 혼잡은 미확인이라 두 조건이 함께 성립하는지 알 수 없다.'),
      ({'noise':None,'crowd':True},'defer','혼잡만 확인됐고 소음은 미확인이라 회피 조건 충족 여부를 확인해야 한다.')]),
    ('T21','train','ACOUSTIC','같은 환경에서 다른 개인 행동',
     '공원이 시끄러우면 어머니는 돌아가지 않고 서서 저를 기다리세요. 조용할 때는 원래 가던 길을 가요. 시끄러운지 모를 때의 반응은 관찰한 적 없어요.',[
      ({'feature':'park','noise':True,'crowd':False},'stay','소음이 확인됐고 어머니는 소음을 피해 걷는 대신 기다리는 분이다.'),
      ({'feature':'park','noise':True,'crowd':None},'stay','혼잡은 미확인이나 확인된 소음에 대한 개인 반응은 대기이다.'),
      ({'feature':'park','noise':False,'crowd':True},'continue','혼잡과 별개로 조용한 공원에서는 원래 이동을 유지한 기록이다.'),
      ({'feature':'park','noise':False,'crowd':None},'continue','조용함은 확인됐고 혼잡은 미확인이므로 조용할 때의 개인 반응을 적용한다.'),
      ({'feature':'park','noise':None,'crowd':False},'defer','사람이 적어도 소음은 미확인이라 대기와 이동을 선택할 근거가 부족하다.'),
      ({'feature':'park','noise':None,'crowd':True},'defer','혼잡을 소음으로 간주하지 않고 소음 관측을 추가 확인해야 한다.')]),
    ('T22','train','SYNTHETIC_ONLY','거부 조건의 확인과 정정',
     '아버지는 A에 가기 싫다고 하신 게 확인되면 목적지를 정하지 않고 걷곤 해요. 싫지 않다고 확인했으면 A로 계속 가시고요. 지금 마음을 확인 못 한 때는 어떤지 모르겠어요.',[
      ({'rejection':True},'roam','현재 A 거부가 확인되어 목표 없이 걷는 개인 이력을 적용한다.'),
      ({'rejection':True,'hour':16},'roam','오후라는 사실보다 현재 확인된 거부와 그에 대한 개인 행동이 결정 근거다.'),
      ({'rejection':False,'noise':None},'continue','A를 거부하지 않는다는 확인에 따라 이동을 유지하며 소음은 미확인으로 남긴다.'),
      ({'rejection':False,'crowd':True},'continue','혼잡에 대한 개인 회피 조건은 없고 A를 거부하지 않는다는 현재 확인이 있다.'),
      ({'rejection':None},'defer','과거 거부 행동만으로 현재도 거부한다고 볼 수 없어 지금 발언 확인이 필요하다.'),
      ({'rejection':None,'hour':16},'defer','시각만으로 현재 A 거부 여부를 알 수 없으므로 선택을 유보한다.')]),
    ('T23','train','ENGINE_ONLY','휴식 종료와 실제 피로 회복',
     '엄마는 쉬는 시간이 끝났어도 아직 많이 힘들어하면 더 앉아 계세요. 덜 힘들어진 게 확인되면 기억한 목적지로 다시 걸어요. 시간이 지났다고 저절로 회복됐다고 보지는 않아요.',[
      ({'f':.9,'previous':'rest','rest':59},'rest','휴식 종료는 1분 전이지만 현재 피로가 높아 더 앉는 개인 조건이다.'),
      ({'f':.9,'previous':'rest','rest':30},'rest','휴식 종료 후 30분이 지났어도 현재 피로가 높다고 주어져 휴식을 선택한다.'),
      ({'f':.1,'previous':'rest','rest':59},'seek:A','피로가 낮아졌고 이전에는 휴식 중이었으므로 기억한 A로 이동을 재개한다.'),
      ({'f':.1,'previous':'rest','rest':30,'target':'B'},'seek:B','현재 낮은 피로를 근거로 휴식 전 기억한 B로 다시 이동한다.'),
      ({'f':.9,'previous':'rest','rest':59,'noise':True},'rest','소음은 관측됐지만 개인에게 명시된 현재 높은 피로 반응은 더 쉬는 것이다.'),
      ({'f':.1,'previous':'rest','rest':59,'target':'B','noise':None},'seek:B','소음은 미확인으로 남기고 확인된 피로 회복과 목표 B에 근거해 이동을 재개한다.')]),
    ('T24','train','CAREGIVER','지시와 다른 사람의 행동 구분',
     '동생이 아버지에게 시장이 시끄러우면 피해서 가라고 했어요. 실제로 아버지가 그렇게 하는지는 못 봤어요.',[
      ({'noise':True},'defer','소음은 확인됐지만 보호자 지시를 실제 개인 행동으로 단정할 수 없다.'),
      ({'noise':True,'note':'옆집 할머니는 시장 소리가 크면 돌아간대요. 우리 아버지가 그러는지는 못 봤어요.'},'defer','다른 사람의 회피 행동은 이 아버지의 개인 특성을 입증하지 않는다.'),
      ({'noise':True,'note':'아버지가 알겠다고 답했지만 이후 행동은 확인하지 못했어요.'},'defer','수락 발언만으로 소음 상황에서 실제로 회피한다고 확정할 수 없다.'),
      ({'noise':True,'note':'아버지는 최근 시장 소리가 클 때마다 반대편으로 돌아가는 모습을 여러 차례 직접 봤어요.'},'avoid','이 아버지의 반복된 회피 관찰과 현재 시장 소음이 연결된다.'),
      ({'noise':True,'crowd':None,'note':'지시 이야기가 아니라 직접 본 기록이에요. 아버지는 시장 소리가 크면 그쪽에서 멀어져요.'},'avoid','혼잡은 미확인이나 현재 소음과 아버지에게 직접 관찰한 회피가 근거다.'),
      ({'noise':True,'note':'돌아간다는 건 옆집 분 얘기였어요. 아버지는 시끄러워도 원래 가던 길을 계속 가셨습니다.'},'continue','타인의 사례를 제외하고 아버지에게 관찰한 지속 이동을 적용한다.')]),
    ('T25','train','ACOUSTIC','관측 조건의 최근 정정',
     '예전 요약에는 시장 소리가 커도 그냥 간다고 돼 있지만 최근에는 큰 소리가 확인되면 돌아가세요. 조용하면 그대로 가세요. 확인 못 한 때는 모르겠고요.',[
      ({'noise':True,'summary':'시끄러워도 계속 걷는다'},'avoid','과거 요약과 달리 최근 원문은 확인된 시장 소음에서 회피한다고 정정했다.'),
      ({'noise':True,'crowd':False,'summary':'소음에 반응하지 않는다'},'avoid','사람이 적더라도 큰 소리가 확인됐고 최신 개인 기록은 회피이다.'),
      ({'noise':False,'summary':'시장은 언제나 회피한다'},'continue','최신 원문은 조용한 시장에서는 그대로 간다고 하므로 과도한 요약을 적용하지 않는다.'),
      ({'noise':None,'summary':'시장은 언제나 회피한다'},'defer','현재 소음은 미확인이며 언제나 회피한다는 요약은 원문의 조건을 보존하지 못한다.'),
      ({'noise':True,'note':'시장이 시끄러워도 최근에는 계속 원래 길로 가세요. 예전에 돌아가던 행동은 요즘과 달라요.','summary':'소음이 있으면 회피한다'},'continue','최근 직접 관찰한 지속 이동으로 과거 회피 요약을 정정한다.'),
      ({'noise':None,'crowd':True},'defer','최근 회피 조건은 소음이며 혼잡만 확인된 현재에는 소음을 추가 확인해야 한다.')]),
    ('T26','train','ACOUSTIC','익숙한 등록 장소로 이동하는 반응',
     '공원에서 큰 소리가 들리면 아버지는 그냥 반대쪽으로 피하는 대신 익숙한 등록 장소 B를 찾아가요. 조용하면 원래 길을 가고, 소리를 확인 못했을 때는 모르겠어요.',[
      ({'feature':'park','noise':True},'seek:B','확인된 공원 소음에 대한 개인 반응은 임의 방향 회피가 아니라 등록 장소 B 찾기다.'),
      ({'feature':'park','noise':True,'crowd':None},'seek:B','혼잡은 미확인이지만 소음이 확인되어 익숙한 B를 찾는 개인 조건이 성립한다.'),
      ({'feature':'park','noise':False,'crowd':True},'continue','공원은 혼잡하지만 조용하다는 관측에 따라 원래 이동을 유지한다.'),
      ({'feature':'park','noise':False,'target':'B'},'continue','이미 B로 이동 중이며 조용할 때는 기존 이동을 유지한다는 개인 기록이다.'),
      ({'feature':'park','noise':None},'defer','소음이 미확인이라 원래 이동과 B 탐색 중 무엇이 해당하는지 구분할 수 없다.'),
      ({'feature':'park','noise':None,'crowd':False},'defer','사람이 적다는 관측을 조용함으로 바꾸지 않고 소음 확인을 요청한다.')])]

def main():
    dst=ROOT/'dataset_augmented'
    if dst.exists():raise SystemExit('immutable dataset exists')
    old=[json.loads(x) for x in (PREVIOUS/'train.jsonl').read_text().splitlines()]
    sources=json.loads((ROOT/'sources.json').read_text())
    base.families=supplements
    added=base.build(old[0]['context'],sources)
    assert len(added)==48
    dst.mkdir()
    blob=('\n'.join(json.dumps(r,ensure_ascii=False,sort_keys=True) for r in old+added)+'\n').encode()
    (dst/'train.jsonl').write_bytes(blob)
    for split in ['development','evaluation']:(dst/(split+'.jsonl')).write_bytes((PREVIOUS/(split+'.jsonl')).read_bytes())
    manifest={'contract':'mind-sft-evidence-v1','records':152,'families':34,'files':{},
      'augmentation':'48 authored contrast records, no model generation',
      'model_calls':0,'gpu_training':False,'human_review':False,'clinical_validation':False,
      'development_role':'previously inspected development set; augmentation guided by its error categories',
      'evaluation_role':'previously authored/visible 16-state holdout; not independent clinical or blind evaluation',
      'comparison_limit':'fixed epoch count also changes optimizer steps when dataset size changes; not a compute-matched ablation'}
    for split in ['train','development','evaluation']:
      p=dst/(split+'.jsonl');rows=[json.loads(x) for x in p.read_text().splitlines()]
      manifest['files'][p.name]={'records':len(rows),'families':len({r['case_family'] for r in rows}),
        'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
        'actions':dict(Counter(r['expected']['action'] or 'insufficient_information' for r in rows))}
    (dst/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    result=audit(dst);(dst/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2));assert not result['errors']
    lines=['# 追加48件の原文と明示ラベル'.replace('追加48件の原文と明示ラベル','추가 48개 합성 입력·명시적 정답 검토'),'',
      'AI가 작성한 조건 대비 사례. 독립 전문가 검수·실제 환자 데이터가 아님. 개발 오류 유형을 보고 보강함.','']
    for r in added:
      lines += ['## '+r['id']+' · '+r['topic'],'',r['context']['person']['evidence_notes'][0]['text'],'',
       '```json',json.dumps({'state':r['context']['state'],'environment':r['context']['environment'],'expected':r['expected']},ensure_ascii=False,indent=2),'```','']
    (ROOT/'추가48개_검토.md').write_text('\n'.join(lines))

if __name__=='__main__':main()
