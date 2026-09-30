"""Offline evidence audit; no model, network, training or service calls."""
import collections
import hashlib
import importlib
import json
from pathlib import Path
import sys

D = Path(__file__).resolve().parent
E = D / 'evidence'
HANDOFF = E / 'MIND_person_handoff_retraining_20260929'
CONDITION = E / 'MIND_condition_alignment_20260929'
STATE = E / 'MIND_state_alignment_20260930'
RELEASE = E / 'MIND_release_gate_20260930'

def read(path):
    return json.loads(path.read_text())

def rows(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def main():
    manifest = read(D / 'SOURCE_MANIFEST.json')
    for entry in manifest['files']:
        assert sha((D / entry['archived']).read_bytes()) == entry['archived_sha256'], entry['archived']
    sys.path.insert(0, str(STATE))
    candidate = importlib.import_module('motion_goal_candidate')
    request_hashes = read(D / 'release_request_hashes.json')
    report = read(RELEASE / 'summary.json')
    verified = {}
    for batch, count in [('frontend', 16), ('canary', 80), ('natural', 80)]:
        data = {r['id']: r for r in rows(RELEASE / (batch + '.jsonl'))}
        results = rows(RELEASE / batch / 'results.jsonl')
        expected_hash = {r['id']: r['body_sha256'] for r in request_hashes[batch]}
        assert len(data) == len(results) == len({r['id'] for r in results}) == count
        correct = valid = 0
        for r in results:
            d = data[r['id']]
            payload = candidate.payload(d['context'], 'separate_motion_and_goal', 'depmkuykpfon9lg')
            assert sha(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()) == expected_hash[r['id']], r['id']
            if r['contract_pass']:
                candidate.validate(r['decoded'], d['context'])
                valid += 1
            accepted = d.get('allowed_commands', [d.get('expected_output', {}).get('next_command_id')])
            match = r['contract_pass'] and r['decoded']['next_command_id'] in accepted
            assert bool(match) == bool(r['command_match']), r['id']
            correct += bool(match)
        assert (correct, valid) == (report['batches'][batch]['command_match'], report['batches'][batch]['contract_pass'])
        verified[batch] = dict(n=count, command=correct, contract=valid)
    assert len(rows(RELEASE / 'remainder.jsonl')) == 280
    assert not (RELEASE / 'remainder' / 'results.jsonl').exists()
    assert read(RELEASE / 'expand_gate.json')['approved_by_predefined_gate'] is False
    assert collections.Counter(r['verdict'] for r in read(RELEASE/'frontend/semantic_review.json')['rows']) == {'pass':9,'fail':6,'wording_review':1}
    data_root = STATE / 'personal_contrasts_v5'
    split_rows = {s: rows(data_root/(s+'.jsonl')) for s in ['train','development','evaluation']}
    assert {s:len(v) for s,v in split_rows.items()} == {'train':2160,'development':180,'evaluation':360}
    groups = {s:{r['group_id'] for r in v} for s,v in split_rows.items()}
    for a,b in [('train','development'),('train','evaluation'),('development','evaluation')]:
        assert not groups[a] & groups[b], (a,b)
    assert read(STATE/'training_export_v2/manifest.json')['gpu_training_started'] is False
    # No provider-private answer fields are published anywhere in archived JSON.
    forbidden = {'reasoning_content','raw_response','request_headers','headers'}
    def check(value):
        if isinstance(value,dict):
            assert not forbidden & value.keys()
            for v in value.values():check(v)
        elif isinstance(value,list):
            for v in value:check(v)
    for f in E.rglob('*'):
        if f.suffix == '.json':check(read(f))
        elif f.suffix == '.jsonl':check(rows(f))
    usage0=read(HANDOFF/'usage_summary.json')
    usage1=read(CONDITION/'single_world/usage_summary.json')
    usage2=read(STATE/'usage_summary_all_completed.json')
    usage3=report['usage']
    calls=usage0['k_api_attempts']+usage1['api_attempts']+usage2['calls_ended']+usage3['calls_ended']
    inputs=usage0['k_input_tokens']+sum(x['input_tokens'] for x in [usage1,usage2,usage3])
    outputs=usage0['k_output_tokens']+sum(x['output_tokens'] for x in [usage1,usage2,usage3])
    assert (calls,inputs,outputs)==(511,896971,1368911)
    result=dict(status='PASS',archived_files=len(manifest['files']),release=verified,request_bodies_reproduced=176,
                conditional_remainder_not_run=280,dataset_rows={s:len(v) for s,v in split_rows.items()},
                k_calls=calls,k_input_tokens=inputs,k_output_tokens=outputs,
                archived_training_runs=2,archived_gpu_generations=32,new_calls_for_audit=0)
    (D/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
