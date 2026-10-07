"""Run the fixed D6/D7 8-input subset on KINTEX with verified cached references.

All outputs, invalid ones included, stay in the denominator. This wrapper
changes only input selection; walker, seed, synthetic environment, population
and reference tolerances are the same as the frozen 128-input walk check.
"""
import json
from pathlib import Path
import sys

from app.llm.mind_policy import Policy
from experiments.mind_contract_ab_20261007 import run_repair8, run_v2, walk_dev8_reuse as reuse


def check_inputs(inputs, refs, frozen):
    folder = frozen / run_v2.DEV128.relative_to(run_v2.BACKEND)
    old, _, oldrefs, _ = run_v2._split(folder, 'dev128')
    old = {r['id']: r for r in old}
    mapping = {}
    for row in inputs:
        key = row['id']
        if row['personal'] != old[key]['personal']:
            raise ValueError('personal input differs: ' + key)
        if reuse.e.rule_set(Policy.model_validate(refs[key])) != reuse.e.rule_set(Policy.model_validate(oldrefs[key])):
            raise ValueError('reference policy differs: ' + key)
        mapping[key] = key
    return mapping


def main():
    # Reuse refuses any scored result not exactly this dataset × two repeats.
    original_dataset = run_v2.dataset
    run_v2.dataset = lambda stage: run_repair8.repair_dataset() if stage == 'd3_dev8' else original_dataset(stage)
    reuse.check_inputs = check_inputs
    reuse.main()
    out = Path(sys.argv[sys.argv.index('--output') + 1])
    result = json.loads(out.read_text())
    result['selected_input_ids'] = list(run_repair8.IDS)
    result['runner_source_sha256'] = {str(p): reuse.sha(p) for p in
        (Path(__file__), Path(reuse.__file__), Path(run_repair8.__file__))}
    run_v2.write(out, result)


if __name__ == '__main__':
    main()
