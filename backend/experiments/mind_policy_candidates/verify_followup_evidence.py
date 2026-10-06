"""Verify published evidence and re-score saved outputs without external calls.

This checks archive integrity and the stated synthetic action metric. It does
not grade source faithfulness independently or rerun the large KINTEX graph.
"""
import hashlib
import json
from pathlib import Path

from app.llm.mind_policy import Policy, RELEASE_QUALIFIED
from experiments.mind_policy_candidates.note_policy_eval import decide, score

ROOT = Path(__file__).parent / 'evidence_20261006'


def read(path):
    return json.loads(path.read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    manifest = read(ROOT / 'publication_manifest.json')
    for item in manifest['files']:
        data = (ROOT / item['path']).read_bytes()
        require(hashlib.sha256(data).hexdigest() == item['published_sha256'],
                f"published hash differs: {item['path']}")
    current = ROOT / 'MIND_practical_gate_20261006'
    inputs = {r['id']: r for r in read(current / 'development_inputs.json')}
    counts = {}
    for candidate in ('note_v4_off', 'person_v6_off', 'person_v6_on',
                      'person_v7_on_pilot', 'person_v7_off_or_probe'):
        folder = current / 'development' / candidate
        summary = read(folder / 'summary.json')
        passed = 0
        seen = set()
        for result in summary['results']:
            identity = (result['id'], result['rep'])
            require(identity not in seen, 'duplicate scored scene')
            seen.add(identity)
            source = inputs[result['id']]
            policy_path = folder / result['person_id'] / str(result['rep']) / 'compiled_policy.json'
            actual = False
            if policy_path.exists():
                policy = Policy.model_validate(read(policy_path))
                actual = score(decide(policy, source['personal'], source['scene']),
                               source['expected_commands'])
            require(actual == result['pass'], f'score differs: {candidate} {identity}')
            passed += actual
        require(passed == summary['gate']['passed'], f'count differs: {candidate}')
        require(len(seen) == summary['gate']['total'], f'denominator differs: {candidate}')
        counts[candidate] = [passed, len(seen)]

    previous = read(ROOT / 'MIND_source_scene_20261005' / 'structured_recovered_summary.json')
    rows = [r for r in previous['results'] if r['arm'] == 'structured_off']
    old_passed = sum(bool(r['output']) and score(r['output'], inputs[r['id']]['expected_commands'])
                     for r in rows)
    require((old_passed, len(rows)) == (9, 16), 'aligned baseline metric differs')
    require(counts['person_v6_on'] == [13, 16], 'best development score differs')

    usage = read(current / 'usage_summary.json')
    require(usage['reserved_attempts'] == usage['finished_attempts'] == 64, 'usage count differs')
    require(not usage['pending_attempts'], 'unfinished request')
    require(usage['started_by_role'] == {'mind_state_alignment_development': 64},
            'unexpected evaluation request')
    replay = read(current / 'actual_k_replay.json')
    for result in replay['results']:
        policy = current / 'development/person_v6_on/W1_1' / str(result['model_repeat']) / 'compiled_policy.json'
        # Publication formatting differs from original bytes, so verify the
        # recorded input digest against the original-source digest in the index.
        entry = next(x for x in manifest['files'] if x['path'] == str(policy.relative_to(ROOT)))
        require(entry['original_sha256'] == result['policy_sha256'], 'replay policy source differs')
        for row in result['snapshots']:
            require(abs(row['mass'] - 1) < 1e-9 and row['unresolved_mass'] == 0, 'mass differs')
            require(abs(row['mean_wait'] + row['mean_rest'] + row['mean_walk'] - row['minute']) < 1e-7,
                    'walking clock differs')
    require(RELEASE_QUALIFIED is False, 'unqualified candidate must not be enabled')
    print(json.dumps({'published_files_verified': len(manifest['files']),
                      'saved_policy_scores_recalculated': counts, 'previous_same_metric': [old_passed, len(rows)],
                      'development_calls': 64, 'evaluation_calls': 0,
                      'new_external_calls': 0, 'large_graph_rerun': False,
                      'clinical_accuracy_measured': False, 'release_qualified': False},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
