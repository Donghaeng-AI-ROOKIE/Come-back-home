import h3
from experiments.personalized_alert_replay import compare_engagement_threshold as study
from experiments.personalized_alert_replay.analyze_targeting_resolution import evaluate_surface
from app.config import settings


def test_threshold_ablation_keeps_candidate_set_and_matches_production():
    center=h3.latlng_to_cell(37.55,126.94,9)
    cells=sorted(h3.grid_disk(center,8))
    weights=list(range(1,len(cells)+1)); total=sum(weights)
    poa={c:w/total for c,w in zip(cells,weights)}
    lat,lng=h3.cell_to_latlng(center)
    for res in (7,8):
        selected,choices=study.select_conditions(poa,res)
        assert set(choices['off'])=={h3.cell_to_parent(c,res) for c in selected}
        for level,threshold in settings.push_prob_threshold.items():
            expected=evaluate_surface(poa,{'lat':lat,'lng':lng},center,res,settings.alert_coverage,settings.max_alert_cells,threshold)
            assert choices[f'on/{level}']==expected['stages']['eligible']['cells']
            assert set(choices[f'on/{level}'])<=set(choices['off'])
            assert choices[f'matched/{level}']==choices[f'on/{level}']


def test_empty_and_single_cell():
    assert all(not v for v in study.select_conditions({},8)[1].values())
    cell=h3.latlng_to_cell(37.55,126.94,9)
    parent=h3.cell_to_parent(cell,8)
    assert all(v==[parent] for v in study.select_conditions({cell:1.},8)[1].values())
