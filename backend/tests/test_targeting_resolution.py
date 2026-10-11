"""Offline checks: production recipient parity without network/storage writes."""
from types import SimpleNamespace
import json

import h3
import numpy as np
import pytest

from app.config import settings
from app.phase3 import alerts
from experiments.personalized_alert_replay import analyze_targeting_resolution as analysis


def fixture_surface():
    center = h3.latlng_to_cell(37.55, 126.94, 9)
    cells = sorted(h3.grid_disk(center, 4))
    weights = list(range(len(cells), 0, -1))
    total = sum(weights)
    return {c: w / total for c, w in zip(cells, weights)}


@pytest.mark.parametrize("resolution", [7, 8])
@pytest.mark.parametrize("level", ["high", "normal", "low"])
def test_matches_production_recipients(monkeypatch, resolution, level):
    poa = fixture_surface()
    lat, lng = h3.cell_to_latlng(next(iter(poa)))
    truth = {"lat": lat, "lng": lng}
    threshold = settings.push_prob_threshold[level]
    result = analysis.evaluate_surface(poa, truth, h3.latlng_to_cell(lat, lng, 9),
                                       resolution, .8, 500, threshold,
                                       targeting_policy="selected_coverage_geographic_cover_v1")
    devices = [SimpleNamespace(token=p, cell_res7=p, engagement=SimpleNamespace(value=level))
               for p in alerts.target_parent_cells(list(poa), res=resolution)]
    captured = []
    monkeypatch.setattr(settings, "push_target_res", resolution)
    monkeypatch.setattr(alerts.devices, "devices_in_cells", lambda cells: [d for d in devices if d.cell_res7 in cells])
    monkeypatch.setattr(alerts.devices, "record_sent", lambda tokens: None)

    def fake_send(tokens, **kwargs):
        captured.extend(tokens)
        return {"sent": len(tokens), "failed": 0, "stub": True}

    monkeypatch.setattr(alerts.push, "send", fake_send)
    sent = alerts.send_alerts("test", alerts.select_alert_cells(poa, coverage=.8, max_cells=500), "", poa=poa)
    assert sorted(captured) == result["stages"]["eligible"]["cells"]
    assert sent["in_area"] == result["stages"]["parents"]["count"]


def test_parent_collapse_boundary_and_empty():
    parent = h3.latlng_to_cell(37.55, 126.94, 8)
    a, b = sorted(h3.cell_to_children(parent, 9))[:2]
    lat, lng = h3.cell_to_latlng(a)
    truth = {"lat": lat, "lng": lng}
    base = analysis.evaluate_surface({a: .5, b: .5}, truth, a, 8, .8, 500, .9)
    narrow = analysis.evaluate_surface({a: 1.0}, truth, a, 8, .8, 500, .9)
    assert base["stages"]["selected"]["count"] == 2
    assert narrow["stages"]["selected"]["count"] == 1
    assert base["stages"]["eligible"]["cells"] == narrow["stages"]["eligible"]["cells"] == [parent]
    above = analysis.evaluate_surface({a: 1.0}, truth, a, 8, .8, 500, .900001)
    assert above["stages"]["eligible"]["count"] == 0
    empty = analysis.evaluate_surface({}, truth, a, 8, .8, 500, .45)
    assert empty["stages"]["eligible"]["count"] == 0
    assert not empty["truth_included"]


def test_cap_and_nonfinite_match_production():
    poa = fixture_surface()
    lat, lng = h3.cell_to_latlng(next(iter(poa)))
    result = analysis.evaluate_surface(poa, {"lat": lat, "lng": lng}, next(iter(poa)), 8, .8, 2, .45)
    assert result["stages"]["selected"]["count"] == 2
    # Raw invalid input is rejected by load_pairs; production helper independently filters nonfinite scores.
    cells = alerts.select_alert_cells({"a": .5, "nan": float("nan"), "b": .3, "inf": float("inf")}, .8, 500)
    assert cells == ["a", "b"]


def test_cluster_pairing_ratio_and_zero_denominator():
    def record(profile, minute, area, hit):
        return {"profile_id": profile, "scenario_id": profile, "minute": minute,
                "truth_included": hit,
                "stages": {stage: {"area_km2": area} for stage in analysis.STAGES}}
    b = [record("p1", 0, 10, True), record("p1", 1, 10, True), record("p2", 0, 20, False)]
    c = [record("p1", 0, 5, True), record("p1", 1, 5, True), record("p2", 0, 10, False)]
    result = analysis.comparison(b, list(reversed(c)), ["p1", "p2"], np.array([[0, 0], [1, 1], [0, 1]]))
    assert result["area_reduction_pct"]["eligible"]["estimate"] == 50
    assert result["area_reduction_pct"]["eligible"]["ci95"] == [50, 50]
    assert result["truth_inclusion_difference_pp"]["estimate"] == 0
    assert analysis.reduce_percent(0, 1) is None
    with pytest.raises(ValueError, match="paired"):
        analysis.comparison(b, c[:-1], ["p1", "p2"], np.array([[0, 1]]))


def test_truth_uses_coordinate_not_parent_proxy():
    # H3 logical parent and direct coordinate assignment differ near some boundaries.
    found = None
    for lat in np.linspace(37.50, 37.60, 40):
        for lng in np.linspace(126.90, 127.00, 40):
            cell = h3.latlng_to_cell(float(lat), float(lng), 9)
            if h3.cell_to_parent(cell, 8) != h3.latlng_to_cell(float(lat), float(lng), 8):
                found = (float(lat), float(lng), cell)
                break
        if found:
            break
    assert found is not None
    lat, lng, cell = found
    result = analysis.evaluate_surface({cell: 1.0}, {"lat": lat, "lng": lng}, cell, 8, .8, 500, .45)
    assert result["truth_parent_proxy_differs"]
    assert not result["truth_included"]
    assert result["truth_included_parent_proxy"]


def test_saved_input_validation_rejects_misalignment(monkeypatch):
    source = analysis.HERE / "results/persona_abc_v2_r1.jsonl"
    pairs, audit = analysis.load_pairs(source)
    assert len(pairs) == 108
    assert len(audit["profiles"]) == 9
    row = json.loads(source.read_text(encoding="utf-8").splitlines()[0])
    row["arms"]["C"]["temporal"]["snapshots"][0]["minute_after_report"] = 999
    # Supply the malformed document in memory; no OS temp-directory dependency.
    monkeypatch.setattr(analysis.Path, "read_text", lambda self, **kwargs: json.dumps(row))
    with pytest.raises(ValueError, match="Unpaired minutes"):
        analysis.load_pairs(source)


def test_saved_res7_matches_legacy_proxy():
    # Different truth indexing is intentional, not a silent regression in thresholds.
    from experiments.personalized_alert_replay.analyze_alert_targeting import evaluate
    source = analysis.HERE / "results/persona_abc_v2_r1.jsonl"
    rows = [json.loads(l) for l in source.read_text(encoding="utf-8").splitlines()]
    pairs, _ = analysis.load_pairs(source)
    for arm in "BC":
        for level, threshold in settings.push_prob_threshold.items():
            new = [analysis.evaluate_surface(p["snapshots"][arm]["surface_cells"], p["truth"],
                                             p["snapshots"][arm]["truth_cell"], 7,
                                             settings.alert_coverage, settings.max_alert_cells, threshold)
                   for p in pairs]
            old = evaluate(rows, arm, level)
            assert sum(r["truth_included_parent_proxy"] for r in new) == old["truth_device_targeted"]
            assert sum(r["stages"]["eligible"]["count"] for r in new) / len(new) == old["mean_target_res7_regions"]
