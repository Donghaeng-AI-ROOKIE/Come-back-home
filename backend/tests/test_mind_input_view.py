"""Offline request ablation integrity, not semantic model evaluation."""
import copy,json
import pytest
from experiments.mind_policy_candidates import situated_actions,source_scene


def inputs():
    personal={'notes':[{'id':'N0','text':'질문: 소리가 크면 피하나요?\n답변: 아니요. 장소 X에서만 멀어졌어요.'},
                       {'id':'N1','text':'앞 답은 제 행동이에요. 어머니 행동은 모르겠어요.'}],
              'places':[{'label':'장소 X','evidence':'mention_only'}],
              'prepared_initial':{'core':{'marker':'summary_does_not_replace_original'}}}
    scene={key:None for key in source_scene.SCENE_FIELDS}
    scene.update(map_distance_m={'market':20,'park':None},noisy=False,crowded=None,continuous_walk_minutes=3,elapsed_minutes=70)
    return personal,scene


def test_source_view_retains_all_sources_and_false_unknown_without_mutation():
    personal,scene=inputs();before=copy.deepcopy((personal,scene))
    request=source_scene.request(personal,scene,'offline')
    data=json.loads(request['messages'][1]['content'])
    assert data['원문']==personal['notes']
    assert data['등록_장소']==personal['places']
    assert 'summary_does_not_replace_original' not in str(data)
    values={r['항목']:r['값'] for r in data['현재_사실']}
    assert values[source_scene.SCENE_FIELDS['noisy']] is False
    assert values[source_scene.SCENE_FIELDS['crowded']] is None
    assert values[source_scene.SCENE_FIELDS['continuous_walk_minutes']]==3
    assert values[source_scene.SCENE_FIELDS['elapsed_minutes']]==70
    assert (personal,scene)==before


def test_ablation_changes_only_user_view():
    personal,scene=inputs()
    baseline=situated_actions.request(personal,scene,'offline',thinking=True)
    ablation=source_scene.request(personal,scene,'offline')
    assert {k:v for k,v in baseline.items() if k!='messages'}=={k:v for k,v in ablation.items() if k!='messages'}
    assert baseline['messages'][0]==ablation['messages'][0]
    assert json.loads(baseline['messages'][1]['content'])['available_commands']==json.loads(ablation['messages'][1]['content'])['선택_명령']


def test_person_words_do_not_select_commands_in_python():
    personal,scene=inputs()
    before=json.loads(source_scene.request(personal,scene,'offline')['messages'][1]['content'])['선택_명령']
    personal['notes']=[{'id':'N0','text':'똑같은 상황에서 정반대의 행동을 하는 사람'}]
    after=json.loads(source_scene.request(personal,scene,'offline')['messages'][1]['content'])['선택_명령']
    assert before==after


def test_large_source_is_rejected_instead_of_truncated():
    personal,scene=inputs();personal['notes'][0]['text']='합성 원문'*20000
    with pytest.raises(ValueError,match='input byte cap'):
        source_scene.request(personal,scene,'offline')
