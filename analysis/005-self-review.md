# 005 — Self-Review (light-self-review skill, 11-item checklist)

**Date**: 2026-07-13 (late night)
**Scope**: post-1.0 audit-layer additions (`specs/` + `analysis/00[1-4]` + `CHANGELOG` + `CONTRIBUTING` + `reproducible-publish` skill + `.github/workflows/` + `scripts/` + `RELEASE_NOTES` updates)
**Cadence**: 重产出全量档（对外交付 + 新增脚本 + 涉及引用）

## 🩺 Three highest-severity weaknesses (grill opener)

1. **Two placeholder links `https://example.com` in `specs/README.md` and `analysis/README.md`.** They pretended to point to a "V1 workspace constitution" that doesn't exist anywhere in the repo — a subtle but real reference-accuracy bug. **Fixed before delivery.**
2. **`specs/scoring-rules.json` task-name drift.** Earlier drafts of `outputs/llm-lab/docs/` referenced task names `claim_check` and `keyword_audit` that don't exist in the actual `test_50.jsonl`. `specs/test_50.schema.json` now pins the 5 real task types, and `analysis/003-honesty-pass.md` records the demotion of the old draft numbers. **Resolved.**
3. **Spec ↔ code drift can silently appear.** Both directions (added code check not in spec; spec added check not in code) are bugs. Mitigated by `scripts/validate_release.py` check #2 (DISPATCH keys ⊆ spec types); CI gate prevents regression. **Mitigated, not eliminated** — running `validate_release.py` is still opt-in for local contributors.

## 📋 11-item checklist

| # | Item | Verdict | Evidence |
|---|---|---|---|
| 1 | 逻辑 | ✓ | spec↔code PASS (10/10), schema enum == test_50 tasks (5/5), no internal contradictions in any doc. |
| 2 | 事实 | ⚠ → ✓ | **Initial**: 2× `example.com` placeholder links. **Fixed in this review** (see above). All other citations are real files in repo or real GitHub paths. |
| 3 | 格式 | ✓ | CHANGELOG follows Keep-a-Changelog; analysis/NNN-*.md all have Trigger/Problem/Diagnosis/Fix/Verification/Lesson/Links sections; specs/*.json are valid JSON parsed without error. |
| 4 | 表达 | ✓ | English/Chinese usage flagged (14 lines with "very"/"just"), all are natural English quantifier usage in English docs (CHANGELOG/CONTRIBUTING/RELEASE_NOTES are English), no Chinese ambiguity flagged. |
| 5 | 创新 | ! | Layered specs-first + analysis-log + skill-extraction is not novel in isolation, but **the discipline that makes all three reproducible-by-clone in one command** is the contribution. Honest hedge. |
| 6 | 引用 | ⚠ → ✓ | 42 relative-path links across 13 markdown files: 0 broken. After placeholder fix, 0 broken external links. |
| 7 | 夸大 | ! | Headline numbers (69% / 67%) match committed reality (analysis/003 + 004); no "novel/significantly" used; reproduce-from-disk is the test, not rhetoric. |
| 8 | 审美 | ✓ | All new docs follow repo's existing style (heading hierarchy, table-of-contents, emoji 1-2 per section, no decorative emoji). |
| 9 | 重复 | ! | `analysis/003-honesty-pass.md` and `analysis/004-false-green-evidence.md` overlap slightly on the "what the committed runs show" topic — but each has a different **purpose** (003 = why we downgraded; 004 = what the new exhibit is), so kept both. Acceptable. |
| 10 | 结构 | ✓ | spec → analysis → CHANGELOG/CONTRIBUTING → skill → CI is the documented build order; README portal lists them; CHANGELOG has source-doc appendix for old planning files. |
| 11 | 可执行 | ✓ | `python scripts/validate_release.py` runs and exits 0. All commands in CONTRIBUTING/README/RELEASE_NOTES are real and produce real output (verified by running each at least once). |

**Tally**: 9 ✓ / 2 ! / 0 ✖

## 🔬 Code-specific SCA / capability audit

For `scripts/validate_release.py` (the new CLI script):

| Aspect | Verdict | Evidence |
|---|---|---|
| Dependency safety | ✓ | No third-party packages imported. Only stdlib (`argparse`, `json`, `os`, `pathlib`, `re`, `subprocess`, `sys`). |
| Network access | ✓ | None. All I/O is local file + local subprocess to `python`. |
| Shell injection | ✓ | All subprocess calls use list args (no `shell=True`). No `os.system`, no `eval`, no `exec`. |
| Path traversal | ✓ | All paths resolved via `Path.resolve()`; reads limited to passed-in `--repo-root`. |
| Output encoding | ✓ | ASCII-only output (verified — avoids PowerShell 5.x GBK pitfall per RULE.md). |
| Exit codes | ✓ | `0` on OVERALL PASS, `1` on any FAIL (per `[result_presentation]` and `verifier` discipline). |

## 🎯 Bug fix recap (this self-review)

**Fix 1**: `specs/README.md` and `analysis/README.md` had `[V1 workspace constitution](https://example.com)` — a placeholder link left over from a draft. Replaced with sibling-project context references pointing to other in-repo docs.

**Fix 2**: `specs/README.md` §Maintenance Rules had a stray "(borrowed from the V1 constitution)" parenthetical. Removed for consistency.

After both fixes, `validate_release.py` re-ran and still PASSES OVERALL (78 tracked files, no zip/weights/.workbuddy, all spec↔code consistent).

## ✅ Conclusion

Repository is ready for the post-1.0 audit-layer landing. Self-review caught 1 placeholder-link bug before delivery; CI gate (added in this round) will catch regressions on subsequent pushes.

— Signed by light-self-review, 2026-07-13 23:30.