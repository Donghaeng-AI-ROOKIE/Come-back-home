"""Versioned, train-only wording repair. No model calls, training, or NLP oracle.

The immutable v5 plus nine reviewed replacements defines v6; materialization
produces full JSONL files and the same SFT interface as training_export_v2.
"""
import argparse
import collections
import copy
import hashlib
import itertools
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ARCHIVE = HERE.parents[1]
STATE = ARCHIVE / 'evidence/MIND_state_alignment_20260930'
SOURCE = STATE / 'personal_contrasts_v5'
sys.path.insert(0, str(STATE))
import motion_goal_candidate as contract
from build_personal_contrasts import policy_results
from audit_personal_contrasts import at

PEOPLE = ('PC009_P1', 'PC023_P1', 'PC037_P1')
SOURCE_SHA = '461c4b3abd2fe57e2b1d574c1fc975617dcedf4237e8821a9f9d5fad69778913'


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def rows_bytes(rows):
    return ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n' for row in rows).encode()


def source_checks():
    """Fail closed if the source, caveat, or contract dependencies changed."""
    pins = json.loads((HERE / 'source_pins.json').read_text())
    for name, sha in pins['sha256'].items():
        if digest((ARCHIVE / name).read_bytes()) != sha:
            raise ValueError('frozen_source_changed:' + name)
    if digest((SOURCE / 'train.jsonl').read_bytes()) != SOURCE_SHA:
        raise ValueError('wrong_parent_train')
    caveat = json.loads((ARCHIVE / 'evidence/MIND_release_gate_20260930/data_wording_caveat.json').read_text())
    affected = {p['person_id'] for p in caveat['affected_profiles'] if p['split'] == 'train'}
    if affected != set(PEOPLE):
        raise ValueError('unexpected_caveat_scope')
    return pins


def revise(rows, replacements):
    """Change exactly one evidence text per affected row, retaining every label."""
    lookup = {(r['person_id'], r['variant']): r for r in replacements}
    if len(lookup) != 9 or set(lookup) != set(itertools.product(PEOPLE, range(3))):
        raise ValueError('replacement_scope')
    result, changes = [], []
    for original in rows:
        row = copy.deepcopy(original)
        if row['person_id'] in PEOPLE:
            spec = lookup[(row['person_id'], row['variant'])]
            note = row['context']['person']['evidence_notes']
            if row['split'] != 'train' or len(note) != 1 or note[0]['id'] != 'N1':
                raise ValueError('unexpected_affected_row')
            if note[0]['text'] != spec['before']:
                raise ValueError('old_wording_mismatch:' + row['id'])
            if row['expected_output']['next_command_id'] != 'continue':
                raise ValueError('unexpected_affected_label')
            note[0]['text'] = spec['after']
            changes.append(dict(id=row['id'], person_id=row['person_id'], variant=row['variant'],
                                path='/context/person/evidence_notes/0/text',
                                before_sha256=digest(spec['before'].encode()),
                                after_sha256=digest(spec['after'].encode())))
        result.append(row)
    if len(changes) != 81 or collections.Counter(c['person_id'] for c in changes) != dict.fromkeys(PEOPLE, 27):
        raise ValueError('expected_exactly_81_changes')
    return result, changes


