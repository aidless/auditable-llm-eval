# 013 — CI v3 (3-OS matrix) red: encoded honesty pass

> **STATUS**: open incident. User-supplied screenshot of the Actions page shows 3 consecutive red runs (#10, #11, #12) on the 3-OS cross-platform matrix commit. All runs terminated in 30-39s. **Root cause is inferred, not confirmed** — the user did not screenshot a specific failed job's log, so we diagnose from timing + analysis of the code (which has known cross-platform risk).

**Date**: 2026-07-14 09:40 (response to user-supplied Actions-page screenshot)
**Verified**: red runs. **Not verified**: root cause. See "Honest gap analysis" below.

---

## 🩺 What we see

User-supplied screenshot of `github.com/aidless/auditable-llm-eval/actions` shows the 12-workflow-run history. The relevant tail:

| run | commit | status | duration | title |
|---|---|---|---:|---|
| 12 | `1c2f707` | ❌ | 39s | docs(analysis): 012-final-state-report |
| 11 | `0b342c6` | ❌ | 30s | feat(ci+tests): cross-platform CI matrix + stdlib unittest suite (pre-amend) |
| 10 | `f51a19e` | ❌ | 31s | feat(ci+tests): cross-platform CI matrix + stdlib unittest suite |
| 9 | `d5aef9e` | ✅ | 9s | (phrase-downgrade + blog) |
| 8 | `cd96feb` | ✅ | ~7s | (link blog/002) |

The first run under the new matrix (`f51a19e`) was already red. Two amend-and-force-push attempts on `1c2f707` did not change the outcome (which is expected — neither changed `release.yml` content).

## 🪤 Most likely root cause (inferred, not confirmed)

The 30-39s duration is diagnostic. Two timelines separate the failure mode:

- **<10s = setup phase**: `actions/setup-python@v5` (we already fixed this; analysis/007).
- **30-40s = setup succeeded, validate ran, a check failed mid-flight** (or one OS-specific hang).

`scripts/validate_release.py` invokes the verifier via `subprocess.run(...)` in `check_verifier()` (line 133). The verifier (`verify_copilot_run.py`) then runs **another** `subprocess.run(...)` internally at section [3] (line 115) to invoke the scorer. Two layers of subprocess on a runner, with stdout being captured.

Looking at `verify_copilot_run.py` section [5] (tamper audit) — this section prints **Chinese strings** to stdout:

```python
print(f"    [真实声称] {pid}: 输出含未否认的 tamper 词 → 应判挂（合理）")
print(f"    [正确否认] {pid}: 含 tamper 词但附近有否定 → 应判过（无误判）")
print(f"    [残留误判] {pid}: scorer 判挂，但原文是否认 → BUG 仍活")
```

**GitHub Actions runner default encoding varies by OS:**

- `ubuntu-latest` — typically UTF-8, works.
- `macos-latest` — typically UTF-8, usually works.
- **`windows-latest` — historically CP1252 / GBK / Mojibake trap.** Even with `setup-python@v5`, the runner's console codepage is OEM-US (CP437) by default. Python's `sys.stdout` then inherits that codepage. When `print()` encounters any character outside the codepage — Chinese characters, em dashes, arrows → it raises `UnicodeEncodeError: 'charmap' codec can't encode character ...`

This is documented in `RULE.md` (§ 4 / § 6 in the workspace rules) as a known PowerShell 5.x trap. The user has hit it before on Windows locally. We did **not** set `PYTHONIOENCODING=utf-8` in the new `release.yml` step that runs the verifier.

Most likely chain: `windows-latest` job → `setup-python` succeeds → validate step runs → verify subprocess runs → verify's [5] tamper audit hits a Chinese string → UnicodeEncodeError on Windows console → subprocess exits with `returncode != 0` and no helpful output → validate_release.py sees the failure (or sees "PASS" string but returncode is 1, so its `ok` is False) → check #3 FAIL → overall FAIL.

Linux + macOS job in the same matrix run might actually be green or yellow, but because `fail-fast: false` AND because matrix runs are still aggregated into one workflow result, **one** job failure makes the entire run red.

**This is consistent with all three runs being red**, because `windows-latest` is part of the matrix every time.

## 🔍 Why we did not catch this locally

In `analysis/008` we verified validate + 39 tests on:
- Windows (`Windows 10.0.x` + Python 3.13.14, the user's local machine)

The user's local Windows PowerShell console has been **explicitly configured** to UTF-8 via past sessions (likely `$PSDefaultParameterValues['Out-Encoding']='utf8'` or similar). The standard GitHub-hosted `windows-latest` runner uses the runner image's default OEM-US codepage, which is different from a user-configured dev box.

In other words: **our local 6-dimension validation was on a machine where the user's console was already UTF-8**; we never tested on a **fresh** Windows runner with default codepage. This is exactly the "two-dimension local CI simulation" failure mode we wrote about in `analysis/008 § What this teaches about CI simulation` — but we didn't catch our own point.

## 🔧 What we did NOT do (deliberately, pending log)

We did **not** commit a fix in this report. Two reasons:

1. The root cause is **inferred, not confirmed**. Without a specific job's failure log, we are pattern-matching on a prior incident, not diagnosing evidence. Committing a fix on inference would be repeating exactly the pattern that produced analysis/006's `high confidence` blunder.
2. The fix is trivial (one-line `env` addition) but should be preceded by verifying the inference.

## 🪞 Honesty pass on prior claims

| prior claim | status after this incident |
|---|---|
| `analysis/008` "predicted PASS, moderate confidence" | invalidated — we predicted PASS on the matrix; it actually failed |
| `analysis/012 § 4` "6-dimension local validation: all PASS" | **partially invalidated** — the 2 dimensions that mattered most (cross-OS runner behavior, fresh Windows console codepage) were not actually covered by our local tests |
| `analysis/012 § 9 single sentence` "The discipline is the deliverable" | still true — this incident is the discipline catching its own bug |

The phrase-downgrade rule pays out exactly as designed: `analysis/006` wrote `high confidence` and got bitten; `analysis/008` wrote `moderate confidence` and got bitten; future analyses from this incident will be written at `inferred pending log` until real evidence arrives.

## 📋 Next steps (depends on what the user sends)

1. **User screenshots a specific failed job's log** (likely the `windows-latest` job) → we extract the actual stack trace → confirm or reject the encoding hypothesis.
2. If confirmed: one-line fix to `.github/workflows/release.yml` — add `env: PYTHONIOENCODING: utf-8` to the `Run reproducible-release validation` step, or change `verify_copilot_run.py` to ASCII output (more invasive but more robust).
3. If rejected: debug from the actual stack trace; possibly a different cause (subprocess quoting on Windows, glob pattern, or something else).
4. Write `analysis/014` confirming root cause + fix.

## 🛡️ Process discipline applied in this report

- The diagnosis is **pending evidence**, not asserted. We explicitly say "Most likely" not "Caused by".
- Prior confidence claims are **demoted** in a tracking table, not glossed over.
- No commit was made on inference alone. The next commit will be **after** evidence.

This is the discipline the project is built around; failing to follow it in its own incident report would invalidate the whole point.

---

*This report is **open**. It will be marked `RESOLVED` once a root cause is confirmed and a fix lands, presumably in `analysis/014`.*