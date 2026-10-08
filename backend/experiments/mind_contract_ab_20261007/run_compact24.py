"""Frozen D12 on the other 24 development people; not a release evaluation.

The eight repair roots and eval64 are excluded. Original questions, scenes and
references are unchanged. D4 saved outputs provide a paired offline comparator.
"""
import argparse
from pathlib import Path

from experiments.mind_contract_ab_20261007 import run_v2 as r, run_repair8, resume_concise8 as guarded

STAGE = 'd12_dev24'


def expanded_dataset():
    inputs, scenes, refs, files = r._split(r.DEV128, 'dev128')
    excluded = {key.split('_')[1] for key in run_repair8.IDS}
    selected = [x for x in inputs if x['form'] == 'original' and x['root_id'] not in excluded]
    ids = {x['id'] for x in selected}
    if len(selected) != 24 or len({x['root_id'] for x in selected}) != 24:
        raise ValueError('frozen expansion must contain 24 distinct non-repair people')
    return selected, [x for x in scenes if x['input_id'] in ids], {i: refs[i] for i in ids}, files


def register():
    r.CANDIDATES['d12'] = ('contract_d12', 'compile_d12', 'PLAN_d12.md')
    r.PARTS = (*r.PARTS, 'dev24')
    for f in (__file__, run_repair8.__file__, guarded.__file__, Path(__file__).with_name('PLAN_d12_expansion.md')):
        path = Path(f).resolve()
        if path not in r.COMMON:
            r.COMMON.append(path)
    old_dataset, old_gate = r.dataset, r.gate
    r.dataset = lambda stage: expanded_dataset() if stage == STAGE else old_dataset(stage)

    def gate(stage, summary):
        if stage != STAGE:
            return old_gate(stage, summary)
        result = old_gate('d12_dev128', summary)
        result['advance'] = False
        result['purpose'] = 'expanded development diagnostic; not independent clinical or release evaluation'
        result['additional_required'] = ['condition counterexamples', 'KINTEX walking', 'source meaning review']
        return result
    r.gate = gate
    old_execute, old_score, old_summary = r.execute, r.score, r.summarize
    r.execute = lambda *args: guarded.execute_guarded(old_execute, *args)
    r.score = lambda *args: guarded.score_with_unavailable(old_score, *args)

    def summarize(module, rows):
        summary = old_summary(module, rows)
        summary['trait_accounting'] = {'available': False, 'unmeasured_responses': len(rows),
            'note': 'Note-level contract does not measure sentence-level trait loss.'}
        return summary
    r.summarize = summarize


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir', required=True)
    p.add_argument('--ledger')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--score-only', action='store_true')
    args = p.parse_args()
    register()
    argv = ['--stage', STAGE, '--run-dir', args.run_dir]
    if args.ledger:
        argv += ['--ledger', args.ledger]
    if args.execute:
        argv += ['--execute']
    if args.score_only:
        argv += ['--score-only']
    r.main(argv)


if __name__ == '__main__':
    main()
