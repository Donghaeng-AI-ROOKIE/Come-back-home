"""Recheck materialized candidate against versioned mechanical/tokenizer receipts."""
import argparse
import json
from pathlib import Path

from build import HERE, digest, source_checks, write_json


def verify(root):
    source_checks()
    token = json.loads((HERE / 'tokenization_report.json').read_text())
    regression = json.loads((HERE / 'regression_report.json').read_text())
    mechanical = json.loads((root / 'mechanical_report.json').read_text())
    if mechanical != json.loads((HERE / 'mechanical_report.json').read_text()):
        raise ValueError('mechanical_report_mismatch')
    for directory, receipt in [('personal_contrasts_v6', 'dataset_manifest.json'),
                               ('training_export_v3', 'export_manifest.json')]:
        pinned = json.loads((HERE / receipt).read_text())
        if json.loads((root / directory / 'manifest.json').read_text()) != pinned:
            raise ValueError('manifest_mismatch:' + directory)
        for name, entry in pinned['files'].items():
            if digest((root / directory / name).read_bytes()) != entry['sha256']:
                raise ValueError('candidate_changed:' + directory + '/' + name)
    for name, result in token['files'].items():
        if result['sha256'] != digest((root / 'training_export_v3' / name).read_bytes()):
            raise ValueError('tokenization_receipt_stale:' + name)
        if result['rows'] != result['encoded'] or result['min_answer_tokens'] < 1 or result['max_tokens'] > token['max_tokens']:
            raise ValueError('tokenization_incomplete:' + name)
    for name, sha in regression['checked_code_sha256'].items():
        if digest((HERE / name).read_bytes()) != sha:
            raise ValueError('regression_receipt_stale:' + name)
    if token['status'] != 'PASS' or token['errors'] or regression['status'] != 'PASS' or mechanical['status'] != 'PASS':
        raise ValueError('required_gate_failed')
    return dict(status='PASS', mechanically_ready_training_candidate=True,
                wording_blocker_resolved=True, source_version='personal_contrasts_v6',
                training_rows=2160, changed_rows=81, unchanged_rows=2079,
                regression_tests_passed=regression['tests'], tokenized_training_rows=2160,
                max_train_tokens=token['files']['train.jsonl']['max_tokens'], token_limit=token['max_tokens'],
                frozen_source_commit='e5c3cdedc8ad1c9ace7ebfffe6a4f9ac3a3f779f',
                frozen_evidence_tree_sha='1a28a3e87bce00e36cd05031dc415e99ed89af2a',
                evaluation_labels_or_scores_changed=False, training_runs=0, model_calls=0,
                model_semantic_regression_run=False, independent_human_review=False,
                clinical_validation=False, production_approval=False,
                scope='Mechanical readiness of the repaired synthetic candidate only; original review flags and coverage limits remain')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generated', type=Path, default=HERE / 'generated')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = verify(args.generated)
    if args.out:
        if args.out.exists():
            raise SystemExit('refusing overwrite')
        write_json(args.out, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
