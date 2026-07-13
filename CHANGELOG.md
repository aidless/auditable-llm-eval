# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> Pre-1.0 (v0.x) = pre-release / dev iterations. v1.0.0 = first reproducible, auditable, end-to-end runnable release.

---

## [Unreleased]

### Added
- `specs/scoring-rules.json` — machine-checkable contract for the 10 `reference_check` types + runtime/overclaim detection
- `specs/eval.endpoints.json` — CLI contract for `eval/run_copilot_eval.py`, `verify_copilot_run.py`, `copilot/score_copilot_run_v2.py`
- `specs/test_50.schema.json` — JSON Schema for the benchmark file
- `analysis/001-scorer-runtime-misclassification-fix.md` — why v3c jumped from 63.95% to 69.00%
- `analysis/002-verify-data-model-rewrite.md` — discipline checker re-aligned with actual scorer output shape
- `analysis/003-honesty-pass.md` — why docs were rewritten to match reproducible reality
- `analysis/004-false-green-evidence.md` — both committed runs reproduce 100%-green vs 67–69% real

---

## [1.0.0] - 2026-07-13 — Auditable, Reproducible

### Summary
First release where the headline score (v3c = 69.00%, v3 = 67.00%) is **re-derivable by anyone with a clone of this repo**, in two commands. Pre-1.0 versions had scores from session logs only and were not reproducible from any committed run.

### Added
- `outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl` — 50-task benchmark (5 task types × 10 each), each with `reference_checks`
- `outputs/llm-lab/datasets/llm_lab_copilot/runs/20260713-211540-copilot-3b-lora-v3c/` — committed v3c run (69.00%)
- `outputs/llm-lab/datasets/llm_lab_copilot/runs/20260713-213920-copilot-3b-lora-v3/` — committed v3 control run (67.00%)
- `eval/run_copilot_eval.py` — entry-point: runs a model on `test_50`, produces outputs/verdicts/report/summary/config
- `copilot/score_copilot_run_v2.py` — authoritative scorer (10 check types; runtime/overclaim detectors; length-guard + harness-error trust after 001 fix)
- `verify_copilot_run.py` — discipline checker (7 checks: outputs integrity, verdict alignment, scorer re-run, tamper audit, config pinning)
- `outputs/llm-lab/REPORT.md` — truthful technical report (headline numbers from disk, not session logs)
- `outputs/llm-lab/README.md` — portal with honest status box (✅ 已可复现)
- `outputs/llm-lab/docs/GETTING_STARTED.md` — beginner guide (no-GPU quick start in 1 min; full training chain with hardcoded-path notes)
- `outputs/llm-lab/docs/blog/001-auditable-llm-eval-no-green-lights.md` — falsifiable story (the dropped-session arc now lives as "motivation, not result")
- `LICENSE` — MIT, copyright `aidless`
- `llm-lab-opensource.zip` — self-contained release asset (benchmark + both runs + training chain + training data)

### Fixed
- **scorer runtime misclassification** ([`analysis/001`](./analysis/001-scorer-runtime-misclassification-fix.md)) — `classify_runtime()` was flagging correct failure-diagnosis answers as `runtime_error`, dropping them from the real score. Added length guard (≥ 200 chars = real diagnosis, not harness echo) + prefer harness-recorded error field. v3c jumped from 63.95% → 69.00%.
- **verify script data-model mismatch** ([`analysis/002`](./analysis/002-verify-data-model-rewrite.md)) — `verify_copilot_run.py` was reading `summary.json` as JSONL and `report.jsonl` rows as if `exact_checks` was a list. Rewrote against actual scorer output shape; all 7 sections now PASS.

### Documentation honesty pass
- Headline numbers corrected from session-log (7.59% / 77.69%) to committed-run (67% / 69%)
- Dropped-session arc demoted from "result" to "motivation" in the blog
- README portal honest-status hedge retired (the hedge was correct while docs were not yet self-verifying)

---

## [0.5.0] - 2026-07-12 — Copilot Prompt v3.2 (pre-test_50)

Pre-release iteration: prompt engineering on a different dataset (`few_shot_v3.2.jsonl`, 123 checks). Final scores (87.80% on 7B, 82.11% on 3B, 68.29% on v2-LoRA) are **from this dataset, not from `test_50`**, so they are not directly comparable to v1.0.0 numbers.

