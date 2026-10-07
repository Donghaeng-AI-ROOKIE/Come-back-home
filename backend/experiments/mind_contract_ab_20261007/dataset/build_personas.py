"""Build a research-grounded persona set (new prototypes, not dev128 derivatives).

Each persona cites verified research evidence IDs (research_basis) and has four
scenes (trigger / non_trigger / boundary_or_release / unobserved_or_conflict).
The authored reference rule must reproduce every scene expectation through the
typed evaluator: internal coherence only, not proof that the Korean wording or
the research mapping is right. AI-authored personas stay draft_unreviewed until
a person reviews them. Labels never enter the model-input file.

Run:  python -m experiments.mind_contract_ab_20261007.dataset.build_personas \
        --fragments personas_a personas_b --prefix eval64 --split evaluation --out DIR
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

from experiments.mind_contract_ab_20261007 import scoring
from experiments.mind_contract_ab_20261007.dataset.build_dev128 import ROLES, case, nearby, scene, spec
from experiments.mind_policy_candidates import condition_program as v4
from experiments.mind_policy_candidates import note_policy_eval as ev

DEFAULT_INTRO = '등록 장소는 어떤 의미인가요?'


class PersonaBuilder:
    def __init__(self, split, evidence_ids):
        self.split, self.evidence_ids = split, set(evidence_ids)
        self.records, self.rows, self.oracles, self.reviews = [], [], {}, []

    def persona(self, pid, family, research_basis, places, qa, rules, cases, summary,
                checks, representable=True, author='AI draft (Claude), 2026-10-07'):
        if any(r['id'] == pid for r in self.records):
            raise ValueError('duplicate ' + pid)
        unknown = set(research_basis) - self.evidence_ids
        if not research_basis or unknown:
            raise ValueError(f'{pid}: research_basis must cite verified evidence IDs; unknown {sorted(unknown)}')
        if not 2 <= len(places) <= 4 or len({p['label'] for p in places}) != len(places):
            raise ValueError(f'{pid}: 2-4 distinct registered places')
        notes = [{'id': 'N' + str(i), 'text': '질문: ' + q + '\n답변: ' + a, 'provenance': 'guardian_original',
                  'source_kinds': ['guardian_turn'], 'recorded_at': ['2026-10-01T10:00:00+09:00']}
                 for i, (q, a) in enumerate(qa)]
        personal = {'notes': notes, 'places': places, 'prepared_initial': {}}
        used = {n for r in rules for n in r['note_ids']}
        out = {'source_assessment': '수기 참조 규칙. 모델 평가나 임상 근거가 아님.', 'rules': rules,
               'non_action_note_ids': [n['id'] for n in notes if n['id'] not in used]}
        policy = v4.compile_note(out, personal, 'ALL')
        if len(cases) != 4 or {c['role'] for c in cases} != set(ROLES):
            raise ValueError(pid + ': need one scene per role ' + str(ROLES))
        for i, item in enumerate(cases):
            row = {'id': f'{pid}_S{i + 1}', 'input_id': pid, 'root_id': pid, 'person_id': pid,
                   'family': family, **item}
            decision = ev.decide(policy, personal, item['scene'])
            if not scoring.scene_pass(decision, row):
                raise AssertionError(f'{row["id"]}: reference gives {decision}, authored {item}')
            self.rows.append(row)
        self.records.append({'id': pid, 'root_id': pid, 'form': 'research_prototype', 'family': family,
                             'split': self.split, 'synthetic': True, 'review_status': 'draft_unreviewed',
                             'author': author, 'personal': personal})
        self.oracles[pid] = policy.model_dump()
        self.reviews.append({'id': pid, 'family': family, 'research_basis': list(research_basis),
                             'summary': summary, 'required_scene_checks': list(checks),
                             'representable_in_current_contract': representable, 'reviewer': None,
                             'review_status': 'draft_unreviewed', 'model_calls': 0,
                             'clinical_validity_reviewed': False})


def build(fragments, split, evidence_ids):
    b = PersonaBuilder(split, evidence_ids)
    dsl = SimpleNamespace(persona=b.persona, spec=spec, scene=scene, nearby=nearby, case=case,
                          DEFAULT_INTRO=DEFAULT_INTRO)
    for name in fragments:
        importlib.import_module(f'experiments.mind_contract_ab_20261007.dataset.{name}').register(dsl)
    texts = {}
    for r in b.records:
        key = json.dumps(r['personal']['notes'], ensure_ascii=False, sort_keys=True)
        if key in texts:
            raise AssertionError(f'{r["id"]} duplicates {texts[key]}')
        texts[key] = r['id']
    return b


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fragments', nargs='+', required=True)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--split', required=True, choices=['evaluation', 'research_development'])
    parser.add_argument('--evidence', type=Path, required=True, help='JSON list of verified evidence IDs')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    b = build(args.fragments, args.split, json.loads(args.evidence.read_text()))
    args.out.mkdir(parents=True, exist_ok=True)
    files = {
        f'{args.prefix}_inputs.jsonl': '\n'.join(json.dumps(r, ensure_ascii=False) for r in b.records) + '\n',
        f'{args.prefix}_scenes.NOT_MODEL_INPUT.json': json.dumps(b.rows, ensure_ascii=False, indent=1) + '\n',
        f'{args.prefix}_reference.NOT_MODEL_INPUT.json': json.dumps(b.oracles, ensure_ascii=False, indent=1) + '\n',
        f'{args.prefix}_review.NOT_MODEL_INPUT.jsonl': '\n'.join(json.dumps(r, ensure_ascii=False) for r in b.reviews) + '\n',
    }
    for name, text in files.items():
        (args.out / name).write_text(text)
    families = {}
    for r in b.records:
        families[r['family']] = families.get(r['family'], 0) + 1
    summary = {'personas': len(b.records), 'scenes': len(b.rows), 'families': families,
               'sha256': {n: hashlib.sha256(t.encode()).hexdigest() for n, t in files.items()},
               'review_status': 'draft_unreviewed (AI authored)', 'model_calls': 0}
    (args.out / f'{args.prefix}_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
