"""80 authored stress inputs: 20 source narratives x four scenes, not 80 people."""
import copy,hashlib,json
from pathlib import Path
from build_compositional_draft import ATOMS,add_fact,FEATURES
from unique_command_contract import validate
D=Path(__file__).resolve().parent
CASES=[
('N01','park_noisy','avoid_park','continue','defer','공원 소리가 시끄러우면 그쪽으로는 안 가고 돌아 나오세요. 조용할 때는 가던 길로 계속 가는 걸 여러 번 봤어요. 시끄러운지 모르면 어느 쪽일지 말할 수 없고요.'),
('N02','market_noisy','stay','continue','defer','시장이 시끄럽다고 피해 걷는 분은 아니에요. 그럴 때는 서서 저를 기다리세요. 소음이 없으면 원래 가시던 길로 가고요. 소리를 확인하지 못한 지금 같은 때의 반응은 모르겠어요.'),
('N03','water_crowded','seek_1','continue','defer','물가에 사람이 붐비는 날에는 가려던 곳을 바꿔 등록 장소 B로 가세요. 사람 없는 날에는 원래 목적지 그대로 가시고요. 붐비는지 모르면 목표를 바꿀지도 몰라요.'),
('N04','forest_noisy','continue','continue','continue','숲길 소리가 시끄러울 때도, 조용할 때도 가던 데로 계속 가세요. 그 소리 유무에 따라 길이나 목표를 바꾸는 분은 아니에요.'),
('N05','reported_tiredness','rest','continue','defer','본인 입으로 많이 지쳤다고 하실 때는 앉아서 쉬세요. 그런 말씀을 하지 않은 게 확인됐을 때는 가던 길을 계속 가셨어요. 지금 말씀하셨는지는 모르겠다면 반응도 정할 수 없어요.'),
('N06','reported_tiredness','continue','continue','continue','지쳤다고 하셔도 정해 둔 곳을 향해 계속 걸으세요. 지쳤다는 말을 안 하실 때도 마찬가지였어요. 제가 쉬라고 권하는 것과 실제로 쉬시는 건 다르더라고요.'),
('N07','self_lost_awareness','stay','continue','defer','길을 잃었다고 스스로 알아차린 뒤에는 서서 가족을 기다렸어요. 본인이 길을 잃었다고 생각하지 않는 게 확인된 때는 가던 길을 갔고요. 본인이 알아차렸는지까지 모르는 때는 어느 쪽일지 모르겠어요.'),
('N08','self_lost_awareness','continue','continue','continue','길을 놓쳤다는 걸 본인이 알아도 계속 걷는 걸 봤어요. 알아차리지 않은 때도 이동을 이어갔어요. 알아차렸다는 사실만으로 멈춘다고 보시면 안 돼요.'),
('N09','family_companion','stay','continue','defer','가족이 곁에 같이 있을 때는 서서 기다리는 모습을 반복해서 봤어요. 가족이 함께 있지 않은 게 확인된 때는 원래 가던 길로 계속 가셨고요. 동행을 모르면 반응도 모르겠어요.'),
('N10','family_companion','continue','continue','continue','가족이 같이 걸어도 안 걸어도 원래 정해 둔 목표를 향해 걸음을 이어가세요. 가족이 있느냐에 따라서 멈추거나 돌아가지는 않았어요.'),
('N11','reported_toilet_need','seek_1','continue','defer','화장실에 가고 싶다고 말씀하면 등록 장소 B로 목적지를 바꿔 가세요. 그런 말씀을 하지 않았다고 확인된 때는 원래 목적지로 갔어요. 말씀 여부를 못 들었으면 어느 쪽일지 모르겠고요.'),
('N12','approaching_stranger','stay','continue','defer','모르는 사람이 다가오면 다른 곳으로 걷지 않고 제자리에 서서 기다려요. 다가오는 사람이 없는 게 확인되면 원래 길을 걸어가세요. 접근 여부를 모르면 어느 반응인지 모르겠어요.'),
('N13','market_noisy','defer','defer','defer','질문: 시장이 시끄러우면 돌아가시나요? 답: 그러셨으면 해서 피해서 가라고 제가 부탁했어요. 실제로 소리가 클 때나 작을 때 어떻게 움직이시는지는 본 적 없어요.'),
('N14','family_companion','defer','defer','defer','제가 곁에 있든 없든 여기서 기다리겠다고 대답은 하셨어요. 그 뒤 실제로 기다렸는지 걸어갔는지는 확인 못 했어요. 대답했다는 사실까지만 알아요.'),
('N15','park_noisy','defer','defer','defer','공원이 시끄러우면 쉬는 사람은 아버지가 아니라 옆집 어르신이에요. 지금 찾는 아버지가 공원에서 어떻게 반응하시는지는 시끄러울 때나 조용할 때나 본 적이 없어요.'),
('N16','market_noisy','defer','defer','defer','예전에 시장에서 일하셨다는 것만 알아요. 요즘 그곳에 가려는지, 시장 소리를 좋아하는지 피하는지, 그런 때 어디로 움직이는지는 모르겠어요.'),
('N17','market_noisy','stay','continue','defer','제가 예전에 소음이 있으면 피한다고 말씀드린 건 현재 모습을 잘못 전한 거였어요. 요즘 반복해서 보니 시끄러우면 제자리에서 기다리고 조용하면 가던 길로 가세요. 소음 여부가 미확인이면 어느 쪽일지 몰라요.'),
('N18','reported_anxiety','rest','continue','defer','불안하다고 직접 말씀하면 잠깐 앉아서 쉬시는 분이에요. 그렇게 말하지 않은 게 확인됐을 때에는 하던 이동을 이어갔어요. 단지 얼굴만 보고 불안하다고 넘겨짚지는 말아 주세요. 말씀 여부를 모르는 상황은 저도 모르겠어요.'),
('N19','reported_cold','seek_1','continue','defer','춥다고 직접 말씀하신 때는 원래 목표를 바꿔 등록 장소 B로 가는 걸 여러 번 봤어요. 그런 발언이 없다고 확인된 때는 가던 길을 가셨고요. 날씨만 보고 본인이 춥다고 말했다고 단정할 수는 없어요. 발언을 못 들었으면 모르겠어요.'),
('N20','heavy_legs','rest','continue','defer','많이 걸었다는 시간만으로 앉으시는 건 아니에요. 본인이 다리가 무겁다고 말하면 앉아서 쉬고, 그 말이 없다고 확인된 때는 계속 걸어요. 지금 어떤 말씀을 하셨는지 모르면 둘 중 어느 행동일지 정할 수 없어요.'),
]
def main():
    out=D/'natural_stress_v1';out.mkdir(exist_ok=False)
    atoms={a['id']:a for a in ATOMS};base=json.loads((D/'dataset/development.jsonl').read_text().splitlines()[0])['context'];rows=[]
    for family,atom_id,yes,no,unknown,original in CASES:
        for i,value in enumerate([True,False,None,True]):
            context=copy.deepcopy(base);cid=f'ST_{family}_{i}'
            context.update(case_id=cid,person_id='stress-'+family,person_revision='natural-stress-v1')
            context['person'].update(evidence_notes=[dict(id='N1',text=original)],compiled_environment_responses=[],
                prepared_person_interpretation={},initial_interpretation={},preparation_status='synthetic_original_only',initial_interpretation_status='not_generated')
            context['state'].update(fatigue=.2,current_action='seek',target_label='등록 장소 A',recent_events=[],elapsed_minutes=60,last_rest_end_minutes=None)
            context['environment'].update(map_proximity_m={f:None for f in FEATURES},observed_signals={},provenance='authored stress scene; no real KINTEX observation')
            path=add_fact(context,atoms[atom_id],value)
            if i==3:
                context['state']['recent_events'].append(dict(kind='unrelated_bird_sound_observation',value=None,elapsed_minutes=60,provenance='synthetic irrelevant observation'))
            command=unknown if value is None else yes if value else no
            reason='개인 반응 또는 필요한 현재 관측이 확인되지 않아 판단 유보.' if command=='defer' else '보호자 원문에 기술된 개인 반응과 현재 관측에 따른 행동.'
            expected=dict(next_command_id=command,source_ids=['N1'],reason=reason);validate(expected,context)
            rows.append(dict(id=cid,group_id='stress-'+family,lineage_id='stress-'+family,split='stress_holdout',context=context,
                authoring_oracle=dict(atom_id=atom_id,value=value,fact_path=path,irrelevant_unknown_added=i==3),expected_output=expected,
                quality=dict(clinical_observations=0,independent_human_review=False,source='AI-authored natural-language stress narrative, not a real caregiver')))
    p=out/'evaluation.jsonl';p.write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows))
    source_texts={r['context']['person']['evidence_notes'][0]['text'] for r in rows}
    for split in ('train','development','evaluation'):
        other=list(map(json.loads,(D/'personal_contrasts_v4'/(split+'.jsonl')).read_text().splitlines()))
        assert not source_texts & {n['text'] for r in other for n in r['context']['person']['evidence_notes']}
    manifest=dict(rows=80,source_narratives=20,clinical_patients=0,new_model_calls=0,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
        status='authored_heldout_draft_not_executed',checks=['command/source validity','exact source disjoint from training/development/evaluation'],
        limitations=['Four scenes per narrative are not independent persons.','Authored by Codex, not independently reviewed caregiver speech.','Prepared K interpretation absent; separate actual-frontend test required.'])
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');print(json.dumps(manifest,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
