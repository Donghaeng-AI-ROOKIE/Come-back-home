import h3
import numpy as np
import pytest
from experiments.personalized_alert_replay import compare_parent_scoring as study
from experiments.personalized_alert_replay.analyze_equal_area_targeting import rank_parents as previous_sum
from app.phase3.alerts import relative_prob_by_parent


def test_ranking_reversal_sum_parity_and_max_production_order():
    a = h3.latlng_to_cell(37.55, 126.94, 8)
    b = next(c for c in sorted(h3.grid_disk(a, 1)) if c != a)
    x,y = sorted(h3.cell_to_children(a, 9))[:2]
    z = sorted(h3.cell_to_children(b, 9))[0]
    poa = {x:.3, y:.3, z:.4}
    assert study.rank_parents(poa, 'sum') == previous_sum(poa)
    assert study.rank_parents(poa, 'sum')[0][0] == a
    assert study.rank_parents(poa, 'max')[0][0] == b
    production = relative_prob_by_parent(poa, res=8)
    assert [c for c,_ in study.rank_parents(poa,'max')] == sorted(production,key=lambda c:(-production[c],c))
    assert study.rank_parents(poa,'sum') == study.rank_parents(dict(reversed(list(poa.items()))),'sum')


def test_paired_gain_loss_and_order():
    def r(p, hit):
        return {'profile_id':p,'scenario_id':p,'minute':0,'hit':hit,'area_km2':1.,'cells':['x']}
    b=[r('p1',False),r('p2',True)]
    c=[r('p2',False),r('p1',True)]
    effect=study.paired_effect(b,c,['p1','p2'],np.array([[0,0],[1,1],[0,1]]))
    assert effect['gained_n']==effect['lost_n']==1
    assert effect['inclusion_difference_pp']==0
    assert effect['same_selected_set_n']==2
    with pytest.raises(ValueError):
        study.paired_effect(b,c[:1],['p1','p2'],np.array([[0,1]]))
