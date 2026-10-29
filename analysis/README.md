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
| 005 | [`005-self-review.md`](./005-self-review.md) | Post-1.0 audit-layer self-review | 11-item checklist over `specs/` + `analysis/` + `CHANGELOG` + workflows. |
| 006 | [`006-ci-simulation.md`](./006-ci-simulation.md) | Need a local stand-in for GitHub Actions | `git archive` mirror + same CI command; proved the *scoring* layer passes. |
| 007 | [`007-ci-v2-fix.md`](./007-ci-v2-fix.md) | Two CI runs went red | Removed broken `cache: pip` from `setup-python@v5`. |
| 008 | [`008-ci-v2-verification.md`](./008-ci-v2-verification.md) | Verify the CI fix locally | Scoring layer verified PASS on a fresh clone (Python 3.11). |
| 009 | [`009-self-review.md`](./009-self-review.md) | Self-review after the CI v2 fix | Checklist over workflow edit + `analysis/007`/`008`. |
| 010 | [`010-confirmed.md`](./010-confirmed.md) | Was `cache: pip` really the root cause? | **Closed**: three green CI runs confirm removing it fixed both red runs. |
| 011 | — | *(number skipped; no entry was ever written)* | Kept as a gap rather than reused, per the "number sequentially" rule. |
| 012 | [`012-final-state-report.md`](./012-final-state-report.md) | End-of-day closure / "where do I start?" | 1-page cheat sheet for the formation day (HEAD `f51a19e`). |
| 013 | [`013-3os-matrix-red.md`](./013-3os-matrix-red.md) | 3-OS matrix red | Red runs confirmed, root cause **inferred not confirmed**. |
| 014 | [`014-ci-v3-confirmed-and-fix.md`](./014-ci-v3-confirmed-and-fix.md) | Root cause hunt for the 3-OS red | `PYTHONIOENCODING=utf-8` confirmed by stack trace + local repro. |
| 015 | [`015-fix-insufficient.md`](./015-fix-insufficient.md) | Fix from `014` did not turn CI green | Confidence demoted to "unverified, likely insufficient". |
| 016 | [`016-week1-doc-consistency-and-packaging.md`](./016-week1-doc-consistency-and-packaging.md) | Cross-repo audit found 3 doc drifts in this repo | Added zero-dependency `pyproject.toml`; aligned the test count to 40 and the deception-zone wording to the 32 points `demo.py` actually prints. |

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