def audit(original, corrected, development, evaluation):
    errors = []
    policies = {p['group_id']: p for p in json.loads((SOURCE / 'policies.json').read_text())}
    splits = {'train': corrected, 'development': development, 'evaluation': evaluation}
    if len(original) != 2160 or len(corrected) != 2160:
        errors.append('train_count')
    changed = []
    for old, new in zip(original, corrected):
        if old == new:
            continue
        changed.append(new['id'])
        restored = copy.deepcopy(new)
        restored['context']['person']['evidence_notes'][0]['text'] = old['context']['person']['evidence_notes'][0]['text']
        if restored != old or new['person_id'] not in PEOPLE or new['split'] != 'train':
            errors.append('out_of_scope_change:' + new['id'])
    if len(changed) != 81:
        errors.append('changed_count')
    for split, rows in splits.items():
        expected_count = {'train': 2160, 'development': 180, 'evaluation': 360}[split]
        if len(rows) != expected_count or len({r['id'] for r in rows}) != len(rows):
            errors.append('count_or_duplicate_id:' + split)
        lineages = collections.defaultdict(list)
        pairs = collections.defaultdict(list)
        for row in rows:
            oracle = row['authoring_oracle']
            p = policies[row['group_id']]
            person = int(row['person_id'].rsplit('P', 1)[1])
            values = [at(row['context'], path) for path in oracle['fact_paths']]
            possible, expected = policy_results(p['kind'], values, p['main_commands'][person], p['second_command'])
            if values != oracle['values'] or possible != oracle['possible_commands'] or expected != oracle['expected_command'] or expected != row['expected_output']['next_command_id']:
                errors.append('oracle_mismatch:' + row['id'])
            if row['split'] != split or p['split'] != split:
                errors.append('split_mismatch:' + row['id'])
            try:
                contract.validate(row['expected_output'], row['context'])
                body = contract.payload(row['context'], 'separate_motion_and_goal', 'offline-audit')
                user = json.loads(body['messages'][1]['content'])
                if user['person'] != row['context']['person']:
                    raise ValueError('person_provenance_changed')
                if any(key in body['messages'][1]['content'] for key in ('authoring_oracle', 'expected_output', 'possible_commands', 'expected_command')):
                    raise ValueError('oracle_leakage')
                source = 'N2' if oracle['kind'] == 'correction' else 'N1'
                if row['expected_output']['source_ids'] != [source]:
                    raise ValueError('wrong_evidence_source')
            except (ValueError, TypeError, KeyError) as exc:
                errors.append(row['id'] + ':' + str(exc))
            lineages[row['lineage_id']].append(row)
            pairs[row['contrast_id']].append(row)
        for group in lineages.values():
            if len(group) != (3 if split == 'train' else 1) or len({json.dumps(r['expected_output'], sort_keys=True) for r in group}) != 1:
                errors.append('variant_label_or_count:' + group[0]['lineage_id'])
        for pair in pairs.values():
            if len(pair) != 2:
                errors.append('incomplete_pair:' + pair[0]['contrast_id'])
                continue
            scenes = []
            for row in pair:
                c = copy.deepcopy(row['context'])
                for key in ('case_id', 'person_id', 'person_revision', 'person'):
                    c.pop(key, None)
                scenes.append(c)
            if scenes[0] != scenes[1]:
                errors.append('paired_scene_changed:' + pair[0]['contrast_id'])
    for a, b in itertools.combinations(splits, 2):
        for key in ('id', 'group_id', 'person_id', 'lineage_id'):
            if {r[key] for r in splits[a]} & {r[key] for r in splits[b]}:
                errors.append('split_leakage:' + key)
        if {r['authoring_oracle']['pair_key'] for r in splits[a]} & {r['authoring_oracle']['pair_key'] for r in splits[b]}:
            errors.append('split_leakage:pair_key')
        if {n['text'] for r in splits[a] for n in r['context']['person']['evidence_notes']} & {n['text'] for r in splits[b] for n in r['context']['person']['evidence_notes']}:
            errors.append('split_leakage:evidence_text')
    return dict(status='FAIL' if errors else 'PASS', errors=errors, train_rows=len(corrected),
                changed_rows=len(changed), unchanged_rows=len(corrected)-len(changed),
                changed_profiles=list(PEOPLE), changed_row_ids=changed,
                base_states=len({r['lineage_id'] for r in corrected}),
                synthetic_profiles=len({r['person_id'] for r in corrected}),
                labels_observations_ids_splits_preserved=not errors,
                checked_rows_including_heldout=sum(map(len, splits.values())),
                scope='Data and input-contract consistency; not model semantic performance')


