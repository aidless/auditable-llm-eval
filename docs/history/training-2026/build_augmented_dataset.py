# -*- coding: utf-8 -*-
"""
Build augmented training set for 3B QLoRA v3.

Step 1: validate every YAML-bearing record in train_seed_200.jsonl via yaml.safe_load.
Step 2: craft 10 eval_yaml_generation examples from few_shot_v3.2.jsonl (yaml_001..010),
        each validated against its reference_checks.
Step 3: emit train_seed_200_clean.jsonl (validated original, 200) and
        train_seed_200_aug.jsonl (clean + 10 augmented = 210).

Run: F:\train_env\Scripts\python.exe build_augmented_dataset.py
"""
import json, yaml, re, sys

SRC = "train_seed_200.jsonl"
CLEAN = "train_seed_200_clean.jsonl"
AUG = "train_seed_200_aug.jsonl"

INSTR = "根据用户需求生成 llm-lab eval.yaml。"

# ── helpers ────────────────────────────────────────────────
def parse_yaml(text):
    """Return (ok, dict_or_None). Handles fenced ```yaml and bare YAML."""
    cands = [text]
    if "```" in text:
        cands += text.split("```")[1::2]
    for c in cands:
        c = c.strip()
        if c.lower().startswith("yaml"):
            c = c[4:].strip()
        try:
            p = yaml.safe_load(c)
            if isinstance(p, dict):
                return True, p
        except Exception:
            pass
    return False, None

def rec_yaml(r):
    """Is this record's output intended to be YAML? (heuristic)"""
    o = str(r.get("output", ""))
    return any(h in o for h in
               ["name:", "verifier:", "models:", "failure_type:",
                "type: structural", "dataset:", "prompts:"])

# ── Step 1: validate source ───────────────────────────────
rows = [json.loads(l) for l in open(SRC, encoding="utf-8") if l.strip()]
n_yaml = n_bad = 0
for i, r in enumerate(rows):
    if rec_yaml(r):
        ok, _ = parse_yaml(str(r["output"]))
        n_yaml += 1
        if not ok:
            n_bad += 1
            print("  [WARN] yaml record fails parse: idx", i)
print(f"[Step1] total={len(rows)} yaml_records={n_yaml} yaml_failures={n_bad}")
assert n_bad == 0, "source has broken YAML — abort (should be 0)"

