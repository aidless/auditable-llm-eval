"""
3B QLoRA fine-tune for llm-lab-copilot eval_yaml generation.
Pure transformers + bitsandbytes — NO unsloth, NO triton (Windows-compatible).

=== 安装（已有 torch 2.6.0+cu124 则跳过第一步）===
  F:\train_env\Scripts\python.exe -m pip install torch==2.6.0+cu124 torchvision==0.21.0+cu124 --index-url https://download.pytorch.org/whl/cu124
  F:\train_env\Scripts\python.exe -m pip install transformers trl peft accelerate bitsandbytes datasets

=== 跑训练 ===
  set HF_HOME=F:/hf_cache
  F:\train_env\Scripts\python.exe train_copilot_3b.py
"""
import os, sys, json, torch, gc
from datetime import datetime

# ── Config ──────────────────────────────────────────────
MODEL_ID      = "Qwen/Qwen2.5-Coder-3B-Instruct"
DATA_FILE     = "train_seed_200_aug.jsonl"   # v3: clean(200) + 10 eval_yaml aug
OUTPUT_DIR    = "outputs/copilot_3b_lora_v3"
EPOCHS        = 1          # v3: 1 epoch to reduce catastrophic forgetting (. bug)
BATCH_SIZE    = 2          # standard QLoRA on 6GB: batch=2, accumulate=2 = effective 4
GRAD_ACCUM    = 2
SEQ_LEN       = 2048
LR            = 2e-5       # v3: lower LR (was 5e-5) — gentler update
LORA_R        = 8          # v3: lower rank (was 16) — less intrusion
LORA_ALPHA    = 16         # v3: alpha=r (was 32) — conservative scaling
WARMUP_RATIO  = 0.05
EVAL_SPLIT    = 0.05

os.environ.setdefault("HF_HOME", "F:/hf_cache")

# ── GPU check ───────────────────────────────────────────
print("=" * 60)
gc.collect()
if torch.cuda.is_available():
    torch.cuda.empty_cache()
    total_mb = torch.cuda.get_device_properties(0).total_memory / 1024**2
    free_mb  = total_mb - torch.cuda.memory_allocated(0)/1024**2
    print(f"GPU: {torch.cuda.get_device_name(0)} | {total_mb:.0f}MB total | {free_mb:.0f}MB free")
else:
    print("NO GPU FOUND — aborting"); sys.exit(1)

# ── Load model (4bit via bitsandbytes) ──────────────────
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
)

print(f"Loading {MODEL_ID} ...")
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True,
)
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token
model.config.use_cache = False
model.gradient_checkpointing_enable()
print("Model loaded")

# ── LoRA via PEFT ───────────────────────────────────────
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

model = prepare_model_for_kbit_training(model)
lora_config = LoraConfig(
    r=LORA_R, lora_alpha=LORA_ALPHA, lora_dropout=0.05, bias="none",
    target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],
    task_type="CAUSAL_LM",
)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

# ── Data ────────────────────────────────────────────────
from datasets import Dataset
records = [json.loads(l) for l in open(DATA_FILE, encoding="utf-8")]

def format_chat(r):
    user = r["instruction"]
    if r.get("input"): user += "\n\n" + r["input"]
    return {"text": f"<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n{r['output']}<|im_end|>"}

data = [format_chat(r) for r in records]
ds = Dataset.from_list(data).train_test_split(test_size=EVAL_SPLIT, seed=42)
print(f"Train: {len(ds['train'])} | Eval: {len(ds['test'])}")

# ── Train ───────────────────────────────────────────────
from trl import SFTTrainer
from transformers import TrainingArguments

training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    per_device_train_batch_size=BATCH_SIZE,
    per_device_eval_batch_size=BATCH_SIZE,
    gradient_accumulation_steps=GRAD_ACCUM,
    warmup_ratio=WARMUP_RATIO,
    num_train_epochs=EPOCHS,
    learning_rate=LR,
    fp16=True,
    logging_steps=10,
    eval_strategy="steps", eval_steps=50,
    save_strategy="steps", save_steps=50,
    optim="paged_adamw_8bit", weight_decay=0.01,
    lr_scheduler_type="cosine", seed=42,
    report_to="none",
    save_total_limit=2,
    remove_unused_columns=False,
)

trainer = SFTTrainer(
    model=model, processing_class=tokenizer,
    train_dataset=ds["train"], eval_dataset=ds["test"],
    
    args=training_args,
)

print(f"\nTraining start: {datetime.now().strftime('%H:%M:%S')}")
trainer.train()
print(f"Training done:  {datetime.now().strftime('%H:%M:%S')}")

# ── Save (adapter only; merge via merge_clean.py on CPU) ──
adapter_dir = os.path.join(OUTPUT_DIR, "adapter")
model.save_pretrained(adapter_dir)
tokenizer.save_pretrained(adapter_dir)
print(f"LoRA adapter -> {adapter_dir}")
print("Done. Next: run merge_clean.py for a clean CPU merge, then ollama import.")
