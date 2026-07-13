# analysis/ — Decision & Fix Log

> Each numbered file in this directory is a **traceable analysis** — what was the trigger, what was wrong, what was the fix, what was the lesson. Read in order to reconstruct how this repo got from idea to current state.

This follows a **留痕可审计 (auditable trace)** discipline (the same pattern used by sibling projects where every decision worth making is worth recording). For the falsifiable exhibit, see [`004-false-green-evidence.md`](./004-false-green-evidence.md) — the chain that motivates writing these.

---

## 📚 Index

| # | file | trigger | TL;DR |
|---|---|---|---|
| 001 | [`001-scorer-runtime-misclassification-fix.md`](./001-scorer-runtime-misclassification-fix.md) | v3c real score came back 63.95%, visibly below expectation | Length-guard the runtime classifier (short = harness echo, long = real diagnosis) + trust harness-recorded error first. v3c → 69.00%. |
| 002 | [`002-verify-data-model-rewrite.md`](./002-verify-data-model-rewrite.md) | verify script false-FAIL on sections [3][5][6] | Rewrote verify against actual scorer output shape (summary.json single object, report.jsonl exact_checks keyed dict). All 7 sections now PASS. |
| 003 | [`003-honesty-pass.md`](./003-honesty-pass.md) | Committed run contradicted documented numbers | Downgraded 7.59% / 77.69% headline numbers to 67% / 69% real committed runs. Honest hedge retired; docs now reproducible end-to-end. |
| 004 | [`004-false-green-evidence.md`](./004-false-green-evidence.md) | Need to validate the false-green phenomenon | Two committed runs both show naive 100% green vs real 67-69%, reproducible in one command. Exhibit for the layering thesis. |

---

## 🛡️ Maintenance Rules

1. **Number sequentially.** New analyses get the next number (`005-...`). Don't reuse numbers.
2. **Naming convention**: `NNN-short-slug.md`. The NNN anchors order; the slug hints at content.
3. **Each entry covers one decision or one bug.** If you're writing a tutorial, that's a different doc (put it in `outputs/llm-lab/docs/blog/` or `docs/GETTING_STARTED.md`).
4. **Required sections**: Trigger / Problem / Diagnosis / Fix / Verification / Lesson / Links. Skipping a section is allowed but rare; "Lesson" should never be skipped.
5. **Link back to specs.** Each analysis should reference the relevant `specs/*.json` file when applicable — that's how readers trace from decision → spec → code.

---

## 🔗 Cross-references

- Specs (machine contracts): [`specs/`](../specs/)
- Reproducer scripts: [`eval/`](../eval/), [`verify_copilot_run.py`](../verify_copilot_run.py)
- Truthful user-facing docs: [`outputs/llm-lab/README.md`](../outputs/llm-lab/README.md), [`outputs/llm-lab/REPORT.md`](../outputs/llm-lab/REPORT.md), [`outputs/llm-lab/docs/blog/001-...`](../outputs/llm-lab/docs/blog/)