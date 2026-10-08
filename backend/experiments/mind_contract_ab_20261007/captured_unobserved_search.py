"""Saved synthetic source on KINTEX with no oracle future observations.

A scope diagnostic, not a new accuracy score or a calibrated latent mind model.
Run with the same captured_walk CLI. Original scenarios/results remain frozen.
"""
from datetime import datetime
from experiments.mind_contract_ab_20261007 import captured_walk


def scenarios():
    return {'unobserved_search': {
        'description': 'Unlocated search: no future family, awareness, pain or environment observations supplied; unknown remains unknown.',
        'start': datetime(2026, 10, 9, 8), 'start_place': None, 'horizon': 360,
        'behavior': [], 'environment': [],
        'evaluation_scope': 'unobserved_context_diagnostic_not_clinical_accuracy',
        'confirmed_end': None}}


def main():
    original = captured_walk.scenarios
    try:
        captured_walk.scenarios = scenarios
        captured_walk.main()
    finally:
        captured_walk.scenarios = original


if __name__ == '__main__':
    main()
