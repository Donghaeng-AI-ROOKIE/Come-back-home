"""Replay the one D15 coverage rejection without changing its failing score."""
import argparse
from pathlib import Path
import socket

from app.llm.mind_policy import Policy
from experiments.mind_contract_ab_20261007 import (
    run_v2 as r, run_compact15, completion, diagnostic_coverage,
    condition_probe, engine_outputs_v2 as e, walk_dev8_reuse as reuse,
)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir', type=Path, required=True)
    p.add_argument('--map', type=Path, required=True)
    p.add_argument('--reference-walks', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists(): raise SystemExit('preserve completed diagnostic')
    inputs, _, refs, _ = run_compact15.selected_dataset()
    scored = r.read(a.run_dir / 'scored.json')
    cached = r.read(a.reference_walks)
    before = r.digest(a.run_dir / 'scored.json')
    if r.digest(a.map) != e.MAP_SHA256: raise ValueError('wrong KINTEX cache')
    reuse.check_sources(r.BACKEND, Path('../../cbh-mind-contract-ab-20261007/backend'))
    socket.socket.connect = e._offline
    site = next(x for x in r.read(e.scoring.ROOT / 'sites.json')['sites'] if x['site_id'] == e.SITE)
    net = e.verified_network(a.map)
    rows = []
    for row in scored['rows']:
        if row['policy'] is not None: continue
        key = row['input_id']
        personal = next(x['personal'] for x in inputs if x['id'] == key)
        source = a.run_dir / key / str(row['rep']) / 'fix/response.public.json'
        status, value = completion.classify(r.read(source))
        if status != 'complete_json': continue
        policy, audit = diagnostic_coverage.compile_for_diagnosis(value, personal)
        reference = Policy.model_validate(refs[key])
        env = e.environment_network(net, site, personal)
        actual = {name: e.walk(env, site, personal, policy, scenario, walkers=150, seed=17)
                  for name, scenario in e.SCENARIOS.items()}
        expected = {name: e.walk(env, site, personal, reference, scenario, walkers=150, seed=17)
                    for name, scenario in e.SCENARIOS.items()}
        assert expected == cached['reference_walks'][key], 'frozen reference replay differs'
        judged = e.judge(actual, expected, cached['tolerance']['per_input_by_scenario'][key])
        rows.append({'input_id': key, 'rep': row['rep'], 'source_sha256': r.digest(source),
                     'original_failure_retained': True, 'coverage_audit': audit,
                     'policy_for_diagnosis_only': policy.model_dump(),
                     'condition_probe': condition_probe.compare(policy, reference),
                     'kintex_diagnostic': judged, 'k_walks': actual})
    assert before == r.digest(a.run_dir / 'scored.json')
    result = {'scope': 'diagnostic only; coverage-incomplete outputs do not become successful outputs',
              'original_score_sha256': before, 'original_scores_unchanged': True,
              'new_external_calls': 0, 'release_qualified': False,
              'harness_sha256': r.digest(Path(__file__)),
              'compiler_sha256': r.digest(Path(diagnostic_coverage.__file__)), 'rows': rows}
    r.write(a.output, result)
    print({'coverage_incomplete_rows': len(rows),
           'diagnostic_walk_preserved': sum(x['kintex_diagnostic']['preserved'] for x in rows),
           'original_scores_unchanged': True})


if __name__ == '__main__': main()
