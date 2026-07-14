# 015 — Fix insufficient: PYTHONIOENCODING alone was not enough

> **STATUS**: open incident. **My fix in `analysis/014` did not fully resolve the 3-OS matrix failure.** Run #14 (commit `64ab364`) is still red. Confidence in the fix is now **demoted** to "unverified, likely insufficient pending log." Do not commit further code changes until a specific failed-job log is examined.

**Date**: 2026-07-14 11:26 (response to user-supplied Actions-page screenshot)
**Confidence demotion**: `analysis/014` "predicted PASS, moderate confidence" → invalidated.

---

## 🩺 What we see

User-supplied screenshot of `github.com/aidless/auditable-llm-eval/actions`:

| run | commit | status | duration |
|---|---|---|---:|
| **#14** | `64ab364` | ❌ | **26s** |
| #13 | `1a08a38` | ❌ | 23s |
| #12 | `1c2f707` | ❌ | 39s |
| #11 | `0b342c6` | ❌ | 30s |
| #10 | `f51a19e` | ❌ | 31s |

**The fix landed. The run is still red.** 26s is shorter than the 30-39s pre-fix signature, but it is not the ~5-10s of a clean pass, so the failure is partial. The fix clearly did *something* (e.g. unblocked the `validate` step on at least one OS), but at least one matrix OS is still failing.

We do not have the per-job log. We do not know whether the failure is in `validate` (likely, given prior incident) or in `tests`, or which OS is the culprit.

## 🪤 Most likely root causes (inferred, ranked)

I refuse to commit a fix on inference alone after one fix already failed. Ranked by likelihood:

1. **`PYTHONIOENCODING` does not propagate to the second-level subprocess on Windows runner.** `validate_release.py` is a Python process. It calls `verify_copilot_run.py` as a subprocess (passes `env=_CHILD_ENV` — good). `verify_copilot_run.py` then calls `copilot/score_copilot_run_v2.py` as a second-level subprocess. The second-level subprocess **may or may not** inherit `PYTHONIOENCODING` from the first-level subprocess. Python 3.11 on Windows does inherit env vars by default, but the `print()` to a stdout that was **already opened with cp1252 by the parent PowerShell** is a different story: the encoding is set when the stream object is created, not when bytes are written. Once opened, the stream is cp1252 forever.

2. **macOS runner default locale is `C` / `POSIX`, not UTF-8.** Similar failure mode: a non-utf-8 LANG / LC_ALL would cause Python to use `ascii` codec, which raises on first non-ASCII character. `PYTHONIOENCODING=utf-8` should fix this too, but if the env var is somehow not inherited, macOS would also crash.

3. **The test suite prints something we didn't expect.** `tests/test_scorer.py` selftest output could trigger a unicode crash. Less likely (we ran tests locally and they all passed), but the test step runs separately from the validate step and might use a different env.

4. **My local "fix works" reproduction was contaminated.** This is the most embarrassing possibility and the one that fits the "本机预设污染" rule added to `~/.workbuddy/MEMORY.md` 30 minutes ago. The user's local Windows has had `$OutputEncoding = UTF8` (or similar) set in past sessions. My local reverse-simulation set `PYTHONIOENCODING=utf-8` *on top of* those presets. The fix may not work on a fresh `windows-latest` runner with no presets at all.

The most plausible: **combination of (1) and (4)**. The fix is real for code that respects the env, but the second-level subprocess in `verify_copilot_run.py` may not.

## 🛡️ Process discipline applied

- I am **not committing a new fix**. Fixes that are based on inference after a previous fix already failed are the textbook case for "trying things to see what sticks" — exactly the behavior the 措辞降级规则 was designed to prevent.
- I am **not** downgrading the user-visible commit history. `64ab364` remains the most recent commit and the most informative one to revert or amend if the user decides.
- I am **not** running further local tests that could be contaminated in the same way.
- I am **requesting evidence** (per-job log) before the next code change.

## 📋 What the user can do

1. **Open run #14 in the Actions page, expand the failed job(s), and screenshot the log.** With the per-job log, we can pinpoint which OS is failing, which step, and what the actual error message is. The previous screenshot showed only the run list; we need the run detail.
2. **Look for the same `UnicodeEncodeError: 'charmap' codec can't encode` pattern**, or a different pattern entirely.
3. **If the failure is the same encoding issue but in a different code path** (e.g. `tests/test_scorer.py` printing something, or a different verify line), the fix may need to be deeper: force UTF-8 in `sys.stdout` at the top of every script, or rewrite the printing code to ASCII.
4. **If the failure is something else** (e.g. macOS locale, missing dep), we'll know.

## 📊 Confidence ladder update

| claim | confidence before this report | confidence now |
|---|---|---|
| `analysis/014` "predicted 6/6 green, moderate confidence" | moderate | **invalidated** |
| `analysis/014` "fix has been **verified by local reproduction**" | moderate | **demoted to "verified locally only; local environment may have presets not present on runner"** |
| `PYTHONIOENCODING=utf-8` is the right *kind* of fix | moderate | **plausible but unproven** — only one reproduction, only locally |
| The actual root cause is encoding-related | moderate | **still plausible**, but could be something else (e.g. macOS locale) |

This is the second time in 24 hours the matrix has gone red, and the second time my prediction has been too optimistic. The pattern is real and worth its own memory note (already added: "本机预设污染" + the 措辞降级 rule above it).

## 🔗 Links

- `analysis/013-3os-matrix-red.md` — initial inference
- `analysis/014-ci-v3-confirmed-and-fix.md` — the fix that didn't fully work (now demoted)
- `~/.workbuddy/MEMORY.md` § "CI 模拟的本机预设污染陷阱" — the cross-project rule that explains why "verified locally" was insufficient

---

*This report is **open** and will be closed when (a) the per-job log is in hand, (b) the real root cause is identified, and (c) a *verified* fix is committed. Until then, no more code changes on inference.*
