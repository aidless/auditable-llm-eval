# 003 — Honesty Pass: Aligning Docs with Reproducible Reality

**Trigger**: After committing the v3c run to disk and verifying the score, the **committed run contradicted the documented numbers**.

**Date**: 2026-07-13 (evening)

---

## 🪤 Problem

The committed reality on disk:

| run | naive verdicts | real `reference_check_rate` | output |
|---|---:|---:|---|
| v3c | 50/50 (100% green) | **69.00%** | coherent text, partial YAML |
| v3 | 50/50 (100% green) | **67.00%** | coherent text, partial YAML |

The pre-committed documentation (`outputs/llm-lab/REPORT.md`, `README.md`, `docs/blog/001-…md`):

| model | doc-claimed score | doc-claimed behavior |
|---|---:|---|
| v3c | 77.69% | fixed model, 0 overclaims |
| v3 | 7.59% | "fence collapse, 31/31 false-green, outputs were ```` ``` ```` repeated until token budget ran out" |

**The "fence collapse" story is real** (it was observed in an earlier dropped session, in conversation logs) **but it is not reproducible from any committed run** in this repo. The committed v3 run produces coherent text and scores 67%, not fence garbage at 7.59%.

This is the **classic reproducibility lie**: the documentation references a phenomenon that the repository does not actually contain.

---

## 🔍 Diagnosis

Three roots:

1. **The 7.59% / 77.69% numbers came from a dropped session's conversation logs**, not from a reproducible run. The conversation logs were the only place where those numbers existed; no `outputs/` or `runs/` was ever committed that produced them.
2. **The blog post was written before the v3c real run was produced**, using those conversation-log numbers as "evidence" of a falsifiable chain. The chain (v3 → v3b ablation → v3c fix) was real in spirit, but its concrete percentages were session-only.
3. **The README "诚实状态" box was correctly hedging ("分数来自会话日志,不能端到端复现")** — but the body of the docs themselves were still using those numbers as headlines.

---

## 🔧 Fix

### 1. Downgrade the dropped-session arc to "motivation, not result"

In `docs/blog/001-…md`, mark the 31/31 → 7.59% → 77.69% story as **historically observed but not reproducible from this repo**. The current blog now leads with the **reproducible evidence**:

> Two real runs in `outputs/llm-lab/datasets/llm_lab_copilot/runs/` show the pattern still holds: **naive verdicts 100% green, real scorer 67–69%**. The core lesson — green lights can hide a 30-point gap — is reproducible in one command.

### 2. Rewrite `REPORT.md` headline numbers

Old: `**77.69%**` and `**7.59%**` (fence collapse).
New: `**69.00%**` and `**67.00%**` (real committed runs).

Both runs reproduce their real scores with `verify_copilot_run.py`. Anyone reading the repo can re-derive these numbers.

### 3. Rewrite the README portal "honest status" box

Old:
> ⚠️ **诚实状态（发布前必读）**：本文档体系的 copilot 评测当前以**草稿脚本**形式存在，**不能端到端复现**…

New:
> ✅ **状态（2026-07-13）：现已可复现。** copilot 评测以脚本形式存在（`eval/run_copilot_eval.py` 入口 + `copilot/score_copilot_run_v2.py` 权威 scorer + `verify_copilot_run.py` 纪律校验器），基准 `test_50.jsonl` 与两个真实 run（…-v3c=**69.00%**、…-v3=**67.00%**）**已提交本仓库**，头版分数可由本仓库端到端复现。

### 4. Rewrite `docs/blog/001-…md` to match

Five sections touched: TL;DR, §2 green-light trap, §5 the fix, §6 scoreboard, §8 reproducibility commands. The blog now consistently uses 69% / 67% with `verify_copilot_run.py` as the canonical recompute step.

---

## ✅ Verification

Re-ran the full reproduce pipeline after the rewrite:

```bash
python verify_copilot_run.py --run-dir outputs/llm-lab/datasets/llm_lab_copilot/runs/20260713-211540-copilot-3b-lora-v3c \
  --dataset outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl \
  --scorer copilot/score_copilot_run_v2.py
# → ALL CHECKS PASSED: 69.00%

python verify_copilot_run.py --run-dir outputs/llm-lab/datasets/llm_lab_copilot/runs/20260713-213920-copilot-3b-lora-v3 \
  --dataset outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl \
  --scorer copilot/score_copilot_run_v2.py
# → ALL CHECKS PASSED: 67.00%
```

Every number in the rewritten docs is now derivable by anyone running these two commands.

---

## 🧬 Lesson

**Reproducible > impressive.** A headline 77.69% from a session log is more impressive than 69% from a committed run — but only one of them is **true**. The 69% is the true one; the 77.69% was a hallucination by the documentation.

**The "honest status" hedge in the README was the right pattern** — it gave readers a way to know the docs were not yet self-verifying. Once the run was committed and verified, the hedge could be retired. Until then, the hedge itself was more honest than the body of the docs.

**The dropped-session arc was a real lesson, just not a reproducible one.** Keeping it in the blog as "motivation" is fine; promoting it to "result" was the lie. The distinction matters: motivation can be anecdotal; result must be reproducible.

---

## 🔗 Links

- Spec source-of-truth: [`specs/`](../specs/)
- Reproducer: [`eval/run_copilot_eval.py`](../eval/run_copilot_eval.py)
- Discipline checker: [`verify_copilot_run.py`](../verify_copilot_run.py)
- Truthful docs: [`outputs/llm-lab/REPORT.md`](../outputs/llm-lab/REPORT.md), [`outputs/llm-lab/README.md`](../outputs/llm-lab/README.md)