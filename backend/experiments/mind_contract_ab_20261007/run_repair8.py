"""Only the eight declared D6 failure-repair inputs; no automatic expansion.

Reuse run_v2's metering, frozen source/data manifest and one correction cap.
This changes no saved D2-D5 score, input, expected answer or product code.
"""
import argparse
from pathlib import Path
from experiments.mind_contract_ab_20261007 import run_v2

IDS = ('DEV_P05_original', 'DEV_P08_preserve', 'DEV_P13_original', 'DEV_P16_preserve',
       'DEV_P26_hard', 'DEV_P29_original', 'DEV_P30_original', 'DEV_P31_original')


def repair_dataset():
    inputs, scenes, reference, files = run_v2._split(run_v2.DEV128, 'dev128')
    by_id = {r['id']: r for r in inputs}
    return ([by_id[i] for i in IDS], [r for r in scenes if r['input_id'] in IDS],
            {i: reference[i] for i in IDS}, files)


def register():
    run_v2.CANDIDATES['d6'] = ('contract_d6', 'compile_d6', 'PLAN_d6.md')
    if Path(__file__).resolve() not in run_v2.COMMON:
        run_v2.COMMON.append(Path(__file__).resolve())
    base = run_v2.dataset
    run_v2.dataset = lambda stage: repair_dataset() if stage == 'd6_dev8' else base(stage)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir', required=True)
    p.add_argument('--ledger')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--score-only', action='store_true')
    args = p.parse_args()
    register()
    argv = ['--stage', 'd6_dev8', '--run-dir', args.run_dir]
    if args.ledger:
        argv += ['--ledger', args.ledger]
    if args.execute:
        argv.append('--execute')
    if args.score_only:
        argv.append('--score-only')
    return run_v2.main(argv)


if __name__ == '__main__':
    main()
