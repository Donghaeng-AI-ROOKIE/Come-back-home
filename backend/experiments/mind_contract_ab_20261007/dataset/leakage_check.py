"""Flag evaluation inputs that are too close to development lineages. No model call.

Two signals, both reported for human review rather than auto-removal:
  text      max character 3-gram Jaccard of guardian answers vs any dev input
  fine      identical reference clauses (fact, operator, value) and command role,
            across all families -> flag (rewrite or move to development)
  coarse    same command roles and fact sets, values ignored -> review only
Fixed 2026-10-07: the first version compared structure only within the same
family name, and the two sets name families differently, so it missed matches.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

TEXT_LIMIT = 0.5


def answers(record):
    return ' '.join(n['text'].split('\n답변: ', 1)[-1] for n in record['personal']['notes'][1:])


def grams(text):
    text = ''.join(text.split())
    return {text[i:i + 3] for i in range(max(0, len(text) - 2))}


def _command(r):
    # Place and goal names differ between sets; compare their role, not the name.
    return (r['action'] + ('_' + r['feature'] if r['feature'] else '')
            + (':goal' if r['goal_label'] else '') + (':scoped' if r['place_labels'] else ''))


def signature(policy):
    """Coarse shape: command role and the set of facts used (no operators/values)."""
    return tuple(sorted((_command(r), tuple(sorted({a['fact'] for c in r['when'] for a in c})))
                        for r in policy['rules']))


def fine_signature(policy):
    """Same command role and identical clauses (fact, operator, value)."""
    return tuple(sorted((_command(r), tuple(sorted(tuple(sorted((a['fact'], a['op'], repr(a['value'])) for a in c))
                                                 for c in r['when'])))
                        for r in policy['rules']))


def check(dev_inputs, dev_reference, dev_family, eval_inputs, eval_reference, eval_family):
    """Family names differ between sets (physical_rest vs rest_endurance), so
    structure is compared across all families. Empty policies (no personal
    rule) are excluded from structure matching; they share a trivial shape."""
    dev_grams = {r['id']: grams(answers(r)) for r in dev_inputs}
    coarse, fine = {}, {}
    for r in dev_inputs:
        ref = dev_reference[r['id']]
        if ref['rules']:
            coarse.setdefault(signature(ref), []).append(r['id'])
            fine.setdefault(fine_signature(ref), []).append(r['id'])
    report = []
    for r in eval_inputs:
        g = grams(answers(r))
        best = max(((len(g & d) / max(1, len(g | d)), i) for i, d in dev_grams.items()), default=(0, None))
        ref = eval_reference[r['id']]
        same_coarse = coarse.get(signature(ref), []) if ref['rules'] else []
        same_fine = fine.get(fine_signature(ref), []) if ref['rules'] else []
        report.append({'id': r['id'], 'family': eval_family[r['id']], 'max_text_jaccard': round(best[0], 3),
                       'nearest_dev': best[1], 'same_coarse_structure_dev': same_coarse[:5],
                       'same_fine_structure_dev': same_fine[:5],
                       'flag': best[0] >= TEXT_LIMIT or bool(same_fine),
                       'review': bool(same_coarse) and not same_fine})
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dev', type=Path, required=True, help='folder with dev128_* files')
    parser.add_argument('--eval', type=Path, required=True, help='folder with eval64_* files')
    args = parser.parse_args()
    load = lambda p: [json.loads(x) for x in p.read_text().splitlines() if x.strip()]  # noqa: E731
    dev = load(args.dev / 'dev128_inputs.jsonl')
    dev_ref = json.loads((args.dev / 'dev128_reference.NOT_MODEL_INPUT.json').read_text())
    dev_family = {s['root_id']: s['family'] for s in json.loads((args.dev / 'dev128_scenes.NOT_MODEL_INPUT.json').read_text())}
    ev = load(args.eval / 'eval64_inputs.jsonl')
    ev_ref = json.loads((args.eval / 'eval64_reference.NOT_MODEL_INPUT.json').read_text())
    ev_family = {r['id']: r['family'] for r in ev}
    report = check(dev, dev_ref, dev_family, ev, ev_ref, ev_family)
    print(json.dumps({'flagged': sum(r['flag'] for r in report), 'coarse_review': sum(r['review'] for r in report),
                      'total': len(report), 'rows': report}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
