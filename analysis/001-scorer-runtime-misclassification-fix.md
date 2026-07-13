# 001 — Scorer Runtime Misclassification Fix

**Trigger**: v3c run real score came back **63.95%** — visibly lower than the expected ~70% range based on prior probe samples.

**Date**: 2026-07-13 (afternoon)

---

## 🪤 Problem

`score_copilot_run_v2.py::classify_runtime(out)` was the source of a silent under-count.

```python
# Original (buggy)
def classify_runtime(out):
    low = (out or "").lower()
    for p in RUNTIME_PATTERNS:
        if re.search(p, low):
            return True
    return False
```

`RUNTIME_PATTERNS` includes `timeout`, `connection refused`, `网络错误`, etc. The classifier was triggering on **legitimate failure-diagnosis answers** (task `c021-c030`) that contain the words "timeout" or "connection refused" as part of correctly diagnosing the failure mode.

When `classify_runtime=True`:
- `score_one()` sets `score=None` (line 222-228)
- `run()` puts that row in `runtime` bucket, not `semantic`
- `overall_reference_check_rate` excludes it from numerator **and** denominator
- Net effect: **correctly-answered diagnostic tasks drop out of the reported pass rate**

In the v3c run, 7 of 50 rows had `runtime_error=True` despite producing legitimate, useful answers — pushing the reported rate down by ~7 points.

---

## 🔍 Diagnosis

Spot-checked `outputs.jsonl` for rows flagged `runtime_error=True`:

| id | task | first 200 chars of output |
|---|---|---|
| c021 | failure_diagnosis | "Provider-side timeout (240s). The API endpoint likely rate-limited..." |
| c022 | failure_diagnosis | "Looks like a connection refused on the host firewall; the model itself..." |
| c024 | failure_diagnosis | "Network timeout. Re-running on a different node should resolve this..." |

These are exactly what `must_distinguish_provider_error` wants to see — **and they were correct answers**.

---

## 🔧 Fix

Two coordinated changes in `copilot/score_copilot_run_v2.py`:

### 1. Length guard in `classify_runtime`

```python
def classify_runtime(out):
    text = (out or "").strip()
    if len(text) >= 200:        # ← new guard
        return False
    low = text.lower()
    for p in RUNTIME_PATTERNS:
        if re.search(p, low):
            return True
    return False
```

**Rationale**: short outputs (< 200 chars) with `timeout` / `connection refused` are harness error echoes (`"Error: connection refused after 240s timeout."`). Long outputs that mention these terms are doing real diagnosis — let them score.

### 2. Prefer harness-recorded error in `score_one`

```python
def score_one(item, pred_text, harness_error=False):
    ...
    runtime_err = bool(harness_error) or classify_runtime(out)   # ← harness first
```

`run()` now passes `herr = bool(pred.get("error"))` so the scorer's runtime flag follows the actual harness verdict when present, with the textual heuristic as fallback.

---

## ✅ Verification

| run | score before fix | score after fix | items w/ runtime_error |
|---|---:|---:|---:|
| v3c (good model) | 63.95% (excluded 7 correct answers) | **69.00%** | 0 |
| v3 (control) | n/a (didn't hit the bug) | **67.00%** | 0 |

Re-ran `--selftest` — all 3 cases still pass.

---

## 🧬 Lesson

**Length-guard heuristics before pattern-match heuristics.** A keyword can mean two opposite things depending on the output's length:
- Short output + "timeout" = harness error
- Long output + "timeout" = failure diagnosis

Same pattern, opposite meaning. Always distinguish with at least one structural feature (length, paragraph count, code-block presence) before flagging.

**Trust the source-of-truth error when present.** The harness can record a real error field. Always read it first; fall back to text heuristics only when absent. This is a general principle: **deterministic signal > probabilistic inference**, whenever the deterministic signal is available.

---

## 🔗 Links

- Spec: [`scoring-rules.json` §global_detectors.runtime_guard](../specs/scoring-rules.json)
- Run: `outputs/llm-lab/datasets/llm_lab_copilot/runs/20260713-211540-copilot-3b-lora-v3c/`
- Diff: `classify_runtime()` + `score_one()` + `run()` in `copilot/score_copilot_run_v2.py`