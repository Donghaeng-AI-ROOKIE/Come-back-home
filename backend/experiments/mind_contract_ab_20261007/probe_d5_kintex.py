"""Offline wiring probe with authored D5 outputs, never a model-quality test.

Uses the existing hash-checked KINTEX roads. Facilities and observations are
synthetic. Do not interpret these two fixtures as dementia behavior validation.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket

from app.geo.roadnet import verified_network
from app.llm.mind_policy import Policy
from experiments.mind_contract_ab_20261007 import contract_d5 as d5
from experiments.mind_contract_ab_20261007 import engine_outputs_v2 as engine
from tests.test_mind_contract_ab import cl
from tests.test_mind_contract_d5 import P08, P08_OUT, behavior, one_note, output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--map', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('refusing to overwrite ' + str(args.output))
    if hashlib.sha256(args.map.read_bytes()).hexdigest() != engine.MAP_SHA256:
        raise SystemExit('KINTEX cache hash differs')
    socket.socket.connect = engine._offline
    net = verified_network(args.map)
    site = next(s for s in json.loads((engine.scoring.ROOT / 'sites.json').read_text())['sites']
                if s['site_id'] == engine.SITE)

    waiting_person = one_note('가족이 곁에 없으면 그 자리에서 기다리세요. 가족이 돌아오면 다시 걸으세요.')
    waiting_output = output(waiting_person, [behavior(
        ['N0.s1', 'N0.s2'], 'wait', [cl(false=['family_present'])], [cl(['family_present'])])])
    waiting_scene = deepcopy(engine.SCENARIOS['S1_morning_lost'])
    waiting_scene.update(horizon=90, strategy={'random_walk': 1.0}, environment=[],
                         behavior=[('family_present', False, 0, 30), ('family_present', True, 30, 90)])
    fixtures = [
        ('family_absence_then_return', waiting_person, waiting_output, waiting_scene),
        ('continued_walk_under_fatigue_rest_in_pain', P08, P08_OUT,
         engine.SCENARIOS['S1_morning_lost']),
    ]
    rows = []
    for name, person, authored, scenario in fixtures:
        policy = d5.compile_d5(authored, person)
        network = engine.environment_network(net, site, person)
        for seed in (17, 18):
            got = engine.walk(network, site, person, policy, scenario, walkers=50, seed=seed)
            blank = engine.walk(network, site, person, Policy(rules=[], unrepresented=[]),
                                scenario, walkers=50, seed=seed)
            rows.append({'fixture': name, 'seed': seed, 'authored_d5_output': authored,
                         'compiled_policy': policy.model_dump(), 'with_personal_rules': got,
                         'without_personal_rules': blank,
                         'same_walk_metrics': engine.components(got) == engine.components(blank)})
    waiting = [r for r in rows if r['fixture'] == 'family_absence_then_return']
    checks = {
        'family_absence_waits_30_minutes': all(abs(r['with_personal_rules']['mean_wait'] - 30) < 0.01 for r in waiting),
        'family_return_allows_movement': all(r['with_personal_rules']['mean_path_km'] > 0 for r in waiting),
        'blank_policy_has_no_personal_wait': all(r['without_personal_rules']['mean_wait'] == 0 for r in waiting),
        'all_probability_mass_preserved': all(r[k]['mass'] == 1 for r in rows
                                             for k in ('with_personal_rules', 'without_personal_rules')),
        'no_unresolved_walks': all(not r[k]['unresolved'] for r in rows
                                 for k in ('with_personal_rules', 'without_personal_rules')),
    }
    report = {'scope': 'authored D5 outputs -> compiled rules -> cached KINTEX walking engine',
              'new_model_calls': 0, 'network_calls': 0, 'model_quality_measured': False,
              'clinical_validity_measured': False, 'map_sha256': engine.MAP_SHA256,
              'environment': engine.SYNTHETIC_LABEL, 'observations': 'synthetic controlled inputs',
              'walkers_per_run': 50, 'walk_runs': 8, 'checks': checks, 'rows': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'checks': checks, 'results': [
        {'fixture': r['fixture'], 'seed': r['seed'], 'personal': r['with_personal_rules'],
         'blank': r['without_personal_rules']} for r in rows]}, ensure_ascii=False))
    if not all(checks.values()):
        raise SystemExit('wiring probe has a failed check; inspect report without repairing outputs')


if __name__ == '__main__':
    main()
