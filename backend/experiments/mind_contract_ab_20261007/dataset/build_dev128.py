"""Build the 128-input development set: 32 roots x (original + 3 derived forms).

Every derived form is an AI-authored draft (review_status=draft_unreviewed). The
authored reference rule must reproduce every authored scene expectation through
the same typed evaluator; that is an internal-coherence check only, not proof
that the Korean text means what the reference says. Labels never enter the
model-input file. Derived forms stay with their root (lineage) for splitting.

Run:  python -m experiments.mind_contract_ab_20261007.dataset.build_dev128 --out DIR
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

from app.llm import mind_policy as m
from experiments.mind_contract_ab_20261007 import scoring
from experiments.mind_policy_candidates import condition_program as v4
from experiments.mind_policy_candidates import note_policy_eval as ev

HERE = Path(__file__).resolve().parent
FORMS = ('original', 'preserve', 'counterfactual', 'hard')
ROLES = ('trigger', 'non_trigger', 'boundary_or_release', 'unobserved_or_conflict')
PLACES = [{'label': '느티공원', 'place_type': 'park'}, {'label': '해든상가', 'place_type': 'market'},
          {'label': '솔빛쉼터', 'place_type': 'park'}]
INTRO = ('등록 장소는 어떤 의미인가요?', '느티공원, 해든상가, 솔빛쉼터는 질문에 나온 후보 이름이에요. 그곳을 좋아하거나 실제로 간다는 뜻은 아니에요.')
FRAGMENTS = ('variants_environment_rest', 'variants_waiting_destination',
             'variants_external_fidelity', 'variants_time_multiple')


def spec(command, condition, ids=('N1',), labels=(), hold=0):
    return {'command': command, 'condition': condition, 'note_ids': list(ids),
            'place_labels': list(labels), 'hold_minutes': hold}


def scene(**kw):
    out = {k: False for k in m.BOOLEAN_FACTS if '.' not in k}
    out.update(current_action='walk', continuous_walk_minutes=0, distance_since_rest_m=0, clock_hour=11,
               map_distance_m={k: 1000 for k in ('market', 'park', 'forest', 'water')},
               noisy=False, crowded=False, current_place_label='등록 장소 밖')
    out.update(kw)
    return out


def nearby(feature, **kw):
    return scene(map_distance_m={**{k: 1000 for k in ('market', 'park', 'forest', 'water')}, feature: 20}, **kw)


def case(role, s, expected, why, status=None, possible=None):
    if role not in ROLES:
        raise ValueError('unknown scene role ' + role)
    return {'role': role, 'scene': s, 'expected_commands': expected,
            'expected_status': status or ('supported' if expected and expected != ['baseline']
                                          else 'no_personal_reaction'),
            'expected_possible_commands': possible, 'rationale': why}


class Builder:
    def __init__(self):
        self.people, self.scenes, self.reference = scoring.load()
        self.records, self.rows, self.oracles, self.reviews = [], [], {}, []

    def _notes(self, qa):
        return [{'id': 'N' + str(i), 'text': '질문: ' + q + '\n답변: ' + a, 'provenance': 'guardian_original',
                 'source_kinds': ['guardian_turn'], 'recorded_at': ['2026-10-01T10:00:00+09:00']}
                for i, (q, a) in enumerate(qa)]

    def originals(self):
        for pid, person in sorted(self.people.items()):
            vid = f'DEV_{pid}_original'
            self.records.append({'id': vid, 'root_id': pid, 'form': 'original', 'split': 'development',
                                 'synthetic': True, 'review_status': 'authored_20261006_results_seen',
                                 'author': 'MIND_diverse_comparison_20261006', 'personal': person['personal']})
            self.oracles[vid] = self.reference[pid]
            for s in (x for x in self.scenes if x['person_id'] == pid):
                self.rows.append({**s, 'id': vid + s['id'][len(pid):], 'input_id': vid, 'root_id': pid, 'role': None})
            self.reviews.append({'id': vid, 'root_id': pid, 'transformation': 'original',
                                 'expected_relation': 'original', 'semantic_changes': '',
                                 'required_scene_checks': [], 'reviewer': None,
                                 'review_status': 'authored_20261006_results_seen'})

    def variant(self, root, form, transformation, relation, qa, rules, cases, semantic_changes,
                checks, prepared=None, places=None):
        if form not in FORMS[1:] or relation not in ('preserve', 'change'):
            raise ValueError('bad form or relation')
        vid = f'DEV_{root}_{form}'
        if any(r['id'] == vid for r in self.records):
            raise ValueError('duplicate ' + vid)
        if root not in self.people:
            raise ValueError('unknown root ' + root)
        personal = {'notes': self._notes(qa), 'places': places or PLACES, 'prepared_initial': prepared or {}}
        used = {n for r in rules for n in r['note_ids']}
        out = {'source_assessment': '수기 참조 규칙. 모델 평가나 임상 근거가 아님.', 'rules': rules,
               'non_action_note_ids': [n['id'] for n in personal['notes'] if n['id'] not in used]}
        policy = v4.compile_note(out, personal, 'ALL')
        if len(cases) != 4 or {c['role'] for c in cases} != set(ROLES):
            raise ValueError(vid + ': need one scene per role ' + str(ROLES))
        for i, item in enumerate(cases):
            row = {'id': f'{vid}_S{i + 1}', 'input_id': vid, 'root_id': root, 'person_id': vid,
                   'family': self.people[root]['family'], **item}
            decision = ev.decide(policy, personal, item['scene'])
            if not scoring.scene_pass(decision, row):
                raise AssertionError(f'{row["id"]}: reference gives {decision}, authored {item}')
            self.rows.append(row)
        self.records.append({'id': vid, 'root_id': root, 'form': form, 'split': 'development', 'synthetic': True,
                             'review_status': 'draft_unreviewed', 'author': 'AI draft (Claude), 2026-10-07',
                             'personal': personal})
        self.oracles[vid] = policy.model_dump()
        self.reviews.append({'id': vid, 'root_id': root, 'transformation': transformation,
                             'expected_relation': relation, 'semantic_changes': semantic_changes,
                             'required_scene_checks': list(checks), 'reviewer': None,
                             'review_status': 'draft_unreviewed', 'model_calls': 0,
                             'clinical_validity_reviewed': False})


def build():
    b = Builder()
    b.originals()
    dsl = SimpleNamespace(variant=b.variant, spec=spec, scene=scene, nearby=nearby, case=case,
                          INTRO=INTRO, PLACES=PLACES)
    for name in FRAGMENTS:
        importlib.import_module(f'experiments.mind_contract_ab_20261007.dataset.{name}').register(dsl)
    by_root = {}
    for r in b.records:
        by_root.setdefault(r['root_id'], set()).add(r['form'])
    missing = {k: sorted(set(FORMS) - v) for k, v in by_root.items() if v != set(FORMS)}
    if missing or len(b.records) != 128:
        raise AssertionError(f'incomplete set: {len(b.records)} inputs, missing {missing}')
    texts = {}
    for r in b.records:
        key = json.dumps(r['personal']['notes'], ensure_ascii=False, sort_keys=True)
        if key in texts:
            raise AssertionError(f'{r["id"]} duplicates {texts[key]}')
        texts[key] = r['id']
    return b


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    b = build()
    args.out.mkdir(parents=True, exist_ok=True)
    files = {
        'dev128_inputs.jsonl': '\n'.join(json.dumps(r, ensure_ascii=False) for r in b.records) + '\n',
        'dev128_scenes.NOT_MODEL_INPUT.json': json.dumps(b.rows, ensure_ascii=False, indent=1) + '\n',
        'dev128_reference.NOT_MODEL_INPUT.json': json.dumps(b.oracles, ensure_ascii=False, indent=1) + '\n',
        'dev128_review.NOT_MODEL_INPUT.jsonl': '\n'.join(json.dumps(r, ensure_ascii=False) for r in b.reviews) + '\n',
    }
    for name, text in files.items():
        (args.out / name).write_text(text)
    summary = {'inputs': len(b.records), 'roots': len({r['root_id'] for r in b.records}),
               'scenes': len(b.rows), 'derived_drafts_unreviewed': sum(r['form'] != 'original' for r in b.records),
               'sha256': {n: hashlib.sha256(t.encode()).hexdigest() for n, t in files.items()},
               'independent_people': 'no: 32 root lineages; derived forms are not new people',
               'model_calls': 0}
    (args.out / 'dev128_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
