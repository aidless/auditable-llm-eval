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