### Added
- Few-shot prompt versions v1 / v2 / v3 / v3.1 / v3.2 / v3.2.1 (see `COPILOT_RETROSPECTIVE.md` §2 timeline)
- `copilot/score_copilot_run_v2.py` original (with the buggy `classify_runtime` fixed later in v1.0.0)
- 3B QLoRA fine-tuning chain (`train_copilot_3b_v3c.py`, `merge_clean_v3c_local.py`, `Modelfile_copilot3c`)

### Known issues (resolved in v1.0.0)
- Scorer tamper-proof detector was substring-only, not negation-aware → fixed by `TAMPER_PROOF_PHRASES` + `denied_before()` (see `COPILOT_RETROSPECTIVE.md` §3.2)
- Naive verdicts passed everything; no discipline layer → resolved by adding `verify_copilot_run.py`

---

## [0.1.0 - 0.4.0] - 2026-07-10 to 2026-07-12 — M0-M3 Pipeline

RTX 3060 6GB QLoRA scaffolding, training troubleshooting, M0-M3 stage gating. See `EXECUTION_PLAN.md` / `RUN_GUIDE.md` / `TRAINING_TROUBLESHOOTING.md` / `M2_CONFIG_REVIEW.md` / `qwen25-3b-tmlr-finetune-plan.md` for the original pipeline design.

These versions are **pre-dataset** and pre-benchmark. The training pipeline is preserved in this repo (root: `train_copilot_3b_*.py`, `merge_clean*.py`, `Modelfile_*`) for users who want to retrain and contribute new model variants, but no trained weights are shipped (intentional — see "Honest caveats" in `outputs/llm-lab/REPORT.md`).

---

## 🪞 Source Documents (full detail)

This CHANGELOG.md is a curated summary. The full original documents are preserved in the repo root and remain authoritative for their respective domains:

| file | role |
|---|---|
| [`COPILOT_RETROSPECTIVE.md`](./COPILOT_RETROSPECTIVE.md) | Pre-v1.0 prompt-engineering evolution timeline (v1 → v3.2) + 3B LoRA first attempts |
| [`COPILOT_NEXT_STEPS.md`](./COPILOT_NEXT_STEPS.md) | Pre-v1.0 next-step proposals based on v3.2 baseline (87.80%) |
| [`EXECUTION_PLAN.md`](./EXECUTION_PLAN.md) | RTX 3060 6GB M0→M3 end-to-end execution plan |
| [`M2_CONFIG_REVIEW.md`](./M2_CONFIG_REVIEW.md) | 3B LoRA default-parameter audit vs plan §3 |
| [`NEXT_STEPS_PLAN.md`](./NEXT_STEPS_PLAN.md) | Pre-v1.0 plan: "评估闭环优先, 不贸然训练" |
| [`RUN_GUIDE.md`](./RUN_GUIDE.md) | M0→M3 monitoring checklist with expected outputs |
| [`RUN_LOG.md`](./RUN_LOG.md) | Run-log template (per-stage timing + VRAM peak) |
| [`TRAINING_TROUBLESHOOTING.md`](./TRAINING_TROUBLESHOOTING.md) | Common RTX 3060 6GB QLoRA failure modes |
| [`qwen25-3b-tmlr-finetune-plan.md`](./qwen25-3b-tmlr-finetune-plan.md) | Original full fine-tuning plan (model selection, hyperparameters, dataset design) |
| [`RELEASE_NOTES_v1.0.md`](./RELEASE_NOTES_v1.0.md) | Copy-paste body for the GitHub Releases page |

---

## 📜 Versioning Policy

- **MAJOR**: headline number from a different dataset / scoring rule (so old numbers are not directly comparable).
- **MINOR**: a new committed run, a new benchmark, a new spec contract, or a new analysis.
- **PATCH**: a fix that does not change reproducible numbers (bug fix in scripts without changing semantics of existing checks).

A change to `specs/*.json` requires a **MINOR** bump. A change to `outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl` requires a **MAJOR** bump (old runs are no longer comparable).

[Unreleased]: https://github.com/aidless/auditable-llm-eval/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/aidless/auditable-llm-eval/releases/tag/v1.0.0
[0.5.0]: https://github.com/aidless/auditable-llm-eval/releases/tag/v0.5.0
[0.1.0 - 0.4.0]: https://github.com/aidless/auditable-llm-eval/releases/tag/v0.4.0