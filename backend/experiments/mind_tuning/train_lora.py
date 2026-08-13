"""마음 행동 LoRA 학습 — v4.2 데이터셋, HANDOFF_학습조건.md 의 조건을 코드로 강제.

GPU 서버에서 실행한다 (로컬 맥 아님). 조건 구현:
  - chat template: 토크나이저 공식 템플릿을 그대로 적용
  - assistant-only loss: 전체 시퀀스에서 프롬프트 구간(system+user+생성유도 토큰)을
    -100 마스킹 — 템플릿 종류와 무관하게 동작하는 프리픽스 길이 방식
  - metadata 미사용: messages 만 읽는다
  - base: --model 로 받은 체크포인트 (서빙 exaone-base 와 동일해야 함 — HANDOFF)

실행 예 (서버):
  python train_lora.py --model <서빙과_동일한_경로_또는_HF_ID> \
      --train train_first_person.jsonl --val val_first_person.jsonl \
      --out ./exaone-mind-lora
"""
from __future__ import annotations

import argparse
import json

import torch
from torch.utils.data import Dataset


class MindSFT(Dataset):
    def __init__(self, path: str, tokenizer, max_len: int = 1536) -> None:
        self.rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
        self.tok = tokenizer
        self.max_len = max_len

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, i: int):
        msgs = self.rows[i]["messages"]
        # 프롬프트(생성 유도 포함) 길이를 재서 그 구간의 라벨을 -100 마스킹한다.
        prompt_ids = self.tok.apply_chat_template(
            msgs[:-1], add_generation_prompt=True, tokenize=True)
        full_ids = self.tok.apply_chat_template(msgs, tokenize=True)
        full_ids = full_ids[: self.max_len]
        labels = list(full_ids)
        for j in range(min(len(prompt_ids), len(labels))):
            labels[j] = -100
        return {"input_ids": full_ids, "labels": labels}


def collate(batch, pad_id: int):
    n = max(len(b["input_ids"]) for b in batch)
    ids, labels, mask = [], [], []
    for b in batch:
        pad = n - len(b["input_ids"])
        ids.append(b["input_ids"] + [pad_id] * pad)
        labels.append(b["labels"] + [-100] * pad)
        mask.append([1] * len(b["input_ids"]) + [0] * pad)
    return {"input_ids": torch.tensor(ids), "labels": torch.tensor(labels),
            "attention_mask": torch.tensor(mask)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True,
                    help="서빙 exaone-base 와 동일한 체크포인트 (HANDOFF 게이트)")
    ap.add_argument("--train", required=True)
    ap.add_argument("--val", required=True)
    ap.add_argument("--out", default="./exaone-mind-lora")
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--batch", type=int, default=2)
    ap.add_argument("--accum", type=int, default=8)
    ap.add_argument("--qlora", action="store_true",
                    help="4bit 로드 (vLLM 과 GPU 공유 시 VRAM 절약)")
    ap.add_argument("--dora", action="store_true",
                    help="DoRA (use_dora=True) — 소규모 SFT 과적합 완화. "
                         "vLLM 서빙이 DoRA 어댑터를 지원하는지 별도 확인 필요")
    ap.add_argument("--neftune", type=float, default=0.0,
                    help="NEFTune 노이즈 alpha (0=끔, 권장 5)")
    ap.add_argument("--code-revision", default="0ff6b5ec7c13b049b253a16a889aa269e6b79a94",
                    help="EXAONE 원격 코드 고정 — 서버 vLLM 과 동일 (최신 원격 코드는 "
                         "transformers 4.56 과 비호환: RopeParameters ImportError)")
    a = ap.parse_args()

    from peft import LoraConfig, get_peft_model
    from transformers import (AutoModelForCausalLM, AutoTokenizer, Trainer,
                              TrainingArguments)

    tok = AutoTokenizer.from_pretrained(a.model, trust_remote_code=True,
                                        code_revision=a.code_revision)
    load_kw: dict = {"torch_dtype": torch.bfloat16, "trust_remote_code": True,
                     "code_revision": a.code_revision}
    if a.qlora:
        from transformers import BitsAndBytesConfig
        load_kw["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True)
    model = AutoModelForCausalLM.from_pretrained(a.model, **load_kw)
    model.config.use_cache = False
    # gradient checkpointing + LoRA 조합 필수 — 없으면 backward 에서
    # "element 0 of tensors does not require grad" (베이스가 전부 동결이라
    # 체크포인트 입력에 grad 경로가 안 생김)
    model.enable_input_require_grads()

    lora = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
        use_dora=a.dora,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"])
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    train_ds = MindSFT(a.train, tok)
    val_ds = MindSFT(a.val, tok)
    print(f"train {len(train_ds)} / val {len(val_ds)}")

    args = TrainingArguments(
        output_dir=a.out, num_train_epochs=a.epochs, learning_rate=a.lr,
        per_device_train_batch_size=a.batch, gradient_accumulation_steps=a.accum,
        per_device_eval_batch_size=a.batch, eval_strategy="steps",
        eval_steps=50, logging_steps=10, save_strategy="epoch",
        bf16=True, gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False}, report_to=[],
        lr_scheduler_type="cosine", warmup_ratio=0.03,
        neftune_noise_alpha=(a.neftune if a.neftune > 0 else None),
    )
    pad_id = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    trainer = Trainer(model=model, args=args, train_dataset=train_ds,
                      eval_dataset=val_ds,
                      data_collator=lambda b: collate(b, pad_id))
    trainer.train()
    model.save_pretrained(a.out)
    tok.save_pretrained(a.out)
    print(f"어댑터 저장: {a.out} — vLLM 서빙: --enable-lora --lora-modules exaone-mind={a.out}")


if __name__ == "__main__":
    main()
