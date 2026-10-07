"""D5-only entry point; the already-running D4 runner stays unchanged.

Delegates to run_v2 including its authorization, previous-stage gates,
no-resubmission logic, source/data hashes, and cost ledger. This entry point
is also hashed so the registration cannot change silently between stages.
"""
from pathlib import Path
import sys

from experiments.mind_contract_ab_20261007 import run_v2


def register_candidate():
    run_v2.CANDIDATES['d5'] = ('contract_d5', 'compile_d5', 'PLAN_d5.md')
    source = Path(__file__).resolve()
    if source not in run_v2.COMMON:
        run_v2.COMMON.append(source)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    for option in ('--stage', '--rescore'):
        for index, argument in enumerate(argv):
            if argument == option and index + 1 < len(argv):
                stage = argv[index + 1]
            elif argument.startswith(option + '='):
                stage = argument.split('=', 1)[1]
            else:
                continue
            if stage not in ('d5_dev8', 'd5_dev128', 'd5_eval64'):
                raise SystemExit('run_d5 only accepts D5 stages; use the frozen runner for other candidates')
    register_candidate()
    return run_v2.main(argv)


if __name__ == '__main__':
    main()
