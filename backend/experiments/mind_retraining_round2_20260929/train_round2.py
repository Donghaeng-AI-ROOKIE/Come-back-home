"""Prepared round-two controlled LoRA study; approval required before GPU execution.

Requires explicit --execute and an approved run specification. Uses only local
model/tokenizer files. Parent enforces wall time and records start/end events.
Optional pilot generation is explicitly capped in the approved specification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone


def log(path, event):
    import fcntl
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a') as f:
        fcntl.flock(f.fileno(),fcntl.LOCK_EX)
        f.write(json.dumps({'schema_version':1,'event_id':str(uuid.uuid4()),
                           'recorded_at':datetime.now(timezone.utc).isoformat(),**event},ensure_ascii=False)+'\n')
        f.flush();os.fsync(f.fileno())


def worker(spec):
    from preflight import encode_supervision
    from audit import audit
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, Trainer, TrainerCallback, set_seed
    from peft import LoraConfig, get_peft_model
    root=Path(spec['dataset']);out=Path(spec['out'])
    if audit(root)['errors']:raise ValueError('dataset audit failed')
    if torch.cuda.device_count()!=1:raise ValueError('select exactly one approved GPU')
    free,total=torch.cuda.mem_get_info()
    if free < spec['min_free_gib']*1024**3:raise ValueError('insufficient free VRAM; do not stop serving')
    tok=AutoTokenizer.from_pretrained(spec['model_path'],local_files_only=True,trust_remote_code=True)
    data={}
    for split in ('train','development'):
        rows=[json.loads(x) for x in (root/(split+'.jsonl')).read_text().splitlines() if x]
        data[split]=[encode_supervision(r['messages'],tok,spec['max_tokens']) for r in rows]
    out.mkdir(parents=True,exist_ok=False)
    (out/'token_lengths.json').write_text(json.dumps({k:[len(r['input_ids']) for r in v] for k,v in data.items()}))
    set_seed(spec['seed'])
    model=AutoModelForCausalLM.from_pretrained(spec['model_path'],local_files_only=True,
                                             trust_remote_code=True,torch_dtype=torch.bfloat16)
    model.to('cuda')
    pad=tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    if pad is None:raise ValueError('no padding/eos token')
    dev_rows=[json.loads(x) for x in (root/'development.jsonl').read_text().splitlines() if x]
    generation_attempts=0
    def probe(tag):
        nonlocal generation_attempts
        if not spec.get('development_generation',False):return
        from contract import validate
        model.eval()
        for row in dev_rows:
            if generation_attempts >= spec['generation_attempt_limit']:
                raise ValueError('generation attempt budget exhausted')
            generation_attempts += 1
            attempt=str(uuid.uuid4());common={'attempt_id':attempt,'run_id':spec['run_id'],
               'resource_type':'self_hosted_gpu','role':'mind_lora_development','candidate':tag,
               'case_id':row['id'],'actual_cost':None,'estimated_cost':None,'support_round':None,
               'currency':None,'cost_status':'unconfirmed','tokens_are_not_separate_api_charges':True}
            log(Path(spec['ledger']),{**common,'event_type':'inference_started'})
            start=time.monotonic();usage=None;status='failed';error_type=None
            try:
                ids=tok.apply_chat_template(row['messages'][:-1],add_generation_prompt=True,
                                             tokenize=True,return_tensors='pt').to('cuda')
                with torch.inference_mode():
                    generated=model.generate(input_ids=ids,attention_mask=torch.ones_like(ids),
                         max_new_tokens=spec['generation_max_tokens'],do_sample=False,pad_token_id=pad)
                answer_ids=generated[0,ids.shape[-1]:]
                usage={'input_tokens':int(ids.shape[-1]),'output_tokens':int(answer_ids.shape[-1])}
                raw=tok.decode(answer_ids,skip_special_tokens=True)
                result={'id':row['id'],'candidate':tag,'raw':raw,'usage':usage}
                try:
                    value=json.loads(raw);validate(value,row['context'])
                    expected=row['expected']
                    result['contract_pass']=True
                    result['action_tuple_match']=all(value[k]==expected[k] for k in
                          ('status','action','goal_operation','goal_label','avoid_feature'))
                    result['decoded']=value
                except (ValueError,TypeError):
                    result.update(contract_pass=False,action_tuple_match=False)
                result['reason_semantic_review_complete']=False
                with (out/(tag+'_development.jsonl')).open('a') as f:f.write(json.dumps(result,ensure_ascii=False)+'\n')
                status='response_received'
            except Exception as exc:
                error_type=type(exc).__name__
                raise
            finally:
                log(Path(spec['ledger']),{**common,'event_type':'inference_finished','outcome':status,
                    'usage':usage,'error_type':error_type,'process_elapsed_seconds':time.monotonic()-start})
    model.config.use_cache=False;model.enable_input_require_grads()
    targets=['q_proj','k_proj','v_proj','out_proj','c_fc_0','c_fc_1','c_proj']
    matches={t:sum(1 for n,m in model.named_modules() if n.rsplit('.',1)[-1]==t and isinstance(m,torch.nn.Linear)) for t in targets}
    if any(n!=32 for n in matches.values()):raise ValueError('unexpected EXAONE LoRA target coverage: '+str(matches))
    set_seed(spec['seed'])  # Pin adapter initialization, not only Trainer RNG.
    model=get_peft_model(model,LoraConfig(r=16,lora_alpha=32,lora_dropout=.05,task_type='CAUSAL_LM',target_modules=targets))
    if sum(1 for n,_ in model.named_modules() if n.endswith('lora_A.default'))!=224:
        raise ValueError('LoRA adapter coverage mismatch')
    (out/'lora_target_coverage.json').write_text(json.dumps(matches,indent=2)+'\n')
    def collate(batch):
        n=max(len(x['input_ids']) for x in batch)
        return {'input_ids':torch.tensor([x['input_ids']+[pad]*(n-len(x['input_ids'])) for x in batch]),
                'attention_mask':torch.tensor([x['attention_mask']+[0]*(n-len(x['input_ids'])) for x in batch]),
                'labels':torch.tensor([x['labels']+[-100]*(n-len(x['input_ids'])) for x in batch])}
    args=TrainingArguments(output_dir=str(out),num_train_epochs=spec['epochs'],learning_rate=1e-4,
       per_device_train_batch_size=1,gradient_accumulation_steps=4,per_device_eval_batch_size=1,
       bf16=True,gradient_checkpointing=True,gradient_checkpointing_kwargs={'use_reentrant':False},
       eval_strategy='epoch',save_strategy='epoch',save_total_limit=6,logging_steps=1,
       lr_scheduler_type='constant',warmup_ratio=0,seed=spec['seed'],data_seed=spec['seed'],report_to=[],
       dataloader_num_workers=0)
    class ProbeCheckpoints(TrainerCallback):
        def on_save(self, args, state, control, **kwargs):
            epoch=int(round(state.epoch))
            if epoch not in spec['probe_epochs']:
                return control
            import random
            import numpy as np
            py_rng=random.getstate();np_rng=np.random.get_state()
            was_training=model.training;was_checkpointing=model.is_gradient_checkpointing
            cache=model.config.use_cache
            try:
                with torch.random.fork_rng(devices=[torch.cuda.current_device()]):
                    model.gradient_checkpointing_disable();model.config.use_cache=True
                    probe('epoch_'+str(epoch))
            finally:
                random.setstate(py_rng);np.random.set_state(np_rng)
                model.config.use_cache=cache
                if was_checkpointing:
                    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
                model.train(was_training)
            return control
    trainer=Trainer(model=model,args=args,train_dataset=data['train'],eval_dataset=data['development'],data_collator=collate,
                    callbacks=[ProbeCheckpoints()])
    trainer.train();trainer.save_state();model.save_pretrained(out/'final');tok.save_pretrained(out/'final')
    model.gradient_checkpointing_disable();model.config.use_cache=True
    if generation_attempts != spec['generation_attempt_limit']:
        raise ValueError('checkpoint probe count incomplete')
    (out/'completed.json').write_text(json.dumps({'training_completed':True,'selected_for_deployment':False,
       'gpu':torch.cuda.get_device_name(0),'total_vram_bytes':total,'peak_allocated_bytes':torch.cuda.max_memory_allocated(),
       'spec':spec},ensure_ascii=False,indent=2)+'\n')


def validate_round2_spec(spec):
    if spec.get('epochs')!=6 or spec.get('probe_epochs')!=[2,4,6]:
        raise ValueError('fixed six-epoch trajectory with 2/4/6 checkpoint probes required')
    if spec.get('seed')!=928 or spec.get('learning_rate')!=1e-4 or spec.get('scheduler')!='constant':
        raise ValueError('controlled seed/learning-rate settings required')
    if not 1 <= spec.get('wall_seconds',0) <= 1200:
        raise ValueError('per-run wall budget exceeds 20 minutes')
    if spec.get('generation_attempt_limit')!=48 or spec.get('generation_max_tokens')!=900:
        raise ValueError('per-run generation cap must be 48 attempts x 900 tokens')
    if spec.get('development_generation') is not True:
        raise ValueError('checkpoint behavioral comparison is required')
    if spec.get('dataset_kind') not in ('original72','augmented120'):
        raise ValueError('unrecognized dataset arm')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--spec',required=True);ap.add_argument('--execute',action='store_true')
    ap.add_argument('--worker',action='store_true');a=ap.parse_args();spec=json.loads(Path(a.spec).read_text())
    if not a.execute:raise SystemExit('preparation only: explicit --execute and approval required')
    if spec.get('approval_status')!='approved' or not spec.get('approval_reference'):
        raise SystemExit('concrete approval reference required')
    for key in ('model_path','dataset','out','ledger'):
        if not Path(spec[key]).is_absolute():raise ValueError('absolute path required: '+key)
    if not Path(spec['model_path']).is_dir():raise ValueError('existing local model path required')
    validate_round2_spec(spec)
    if spec.get('development_generation',False):
        if not 1<=spec['generation_max_tokens']<=900:raise ValueError('generation token ceiling exceeded')
        if spec.get('generation_attempt_limit')!=48:raise ValueError('explicit generation budget 48 required')
        rows=[x for x in (Path(spec['dataset'])/'development.jsonl').read_text().splitlines() if x]
        if len(rows)*3!=48:raise ValueError('development budget changed')
    manifest=Path(spec['dataset'])/'manifest.json'
    if hashlib.sha256(manifest.read_bytes()).hexdigest()!=spec['manifest_sha256']:raise ValueError('manifest changed')
    inventory=Path(spec.get('runtime_inventory_path',''))
    if not inventory.is_file() or hashlib.sha256(inventory.read_bytes()).hexdigest()!=spec.get('runtime_inventory_sha256'):
        raise ValueError('runtime inventory file/hash missing or changed')
    if a.worker:worker(spec);return
    if Path(spec['out']).exists():raise ValueError('new experiment output directory required')
    if not spec.get('runtime_inventory_sha256'):raise ValueError('pin model/code/tokenizer/library inventory first')
    ledger=Path(spec['ledger']);run=str(uuid.uuid4());spec['run_id']=run;start=time.monotonic()
    runtime_spec=Path(spec['out']).parent/(run+'.run_spec.json')
    runtime_spec.parent.mkdir(parents=True,exist_ok=True)
    runtime_spec.write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n')
    common={'run_id':run,'role':'mind_lora_round2_training','resource_type':'self_hosted_gpu',
            'model':'LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct','actual_cost':None,'estimated_cost':None,
            'gpu_billed_hours':None,'support_round':None,'currency':None,'cost_status':'unconfirmed',
            'dataset_manifest_sha256':spec['manifest_sha256']}
    log(ledger,{**common,'event_type':'training_started'})
    outcome='failed';code=None;proc=None
    try:
        env={**os.environ,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','WANDB_DISABLED':'true'}
        proc=subprocess.Popen([sys.executable,__file__,'--spec',str(runtime_spec),'--execute','--worker'],
                              env=env,start_new_session=True)
        try:
            code=proc.wait(timeout=spec['wall_seconds']);outcome='completed' if code==0 else 'failed'
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGKILL);proc.wait();outcome='wall_budget_exhausted'
    finally:
        if proc is not None and proc.poll() is None:
            os.killpg(proc.pid,signal.SIGKILL);proc.wait()
            outcome='interrupted'
        log(ledger,{**common,'event_type':'training_finished','outcome':outcome,'exit_code':code,
                    'process_elapsed_seconds':time.monotonic()-start,
                    'elapsed_is_not_gpu_billing_time':True})
    if outcome!='completed':raise SystemExit(outcome)


if __name__=='__main__':main()
