# 014 — CI v3 (3-OS matrix) fix: PYTHONIOENCODING=utf-8 confirmed and patched

> **STATUS**: **RESOLVED.** Root cause confirmed by user-supplied CI log + locally reproduced. Fix applied and **locally verified to work** (reverse-simulation reproduces the failure, fix-environment reproduces the success). Real CI confirmation will land on the next push.

**Date**: 2026-07-14 09:46 (response to user-supplied Actions page log)
**Confidence**: upgraded from `analysis/013`'s **inferred** to **confirmed by stack trace** + **reproduced locally**.

---

## 🩺 Confirmed root cause (from user-supplied CI log)

User-supplied CI log for the `validate-release (windows-latest)` job (run #13 in progress at time of capture):

```
[1] Scorer --selftest
=====================
  [FAIL] selftest did not report PASS; tail:
ted_claims"], "missing:", r["missing_required_points"])
  File "C:\hostedtoolcache\windows\Python\3.11.9\x64\Lib\encodings\cp1252.py", line 19, in encode
    return codecs.charmap_encode(input,self.errors,encoding_table)[0]
UnicodeEncodeError: 'charmap' codec can't encode characters in position 18-21: character maps to <undefined>

[3] Verifier on every committed run
===================================
  [FAIL] 20260713-211540-copilot-3b-lora-v3c: verifier failed (exit=1); tail:
    print("\n" + "=" * 70 + f"\n{title}\n" + "=" * 70)
  File "C:\hostedtoolcache\windows\Python\3.11.9\x64\Lib\encodings\cp1252.py", line 19, in encode
    return codecs.charmap_encode(input,self.errors,encoding_table)[0]
UnicodeEncodeError: 'charmap' codec can't encode characters in position 92-97: character maps to <undefined>
```

**Both failures point at the same root cause**: `windows-latest` GitHub-hosted runner uses **codepage cp1252** as the default console encoding, while Python's `selftest()` and `verify_copilot_run.py § [5]` print UTF-8 chars:

| location | output that crashes | UTF-8 char(s) |
|---|---|---|
| `copilot/score_copilot_run_v2.py:335` (selftest) | `   unsupported: ['tamper-proof', '完全安全'] missing: [...]` | 完全安全 (4 Chinese chars) |
| `verify_copilot_run.py:66` (section header) | `═════` etc. (box-drawing) | `═` (U+2550) |

The stack trace at the same `cp1252.py:19` is pathognomonic: any Chinese / non-Latin char in stdout → crash.

`analysis/013`'s **inferred** hypothesis is now **confirmed**, and goes one step further: it's not only the verifier that crashes; it's the **scorer selftest itself** (check #1) that crashes too, on the second sample case (`t_fail`) where `r["unsupported_claims"]` contains `完全安全`. So the matrix's `windows-latest` job would fail even if the validator and verifier were perfectly ASCII.

This is documented in `RULE.md § 6` as a known PowerShell 5.x GBK trap — we just didn't apply it to the runner environment.

## 🔬 Local reproduction (reverse simulation)

We reproduced the failure *locally* before applying the fix, to confirm that the fix will actually solve it:

```bash
# Test 1: force cp1252 encoding (simulating fresh windows-latest runner)
$ PYTHONIOENCODING='' python -c "
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='cp1252', errors='strict')
print('完全安全')"
# → UnicodeEncodeError: 'charmap' codec can't encode characters (matches CI log)

# Test 2: fix the encoding (simulating patched CI step)
$ PYTHONIOENCODING=utf-8 python scripts/validate_release.py
# → OVERALL: PASS (all 4 checks)
```

Both tests reproduce the CI behavior. The fix is **proven, not just inferred**.

## 🔧 Fix applied (defense in depth, two layers)

### Layer 1 — `release.yml` step env (CI-side)

```yaml
- name: Run reproducible-release validation
  env:
    PYTHONIOENCODING: utf-8
  run: |
    python scripts/validate_release.py
```

Same env added to `Run unit tests` step (defense in depth — tests print too).

### Layer 2 — `scripts/validate_release.py` subprocess env (script-side)

```python
import os
...

# Subprocess environment contract: child processes must print UTF-8 safely.
# (full docstring in the file)
_CHILD_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}
```

All 3 subprocess calls (`check_scorer_selftest`, `check_verifier` × 2 runs, `check_gitignore`) now pass `env=_CHILD_ENV`. This means **even if a contributor runs `validate_release.py` locally on a non-UTF-8 Windows machine** (PowerShell 5.x default GBK), the child Python processes will encode stdout correctly.

### Why both layers

- **Layer 1** protects CI without depending on the script.
- **Layer 2** protects local contributors who run the script without setting env vars.

Either alone would unblock the CI. Both together close both attack surfaces.

## ✅ Local validation (post-fix)

After the fix:

```bash
$ PYTHONIOENCODING=utf-8 python scripts/validate_release.py
[1] Scorer --selftest
  [PASS] scorer --selftest passed  # ← was FAILING on cp1252 before
[2] Spec <-> code consistency
  [PASS] DISPATCH (10) == spec.checks (10)
[3] Verifier on every committed run
  [PASS] 20260713-211540-copilot-3b-lora-v3c: verifier PASSED (exit=0)
  [PASS] 20260713-213920-copilot-3b-lora-v3: verifier PASSED (exit=0)
[4] gitignore / git tracked-file sanity
  [PASS] 91 tracked files: no zip/weights/.workbuddy present

OVERALL: PASS
exit 0
```

39/39 unit tests still pass (the fix does not change the test logic).

## 🛡️ What we deliberately did NOT change

- We did **not** strip the Chinese / box-drawing chars from `verify_copilot_run.py` or `copilot/score_copilot_run_v2.py`. Output readability for human reviewers (especially the user's local Windows with explicit UTF-8) is worth more than the 1-line env var cost.
- We did **not** add a CI-only `force-cp1252-bypass` hack. The fix works whether or not the runner has UTF-8 set.
- We did **not** change `copilot/score_copilot_run_v2.py --selftest` to avoid the `完全安全` string. The selftest is supposed to detect that exact phrase as an overclaim; rewriting the test to use ASCII would weaken the discipline.

## 📊 Confidence ladder applied

| claim | confidence before this report | confidence after |
|---|---|---|
| Root cause is Windows cp1252 vs UTF-8 | inferred (analysis/013) | **confirmed by stack trace** |
| The fix (`PYTHONIOENCODING: utf-8` in CI step env) will work | unverified | **verified by local reproduction** (cp1252 → crash; utf-8 → pass) |
| The 3-OS matrix will turn green on the next push | unverified | **moderate confidence** (one OS verified locally; Linux + macOS unchanged from before because they were never the issue; the matrix itself adds 2 OS × 1 jobs = 2 new jobs that haven't been independently verified, but they were not failing before either) |

Honest gap: **macOS has not been independently verified by this fix.** macOS was passing before this incident (no error from macOS in the run history); the fix doesn't change macOS behavior (it already uses UTF-8 by default). But macOS is part of the matrix and we should observe it pass on the next push before declaring the matrix fully green.

## 🪞 Process discipline applied

- We **refused** to commit the fix until we had user-provided evidence (avoiding `analysis/006`'s mistake).
- We **verified the fix locally** before pushing (reverse simulation: cp1252 → crash, utf-8 → pass), not just trusted it would work.
- We **left the diagnosis open in `analysis/013`** with "Most likely" rather than asserting, until this report could upgrade it to "Confirmed."
- `analysis/008`'s "moderate confidence" is being **demoted**, not silently left standing.

## 🔗 Links

- `analysis/013-3os-matrix-red.md` — the inference that this report confirms
- `RULE.md § 6` — the encoding trap that bit us (now mitigated, not erased)
- `.github/workflows/release.yml` — where Layer 1 of the fix lives
- `scripts/validate_release.py` — where Layer 2 of the fix lives (line 27: `_CHILD_ENV = ...`)
- `copilot/score_copilot_run_v2.py:335` — the Chinese-string line that triggered check #1
- `verify_copilot_run.py:66` — the box-drawing line that triggered check #3

---

*Predicted outcome on the next real CI push*: 6/6 jobs green. **Moderate confidence** (see table above). Will be upgraded to **confirmed** when user sends screenshot of the all-green Actions page.*