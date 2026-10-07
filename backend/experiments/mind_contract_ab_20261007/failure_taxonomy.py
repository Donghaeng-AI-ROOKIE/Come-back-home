"""Classify the saved 2026-10-06 failures without changing them. No model call.

One row per saved response: source answer, completion status, compiled rules,
scene outcomes, failure categories and the KINTEX slots replaying that response.
Categories (several may apply to one response):
  출력_미완료  finish_reason=length or empty content
  출력_경계    stop, but not exactly one clean JSON object
  규칙_누락    a reference behavior's source note has no compiled rule
  목적지_결합  a reference seek became a non-seek rule scoped to the goal
  해석_오류    a rule exists but scenes fail, an unsupported action, or a contract rejection
  엔진_소비    policy matched every scene, yet an authored walking check failed
Categories are typed comparisons with the authored reference, not clinical truth.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.llm.initial_behavior import decode_json_content
from experiments.mind_contract_ab_20261007 import completion, scoring
from experiments.mind_policy_candidates import condition_program as v4
from experiments.mind_policy_candidates import note_policy_eval as ev


def categories(row, reference):
    found = []
    if row['completion'] in ('incomplete_length', 'empty'):
        return ['출력_미완료']
    if row['completion'] != 'complete_json':
        return ['출력_경계']
    if row['compile_error']:
        return ['해석_오류']
    rules = row['policy']['rules']
    cited = {e['note_id'] for r in rules if not r['id'].startswith('initial_env_') for e in r['evidence']}
    for ref in reference['rules']:
        if ref['id'].startswith('initial_env_'):
            continue
        notes = {e['note_id'] for e in ref['evidence']}
        if not notes & cited:
            found.append('규칙_누락')
    if 'goal_scope_swap' in row['critical']:
        found.append('목적지_결합')
    failing = [s for s in row['scenes'] if not s['pass']]
    if failing and not found:
        found.append('해석_오류')
    if {'action_without_reference', 'withheld_action_injected'} & set(row['critical']):
        found.append('해석_오류')
    return sorted(set(found))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('refusing to overwrite ' + str(args.output))
    root = scoring.ROOT
    people, scenes, reference = scoring.load(root)
    spatial = json.loads((root / 'spatial_index.json').read_text())
    rows = []
    for path in sorted((root / 'comparison').glob('*/*/*/result.json')):
        saved = json.loads(path.read_text())
        pid, arm, rep = saved['person_id'], saved['arm'], str(saved['rep'])
        personal = people[pid]['personal']
        public = json.loads((path.parent / 'response.public.json').read_text())
        status, value = completion.classify(public)
        row = {'person_id': pid, 'family': people[pid]['family'], 'arm': arm, 'rep': rep,
               'answers': [n['text'].split('\n답변: ', 1)[-1] for n in personal['notes'][1:]],
               'completion': status, 'saved_valid': saved['valid'], 'compile_error': None,
               'model_rules': (value or {}).get('rules') if isinstance(value, dict) else None}
        policy = None
        if status == 'complete_json':
            try:
                policy = v4.compile_note(decode_json_content(public['final_content']), personal, 'ALL')
            except Exception as error:  # noqa: BLE001 - every rejection is recorded, none repaired
                row['compile_error'] = str(error).splitlines()[0][:200]
        # The scoring path must agree with the saved validity, or this audit is wrong.
        assert (policy is not None) == saved['valid'], path
        row['policy'] = policy.model_dump() if policy else None
        row['scenes'] = []
        for s in (x for x in scenes if x['person_id'] == pid):
            decision = ev.decide(policy, personal, s['scene']) if policy else None
            row['scenes'].append({'id': s['id'], 'expected': s['expected_commands'],
                                  'got': decision and {k: decision[k] for k in ('status', 'commands')},
                                  'pass': scoring.scene_pass(decision, s)})
        row['critical'] = scoring.critical(policy, personal, reference[pid], pid)
        row['categories'] = categories(row, reference[pid])
        slots = [s for s in spatial if s['person_id'] == pid and s['arm'] == arm and str(s['rep']) == rep]
        row['kintex'] = {'slots': len(slots), 'executed': sum(s['status'] == 'executed' for s in slots),
                         'authored_checks_all_passed': sum(s['status'] == 'executed' and all(
                             s['authored_behavior_checks'].values()) for s in slots),
                         'mean_path_km_6h': (round(sum(s['at_6h']['mean_path_km'] for s in slots if s['status'] == 'executed')
                                                   / max(1, sum(s['status'] == 'executed' for s in slots)), 2) if slots else None)}
        if (slots and all(x['pass'] for x in row['scenes'])
                and row['kintex']['authored_checks_all_passed'] < row['kintex']['executed']):
            row['categories'].append('엔진_소비')
        rows.append(row)
    passed = sum(s['pass'] for r in rows for s in r['scenes'])
    assert passed == 150 + 178, passed  # must equal the frozen published total
    counts = {}
    for r in rows:
        for c in r['categories']:
            key = r['arm'] + ':' + c
            counts[key] = counts.get(key, 0) + 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'model_calls': 0, 'source': 'evidence_diverse_20261006 (unchanged)',
                                       'responses': len(rows), 'decisions_passed': passed,
                                       'category_counts_by_arm': dict(sorted(counts.items())),
                                       'rows': rows}, ensure_ascii=False, indent=1))
    print(json.dumps(dict(sorted(counts.items())), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
