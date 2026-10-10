"""Frozen scoring for the main final verification: D (full product) vs B (no personal answers).

Run only after every prediction of the split is saved. No model calls.
Definitions are those of EFFICIENCY_KINTEX_v1 (evaluate.py + evaluate_v2.py
direct device res7 cell + final_analysis AUC); see PROTOCOL.md for the frozen
decision rule. Failures stay in: zero coverage, area unresolved (never zero-area
credit), AUC contribution 0.
usage: PYTHONPATH=<main backend> python evaluate_main.py --data DIR --out DIR --split evaluation
"""
from pathlib import Path
import argparse, json, math, os
os.environ.update(PERSIST_STORAGE="false", EXAONE_WARMUP_ENABLED="false", PUSH_ENABLED="false")
from types import SimpleNamespace
import numpy as np
import h3
from pyproj import Geod
from shapely.geometry import Polygon
from app.phase3 import alerts
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from geo_policy import geographic_scores  # noqa: E402

ARMS = ["B_population", "D_full_prepared"]
SEEDS = (104729, 130363); HOURS = (1, 2, 4, 6); FUTURES = ("habitual", "departure", "contradictory")
AUC_LIMITS = (10, 20, 30)
BOOT, BOOT_SEED = 10000, 20261011
GEOD = Geod(ellps="WGS84")


def h3_area(cells):
    return sum(h3.cell_area(c, unit="km^2") for c in cells)


def geo_area(cell):
    poly = Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(cell)])
    return abs(GEOD.geometry_area_perimeter(poly)[0]) / 1e6


def ranked(p):
    return sorted(p.items(), key=lambda x: (-x[1], x[0]))


def map80(p):
    cells = set(); total = 0.
    for c, mass in ranked(p):
        cells.add(c); total += mass
        if total >= .8: break
    return cells


def alert_cells(p):
    # Production res7 normal footprint (same as v1/v2 scoring).
    candidate = alerts.target_parent_cells(alerts.select_alert_cells(p), res=7)
    rel = alerts.relative_prob_by_parent(p, res=7)
    return {c for c in candidate if alerts.eligible_for_alert(
        SimpleNamespace(cell_res7=c, engagement=SimpleNamespace(value="normal")), "poa", rel)}


def ranked_areas(poa):
    if not poa or any(not math.isfinite(v) or v < 0 for v in poa.values()) or abs(sum(poa.values()) - 1) > 1e-6:
        raise ValueError("invalid normalized forecast")
    area, cumulative = 0., {}
    for cell, probability in sorted(geographic_scores(poa).items(), key=lambda kv: (-kv[1], kv[0])):
        if probability <= 0: continue
        area += geo_area(cell); cumulative[cell] = area
    return cumulative


def contribution(first_area, limit):
    return 0. if first_area is None else max(0., 1 - first_area / limit)


def rows(inputs, truth, out, split):
    pos = {(t["person_id"], s["hour"], t["future"]): s["position"] for t in truth for s in t["snapshots"]}
    z = []
    for item in [x for x in inputs if x["split"] == split]:
        pid = item["person_id"]
        failure = out / "people" / pid / "walk_failure.json"
        failed_arms = set(json.loads(failure.read_text()).get("failed_arms", ARMS)) if failure.exists() else set()
        for arm in ARMS:
            for seed in SEEDS:
                f = out / "people" / pid / f"walk_{arm}_{seed}.json"
                snaps = {s["hour"]: s for s in json.loads(f.read_text())["snapshots"]} if f.exists() else {}
                missing = not f.exists() and arm not in failed_arms  # a recorded failure is final, not pending
                for hour in HOURS:
                    s = snaps.get(hour, {}); complete = bool(s.get("complete")); p = s.get("cells", {}) if complete else {}
                    m = map80(p) if complete else set(); a = alert_cells(p) if complete else set()
                    ranks = ranked_areas(p) if complete else {}
                    for future in FUTURES:
                        q = pos[(pid, hour, future)]
                        c9 = h3.latlng_to_cell(q["lat"], q["lng"], 9); c7 = h3.latlng_to_cell(q["lat"], q["lng"], 7)
                        z.append(dict(person_id=pid, family=item["family"], arm=arm, seed=seed, hour=hour, future=future,
                            complete=complete, pending=missing, engine=s.get("engine"),
                            error_type=s.get("error_type") or ("recorded_failure" if not f.exists() else None),
                            map_area=h3_area(m) if complete else None, map_hit=int(c9 in m),
                            alert_area=h3_area(a) if complete else None, alert_hit=int(c7 in a),
                            first_area=ranks.get(c7)))
    return z


