"""CPU-only verification using pinned local EXAONE tokenizer files; no downloads."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import sys

from build import ARCHIVE, HERE, digest, read_rows, write_json

sys.path.insert(0, str(ARCHIVE / 'evidence/MIND_person_handoff_retraining_20260929'))
from preflight import encode_supervision


def validate(root, tokenizer_path, max_tokens=8192):
    from transformers import AutoTokenizer
    pin = json.loads((HERE / 'tokenizer_pin.json').read_text())
    for name, sha in pin['files'].items():
        if digest((tokenizer_path / name).read_bytes()) != sha:
            raise ValueError('tokenizer_hash_mismatch:' + name)
    tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_path), local_files_only=True, trust_remote_code=False)
    manifest = json.loads((root / 'manifest.json').read_text())
    if set(manifest['files']) != {'train.jsonl', 'train_base.jsonl', 'development.jsonl'}:
        raise ValueError('unexpected_trainer_files')
    report = dict(status='FAIL', tokenizer=pin, max_tokens=max_tokens, files={}, errors=[],
                  encoding_method='generation_prefix_plus_answer_tokens',
                  local_files_only=True, gpu_disabled=True, inference_calls=0, training_runs=0,
                  versions={p: importlib.metadata.version(p) for p in ('transformers', 'tokenizers')})
    for name, entry in manifest['files'].items():
        blob = (root / name).read_bytes()
        if digest(blob) != entry['sha256']:
            raise ValueError('export_hash_mismatch:' + name)
        rows = read_rows(root / name)
        if len(rows) != entry['rows'] or not rows:
            raise ValueError('export_row_count:' + name)
        lengths, supervised = [], []
        for row in rows:
            try:
                if json.loads(row['messages'][-1]['content']) != row['expected_output']:
                    raise ValueError('assistant_label_mismatch')
                encoded = encode_supervision(row['messages'], tokenizer, max_tokens)
                n_prompt = encoded['labels'].count(-100)
                if n_prompt == 0 or encoded['labels'][:n_prompt] != [-100] * n_prompt:
                    raise ValueError('prompt_mask_mismatch')
                if encoded['labels'][n_prompt:] != encoded['input_ids'][n_prompt:]:
                    raise ValueError('answer_mask_mismatch')
                lengths.append(len(encoded['input_ids']))
                supervised.append(len(encoded['input_ids']) - n_prompt)
            except (ValueError, TypeError, KeyError) as exc:
                report['errors'].append(dict(file=name, id=row['id'], error=str(exc)))
        report['files'][name] = dict(rows=len(rows), encoded=len(lengths), sha256=digest(blob),
                                   total_tokens=sum(lengths), supervised_tokens=sum(supervised),
                                   min_tokens=min(lengths, default=None), max_tokens=max(lengths, default=None),
                                   min_answer_tokens=min(supervised, default=None))
    report['status'] = 'FAIL' if report['errors'] else 'PASS'
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=HERE / 'generated/training_export_v3')
    parser.add_argument('--tokenizer-path', required=True, type=Path)
    parser.add_argument('--max-tokens', type=int, default=8192)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit('refusing overwrite')
    result = validate(args.dataset, args.tokenizer_path, args.max_tokens)
    write_json(args.out, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['status'] == 'PASS' else 1)
