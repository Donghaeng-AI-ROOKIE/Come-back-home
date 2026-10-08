"""D12 compact-expression comparison on the same fixed repair8 sources."""
import argparse
from pathlib import Path
from experiments.mind_contract_ab_20261007 import run_v2 as r, run_repair8, resume_concise8 as guarded


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir', required=True); p.add_argument('--ledger')
    p.add_argument('--execute', action='store_true'); a = p.parse_args()
    r.CANDIDATES['d12'] = ('contract_d12', 'compile_d12', 'PLAN_d12.md')
    for f in (__file__, run_repair8.__file__, guarded.__file__):
        path = Path(f).resolve()
        if path not in r.COMMON: r.COMMON.append(path)
    original_dataset = r.dataset
    r.dataset = lambda stage: run_repair8.repair_dataset() if stage == 'd12_dev8' else original_dataset(stage)
    old_execute, old_score = r.execute, r.score
    r.execute = lambda *args: guarded.execute_guarded(old_execute, *args)
    r.score = lambda *args: guarded.score_with_unavailable(old_score, *args)
    old_summarize = r.summarize
    def summarize(module, rows):
        out = old_summarize(module, rows)
        out['trait_accounting'] = {'available': False, 'unmeasured_responses': len(rows),
            'note': 'Compact note-level contract cannot measure per-sentence trait loss; do not interpret as zero loss.'}
        return out
    r.summarize = summarize
    argv = ['--stage', 'd12_dev8', '--run-dir', a.run_dir]
    if a.ledger: argv += ['--ledger', a.ledger]
    if a.execute: argv.append('--execute')
    r.main(argv)


if __name__ == '__main__': main()
