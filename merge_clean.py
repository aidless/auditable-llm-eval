"""Clean merge: load base fp16 + LoRA adapter → merge → save. Fixed 4bit merge artifacts."""
import torch, os
os.environ["HF_HOME"] = "F:/hf_cache"

from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

BASE = "Qwen/Qwen2.5-Coder-3B-Instruct"
ADAPTER = "outputs/copilot_3b_lora_v3/adapter"
OUT = "outputs/copilot_3b_lora_v3/merged_clean"

print(f"Loading base (CPU, no GPU needed): {BASE}")
model = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.float16, device_map="cpu", offload_folder="F:/offload", trust_remote_code=True)
tokenizer = AutoTokenizer.from_pretrained(BASE, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token

print(f"Loading adapter: {ADAPTER}")
model = PeftModel.from_pretrained(model, ADAPTER)

print("Merging...")
model = model.merge_and_unload()

print(f"Saving to {OUT}")
model.save_pretrained(OUT, safe_serialization=True)
tokenizer.save_pretrained(OUT)
print("Done — clean merged model ready for ollama.")
