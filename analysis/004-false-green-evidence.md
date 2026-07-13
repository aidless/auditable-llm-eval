# 004 — False-Green Evidence: Reproducible Demonstration

**Trigger**: The whole point of `llm-lab-copilot` is to catch "false-green" verdicts — a verification system that reports **100% pass** while the actual quality is much lower. To validate this is a real phenomenon (not just a critique of naive verifiers in general), we need committed runs that exhibit it.

**Date**: 2026-07-13 (evening)

---

## 🎯 The Phenomenon

A "false-green" verdict is one where:

1. **Naive verdict panel**: passes (e.g. "structural: non-empty, length-ok")
2. **Authoritative scorer**: fails (e.g. "missing required keyword", "overclaim detected", "wrong answer")

The gap between these two is the **deception zone**. If your eval pipeline only reports #1, you ship bad models. If it reports #2, you ship good ones.

---

## 🔬 Reproducible Evidence (both committed)

### Run 1: v3c (a competent LoRA adapter)

| signal | value |
|---|---|
| Run directory | `runs/20260713-211540-copilot-3b-lora-v3c` |
| Model | `copilot-3b-lora-v3c:latest` (Qwen2.5-3B + LoRA, fixed hyperparameters) |
| Verdicts (naive) | **50 / 50 = 100% green** |
| Real `reference_check_rate` | **69.00%** (138 / 200 reference checks passed) |
| `unsupported_claims` rows | 7 |
| `runtime_error` rows | 0 |

**Gap**: 100% green vs 69% real → **31-point deception zone**.

### Run 2: v3 (control LoRA adapter)

| signal | value |
|---|---|
| Run directory | `runs/20260713-213920-copilot-3b-lora-v3` |
| Model | `copilot-3b-lora-v3:latest` (same base, different LoRA hyperparameters) |
| Verdicts (naive) | **50 / 50 = 100% green** |
| Real `reference_check_rate` | **67.00%** (134 / 200 reference checks passed) |
| `unsupported_claims` rows | 7 |
| `runtime_error` rows | 0 |

**Gap**: 100% green vs 67% real → **33-point deception zone**.

---

## 🔍 Why the naive verdicts say "100% green"

The naive verdict logic (in `eval/run_copilot_eval.py`) is:

```python
verdict = "pass" if (output and min_len <= len(output) <= max_len) else "fail"
```

Where `min_len=20`, `max_len=8000`. Both v3 and v3c produce outputs in the 100-2000 char range with content — every single one passes this guard. The naive verifier has **no opinion on whether the answer is correct**, only on whether it's non-empty and length-plausible.

For a domain like ours (copilot for ML eval design), a structurally-plausible-but-wrong answer is exactly the failure mode we care about. Naive verdicts are blind to it.

---

## 🧪 What the real scorer catches

Sampling 10 representative rows from v3c where `score < 1.0`:

| id | task | what's wrong |
|---|---|---|
| c005 | eval_yaml | missing `metrics` keyword |
| c013 | report_summary | no rerun/reproducibility mention |
| c025 | failure_diagnosis | missed `provider` distinction (blamed model for infra issue) |
| c032 | verifier_design | didn't recommend manual/semantic review |
| c042 | reviewer_qa | claimed semantic quality from structural check |
| ... | ... | ... |

These are exactly the **cognitive-honesty** failures the 10 `reference_check` types were designed to catch. None of them are visible from the naive verdicts.

---

## ✅ How to reproduce

```bash
# 1. Verify v3c run (committed)
python verify_copilot_run.py \
  --run-dir outputs/llm-lab/datasets/llm_lab_copilot/runs/20260713-211540-copilot-3b-lora-v3c \
  --dataset outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl \
  --scorer copilot/score_copilot_run_v2.py
# → ALL CHECKS PASSED: 69.00%

# 2. Verify v3 control run (committed)
python verify_copilot_run.py \
  --run-dir outputs/llm-lab/datasets/llm_lab_copilot/runs/20260713-213920-copilot-3b-lora-v3 \
  --dataset outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl \
  --scorer copilot/score_copilot_run_v2.py
# → ALL CHECKS PASSED: 67.00%
```

If a clone of this repo can't reach these numbers with these commands, the repo is broken; file an issue with `verify_copilot_run.py` output.

---

## 🧬 Lesson

**The naive verifier is a feature, not a bug.** It exists because structural checks are cheap and fast. The **bug** is treating it as the final word. The fix is layering:

1. **Layer 1**: naive verdict (structural, fast, 100% green here)
2. **Layer 2**: authoritative scorer (semantic-aware, exposes the gap)
3. **Layer 3**: discipline checker (`verify_copilot_run.py`, ensures Layer 2 is honest)

The repo ships all three. The 30-point gap between Layer 1 and Layer 2 in both committed runs is the **exhibit** — proof that the layering matters.

---

## 🔗 Links

- Run v3c: [`runs/20260713-211540-copilot-3b-lora-v3c/`](../outputs/llm-lab/datasets/llm_lab_copilot/runs/20260713-211540-copilot-3b-lora-v3c/)
- Run v3: [`runs/20260713-213920-copilot-3b-lora-v3/`](../outputs/llm-lab/datasets/llm_lab_copilot/runs/20260713-213920-copilot-3b-lora-v3/)
- Spec: [`specs/scoring-rules.json`](../specs/scoring-rules.json)
- Blog: [`docs/blog/001-auditable-llm-eval-no-green-lights.md`](../outputs/llm-lab/docs/blog/001-auditable-llm-eval-no-green-lights.md)