def mean(v):
    v = [x for x in v if x is not None]
    return float(np.mean(v)) if v else None


def arm_summary(z):
    out = {}
    for arm in ARMS:
        y = [r for r in z if r["arm"] == arm]
        out[arm] = dict(rows=len(y), complete=sum(r["complete"] for r in y), pending=sum(r["pending"] for r in y),
            map_area=mean([r["map_area"] for r in y]), map_hit=mean([r["map_hit"] for r in y]),
            alert_area=mean([r["alert_area"] for r in y]), alert_hit=mean([r["alert_hit"] for r in y]),
            **{f"auc{L}": mean([100 * contribution(r["first_area"], L) for r in y]) for L in AUC_LIMITS},
            engines=dict(sorted({str(e): sum(1 for r in y if r["engine"] == e) // 3 for e in {r["engine"] for r in y}}.items())))
    return out


def paired(z, people, metric, level):
    """Person-cluster bootstrap of the D-B difference of person means."""
    vec = []
    for pid in people:
        d = [r for r in z if r["person_id"] == pid and r["arm"] == "D_full_prepared"]
        b = [r for r in z if r["person_id"] == pid and r["arm"] == "B_population"]
        if metric.endswith("area") and any(not r["complete"] for r in d + b):
            return dict(delta=None, ci=None, reason="incomplete predictions; no zero-area credit")
        if metric.startswith("auc"):
            L = int(metric[3:]); f = lambda y: mean([100 * contribution(r["first_area"], L) for r in y])
        else:
            f = lambda y: mean([r[metric] for r in y])
        vec.append(f(d) - f(b))
    v = np.array(vec); idx = np.random.default_rng(BOOT_SEED).integers(0, len(people), (BOOT, len(people)))
    tail = (1 - level) / 2
    return dict(delta=float(v.mean()), ci=np.quantile(v[idx].mean(axis=1), [tail, 1 - tail]).tolist(), level=level,
                people_better=int((v > 0).sum()), people_worse=int((v < 0).sum()))


def decide(z, people):
    p1 = paired(z, people, "auc10", .975)
    hit = paired(z, people, "map_hit", .975); area = paired(z, people, "map_area", .975)
    P1 = p1["ci"] is not None and p1["ci"][0] > 0
    P2 = (hit["ci"] is not None and area["ci"] is not None and hit["ci"][0] > 0 and area["ci"][1] < 0)
    verdict = "CONFIRMED" if (P1 or P2) else "NOT_CONFIRMED"
    return dict(verdict=verdict, P1_equal_alert_area_auc10=dict(holds=P1, **p1),
                P2_smaller_map_more_often=dict(holds=P2, map_hit=hit, map_area=area))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--split", default="evaluation"); a = ap.parse_args()
    root, out = Path(a.data), Path(a.out)
    inputs = json.loads((root / "inputs.json").read_text()); truth = json.loads((root / "truth_private.json").read_text())
    z = rows(inputs, truth, out, a.split)
    people = sorted({r["person_id"] for r in z})
    assert not any(r["pending"] for r in z), "score only after every prediction is saved"
    result = dict(split=a.split, people=len(people), arms=arm_summary(z), decision=decide(z, people),
        secondary_95={m: paired(z, people, m, .95) for m in ("alert_hit", "alert_area", "map_hit", "map_area", "auc10", "auc20", "auc30")},
        by_future={f: arm_summary([r for r in z if r["future"] == f]) for f in FUTURES},
        by_hour={str(h): arm_summary([r for r in z if r["hour"] == h]) for h in HOURS},
        by_family={k: arm_summary([r for r in z if r["family"] == k]) for k in ("goal", "rest", "wait", "avoid")},
        notes=dict(all_synthetic=True, independent_n=len(people), boot=BOOT, boot_seed=BOOT_SEED,
            map="res9 cumulative 80% probability; exact synthetic truth res9 cell", alert="production res7 normal footprint; direct device res7 cell",
            auc="AUC@L = mean of 100*max(0,1-r/L), r = area at which the truth res7 cell is first included by geographic score rank; failure = 0"))
    (out / f"rows_{a.split}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in z))
    (out / f"summary_{a.split}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(dict(decision=result["decision"], arms=result["arms"]), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
