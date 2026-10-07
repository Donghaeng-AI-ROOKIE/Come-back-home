"""Paired D10/D11 on frozen repair8; no gold changes or automatic expansion."""
import argparse
from pathlib import Path
from experiments.mind_contract_ab_20261007 import run_v2 as r, run_repair8, resume_concise8 as guarded


def register():
    r.CANDIDATES.update({'d10': ('contract_d10', 'compile_d10', 'PLAN_nonreasoning.md'),
                         'd11': ('contract_d11', 'compile_d11', 'PLAN_nonreasoning.md')})
    for path in (Path(__file__).resolve(), Path(run_repair8.__file__), Path(guarded.__file__)):
        if path not in r.COMMON: r.COMMON.append(path)
    dataset = r.dataset
    r.dataset = lambda stage: run_repair8.repair_dataset() if stage in ('d10_dev8', 'd11_dev8') else dataset(stage)
    execute, score = r.execute, r.score
    r.execute = lambda *args: guarded.execute_guarded(execute, *args)
    r.score = lambda *args: guarded.score_with_unavailable(score, *args)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate', choices=('d10', 'd11'), required=True)
    p.add_argument('--run-dir', required=True); p.add_argument('--ledger')
    p.add_argument('--execute', action='store_true'); a = p.parse_args()
    register()
    argv = ['--stage', a.candidate + '_dev8', '--run-dir', a.run_dir]
    if a.ledger: argv += ['--ledger', a.ledger]
    if a.execute: argv.append('--execute')
    r.main(argv)


if __name__ == '__main__': main()
