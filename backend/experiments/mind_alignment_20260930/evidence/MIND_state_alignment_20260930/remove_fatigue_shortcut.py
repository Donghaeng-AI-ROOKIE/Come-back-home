"""Train-only negative control: a simulator proxy is not a spoken report."""
import collections
import hashlib
import json
from pathlib import Path
import audit_personal_contrasts

D = Path(__file__).resolve().parent

def build():
    src = D / 'personal_contrasts_v4'
    out = D / 'personal_contrasts_v5'
    out.mkdir(exist_ok=False)
    rows = [json.loads(x) for x in (src / 'train.jsonl').read_text().splitlines()]
    changes = []
    for row in rows:
        # Each paired scene and its wording variants receive the same proxy.
        # Use no guardian words, action labels, oracle values or person index.
        scene_key = row['contrast_id'].rsplit('_V', 1)[0]
        value = (.1, .5, .9)[int(hashlib.sha256(('proxy-v5:' + scene_key).encode()).hexdigest(), 16) % 3]
        old = row['context']['state']['fatigue']
        row['context']['state']['fatigue'] = value
        row['quality']['fatigue_proxy_assignment'] = 'scene-hash balanced nuisance; independent of reported tiredness; identical within personal pair and wording variants'
        changes.append(dict(id=row['id'],old_fatigue_proxy=old,new_fatigue_proxy=value))
    (out / 'train.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows))
    for name in ('development.jsonl','evaluation.jsonl','policies.json'):
        (out / name).write_bytes((src / name).read_bytes())
    manifest = json.loads((src / 'manifest.json').read_text())
    manifest['parent_version'] = 'personal_contrasts_v4'
    manifest['status'] = 'training_candidate_for_conditional_personalization_not_full_mind_model'
    manifest['fatigue_change'] = 'Break report=true -> proxy=.9 correlation in train only. Ground-truth personal conditions, observations and commands unchanged. No new sample rows.'
    for name, entry in manifest['files'].items():
        entry['sha256'] = hashlib.sha256((out / name).read_bytes()).hexdigest()
    (out / 'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (out / 'proxy_changes.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in changes))
    report = audit_personal_contrasts.audit(out)
    assert not report['errors'], report['errors']
    original = {r['id']:r for r in map(json.loads,(src/'train.jsonl').read_text().splitlines())}
    for r in rows:
        old = original[r['id']]
        assert r['expected_output'] == old['expected_output']
        assert r['context']['person'] == old['context']['person']
        assert r['context']['state']['recent_events'] == old['context']['state']['recent_events']
    distributions = collections.defaultdict(collections.Counter)
    for r in rows:
        if r['variant'] != 0: continue
        o = r['authoring_oracle']
        for atom,val in zip((o['first_atom'],o['second_atom']),o['values']):
            if atom == 'reported_tiredness': distributions[str(val)][str(r['context']['state']['fatigue'])] += 1
    assert all(len(v) == 3 for v in distributions.values())
    summary = dict(status='PASS',rows=len(rows),added_rows=0,
        unchanged_originals_and_labels=True,
        development_unchanged=(out/'development.jsonl').read_bytes()==(src/'development.jsonl').read_bytes(),
        evaluation_unchanged=(out/'evaluation.jsonl').read_bytes()==(src/'evaluation.jsonl').read_bytes(),
        base_rows_tiredness_report_by_proxy={k:dict(v) for k,v in distributions.items()},
        not_clinical_calibration=True,remaining_gaps=['all current actions are seek','all elapsed_minutes are 60','no saved K preparation','no clinical review'])
    (out/'negative_control_audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__ == '__main__':build()
