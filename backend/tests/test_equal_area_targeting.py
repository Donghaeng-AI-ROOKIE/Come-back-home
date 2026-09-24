import h3
import pytest
from experiments.personalized_alert_replay import analyze_equal_area_targeting as study


def test_mass_ranking_uses_sum_not_peak():
    p1 = h3.latlng_to_cell(37.55, 126.94, 8)
    p2 = next(c for c in h3.grid_disk(p1, 1) if c != p1)
    a, b = sorted(h3.cell_to_children(p1, 9))[:2]
    c = sorted(h3.cell_to_children(p2, 9))[0]
    ranked = study.rank_parents({a: .3, b: .3, c: .4})
    assert ranked[0][0] == p1
    assert ranked[0][1] == pytest.approx(.6)


def test_prefix_stops_without_skipping(monkeypatch):
    monkeypatch.setattr(study, 'area', lambda c: {'a': .6, 'b': .7, 'c': .2}[c])
    ranked = [('a', .5), ('b', .3), ('c', .2)]
    assert study.select_prefix(ranked, 1.) == (['a'], .6)
    assert study.select_prefix(ranked, .5) == ([], 0.)
    assert study.select_prefix(ranked, 1.5)[0] == ['a', 'b', 'c']


def test_nested_selection_and_cap():
    p = h3.latlng_to_cell(37.55, 126.94, 9)
    cells = sorted(h3.grid_disk(p, 8))
    ranked = study.rank_parents({c: 1/len(cells) for c in cells})
    previous = set()
    for budget in study.BUDGETS:
        selected, used = study.select_prefix(ranked, budget)
        assert used <= budget + 1e-12
        assert previous <= set(selected)
        previous = set(selected)
