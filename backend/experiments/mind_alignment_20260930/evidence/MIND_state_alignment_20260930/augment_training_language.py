"""Train-only wording augmentation. Frozen development/evaluation bytes copied.

This is authored linguistic augmentation, not new observed persons or facts.
"""
import copy,hashlib,json,collections
from pathlib import Path
D=Path(__file__).resolve().parent
VERBS={
 'continue':('가던 곳을 향해 걷는 걸 이어갑니다','가려던 곳과 가던 방향을 그대로 유지해요'),
 'rest':('잠깐 앉아서 쉽니다','앉아서 몸을 쉬게 해요'),
 'stay':('다른 데로 가지 않고 그 자리에 서서 기다립니다','이동하지 않고 제자리에서 기다려요'),
 'roam':('목적지를 따로 두지 않고 주변을 걷습니다','가려는 곳을 정하지 않은 채 주변을 걸어 다녀요'),
 'seek_1':('원래 목표 대신 등록 장소 B로 가려고 합니다','가려던 곳을 등록 장소 B로 바꿔 그쪽으로 가요'),
}
for k,label in [('park','공원'),('market','시장'),('forest','숲길'),('water','물가')]:
    VERBS['avoid_'+k]=(f'{label}에서 멀어지는 길로 돌아갑니다',f'{label}을 피하는 쪽으로 걸어가요')

PHRASES={
 'reported_tiredness':('많이 지쳤다고 직접 이야기할 때','본인이 많이 지쳤다고 말한 경우'),
 'heavy_legs':('다리가 무겁다고 직접 이야기할 때','본인이 다리가 무겁다고 말한 경우'),
 'self_lost_awareness':('스스로 길을 잃었다는 걸 알아차렸을 때','길을 잃었다고 본인이 알아차린 경우'),
 'reported_thirst':('목이 마르다고 직접 이야기할 때','본인이 목마르다고 말한 경우'),
 'reported_hunger':('배가 고프다고 직접 이야기할 때','본인이 배고프다고 말한 경우'),
 'reported_toilet_need':('화장실에 가고 싶다고 직접 이야기할 때','본인이 화장실에 가고 싶다고 말한 경우'),
 'familiar_place_recognition':('주변 장소가 익숙한 곳임을 본인이 알아봤을 때','주변의 익숙한 장소를 본인이 알아본 경우'),
 'reported_anxiety':('불안하다고 직접 이야기할 때','본인이 불안하다고 말한 경우'),
 'reported_pain':('몸이 아프다고 직접 이야기할 때','본인이 몸이 아프다고 말한 경우'),
 'reported_cold':('춥다고 직접 이야기할 때','본인이 춥다고 말한 경우'),
 'approaching_stranger':('낯선 사람이 다가올 때','낯선 사람이 다가오는 경우'),
 'family_companion':('가족이 곁에서 함께 걸을 때','가족이 곁에서 동행하는 경우'),
}
for f,l in [('park','공원'),('market','시장'),('forest','숲길'),('water','물가')]:
    PHRASES[f+'_noisy']=(f'{l}에서 소음이 들릴 때',f'{l}에서 소음이 들리는 경우')
    PHRASES[f+'_crowded']=(f'{l}에 사람이 붐빌 때',f'{l}에 사람이 붐비는 경우')

def wording(kind,first,second,main,other,index):
    a,b=PHRASES[first][index],PHRASES[second][index]
    x,y,z=VERBS[main][index],VERBS['continue'][index],VERBS[other][index]
    if kind in ('single','correction','latest_observation'):
        return f'질문: {a}는 어떤가요? 답변: {x}. 질문: 그런 상황이 아니면요? 답변: {y}. {b}만으로는 이 반응이 달라지지는 않아요.'
    if kind=='and':return f'말씀하신 두 가지, 즉 {a}와 {b}가 함께 겹쳐야 {x}. 하나라도 해당하지 않으면 {y}. 하나만 해당할 때까지 같은 반응이라고 말한 건 아니에요.'
    if kind=='or':return f'{a}와 {b} 중 어느 하나라도 해당하면 {x}. 두 가지가 동시에 있어야 하는 건 아니고요. 둘 다 해당하지 않는 경우에만 {y}.'
    if kind=='unless':return f'{a}는 보통 {x}. 단, {b}라면 예외예요. 그때는 {y}. 처음 말씀드린 상황 자체가 아닐 때도 {y}.'
    if kind=='priority':return f'겹칠 때의 순서도 말씀드릴게요. {a}라면 우선 {x}. 그 첫 상황이 아닐 때에 한해서, {b}라면 {z}. 두 가지 모두 아니라면 {y}.'
    raise ValueError(kind)

def build():
    src=D/'personal_contrasts_v3';out=D/'personal_contrasts_v4';out.mkdir(exist_ok=False)
    policies={p['group_id']:p for p in json.loads((src/'policies.json').read_text())}
    original=[json.loads(x) for x in (src/'train.jsonl').read_text().splitlines()];updated=[]
    for row in original:
        r=copy.deepcopy(row);v=r['variant'];p=policies[r['group_id']]
        if v:
            index=v-1;person=int(r['person_id'].rsplit('P',1)[-1]);main=p['main_commands'][person]
            new=wording(p['kind'],p['first']['id'],p['second']['id'],main,p['second_command'],index)
            if p['kind']=='correction':
                r['context']['person']['evidence_notes'][1]['text']='앞선 N1의 설명은 현재 모습을 잘못 전한 내용입니다. 제가 반복해 본 현재 반응으로 바로잡을게요. '+new
            else:r['context']['person']['evidence_notes'][0]['text']='직접 함께 외출하며 여러 번 봤던 모습에 관한 답변입니다. '+new
        r['quality']['language_variant_method']='authored clause paraphrase and reordered explanation, no new person or observation'
        updated.append(r)
    (out/'train.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in updated))
    for name in ('development.jsonl','evaluation.jsonl','policies.json'):(out/name).write_bytes((src/name).read_bytes())
    manifest=json.loads((src/'manifest.json').read_text())
    manifest['templates']='Train variants 1/2 use authored clause paraphrases; development/evaluation byte-identical to v3. Shared conditional grammar remains.'
    manifest['parent_version']='personal_contrasts_v3'
    for name,entry in manifest['files'].items():entry['sha256']=hashlib.sha256((out/name).read_bytes()).hexdigest()
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(train_rows=len(updated),new_patient_count=0,development_unchanged=(out/'development.jsonl').read_bytes()==(src/'development.jsonl').read_bytes(),evaluation_unchanged=(out/'evaluation.jsonl').read_bytes()==(src/'evaluation.jsonl').read_bytes()),ensure_ascii=False))
if __name__=='__main__':build()
