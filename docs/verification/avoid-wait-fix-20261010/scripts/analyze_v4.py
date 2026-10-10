"""Pre-merge check aggregation (2026-10-10, third follow-up). No model calls.

Development re-analysis of previously inspected synthetic E01-E40; not an
independent evaluation. Separates:
- the same 31 evaluation people (evaluation split minus E20) before/after,
- E20 map recovery (the deployed map was not published there),
- the diagnostic interpretation corrections (E07, E23, E27, E31, E35), never
  mixed into the product comparison.

Labels: deployed = 43a3b2c (PR #274 head, deployed); prev_fix = 6a693d7
(unobserved family treated as absent); final = c2f111a (unobserved family stays
uncertain, interpretation checks disclosed); interpfix = final code with the
documented manual corrections.

Usage: python analyze_v4.py <X>
"""
import json, sys
from pathlib import Path
import numpy as np

X = Path(sys.argv[1]); A = X / 'analysis'; A.mkdir(exist_ok=True)
SEEDS = (104729, 130363); BUDGETS = [.25, .5, 1, 2, 4, 8, 12, 20, 30]
FIX = ['E07', 'E23', 'E27', 'E31', 'E35']
DROP5 = ['E15', 'E19', 'E34', 'E35', 'E39']


def rows(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def mean(v):
    v = [x for x in v if x is not None]
    return float(np.mean(v)) if v else None


def D(path):
    return [r for r in rows(X / path / 'metrics_rows_v2.jsonl') if r['arm'] == 'D_full_prepared' and not r.get('pending')]


def boot(v, seed=20261010, n=10000):
    v = np.asarray([x for x in v if x is not None], float)
    d = v[np.random.default_rng(seed).integers(0, len(v), (n, len(v)))].mean(axis=1)
    return dict(delta=float(v.mean()), ci95=[float(np.quantile(d, .025)), float(np.quantile(d, .975))], people=int(len(v)))


def summary(z):
    c = [r for r in z if r['complete']]
    return dict(people=len({r['person_id'] for r in z}), checks=len(z), incomplete_checks=len(z) - len(c),
                map_hit=mean([r['map_hit'] for r in z]), alert_hit=mean([r['alert_hit'] for r in z]),
                map_area_km2=mean([r['map_area'] for r in c]), alert_area_km2=mean([r['alert_area'] for r in c]),
                equal_area_map_hit={str(b): mean([r['budget_hits']['map'][i] if r['complete'] else 0 for r in z]) for i, b in enumerate(BUDGETS)})


def per_person(z, key):
    return {pid: mean([r[key] for r in z if r['person_id'] == pid]) for pid in sorted({r['person_id'] for r in z})}


def paired(za, zb, key):
    a, b = per_person(za, key), per_person(zb, key)
    return boot([a[p] - b[p] for p in a])


dep, prev, fin = D('out_deployed'), D('out_final'), D('out_final4')
fix = D('out_final4_interpfix')
R = {'label': 'development re-analysis of previously inspected synthetic E01-E40 (not an independent evaluation)',
     'code': {'deployed': '43a3b2c (PR #274 head, deployed)', 'prev_fix': '6a693d7 (unobserved family = absent)',
              'final': 'c2f111a (unobserved family = uncertain; interpretation checks disclosed)'},
     'judges': 'all classifications and code reviews in this work were AI (Claude subagents); no human review',
     'new_model_calls': 0}

# 1. the same 31 evaluation people
ev31 = lambda z: [r for r in z if r['split'] == 'evaluation' and r['person_id'] != 'E20']
R['same_31_evaluation_people'] = dict(
    deployed=summary(ev31(dep)), prev_fix=summary(ev31(prev)), final=summary(ev31(fin)),
    final_minus_deployed={k: paired(ev31(fin), ev31(dep), k) for k in ('map_hit', 'alert_hit', 'map_area', 'alert_area')},
    final_minus_deployed_equal_area={str(b): boot([a - c for a, c in zip(
        [mean([r['budget_hits']['map'][i] for r in ev31(fin) if r['person_id'] == p]) for p in sorted({r['person_id'] for r in ev31(fin)})],
        [mean([r['budget_hits']['map'][i] for r in ev31(dep) if r['person_id'] == p]) for p in sorted({r['person_id'] for r in ev31(dep)})])])
        for i, b in enumerate(BUDGETS)},
    prev_fix_minus_deployed={k: paired(ev31(prev), ev31(dep), k) for k in ('map_hit', 'alert_hit', 'map_area', 'alert_area')})
dev8 = lambda z: [r for r in z if r['split'] == 'development']
R['development_8_people'] = dict(deployed=summary(dev8(dep)), final=summary(dev8(fin)))

# 2. E20 map recovery
e20 = lambda z: [r for r in z if r['person_id'] == 'E20']
R['E20_map_recovery'] = {k: dict(summary(e20(z)), map_hits=sum(r['map_hit'] for r in e20(z)), alert_hits=sum(r['alert_hit'] for r in e20(z)))
                         for k, z in (('deployed', dep), ('prev_fix', prev), ('final', fin))}

# 3. per person (all 40) deployed vs final, with prev_fix for reference
def walk(label, pid, seed):
    return json.loads((X / label / 'people' / pid / f'walk_D_full_prepared_{seed}.json').read_text())


def behaviour(label, pid):
    out = dict(wait=[], rest=[], rules={})
    for seed in SEEDS:
        b = (walk(label, pid, seed)['snapshots'][-1].get('behaviour') or {}).get('agent') or {}
        out['wait'].append(b.get('mean_wait_minutes')); out['rest'].append(b.get('mean_rest_minutes'))
        for k, v in (b.get('mean_rule_minutes') or {}).items():
            out['rules'].setdefault(k, []).append(v)
    return dict(wait=mean(out['wait']), rest=mean(out['rest']), rules={k: float(np.mean(v)) for k, v in sorted(out['rules'].items())})


table = []
for pid in sorted(p.name for p in (X / 'out_final4/people').iterdir() if p.is_dir()):
    item = dict(person_id=pid)
    for label, z in (('deployed', dep), ('prev_fix', prev), ('final', fin)):
        zz = [r for r in z if r['person_id'] == pid]
        item[label] = dict(map_hits=sum(r['map_hit'] for r in zz), alert_hits=sum(r['alert_hit'] for r in zz), checks=len(zz),
                           complete=sum(r['complete'] for r in zz), map_area=mean([r['map_area'] for r in zz if r['complete']]))
        item['split'] = zz[0]['split']
    for label, root in (('deployed', 'out_deployed'), ('final', 'out_final4')):
        item[label].update(behaviour(root, pid))
    sd = [s for seed in SEEDS for s in walk('out_deployed', pid, seed)['snapshots']]
    sf = [s for seed in SEEDS for s in walk('out_final4', pid, seed)['snapshots']]
    item['maps_identical_to_deployed'] = sum(a['cells'] == b['cells'] for a, b in zip(sd, sf)); item['maps'] = len(sf)
    item['interpretation_checks'] = walk('out_final4', pid, SEEDS[0])['snapshots'][-1]['quality'].get('interpretation_checks')
    item['rule_execution_drops'] = [dict(rule_id=k, deployed_min=v, final_min=item['final']['rules'].get(k, 0.))
                                    for k, v in item['deployed']['rules'].items() if v >= 1 and item['final']['rules'].get(k, 0.) < .1 * v]
    table.append(item)
(A / 'person_table_v4.json').write_text(json.dumps(table, ensure_ascii=False, indent=1) + '\n')
R['people_maps_identical'] = [t['person_id'] for t in table if t['maps_identical_to_deployed'] == t['maps']]
R['people_map_hits_decreased'] = [(t['person_id'], t['deployed']['map_hits'], t['final']['map_hits']) for t in table
                                  if t['final']['map_hits'] < t['deployed']['map_hits']]
R['people_map_hits_increased'] = [(t['person_id'], t['deployed']['map_hits'], t['final']['map_hits']) for t in table
                                  if t['final']['map_hits'] > t['deployed']['map_hits']]
R['wait_rest_drops_over_1min'] = [(t['person_id'], k, round(t['deployed'][k], 2), round(t['final'][k], 2)) for t in table
                                  for k in ('wait', 'rest') if t['deployed'][k] is not None and t['final'][k] is not None and t['final'][k] < t['deployed'][k] - 1]
R['rule_execution_drops'] = {t['person_id']: t['rule_execution_drops'] for t in table if t['rule_execution_drops']}
R['containment_drop_5_people'] = {t['person_id']: {k: t[k]['map_hits'] for k in ('deployed', 'prev_fix', 'final')} for t in table if t['person_id'] in DROP5}
R['interpretation_checks_flagged'] = {t['person_id']: [(c['check'], c['wait_rule_id'], c['movement_rule_id']) for c in t['interpretation_checks'] or []]
                                     for t in table if t['interpretation_checks']}

# 4. diagnostic interpretation corrections (kept apart from the product comparison)
diag = {}
for pid in FIX:
    zf = [r for r in fin if r['person_id'] == pid]; zx = [r for r in fix if r['person_id'] == pid]; zd = [r for r in dep if r['person_id'] == pid]
    diag[pid] = {label: dict(map_hits=sum(r['map_hit'] for r in z), alert_hits=sum(r['alert_hit'] for r in z), checks=len(z),
                             map_area=mean([r['map_area'] for r in z if r['complete']]), alert_area=mean([r['alert_area'] for r in z if r['complete']]))
                 for label, z in (('deployed', zd), ('final_stored_policy', zf), ('final_with_manual_correction', zx))}
    diag[pid]['behaviour'] = {label: behaviour(root, pid) for label, root in (('deployed', 'out_deployed'), ('final_stored_policy', 'out_final4'),
                                                                              ('final_with_manual_correction', 'out_final4_interpfix'))}
R['diagnostic_interpretation_corrections'] = diag
(A / 'summary_v4.json').write_text(json.dumps(R, ensure_ascii=False, indent=1) + '\n')
print(json.dumps({k: R[k] for k in ('same_31_evaluation_people', 'E20_map_recovery', 'people_map_hits_decreased', 'people_map_hits_increased',
                                     'wait_rest_drops_over_1min', 'rule_execution_drops', 'containment_drop_5_people')}, ensure_ascii=False, indent=1))
