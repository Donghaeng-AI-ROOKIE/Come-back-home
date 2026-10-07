"""Tokenizer-only preparation. Explicit local tokenizer path; never downloads models.

This does not run inference or training. Run on the approved server only after
the server preparation scope is confirmed. Length checks reject, never truncate.
"""
import argparse
import hashlib
import json
from pathlib import Path


def encode_supervision(messages, tokenizer, max_tokens):
    if len(messages)!=3 or [m['role'] for m in messages]!=['system','user','assistant']:
        raise ValueError('expected_one_answer_conversation')
    # Preserve the exact generation prefix: joint BPE can merge its final
    # character with the first answer character. Encode the answer separately.
    prompt_text=tokenizer.apply_chat_template(messages[:-1],add_generation_prompt=True,tokenize=False)
    full_text=tokenizer.apply_chat_template(messages,tokenize=False)
    if not full_text.startswith(prompt_text):
        raise ValueError('chat_template_prefix_mismatch')
    answer_text=full_text[len(prompt_text):]
    prompt=tokenizer.apply_chat_template(messages[:-1],add_generation_prompt=True,tokenize=True)
    answer=tokenizer.encode(answer_text,add_special_tokens=False)
    if not answer or not messages[-1]['content']:
        raise ValueError('no_supervised_tokens')
    full=prompt+answer
    if tokenizer.decode(full,skip_special_tokens=False,clean_up_tokenization_spaces=False)!=full_text:
        raise ValueError('tokenization_text_roundtrip_mismatch')
    if len(full)>max_tokens:
        raise ValueError(f'answer_would_be_truncated:{len(full)}>{max_tokens}')
    return {'input_ids':full,'labels':[-100]*len(prompt)+answer,
            'attention_mask':[1]*len(full)}



def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--dataset',required=True)
    ap.add_argument('--tokenizer-path',required=True)
    ap.add_argument('--max-tokens',type=int,default=4096)
    ap.add_argument('--out',required=True)
    a=ap.parse_args()
    path=Path(a.tokenizer_path)
    if not path.is_dir():raise SystemExit('local tokenizer directory required')
    out=Path(a.out)
    if out.exists():raise SystemExit('refusing overwrite')
    from transformers import AutoTokenizer
    tok=AutoTokenizer.from_pretrained(str(path),local_files_only=True,trust_remote_code=False)
    root=Path(a.dataset);manifest=json.loads((root/'manifest.json').read_text())
    result={'max_tokens':a.max_tokens,'local_files_only':True,'encoding_method':'generation_prefix_plus_answer_tokens','inference_calls':0,'files':{},'errors':[]}
    out.mkdir(parents=True)
    for name,entry in manifest['files'].items():
        blob=(root/name).read_bytes()
        if hashlib.sha256(blob).hexdigest()!=entry['sha256']:raise ValueError('dataset hash mismatch')
        rows=[json.loads(x) for x in blob.decode().splitlines() if x]
        encoded=[];lengths=[];targets=[]
        for r in rows:
            try:
                item=encode_supervision(r['messages'],tok,a.max_tokens)
                lengths.append(len(item['input_ids']));targets.append(sum(v!=-100 for v in item['labels']))
                encoded.append({'id':r['id'],**item})
            except ValueError as e:result['errors'].append({'id':r['id'],'error':str(e)})
        result['files'][name]={'records':len(rows),'encoded':len(encoded),'max_length':max(lengths,default=None),
                              'min_target_tokens':min(targets,default=None)}
        # Any rejected example prevents silently training on a selected subset.
        if len(encoded)==len(rows):
            (out/name).write_text('\n'.join(json.dumps(x) for x in encoded)+'\n')
    result['status']='FAIL' if result['errors'] else 'PASS'
    (out/'tokenization_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    if result['errors']:raise SystemExit('preflight failed; do not train on partial outputs')


if __name__=='__main__':main()
