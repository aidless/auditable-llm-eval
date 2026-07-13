# v1.0.0 — Auditable LLM Eval (reproducible)

**Auditable LLM evaluation that catches false-green pass rates — a reproducible copilot benchmark with `reference_checks` + honest scoring.**

---

## Why this exists

Most eval dashboards show a "pass rate." That number is usually a structural mirage.

In our own run, a naive verifier reported **100% pass** (every output was non-empty and long enough). The authoritative scorer told a different story: **~67–69%** real pass rate. The "green lights" were blind to substantive failures — they only checked structure, not whether the answer was actually correct or honest.

This repo is the fix: a benchmark where every task ships with **programmatic `reference_checks`** (including *cognitive-honesty* dimensions — must not claim tamper-proofness, must not overclaim, must warn of structural limits), plus a discipline checker that re-runs the real scorer from disk and surfaces the gap. It is **end-to-end reproducible** from this release.

---

## What's in this release

- **Benchmark** `test_50.jsonl` — 50 tasks across 5 types (`reviewer_qa`, `failure_diagnosis`, `report_summary`, `keyword_audit`, `claim_check`), each with machine-checkable `reference_checks`.
- **Two committed real runs** (fully reproducible from this repo):
  - `runs/20260713-211540-…-v3c` → **69.00%** real pass
  - `runs/20260713-213920-…-v3` → **67.00%** real pass
  - *Both* were reported as **100% green** by the naive verifier — the core lesson, reproducible in one command.
- **Eval scripts** (only Python **standard library** required — no `pip install`):
  - `eval/run_copilot_eval.py` — entry point: runs the model and produces outputs/verdicts/report/summary/config
  - `copilot/score_copilot_run_v2.py` — authoritative scorer (10 check types, honest scoring)
  - `verify_copilot_run.py` — discipline checker: re-runs scorer from disk, asserts the numbers
- **Full training chain** (for GPU users): `train_copilot_3b_v3c.py` → `merge_clean_v3c_local.py` → `Modelfile_copilot3c` (LoRA fine-tune + CPU fp16 merge + Ollama import)
- **Docs**: `REPORT.md`, `README.md` portal, `docs/GETTING_STARTED.md` (beginner guide), `docs/blog/001-…` (the story), `docs/adr/` (design decisions), `docs/LESSONS.md`
- **`llm-lab-opensource.zip`** — self-contained package: benchmark + both runs + all scripts + training chain + training data, **no model weights** (see caveats).

---

## Quick start (beginner-friendly)

You don't need a GPU to see the core lesson.

**1-minute minimum check** — no Ollama install needed, just verify the committed run:
```bash
python verify_copilot_run.py \
  --run-dir outputs/llm-lab/datasets/llm_lab_copilot/runs/20260713-211540-copilot-3b-lora-v3c \
  --dataset outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl \
  --scorer copilot/score_copilot_run_v2.py
```
All 7 checks PASS → the 69.00% is computed from disk, not claimed.