# ── Step 2: 10 augmented eval_yaml examples ───────────────
# Each: (id, input_user_request, yaml_str, reference_checks)
AUG_SPECS = [
    ("yaml_001",
     "比较 deepseek-r1:7b 和 qwen3:4b，在 5 条问题上跑 structural verifier。",
     """name: exact_provider_compare
models:
  - id: deepseek_r1_7b
    provider: ollama
    model: deepseek-r1:7b
    base_url: http://localhost:11434
    timeout_sec: 240
    params:
      temperature: 0
  - id: qwen3_4b
    provider: ollama
    model: qwen3:4b
    base_url: http://localhost:11434
    timeout_sec: 240
    params:
      temperature: 0
prompts:
  - id: p001
    input: Explain why trace logs help reproducibility.
  - id: p002
    input: What is the capital of Peru?
  - id: p003
    input: How do you say hello in Spanish?
  - id: p004
    input: What is the chemical symbol for water?
  - id: p005
    input: Summarize the purpose of an evidence package.
verifier:
  type: structural
  checks:
    non_empty: true
    min_chars: 30
    max_chars: 1200
""",
     {"must_parse_yaml": True, "required_keys": ["name", "models", "verifier"],
      "required_models": ["deepseek-r1:7b", "qwen3:4b"], "required_providers": ["ollama"]}),

    ("yaml_002",
     "比较两个 OpenAI-compatible 本地服务，要求回答提到 trace 或 verifier。",
     """name: openai_compatible_compare
models:
  - id: local_server_a
    provider: openai_compatible
    model: local-model-a
    base_url: http://localhost:1234/v1
    timeout_sec: 180
    params:
      temperature: 0
  - id: local_server_b
    provider: openai_compatible
    model: local-model-b
    base_url: http://localhost:5678/v1
    timeout_sec: 180
    params:
      temperature: 0
prompts:
  - id: p001
    input: Explain how a trace log helps reproducibility.
  - id: p002
    input: Why is a structural verifier useful for eval?
verifier:
  type: structural
  checks:
    non_empty: true
    min_chars: 30
    max_chars: 1200
    any_keywords: ["trace", "verifier"]
""",
     {"must_include_any_keywords": True, "must_parse_yaml": True,
      "required_providers": ["openai_compatible"]}),

    ("yaml_003",
     "用 qwen3:4b 跑 real_eval_questions.jsonl 前 20 条，temperature=0。",
     """name: qwen3_dataset_eval
models:
  - id: qwen3_4b
    provider: ollama
    model: qwen3:4b
    base_url: http://localhost:11434
    timeout_sec: 240
    params:
      temperature: 0
dataset:
  path: real_eval_questions.jsonl
  limit: 20
  id_field: id
  input_field: input
verifier:
  type: structural
  checks:
    non_empty: true
    min_chars: 30
    max_chars: 1200
""",
     {"must_parse_yaml": True, "required_dataset_limit": 20,
      "required_keys": ["dataset", "models", "verifier"],
      "required_params": {"temperature": 0}}),

    ("yaml_004",
     "设计一个会触发 provider error 的 Ollama 配置，用于测试 errors.jsonl。",
     """name: trigger_provider_error
models:
  - id: ollama_flaky
    provider: ollama
    model: nonexistent-model-xyz
    base_url: http://localhost:11434
    timeout_sec: 5
    params:
      temperature: 0
prompts:
  - id: p001
    input: Generate a detailed explanation of quantum computing.
verifier:
  type: structural
  checks:
    non_empty: true
    min_chars: 10
""",
     {"must_have_short_timeout": True, "must_not_hide_errors": True,
      "must_parse_yaml": True, "required_providers": ["ollama"]}),

    ("yaml_005",
     "比较两个 OpenAI-compatible 本地服务，要求回答提到 trace 或 verifier。",
     """name: openai_compatible_compare_two
models:
  - id: svc_a
    provider: openai_compatible
    model: local-model-a
    base_url: http://localhost:1234/v1
    timeout_sec: 180
    params:
      temperature: 0
  - id: svc_b
    provider: openai_compatible
    model: local-model-b
    base_url: http://localhost:1234/v1
    timeout_sec: 180
    params:
      temperature: 0
prompts:
  - id: p001
    input: Describe what a trace log records during an eval run.
  - id: p002
    input: What does a structural verifier actually guarantee?
verifier:
  type: structural
  checks:
    non_empty: true
    min_chars: 30
    max_chars: 1200
    any_keywords: ["trace", "verifier"]
""",
     {"must_include_any_keywords": True, "must_parse_yaml": True,
      "required_providers": ["openai_compatible"]}),

    ("yaml_006",
     "生成评估 report summary 的配置，要求答案提醒 structural verifier 的限制。",
     """name: report_summary_with_verifier_limitation
models:
  - id: local_server_a
    provider: openai_compatible
    model: local-model-a
    base_url: http://localhost:1234/v1
    timeout_sec: 180
    params:
      temperature: 0
prompts:
  - id: p001
    input: Summarize the current run and note the limits of the structural verifier.
verifier:
  type: structural
  checks:
    non_empty: true
    min_chars: 40
    max_chars: 1500
    any_keywords: ["structural", "surface", "semantic", "limitation"]
""",
     {"must_include_warning_keyword_check": True, "must_parse_yaml": True,
      "required_keys": ["name", "models", "verifier"]}),

    ("yaml_007",
     "生成 failure diagnosis 任务的评估配置，要求输出包含原因和建议。",
     """name: failure_diagnosis_eval
models:
  - id: local_server_a
    provider: openai_compatible
    model: local-model-a
    base_url: http://localhost:1234/v1
    timeout_sec: 180
    params:
      temperature: 0
prompts:
  - id: p001
    input: Diagnose this verifier failure and suggest a fix.
verifier:
  type: structural
  checks:
    non_empty: true
    min_chars: 40
    max_chars: 1500
    any_keywords: ["failure", "diagnosis", "provider", "error", "config", "dataset"]
""",
     {"must_include_any_keywords": True, "must_include_min_chars": True,
      "must_parse_yaml": True}),

    ("yaml_008",
     "生成 eval.yaml 生成任务的评估配置，输出必须包含 name/models/verifier 字段。",
     """name: eval_yaml_generation_eval
models:
  - id: local_server_a
    provider: openai_compatible
    model: local-model-a
    base_url: http://localhost:1234/v1
    timeout_sec: 180
    params:
      temperature: 0
prompts:
  - id: p001
    input: Generate an eval.yaml for two models.
verifier:
  type: structural
  checks:
    non_empty: true
    min_chars: 30
    max_chars: 1200
""",
     {"must_include_all_keywords": ["name:", "models:", "verifier:"],
      "must_parse_yaml": True}),

    ("yaml_009",
     "用 Ollama 比较 3 个模型，要求每个调用 timeout_sec 至少 180。",
     """name: ollama_three_model_compare
models:
  - id: model_a
    provider: ollama
    model: qwen3:4b
    base_url: http://localhost:11434
    timeout_sec: 180
    params:
      temperature: 0
  - id: model_b
    provider: ollama
    model: deepseek-r1:7b
    base_url: http://localhost:11434
    timeout_sec: 180
    params:
      temperature: 0
  - id: model_c
    provider: ollama
    model: llama3.1:8b
    base_url: http://localhost:11434
    timeout_sec: 180
    params:
      temperature: 0
prompts:
  - id: p001
    input: Explain why trace logs help reproducibility.
verifier:
  type: structural
  checks:
    non_empty: true
    min_chars: 30
    max_chars: 1200
""",
     {"min_models": 3, "min_timeout_sec": 180, "must_parse_yaml": True,
      "required_providers": ["ollama"]}),

    ("yaml_010",
     "只跑一个 prompt，要求模型解释 evidence package 中 manifest.json 的作用。",
     """name: manifest_explanation_eval
models:
  - id: local_server_a
    provider: openai_compatible
    model: local-model-a
    base_url: http://localhost:1234/v1
    timeout_sec: 180
    params:
      temperature: 0
prompts:
  - id: p001
    input: Explain the purpose of manifest.json in an evidence package.
verifier:
  type: structural
  checks:
    non_empty: true
    min_chars: 30
    max_chars: 1200
    any_keywords: ["manifest.json", "evidence package", "purpose"]
""",
     {"must_include_keyword": "manifest.json", "must_parse_yaml": True,
      "required_keys": ["prompts", "verifier"]}),
]

