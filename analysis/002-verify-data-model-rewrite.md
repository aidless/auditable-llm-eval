# 002 — Verify Script Data-Model Rewrite

**Trigger**: First run of `verify_copilot_run.py` against the v3c committed run produced **false FAIL** on sections [3] and [5] — and the actual failure was in the verifier, not the run.

**Date**: 2026-07-13 (late afternoon)

---

## 🪤 Problem

`verify_copilot_run.py` was written from a **planned** scorer output shape, not the **actual** one. Two mismatches:

### Section [3]: summary.json was read as JSON Lines, not single JSON

```python
# WRONG — assumed jsonl
scores = [json.loads(line) for line in open(summary_path)]
```

But `score_copilot_run_v2.py::run()` writes `summary.json` as a **single JSON object** (one dict, multi-line formatted), not JSONL:

```python
with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)   # single object
```

So `json.loads(line)` would fail on indented multi-line content (or, if the file was on one line by accident, on the `total/semantic_scored/runtime_errors/...` dict vs the expected list shape).

### Section [5]: tamper audit assumed wrong report field shape

```python
# WRONG — assumed flat checks list per row
for row in scores:
    if checks["name"] == "must_not_claim_tamper_proof" and not checks["passed"]:
        ...
```

But `report.jsonl` rows actually look like:

```json
{
  "id": "c001",
  "task": "eval_yaml",
  "exact_checks": {
    "must_include_all_keywords": {"passed": true, "detail": "全部命中"},
    "must_recommend_manual_or_semantic_eval": {"passed": true, "detail": "命中: ['人工']"}
  },
  "soft_checks": {...},
  "unsupported_claims": [],
  "score": 1.0,
  "runtime_error": false
}
```

`exact_checks` is a **dict keyed by check type**, not a list with `name`/`passed` fields. The verifier was reading from a non-existent structure.

---

## 🔍 Diagnosis

1. Read `copilot/score_copilot_run_v2.py` lines 263-298 — confirmed `summary.json` is single-object, `report.jsonl` is per-row dict with `exact_checks` keyed dict.
2. Re-read `verify_copilot_run.py` against the **actual** sample outputs of a real run.
3. Identified two specific section paths that needed rewriting.

---

## 🔧 Fix

### Section [3] rewrite

Don't load summary from disk; instead **call the scorer fresh and read the summary file it just wrote**:

```python
import subprocess, json
# re-run scorer
subprocess.run(["python", scorer, "--tests", dataset,
                "--predictions", f"{run_dir}/outputs.jsonl",
                "--out", "_verify_report.jsonl", "--summary", "_verify_summary.json"], check=True)
# read back the summary it wrote
with open("_verify_summary.json", encoding="utf-8") as f:
    fresh = json.load(f)
assert fresh["overall_reference_check_rate"] == committed["overall_reference_check_rate"]
assert fresh["by_task"] == committed["by_task"]
assert fresh["runtime_errors"] == committed["runtime_errors"]
```

This makes the verify script **authoritative**: it doesn't trust what's in the committed `summary.json`, it re-derives the number from raw outputs.

### Section [5] tamper audit rewrite

```python
# Read committed report.jsonl
import json
report = [json.loads(l) for l in open(f"{run_dir}/report.jsonl", encoding="utf-8") if l.strip()]
# For each row, check all dataset reference_checks are present in exact_checks or soft_checks
for item in test_set:
    row = next(r for r in report if r["id"] == item["id"])
    declared = set(row["exact_checks"]) | set(row["soft_checks"])
    required = {c["type"] for c in item["reference_checks"]}
    missing = required - declared
    assert not missing, f"row {row['id']}: removed check(s) {missing}"
```

This catches silent check removal — if someone tampered with `outputs.jsonl` or `report.jsonl` to drop a check, the audit fires.

### Section [6] (also fixed) — task field alias + reference_checks list vs dict

```python
# WRONG
task_type = rec.get("task_type")
ref_dict = rec.get("reference_checks") or {}

# RIGHT — 'task' (not task_type) and reference_checks is a list
task = rec.get("task")
ref_checks = rec.get("reference_checks") or []
ref_types = {c.get("type") for c in ref_checks}
```

The dataset uses `task` (not `task_type`), and `reference_checks` is a **list of dicts** (not a dict itself).

---

## ✅ Verification

Ran `verify_copilot_run.py` against the v3c run after the rewrite:

```
[1] outputs.jsonl integrity ........ PASS (50/50 non-empty, no errors)
[2] verdicts.jsonl alignment ....... PASS (50 verdicts, matches outputs)
[3] scorer re-run reproduces ....... PASS (overall=0.69, by_task=5 rows match, runtime_errors=0)
[4] summary.json tampering ......... PASS (no mutation)
[5] report.jsonl tamper audit ...... PASS (all 50 rows declare all required check types)
[6] dataset integrity .............. PASS (50 items, all reference_checks present)
[7] config.yaml pinning ............ PASS (model=qwen2.5:3b default, temperature=0)

ALL CHECKS PASSED: 69.00% (50/50 verdicts, 138/200 reference checks pass)
```

Re-ran the same verify against the v3 control run — also PASS (67.00%).

---

## 🧬 Lesson

**Discipline checkers must read the actual contract, not a planned one.** When writing a verifier, always read the producer's code and a real output sample **before** writing the assertion logic. A 5-minute read saves an afternoon of false-negative debugging.

**Section [3] re-running the scorer is the strongest possible test.** It says: "the committed score is recomputable from raw outputs by anyone with the scorer." That's the entire point of reproducibility — anyone reading the repo should be able to re-derive the same number.

---

## 🔗 Links

- Verifier: `verify_copilot_run.py`
- Producer: `copilot/score_copilot_run_v2.py`
- Spec: [`specs/scoring-rules.json`](../specs/scoring-rules.json), [`specs/eval.endpoints.json`](../specs/eval.endpoints.json)
- v3c run: `outputs/llm-lab/datasets/llm_lab_copilot/runs/20260713-211540-copilot-3b-lora-v3c/`