**5-minute experience** — install [Ollama](https://ollama.com), pull any model, watch "100% green vs ~66% real":
```bash
# 1) install Python 3.10+, then Ollama, then:
ollama pull qwen2.5:3b
# 2) run the benchmark:
python eval/run_copilot_eval.py --model qwen2.5:3b
# 3) verify the real score:
python verify_copilot_run.py --run-dir <run_dir_printed_above> \
  --dataset outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl \
  --scorer copilot/score_copilot_run_v2.py
```

**Full training (needs NVIDIA GPU)** — see `docs/GETTING_STARTED.md` §路径 B for step-by-step commands, expected outputs, and the hardcoded-path notes (`BASE` in `merge_clean_v3c_local.py`, `FROM` in `Modelfile_copilot3c`).

---

## Reproducible results (same dataset, same scorer)

| model | naive verdicts | real `reference_check_rate` | notes |
|---|---:|---:|---|
| v3c (LoRA, fixed) | 50/50 (100%) | **69.00%** | honest scoring, 0 overclaims |
| v3 (LoRA, control) | 50/50 (100%) | **67.00%** | same naive 100% green |

The point is not the absolute number — it is that **a 100% green dashboard hid a 31-point gap**, and this repo lets anyone reproduce and audit that gap.

---

## Honest caveats

- **Model weights are excluded** (size + licensing). To reproduce training, supply your own 3B base and the training data.
- **Training data** (`train_seed_200_aug.jsonl`) is in the release **zip** for self-containment, but is intentionally **not in the git repo** (`.gitignore`) — clone-and-train users should obtain it from the release asset or contact the author.
- Scores reflect this specific 50-sample benchmark and scorer; they are honest measurements, not a claim of SOTA.
- `score_copilot_run_v2.py` and `verify_copilot_run.py` are functional but labeled "draft" — the audit methodology is the deliverable, the exact checks will evolve.

---

## License

MIT — see `LICENSE`. (Copyright: aidless.)

---

**Links**
- Repo: https://github.com/aidless/auditable-llm-eval
- Beginner guide: `docs/GETTING_STARTED.md`
- Full story: `docs/blog/001-auditable-llm-eval-no-green-lights.md`

---

## 🧱 Post-1.0 Audit Layers (added 2026-07-13, no headline-number change)

> These layers do not change any committed score. They make the existing scores **more auditable, more reproducible, more contributor-friendly**.

After tagging v1.0.0, four structural additions landed (still in tag `v1.0.0` HEAD, not a new version — they're hygiene, not science):

### 1. Contract layer — `specs/`

Three machine-checkable JSON contracts paired with a `README.md` containing a one-line consistency check:

| File | Purpose | Pair |
|---|---|---|
| `specs/scoring-rules.json` | 10 `reference_check` types + runtime/overclaim detection | `copilot/score_copilot_run_v2.py` |
| `specs/eval.endpoints.json` | CLI contract for the three eval scripts | `eval/run_copilot_eval.py` · `verify_copilot_run.py` · `copilot/score_copilot_run_v2.py` |
| `specs/test_50.schema.json` | JSON Schema for `test_50.jsonl` (pins 5 task types) | `outputs/.../test_50.jsonl` |

**Why**: a contract change forces a scorer change (and vice versa). Drift in either direction is now detectable with a one-line Python check.

### 2. Decision log — `analysis/`

Four numbered analyses, each with `Trigger / Problem / Diagnosis / Fix / Verification / Lesson / Links`:

- `analysis/001-scorer-runtime-misclassification-fix.md` — why v3c jumped from 63.95% to 69.00% (length-guard + harness-error trust)
- `analysis/002-verify-data-model-rewrite.md` — why the verifier false-FAIL'd at first, and how the rewrite aligns with actual scorer output shape
- `analysis/003-honesty-pass.md` — how the headline 7.59%/77.69% got downgraded to reality 67%/69%
- `analysis/004-false-green-evidence.md` — the reproducible exhibit for the false-green thesis

**Why**: future contributors (including future-you) need to read why, not just what.

### 3. Standardized contribution surface

- `CHANGELOG.md` — SemVer timeline + source-doc appendix (root-level planning docs preserved for context)
- `CONTRIBUTING.md` — how to add a new run / new check / new task, plus a 3-gate local validation policy
- `scripts/validate_release.py` — one-shot local validator (mirrored from the user-level `reproducible-publish` skill)

### 4. CI that enforces the discipline

`.github/workflows/release.yml` runs `validate_release.py` on every push and PR:

- ⚡ ubuntu-latest, Python 3.11, ~30 s
- 🎯 **No Ollama / no GPU required** — the verifier re-runs the scorer against committed `outputs.jsonl`, never against the live model
- 🚪 Fails the push if any of the 4 checks fails

**Status badge** (add to README):
```markdown
[![release-validate](https://github.com/aidless/auditable-llm-eval/actions/workflows/release.yml/badge.svg)](https://github.com/aidless/auditable-llm-eval/actions/workflows/release.yml)
```

---

## ✅ Reproducibility self-check (re-run this any time)

```bash
# 1) install nothing — Python stdlib only for the core scripts
python scripts/validate_release.py
# OVERALL: PASS  ← if you see this, the release is honest

# 2) fresh-clone dry run (gold standard)
cd /tmp && rm -rf clone_test
git clone https://github.com/aidless/auditable-llm-eval.git clone_test
cd clone_test
python scripts/validate_release.py
# OVERALL: PASS  ← if you see this too, the headline numbers truly trust no-one-but-the-clone
```

If step 1 passes but step 2 fails, the release is broken — file an issue with the failing step's tail output.