# ── validator against reference_checks ─────────────────────
def validate(rid, ystr, rc):
    ok, d = parse_yaml(ystr)
    errs = []
    if not ok or d is None:
        errs.append("not a YAML dict")
        return errs
    if rc.get("must_parse_yaml") and not ok:
        errs.append("must_parse_yaml failed")
    for k in rc.get("required_keys", []):
        if k not in d:
            errs.append(f"missing required_key {k}")
    if "required_models" in rc:
        blob = json.dumps(d, ensure_ascii=False)
        for m in rc["required_models"]:
            if m not in blob:
                errs.append(f"missing required_model {m}")
    if "required_providers" in rc:
        blob = json.dumps(d, ensure_ascii=False)
        for p in rc["required_providers"]:
            if f'"provider": "{p}"' not in blob:
                errs.append(f"missing required_provider {p}")
    if "required_dataset_limit" in rc:
        lim = (d.get("dataset") or {}).get("limit")
        if not (isinstance(lim, int) and lim >= rc["required_dataset_limit"]):
            errs.append(f"dataset.limit {lim} < {rc['required_dataset_limit']}")
    if "required_params" in rc:
        for m in d.get("models", []):
            for pk, pv in rc["required_params"].items():
                if m.get("params", {}).get(pk) != pv:
                    errs.append(f"model {m.get('id')} params.{pk}!={pv}")
    if "min_models" in rc:
        if len(d.get("models", [])) < rc["min_models"]:
            errs.append(f"models {len(d.get('models',[]))} < {rc['min_models']}")
    if "min_timeout_sec" in rc:
        for m in d.get("models", []):
            if not (isinstance(m.get("timeout_sec"), int) and m["timeout_sec"] >= rc["min_timeout_sec"]):
                errs.append(f"model {m.get('id')} timeout {m.get('timeout_sec')} < {rc['min_timeout_sec']}")
    if rc.get("must_have_short_timeout"):
        tos = [m.get("timeout_sec") for m in d.get("models", [])]
        if not any(isinstance(t, int) and t <= 10 for t in tos):
            errs.append("no short timeout_sec<=10")
    if "required_keys" in rc and "verifier" in rc["required_keys"]:
        if "verifier" not in d:
            errs.append("missing verifier")
    if rc.get("must_include_all_keywords"):
        blob = ystr
        for kw in rc["must_include_all_keywords"]:
            if kw not in blob:
                errs.append(f"missing keyword {kw}")
    if rc.get("must_include_keyword"):
        if rc["must_include_keyword"] not in ystr:
            errs.append(f"missing keyword {rc['must_include_keyword']}")
    if rc.get("must_include_any_keywords"):
        if "any_keywords" not in ystr:
            errs.append("missing any_keywords")
    if rc.get("must_include_min_chars"):
        if "min_chars" not in ystr:
            errs.append("missing min_chars")
    if rc.get("must_include_warning_keyword_check"):
        if "any_keywords" not in ystr:
            errs.append("missing any_keywords for warning check")
    if rc.get("must_not_hide_errors"):
        blob = ystr.lower()
        if "swallow" in blob or "ignore_error" in blob or "hide_error" in blob:
            errs.append("looks like it hides errors")
    return errs

# ── Step 3: emit files ─────────────────────────────────────
aug_records = []
all_ok = True
for rid, uin, ystr, rc in AUG_SPECS:
    errs = validate(rid, ystr, rc)
    if errs:
        all_ok = False
        print(f"  [FAIL] {rid}: {errs}")
    else:
        print(f"  [OK]   {rid}")
    aug_records.append({"input": uin, "instruction": INSTR, "output": ystr.rstrip("\n")})

assert all_ok, "some augmented records failed validation — fix before writing"
assert len(aug_records) == 10

# clean = original (validated). aug = clean + 10
with open(CLEAN, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
with open(AUG, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for r in aug_records:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print(f"\n[Done] wrote {CLEAN} ({len(rows)} records) and {AUG} ({len(rows)+len(aug_records)} records)")
