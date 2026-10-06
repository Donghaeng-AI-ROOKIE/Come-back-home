"""Flag evaluation inputs that are too close to development lineages. No model call.

Two signals, both reported for human review rather than auto-removal:
  text      max character 3-gram Jaccard of guardian answers vs any dev input
  structure same family and the same set of (command, facts, scope) reference rules
A flagged item must be rewritten or moved to development before the set is frozen.
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


def signature(policy):
    rows = []
    for r in policy['rules']:
        facts = sorted({a['fact'] for clause in r['when'] for a in clause})
        command = r['action'] + ('_' + r['feature'] if r['feature'] else '') + (':' + r['goal_label'] if r['goal_label'] else '')
        rows.append((command, tuple(facts), tuple(sorted(r['place_labels']))))
    return tuple(sorted(rows))


def check(dev_inputs, dev_reference, dev_family, eval_inputs, eval_reference, eval_family):
    dev_grams = {r['id']: grams(answers(r)) for r in dev_inputs}
    dev_sigs = {}
    for r in dev_inputs:
        dev_sigs.setdefault((dev_family[r['root_id']], signature(dev_reference[r['id']])), []).append(r['id'])
    report = []
    for r in eval_inputs:
        g = grams(answers(r))
        best = max(((len(g & d) / max(1, len(g | d)), i) for i, d in dev_grams.items()), default=(0, None))
        same = dev_sigs.get((eval_family[r['id']], signature(eval_reference[r['id']])), [])
        report.append({'id': r['id'], 'max_text_jaccard': round(best[0], 3), 'nearest_dev': best[1],
                       'same_structure_dev': same[:5],
                       'flag': best[0] >= TEXT_LIMIT or bool(same)})
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
    print(json.dumps({'flagged': sum(r['flag'] for r in report), 'total': len(report), 'rows': report},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
