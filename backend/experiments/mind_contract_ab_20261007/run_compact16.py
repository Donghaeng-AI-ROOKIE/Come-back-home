"""Frozen D15 diagnostic inputs, new D16 requests; no hidden score feedback."""
import argparse
from pathlib import Path
from experiments.mind_contract_ab_20261007 import run_v2 as r, run_compact15 as previous


def register():
    previous.register()
    r.CANDIDATES['d16'] = ('contract_d16', 'compile_d16', 'PLAN_d16.md')
    r.COMMON.append(Path(__file__).resolve())
    old = r.dataset
    r.dataset = lambda stage: previous.selected_dataset() if stage == 'd16_dev8' else old(stage)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir', required=True)
    p.add_argument('--ledger')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--score-only', action='store_true')
    a = p.parse_args()
    register()
    argv = ['--stage', 'd16_dev8', '--run-dir', a.run_dir]
    if a.ledger: argv += ['--ledger', a.ledger]
    if a.execute: argv += ['--execute']
    if a.score_only: argv += ['--score-only']
    r.main(argv)


if __name__ == '__main__': main()
