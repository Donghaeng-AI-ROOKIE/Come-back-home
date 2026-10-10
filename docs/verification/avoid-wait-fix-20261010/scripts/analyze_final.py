"""Final aggregation: deployed (43a3b2c) vs fixed (6a693d7). Development re-analysis of
previously inspected synthetic people E01-E40; not a new independent evaluation.

Inputs: out_deployed (D), out_final (B/C from af68b36 verified identical, D from
6a693d7), metrics/service rows, behaviour totals, controlled checks.
Writes analysis/final_summary.json and analysis/person_table.json.
"""
import json, sys
from pathlib import Path
import numpy as np

X = Path(sys.argv[1]); E = Path(sys.argv[2]); A = X / 'analysis'; A.mkdir(exist_ok=True)
SEEDS = (104729, 130363); BUDGETS = [.25, .5, 1, 2, 4, 8, 12, 20, 30]


def rows(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def mean(v):
    v = [x for x in v if x is not None]
    return float(np.mean(v)) if v else None


def boot(per_person, seed=20261010, n=10000):
    v = np.asarray([x for x in per_person if x is not None], float)
    if not len(v):
        return None
    d = v[np.random.default_rng(seed).integers(0, len(v), (n, len(v)))].mean(axis=1)
    return dict(delta=float(v.mean()), ci95=[float(np.quantile(d, .025)), float(np.quantile(d, .975))],
                people=int(len(v)), excluded_incomplete=int(sum(x is None for x in per_person)))


def summary(z):
    c = [r for r in z if r['complete']]
    return dict(people=len({r['person_id'] for r in z}), checks=len(z), incomplete_checks=len(z) - len(c),
                map_hit=mean([r['map_hit'] for r in z]), alert_hit=mean([r['alert_hit'] for r in z]),
                map_area_km2_complete=mean([r['map_area'] for r in c]), alert_area_km2_complete=mean([r['alert_area'] for r in c]),
                equal_area_map_hit={str(b): mean([r['budget_hits']['map'][i] if r['complete'] else 0 for r in z]) for i, b in enumerate(BUDGETS)})


def paired(za, zb, key, area=False):
    out = []
    for pid in sorted({r['person_id'] for r in za}):
        a = [r for r in za if r['person_id'] == pid]; b = [r for r in zb if r['person_id'] == pid]
        out.append(None if area and any(not r['complete'] for r in a + b) else float(np.mean([r[key] for r in a]) - np.mean([r[key] for r in b])))
    return boot(out)


dep = [r for r in rows(X / 'out_deployed/metrics_rows_v2.jsonl') if r['arm'] == 'D_full_prepared' and not r.get('pending')]
fin = [r for r in rows(X / 'out_final/metrics_rows_v2.jsonl') if not r.get('pending')]
R = {'label': 'development re-analysis of previously inspected synthetic E01-E40 (not an independent evaluation)',
     'code': {'deployed': '43a3b2c (PR #274 head, deployed)', 'fixed': '6a693d7 (this branch)',
              'B_C_component': 'af68b36, verified bit-identical to 6a693d7 on 24 sampled snapshots'},
     'new_model_calls': 0}
for split in ('evaluation', 'development'):
    d = [r for r in dep if r['split'] == split]
    f = {arm: [r for r in fin if r['split'] == split and r['arm'] == arm] for arm in ('B_population', 'C_initial_person', 'D_full_prepared')}
    R[split] = dict(
        deployed_D=summary(d), fixed_D=summary(f['D_full_prepared']),
        fixed_minus_deployed=dict(map_hit=paired(f['D_full_prepared'], d, 'map_hit'), alert_hit=paired(f['D_full_prepared'], d, 'alert_hit'),
                                  map_area=paired(f['D_full_prepared'], d, 'map_area', True), alert_area=paired(f['D_full_prepared'], d, 'alert_area', True)),
        component_fixed_engine={arm: summary(z) for arm, z in f.items()},
        component_D_minus_C=dict(map_hit=paired(f['D_full_prepared'], f['C_initial_person'], 'map_hit'),
                                 alert_hit=paired(f['D_full_prepared'], f['C_initial_person'], 'alert_hit'),
                                 map_area=paired(f['D_full_prepared'], f['C_initial_person'], 'map_area', True)),
        component_C_minus_B=dict(map_hit=paired(f['C_initial_person'], f['B_population'], 'map_hit'),
                                 alert_hit=paired(f['C_initial_person'], f['B_population'], 'alert_hit'),
                                 map_area=paired(f['C_initial_person'], f['B_population'], 'map_area', True)))

svc = {}
for label in ('deployed', 'final'):
    z = [r for r in rows(X / f'service_{label}/rows.jsonl') if r['split'] == 'evaluation']
    svc[label] = {arm: dict(people=len({r['person_id'] for r in z if r['arm'] == arm}),
                            incomplete_checks=sum(not r['complete'] for r in z if r['arm'] == arm),
                            alert_hit=mean([r['hit'] for r in z if r['arm'] == arm]),
                            alert_area_km2_complete=mean([r['area_km2'] for r in z if r['arm'] == arm and r['complete']]))
                  for arm in ('alert_district_proxy', 'alert_city_proxy', 'preliminary', 'final')}
R['service_comparison_evaluation'] = svc
prelim = [r for r in rows(E / 'final_analysis_20261010/map_rows.jsonl') if r['arm'] == 'preliminary' and r['person_id'] >= 'E09']
R['preliminary_map_evaluation'] = dict(map_hit=mean([r['map_hit'] for r in prelim]), map_area_km2=mean([r['map_area'] for r in prelim if r['complete']]))

# ---- per person: hits and executed behaviour per rule (agent channel, 6 h, mean of seeds)
people = sorted(p.name for p in (X / 'out_final/people').iterdir() if p.is_dir())
table = []
for pid in people:
    item = {'person_id': pid}
    for label, root, z in (('deployed', X / 'out_deployed', dep), ('fixed', X / 'out_final', [r for r in fin if r['arm'] == 'D_full_prepared'])):
        zz = [r for r in z if r['person_id'] == pid]
        item[f'{label}_map_hit'] = mean([r['map_hit'] for r in zz]); item[f'{label}_alert_hit'] = mean([r['alert_hit'] for r in zz])
        item[f'{label}_complete'] = sum(r['complete'] for r in zz); item['checks'] = len(zz)
        item['split'] = zz[0]['split'] if zz else None; item['family'] = zz[0]['family'] if zz else None
        rules = {}; insufficient = {}; wait = []; rest = []; dist = []; seq = None; src = None; same = 0
        for seed in SEEDS:
            w = json.loads((root / 'people' / pid / f'walk_D_full_prepared_{seed}.json').read_text())
            src = w.get('policy_source'); last = w['snapshots'][-1]
            b = (last.get('behaviour') or {}).get('agent') or {}
            for k, v in (b.get('mean_rule_minutes') or {}).items(): rules.setdefault(k, []).append(v)
            for k, v in (b.get('mean_environment_insufficient_minutes') or {}).items(): insufficient.setdefault(k, []).append(v)
            wait.append(b.get('mean_wait_minutes')); rest.append(b.get('mean_rest_minutes')); dist.append(b.get('mean_distance_m'))
            seq = seq or last['quality'].get('sequence_normalization')
        item[f'{label}_rule_minutes_6h'] = {k: float(np.mean(v)) for k, v in sorted(rules.items())}
        item[f'{label}_env_insufficient_minutes_6h'] = {k: float(np.mean(v)) for k, v in sorted(insufficient.items())}
        item[f'{label}_wait_minutes_6h'] = mean(wait); item[f'{label}_rest_minutes_6h'] = mean(rest); item[f'{label}_distance_m_6h'] = mean(dist)
        if label == 'fixed':
            item['ordered_pairs'] = (seq or {}).get('ordered', []); item['not_ordered'] = (seq or {}).get('not_ordered', [])
            item['policy_source'] = src
    snaps_d = [s for seed in SEEDS for s in json.loads((X / 'out_deployed/people' / pid / f'walk_D_full_prepared_{seed}.json').read_text())['snapshots']]
    snaps_f = [s for seed in SEEDS for s in json.loads((X / 'out_final/people' / pid / f'walk_D_full_prepared_{seed}.json').read_text())['snapshots']]
    item['maps_identical'] = sum(a['cells'] == b['cells'] for a, b in zip(snaps_d, snaps_f)); item['maps'] = len(snaps_f)
    # Trait-loss flags: a rule executed before but (almost) not after, unless explained.
    flags = []
    for rid, before in item['deployed_rule_minutes_6h'].items():
        after = item['fixed_rule_minutes_6h'].get(rid, 0.)
        if before >= 1 and after < .1 * before:
            flags.append({'rule_id': rid, 'deployed_min': before, 'fixed_min': after})
    item['rule_execution_drops'] = flags
    table.append(item)
(A / 'person_table.json').write_text(json.dumps(table, ensure_ascii=False, indent=1) + '\n')
R['people_changed'] = [t['person_id'] for t in table if t['maps_identical'] != t['maps']]
R['people_unchanged'] = [t['person_id'] for t in table if t['maps_identical'] == t['maps']]
R['rule_execution_drops'] = {t['person_id']: t['rule_execution_drops'] for t in table if t['rule_execution_drops']}
R['people_hit_decreased'] = [(t['person_id'], t['deployed_map_hit'], t['fixed_map_hit']) for t in table
                             if t['fixed_map_hit'] is not None and t['deployed_map_hit'] is not None and t['fixed_map_hit'] < t['deployed_map_hit'] - 1e-9]
# E27 interpretation-fix variant (separate; not part of the fixed-code table)
e27 = X / 'out_fixed3_E27fix/people/E27'
if e27.exists():
    R['E27_interpretation_fix_variant'] = {str(seed): [dict(hour=s['hour'], complete=s['complete'],
        identical_to_fixed=s['cells'] == t['cells']) for s, t in zip(json.loads((e27 / f'walk_D_full_prepared_{seed}.json').read_text())['snapshots'],
        json.loads((X / 'out_final/people/E27' / f'walk_D_full_prepared_{seed}.json').read_text())['snapshots'])] for seed in SEEDS}
(A / 'final_summary.json').write_text(json.dumps(R, ensure_ascii=False, indent=1) + '\n')
print(json.dumps({k: R[k] for k in ('people_changed', 'rule_execution_drops', 'people_hit_decreased')}, ensure_ascii=False, indent=1))
