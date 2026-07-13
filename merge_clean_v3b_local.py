"""Clean merge v3b: local base snapshot + LoRA adapter -> merge -> save. CPU, no network."""
import torch, os, time
os.environ["HF_HOME"] = "F:/hf_cache"
os.environ["TRANSFORMERS_OFFLINE"] = "1"   # hard-block any network/repo resolution
t0 = time.time()
def log(*a): print(f"[{time.time()-t0:6.1f}s]", *a, flush=True)

from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

BASE = "F:/hf_cache/hub/models--Qwen--Qwen2.5-Coder-3B-Instruct/snapshots/488639f1ff808d1d3d0ba301aef8c11461451ec5"
ADAPTER = "outputs/copilot_3b_lora_v3b/adapter"
OUT = "outputs/copilot_3b_lora_v3b/merged_clean"

log("Loading base (CPU, local snapshot, offline)")
model = AutoModelForCausalLM.from_pretrained(
    BASE, torch_dtype=torch.float16, device_map="cpu",
    offload_folder="F:/offload", low_cpu_mem_usage=True,
)
log("Loading tokenizer (local)")
tokenizer = AutoTokenizer.from_pretrained(BASE)
tokenizer.pad_token = tokenizer.eos_token

log("Loading adapter")
model = PeftModel.from_pretrained(model, ADAPTER)

log("Merging")
model = model.merge_and_unload()

log(f"Saving to {OUT}")
model.save_pretrained(OUT, safe_serialization=True)
tokenizer.save_pretrained(OUT)
log("Done — clean merged model v3b ready for ollama.")
