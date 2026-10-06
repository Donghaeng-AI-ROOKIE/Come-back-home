"""Recompile and re-score all 512 saved decisions, without the online runner.

This verifies implementation reproducibility, not clinical truth or new model
performance. Verifies public file/member hashes and saved walking invariants as well.
Requires the project dependencies. Does not run model or map queries.
"""
import argparse
import hashlib
import json
import socket
import sys
import tarfile
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent / 'evidence_diverse_20261006'
BACKEND = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(BACKEND))


def deny_network(*args, **kwargs):
    raise RuntimeError('This saved-output replay prohibits network access')


socket.create_connection = deny_network
socket.socket.connect = deny_network
socket.socket.connect_ex = deny_network

from app.llm import initial_behavior, mind_policy
from experiments.mind_policy_candidates import condition_program as candidate
from experiments.mind_policy_candidates import note_policy_eval as evaluator


def read(path):
    return json.loads(path.read_text())


def verify_archive():
    manifest = read(DATA / 'publication_manifest.json')
    for item in manifest['files']:
        assert hashlib.sha256((DATA / item['path']).read_bytes()).hexdigest() == item['published_sha256'], item['path']
    archive_manifest = read(DATA / 'spatial_archive_manifest.json')
    expected = {m['path']: m for m in archive_manifest['members']}
    seen = set()
    statuses = Counter()
    checkpoints = 0
    index = {r['archive_member']: r for r in read(DATA / 'spatial_index.json')}
    with tarfile.open(DATA / archive_manifest['archive'], 'r:gz') as tar:
        for member in tar:
            assert member.isfile() and member.name in expected and member.name not in seen
            raw = tar.extractfile(member).read()
            assert hashlib.sha256(raw).hexdigest() == expected[member.name]['published_sha256']
            seen.add(member.name)
            if member.name == 'spatial/manifest.json':
                continue
            row = json.loads(raw)
            assert row['status'] == index[member.name]['status']
            statuses[row['status']] += 1
            if row['status'] != 'executed':
                continue
            assert row['authored_behavior_checks'] == index[member.name]['authored_behavior_checks']
            assert all(row['engineering'][k] is True for k in (
                'mass_conserved', 'clock_accounting', 'distance_matches_walk_time', 'full_horizon_resolved'))
            assert [s['minute'] for s in row['snapshots']] == [60, 120, 240, 360]
            for snap in row['snapshots']:
                assert abs(sum(snap['cells'].values()) - 1) < 1e-8
                assert snap['quality']['unresolved_mass'] == 0
                assert abs(sum(snap[k] for k in ('mean_wait_minutes', 'mean_rest_minutes', 'mean_walk_minutes')) - snap['minute']) < 1e-7
            if row['engineering']['checkpoint_equal'] is not None:
                assert row['engineering']['checkpoint_equal'] is True
                checkpoints += 1
    assert seen == set(expected) and len(index) == 384
    assert sum(statuses.values()) == 384 and statuses['executed'] == 276
    assert checkpoints == 23
    usage = read(DATA / 'usage_summary.json')
    assert usage['started'] == usage['finished'] == 128 and usage['pending'] == 0
    assert usage['known_token_subtotals'] == {'prompt_tokens': 218096, 'completion_tokens': 383341, 'total_tokens': 601437}
    assert read(DATA / 'selection.json')['selected_arm'] is None
    assert read(DATA / 'selection.json')['evaluation_calls'] == 0
    assert candidate.RELEASE_QUALIFIED is False and mind_policy.RELEASE_QUALIFIED is False
    return {'published_files': len(manifest['files']), 'spatial_members': len(seen),
            'spatial_statuses': dict(statuses), 'saved_checkpoints_verified': checkpoints,
            'evaluation_calls': 0, 'release_qualified': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, help='Optional new report file; refuses overwrite')
    args = parser.parse_args()
    archive = verify_archive()
    manifest = read(DATA / 'manifest.json')
    published = {r['path']: r for r in read(DATA / 'publication_manifest.json')['files']}
    for filename, digest in manifest['data_sha256'].items():
        # Map provenance contains redacted local paths. Compare source hashes
        # against the original freeze, and bytes against the public manifest.
        assert published[filename]['original_sha256'] == digest, filename
        assert hashlib.sha256((DATA / filename).read_bytes()).hexdigest() == published[filename]['published_sha256'], filename
    for module in (candidate, evaluator, mind_policy, initial_behavior):
        original = [v for k, v in manifest['source_sha256'].items()
                    if Path(k).name == Path(module.__file__).name]
        assert len(original) == 1
        assert hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() == original[0]
    people = {p['person_id']: p for p in read(DATA / 'profiles.json')}
    scenes = read(DATA / 'scenes.json')
    original = read(DATA / 'comparison' / 'summary.json')['results']
    key = lambda r: (r['id'], r['arm'], r['rep'])
    expected = {key(r): (r['decision'], r['pass']) for r in original}
    actual = {}
    counts = {arm: {'outputs': 0, 'valid_outputs': 0, 'passed': 0, 'total': 0}
              for arm in ('on', 'off')}
    for file in sorted((DATA / 'comparison').glob('*/*/*/result.json')):
        r = read(file)
        personal = people[r['person_id']]['personal']
        public = read(file.parent / 'response.public.json')
        policy = None
        if r['valid']:
            assert public['finish_reason'] == 'stop'
            output = initial_behavior.decode_json_content(public['final_content'])
            assert output == r['output']
            policy = candidate.compile_note(output, personal, 'ALL', whole_person=True)
            assert policy.model_dump() == read(file.parent / 'compiled_policy.json')
        else:
            # Keep incomplete outputs as failures, even if a prefix is parseable.
            if public.get('finish_reason') == 'stop' and public.get('final_content'):
                try:
                    value = initial_behavior.decode_json_content(public['final_content'])
                    candidate.compile_note(value, personal, 'ALL', whole_person=True)
                except Exception:
                    pass
                else:
                    raise AssertionError(f'Previously invalid output now accepted: {file}')
        c = counts[r['arm']]
        c['outputs'] += 1
        c['valid_outputs'] += int(r['valid'])
        for scene in (s for s in scenes if s['person_id'] == r['person_id']):
            decision = evaluator.decide(policy, personal, scene['scene']) if policy else None
            passed = bool(decision and decision['status'] == scene['expected_status']
                          and set(decision['commands']) == set(scene['expected_commands'])
                          and (scene['expected_possible_commands'] is None
                               or set(decision['possible_commands']) == set(scene['expected_possible_commands'])))
            k = (scene['id'], r['arm'], r['rep'])
            assert k not in actual
            actual[k] = (decision, passed)
            c['total'] += 1
            c['passed'] += int(passed)
    assert len(actual) == 512 and actual == expected
    assert counts['on']['passed'] == 150 and counts['off']['passed'] == 178
    result = {'saved_decisions': len(actual), 'exact_match': True,
              'arms': counts, 'model_calls': 0, 'network_allowed': False,
              'scope': 'Saved public outputs recompiled and scored; saved spatial invariants checked; no new simulation or clinical evaluation',
              'archive': archive}
    if args.output:
        with args.output.open('x') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write('\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
