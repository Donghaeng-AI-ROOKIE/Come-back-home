"""Fixed source-repair inputs, D8 schema vs plain decoding. Never changes gold."""
import argparse
from pathlib import Path
from experiments.mind_contract_ab_20261007 import run_repair8, run_v2


def register():
    run_v2.CANDIDATES.update({'d8': ('contract_d8', 'compile_d8', 'PLAN_d8.md'),
                              'd8plain': ('contract_d8plain', 'compile_d8plain', 'PLAN_d8.md')})
    for path in (Path(__file__).resolve(), Path(run_repair8.__file__).resolve()):
        if path not in run_v2.COMMON:
            run_v2.COMMON.append(path)
    base = run_v2.dataset
    run_v2.dataset = lambda stage: run_repair8.repair_dataset() if stage in ('d8_dev8', 'd8plain_dev8') else base(stage)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate', choices=('d8', 'd8plain'), required=True)
    p.add_argument('--run-dir', required=True)
    p.add_argument('--ledger')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--score-only', action='store_true')
    a = p.parse_args()
    register()
    argv = ['--stage', a.candidate + '_dev8', '--run-dir', a.run_dir]
    if a.ledger:
        argv += ['--ledger', a.ledger]
    if a.execute:
        argv.append('--execute')
    if a.score_only:
        argv.append('--score-only')
    return run_v2.main(argv)


if __name__ == '__main__':
    main()
