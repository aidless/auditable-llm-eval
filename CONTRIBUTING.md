# Contributing to auditable-llm-eval

Thanks for your interest in making LLM evaluation more honest. This document explains how to contribute **a new model run, a new check type, or a new benchmark task** while preserving the reproducibility guarantees of the project.

---

## 🎯 What this project is (and isn't)

**It is** an open evaluation pipeline where:
- Every benchmark task has programmatic `reference_checks` (including *cognitive-honesty* dimensions)
- A naive structural verifier and an authoritative scorer run in parallel; the gap between them is exposed
- Every committed run is verifiable end-to-end via `verify_copilot_run.py`

**It isn't** a leaderboard or a one-shot benchmark. The point is the **methodology** — anyone reading this repo can re-derive the headline numbers from raw outputs, and a tampering attempt will be detected.

---

## 🧰 Before you start

1. Read [`outputs/llm-lab/README.md`](./outputs/llm-lab/README.md) (the portal)
2. Read [`outputs/llm-lab/docs/GETTING_STARTED.md`](./outputs/llm-lab/docs/GETTING_STARTED.md) (5-minute setup)
3. Read at least one [`analysis/00*.md`](./analysis/) to understand the discipline (e.g. [001 — runtime misclassification](./analysis/001-scorer-runtime-misclassification-fix.md))
4. Skim [`specs/`](./specs/) — the contracts are the source of truth for what code does

If anything in the docs contradicts what you observe when running, **open an issue**. Reproducibility beats polish.

---

## 🛠️ Types of contributions

### 1. Add a new model run (most common)

You trained a new adapter, or want to evaluate an existing model on `test_50`. Steps:

```bash
# 1. Make sure the model is in ollama
ollama list   # confirm tag matches

# 2. Run the eval
python eval/run_copilot_eval.py --model <your-model-tag>

# 3. Verify the new run
python verify_copilot_run.py \
  --run-dir outputs/llm-lab/datasets/llm_lab_copilot/runs/<new-run-dir> \
  --dataset outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl \
  --scorer copilot/score_copilot_run_v2.py

# 4. Confirm 7/7 PASS before opening a PR
```

If verify fails, do not open a PR; debug locally first. The most common cause is mismatched ollama URL or a model that doesn't follow the prompt format.

### 2. Add a new `reference_check` type

This requires updating the contract **first**:

