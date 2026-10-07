"""Offline D5 preflight: saved outputs, request sizes, and disputed draft data.

No model, SSH, map acquisition or candidate generation. This is compiler/data
validation; it does not measure D5 model quality or clinical validity.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from experiments.mind_contract_ab_20261007 import completion, contract_d3, contract_d4, contract_d5
from experiments.mind_contract_ab_20261007 import run_d5, run_v2, scoring
from experiments.mind_contract_ab_20261007.dataset import leakage_check
from experiments.mind_policy_candidates import note_policy_eval
from app.llm.mind_policy import Policy

HERE = Path(__file__).resolve().parent


def load_lines(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def audit(run_dir):
    run_d5.register_candidate()
    inputs, scenes, refs, paths = run_v2.dataset('d5_dev128')
    people = {x['id']: x for x in inputs}
    requests = {}
    for stage in ('d5_dev8', 'd5_dev128'):
        stage_inputs, _, _, _ = run_v2.dataset(stage)
        sizes = [(len(json.dumps(contract_d5.request(x['personal'], run_v2.transport.MODEL),
                                 ensure_ascii=False).encode()), x['id']) for x in stage_inputs]
        requests[stage] = {
            'inputs': len(stage_inputs), 'first_calls': 2 * len(stage_inputs),
            'maximum_calls_including_one_correction': 4 * len(stage_inputs),
            'largest_first_request_bytes': max(sizes)[0],
            'largest_first_request_input_id': max(sizes)[1],
            'output_limit_tokens_per_call': contract_d5.SAMPLING['max_tokens'],
            'input_tokens': None,
            'note': 'First-request bytes only; correction adds the previous final output. Not a token estimate.',
        }
    old = json.loads((run_dir / 'd3_dev128' / 'scored_v2.json').read_text())
    replay = Counter(d3_valid_replayed=0, accepted_by_both=0,
                     same_ordered_engine_input=0, d5_only_rejected=0, rejected_by_both=0)
    rejections = []
    for row in old['rows']:
        if row['final_problem'] is not None:
            continue
        iid = row['input_id']
        folder = run_dir / 'd3_dev128' / iid / str(row['rep'])
        path = folder / ('fix' if row['corrected'] else 'first') / 'response.public.json'
        status, value = completion.classify(json.loads(path.read_text()))
        assert status == 'complete_json'
        personal = people[iid]['personal']
        contract_d3.compile_d3(value, personal)
        converted = contract_d5.from_d3(value, personal)
        replay['d3_valid_replayed'] += 1
        p4 = p5 = None
        error4 = error5 = None
        try:
            p4 = contract_d4.compile_d4(value, personal)
        except Exception as error:
            error4 = str(error)
        try:
            p5 = contract_d5.compile_d5(converted, personal)
        except Exception as error:
            error5 = str(error)
        if p4 is not None and p5 is not None:
            replay['accepted_by_both'] += 1
            if contract_d5.engine_input_key(p4) == contract_d5.engine_input_key(p5):
                replay['same_ordered_engine_input'] += 1
        if p4 is not None and p5 is None:
            replay['d5_only_rejected'] += 1
        if p4 is None and p5 is None:
            replay['rejected_by_both'] += 1
        if error5:
            rejections.append({'id': iid, 'rep': row['rep'], 'd4_rejected': error4 is not None,
                               'd5_errors': contract_d5.errors(converted, personal)})
    folder = HERE / 'dataset' / 'disputed_v1'
    drafts = load_lines(folder / 'disputed_inputs.jsonl')
    draft_scenes = json.loads((folder / 'disputed_scenes.NOT_MODEL_INPUT.json').read_text())
    draft_refs = json.loads((folder / 'disputed_reference.NOT_MODEL_INPUT.json').read_text())
    families = {r['id']: r['family'] for r in drafts}
    overlap = leakage_check.check(inputs, refs, {r['id']: r['family'] for r in inputs},
                                  drafts, draft_refs, families)
    baseline = Counter()
    by_family = {}
    for person in drafts:
        group = by_family.setdefault(person['family'], Counter())
        ref = Policy.model_validate(draft_refs[person['id']])
        empty = Policy(rules=[], unrepresented=[])
        for s in (x for x in draft_scenes if x['input_id'] == person['id']):
            expected = note_policy_eval.decide(ref, person['personal'], s['scene'])
            assert scoring.scene_pass(expected, s)
            no_trait = note_policy_eval.decide(empty, person['personal'], s['scene'])
            for c in (baseline, group):
                c['scenes'] += 1
                c['reference_pass'] += 1
                c['empty_policy_pass'] += scoring.scene_pass(no_trait, s)
                c['empty_policy_fails'] += not scoring.scene_pass(no_trait, s)
    return {
        'status': 'offline_preflight', 'new_model_calls': 0,
        'model_quality_measured': False, 'human_review_completed': False,
        'source_sha256': run_v2.source_sha256('d5'),
        'dev128_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        'requests': requests,
        'd3_replay': {'counts': dict(replay), 'rejections': rejections,
                      'scored_v2_sha256': hashlib.sha256(
                          (run_dir / 'd3_dev128' / 'scored_v2.json').read_bytes()).hexdigest(),
                      'limitation': 'D3 has no D5 roles/relations; fixed conversion cannot test their model generation.'},
        'disputed': {'personas': len(drafts), 'scenes': len(draft_scenes),
                     'empty_policy_baseline': dict(baseline),
                     'by_family': {k: dict(v) for k, v in by_family.items()},
                     'fine_overlap_or_text_flagged': sum(x['flag'] for x in overlap),
                     'coarse_review_only': sum(x['review'] for x in overlap),
                     'overlap': overlap, 'review_status': 'AI draft; human review pending',
                     'split': 'research_development; not independent final evaluation'},
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    report = audit(args.run_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'replay': report['d3_replay']['counts'],
                      'disputed': {k: v for k, v in report['disputed'].items() if k != 'overlap'},
                      'requests': report['requests']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