def export(rows):
    result = []
    for row in rows:
        contract.validate(row['expected_output'], row['context'])
        messages = contract.payload(row['context'], 'separate_motion_and_goal', 'not-an-api-call')['messages']
        result.append({**{k: row[k] for k in ('id', 'group_id', 'person_id', 'lineage_id', 'variant')},
                       'messages': messages + [dict(role='assistant', content=json.dumps(row['expected_output'], ensure_ascii=False))],
                       'expected_output': row['expected_output'],
                       'source_sha256': digest(json.dumps(row, ensure_ascii=False, sort_keys=True).encode()),
                       'clinical_observation': False, 'real_frontend_output': False})
    return result


def build(out):
    pins = source_checks()
    out = out.resolve()
    if out == ARCHIVE or ARCHIVE in out.parents and HERE not in out.parents:
        raise ValueError('output_must_not_overlap_frozen_archive')
    if out.exists():
        raise ValueError('refusing_overwrite:' + str(out))
    original = read_rows(SOURCE / 'train.jsonl')
    replacements = json.loads((HERE / 'replacements.json').read_text())
    corrected, changes = revise(original, replacements)
    development = read_rows(SOURCE / 'development.jsonl')
    evaluation = read_rows(SOURCE / 'evaluation.jsonl')
    report = audit(original, corrected, development, evaluation)
    if report['errors']:
        raise ValueError(report['errors'])
    dataset = out / 'personal_contrasts_v6'
    training = out / 'training_export_v3'
    dataset.mkdir(parents=True)
    training.mkdir()
    (dataset / 'train.jsonl').write_bytes(rows_bytes(corrected))
    for name in ('development.jsonl', 'evaluation.jsonl', 'policies.json'):
        (dataset / name).write_bytes((SOURCE / name).read_bytes())
    (out / 'changes.jsonl').write_bytes(rows_bytes(changes))
    train = export(corrected)
    files = {'train.jsonl': train, 'train_base.jsonl': [r for r in train if r['variant'] == 0],
             'development.jsonl': export(development)}
    for name, rows in files.items():
        (training / name).write_bytes(rows_bytes(rows))
    manifest = dict(version='personal_contrasts_v6', parent_version='personal_contrasts_v5',
                    parent_train_sha256=SOURCE_SHA, status='wording_repaired_mechanical_candidate_not_trained',
                    changed_profiles=list(PEOPLE), changed_rows=81,
                    changed_path='/context/person/evidence_notes/0/text',
                    development_and_evaluation='byte-identical frozen references; evaluation caveats remain',
                    quality_flags='Original row-level review flags retained; mechanical PASS is not independent review',
                    human_review=False, clinical_validation=False, model_calls=0, training_runs=0,
                    files={n: dict(rows=len(read_rows(dataset / n)), sha256=digest((dataset / n).read_bytes()))
                           for n in ('train.jsonl', 'development.jsonl', 'evaluation.jsonl')})
    write_json(dataset / 'manifest.json', manifest)
    write_json(training / 'manifest.json', dict(status='candidate_pending_current_tokenization',
        source_version='personal_contrasts_v6', contract='frozen motion_goal_candidate:separate_motion_and_goal',
        evaluation_included=False, training_runs=0,
        files={n: dict(rows=len(rows), sha256=digest((training / n).read_bytes())) for n, rows in files.items()}))
    report['development_byte_identical'] = (dataset / 'development.jsonl').read_bytes() == (SOURCE / 'development.jsonl').read_bytes()
    report['evaluation_byte_identical'] = (dataset / 'evaluation.jsonl').read_bytes() == (SOURCE / 'evaluation.jsonl').read_bytes()
    report['source_files_verified'] = len(pins['sha256'])
    source_checks()
    write_json(out / 'mechanical_report.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=HERE / 'generated')
    args = parser.parse_args()
    print(json.dumps(build(args.out), ensure_ascii=False, indent=2))