1. Edit [`specs/scoring-rules.json`](./specs/scoring-rules.json) — add the new check type under `checks` with full rationale, soft/exact, negation-awareness, keyword-field aliasing
2. Update the spec ↔ code consistency check in [`specs/README.md`](./specs/README.md#-how-to-verify-specs-are-consistent-with-code)
3. Implement `check_<new_name>` and add to `DISPATCH` in `copilot/score_copilot_run_v2.py`
4. Add at least 2 test cases to `selftest()` that exercise the new check
5. Add at least 1 `reference_check` entry in `test_50.jsonl` using the new type
6. Re-run `verify_copilot_run.py` against both committed runs — they should still PASS (otherwise your new check is breaking existing checks)
7. Bump `specs/scoring-rules.json` version (MINOR)

**Never** add a check to the scorer without adding it to the spec. The spec is the contract.

### 3. Add new benchmark tasks

1. Add new rows to `outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl` (or a new file `test_<N>.jsonl` if changing the size warrants)
2. Each row must have `id` (unique), `task` (one of the 5 task types), `prompt`, `reference_checks`
3. **Bump MAJOR**: existing runs are no longer directly comparable. Update [`CHANGELOG.md`](./CHANGELOG.md)
4. Update [`specs/test_50.schema.json`](./specs/test_50.schema.json) to reflect any new task type
5. Update the docs to point to the new dataset

### 4. Fix a bug in scorer / verifier / eval

1. Reproduce the bug with the smallest possible input
2. Write a regression test in the relevant `selftest()` (scorer) or as an inline check in the verifier
3. Fix the bug
4. Re-run **all** committed `verify_copilot_run.py` runs — they must still PASS
5. Add an `analysis/NNN-<slug>.md` describing the trigger / problem / fix / lesson

### 5. Improve documentation

Light edits: PR directly. Heavy restructure: open an issue first to align on scope.

---

## 🚫 What we will not merge

- **Results from runs that fail `verify_copilot_run.py`.** A non-reproducible run is not a contribution.
- **Hidden check changes.** Adding a new check type without updating `specs/scoring-rules.json` is a silent contract break.
- **Mixed-encoding commits.** All `.md` files in this repo are UTF-8; `PowerShell Add-Content` defaults to GBK and will mangle them — use Python `open(..., encoding='utf-8')` or `Write` tool. (See `analysis/003-honesty-pass.md` for a related trap.)
- **Model weights in the repo.** This repo intentionally ships only scripts + runs (small JSON files). Weights live in ollama / HuggingFace / wherever; link to them in `outputs/llm-lab/REPORT.md` if relevant.
- **Numbers without provenance.** Every score in this repo must be derivable from `test_50.jsonl` + scorer + a committed run. If you can't reproduce your number, don't claim it.

---

## 📏 Style guide

- **Markdown**: GitHub-flavored. Code in backticks, filenames in backticks.
- **Code**: Python 3.10+ compatible. Standard library only for `eval/`, `verify_copilot_run.py`, `copilot/score_copilot_run_v2.py` (the core pipeline must remain dependency-free for beginners).
- **Naming**: snake_case for files, kebab-case for slug in markdown filenames.
- **Emoji**: 1–2 per section max, used for status (✅ ⚠️ ⚪) or section markers. No decorative emoji.

---

## 🧪 Local validation before PR

```bash
# 1. Scorer selftest (must PASS)
python copilot/score_copilot_run_v2.py --selftest

# 2. Verify both committed runs (must PASS both)
python verify_copilot_run.py --run-dir outputs/llm-lab/datasets/llm_lab_copilot/runs/20260713-211540-copilot-3b-lora-v3c --dataset outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl --scorer copilot/score_copilot_run_v2.py
python verify_copilot_run.py --run-dir outputs/llm-lab/datasets/llm_lab_copilot/runs/20260713-213920-copilot-3b-lora-v3 --dataset outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl --scorer copilot/score_copilot_run_v2.py

# 3. Spec ↔ code consistency (must PASS)
python - <<'PY'
import re, json
src = open('copilot/score_copilot_run_v2.py', encoding='utf-8').read()
m = re.search(r'DISPATCH\s*=\s*\{([^}]+)\}', src, re.S)
code_types = set(re.findall(r'"([^"]+)"\s*:\s*\(check_', m.group(1)))
spec_types = {c['type'] for c in json.load(open('specs/scoring-rules.json', encoding='utf-8'))['checks']}
print('PASS' if not (code_types - spec_types or spec_types - code_types) else 'DRIFT')
PY
```

All three must say `PASS`. If any says `FAIL` / `DRIFT`, your PR isn't ready.

---

## 📐 Confidence-phrasing rules (the only project-wide writing rule)

This repo has a permanent rule about how to write confidence claims. It exists because the project got bitten by it once and we don't want to get bitten again.

**The rule:** phrases like "high confidence", "almost certainly", "definitely", "clearly", "obviously" are **phrasing-class failure modes** — independent of model or method, they invite overclaiming. Each gets demoted once bitten, and a single new verification dimension does **not** upgrade them back.

### Confidence ladder (use this when you write any conclusion)

| Confidence level | Required evidence | Example phrasing |
|---|---|---|
| **Confirmed** | Real measurement **+** peer review **+** multiple independent verifications | "Confirmed", "established", "verified by N independent runs" |
| **Moderate** | Real measurement **+** single-dimension local verification **+** inferred extrapolation | "Moderate confidence", "predicted", "with the caveat that …" |
| **Speculative** | Inference only, no measurement | "May", "possibly", "likely cause" |
| **Unverifiable** | Requires external access (CI, real-world deploy, peer review) | "Unverified locally; the following dimensions cannot be tested: …" |

### The one-line test

Before writing any confidence claim, ask:

> "If this turns out wrong, how embarrassing would it be?"

If the answer is "very", you do not have enough verification dimensions — drop the confidence level.

### Why this rule is in the contributor guide, not just personal memory

The repo's first CI simulation report (`analysis/006`, "predicted PASS, high confidence") was bitten by reality within hours. A follow-up (`analysis/008`) repeated the same "high confidence" phrasing despite adding one more verification dimension. The second phrasing was downgraded to "moderate confidence" only because a self-review caught it.

Future contributors — including future-us — will be tempted to write "high confidence" the moment a local test passes. **This rule is the guardrail.** It's a self-discipline rule, not a CI-enforced rule, so it lives here in prose rather than in `validate_release.py`. But a reviewer may still flag a PR that uses "high confidence" without strong evidence.

### Real example from this repo's history

> ❌ `analysis/006` (deleted from index, but archived in git history): "predicted GitHub Actions outcome on this HEAD: PASS (high confidence)" — only verified the **scoring layer** (one dimension). Got bitten.
>
> ✅ `analysis/008`: "predicted PASS, **moderate confidence**" — verified the scoring layer (Python 3.13) **and** the Python version (3.11) **and** the fresh-clone equivalence. Two independent dimensions, but the actual GitHub Actions runner was still untested. So "moderate", not "high".
>
> ✅ `analysis/010`: "Confirmed by 3 green GitHub Actions runs after the fix." — external evidence (real CI runs) exists, so the upgrade to "confirmed" is justified.

---

## 🤝 Community norms

- Disagreements about check semantics → open an issue with a 50-word scenario, not a 500-word essay
- Disagreements about methodology → open an issue with a worked counter-example
- Personal attacks, gatekeeping, or "you should know this" → don't. We're all here to make eval more honest.

---

## 📜 License

By contributing, you agree your contributions are licensed under the project's [MIT License](./LICENSE).

---

*Thank you for making LLM evaluation more honest, one reproducible run at a time.*