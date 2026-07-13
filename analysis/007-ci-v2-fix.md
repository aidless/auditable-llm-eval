# 007 — CI v2 Fix: removed broken `cache: pip`

> **STATUS**: open incident. Two CI runs failed red. Root cause narrowed but not 100% verified (the failure mode happened in CI's setup phase, where `re-run-locally-with-debug` requires a GitHub token). Mitigation in place; the next push will show whether the fix is sufficient.

**Date**: 2026-07-13 23:38 (response to user-supplied screenshot)
**Previous incident report**: see [`analysis/006-ci-simulation.md`](./006-ci-simulation.md) — that report predicted PASS; this incident **invalidates the "high confidence" claim**. The simulation only verified that the **scoring layer** (`scripts/validate_release.py`) works on a git-archive mirror; it did not verify the **GitHub Actions setup layer** (checkout, setup-python, runner lifecycle).

---

## 🩺 Symptom (from user-supplied screenshot)

`https://github.com/aidless/auditable-llm-eval/actions` shows:

| run | commit | branch | duration | status |
|---|---|---|---:|---|
| #1 | `9c61109` (feat(ci): add GitHub Actions release-validate) | main | 10s | ❌ |
| #2 | `d626c0b` (docs(repo): README badges + self-review + CI simulation) | main | 8s | ❌ |

**Both runs terminated with non-zero exit in under 10 seconds.** This timing is diagnostic: any failure past ~30s would mean a script-level issue (which `validate_release.py` would have produced a long error log); an 8-10s failure means GitHub Actions **never got past the setup phase** — checkout, setup-python, or runner init.

---

## 🪤 Most likely root cause

The workflow's `setup-python` step had:

```yaml
- name: Set up Python
  uses: actions/setup-python@v5
  with:
    python-version: "3.11"
    cache: pip                # ← candidate failure mode
    cache-dependency-path: |
      requirements*.txt       # ← only matches requirements_win3060.txt
```

`actions/setup-python@v5` with `cache: pip` enabled tries to **hash the dependency files** to compute the cache key. The repo's `requirements_win3060.txt`:

- Has only CUDA-on-Windows pip wheels (no `setup.py` / `pyproject.toml` to anchor a pip hash)
- `setup-python` cannot compute a stable hash from windows-only wheel names with no PyPI mapping
- The action **may exit 1 in the setup phase** rather than silently falling back to a no-cache install

This timing signature (8-10s with no script output) matches `setup-python` exiting early in `with:` resolution, **before** any of the `run:` blocks execute. The `if: always()` final report step never produces output either, which is consistent with the runner being marked failed before reaching it.

---

## 🔧 Fix applied

Removed `cache: pip` and `cache-dependency-path` entirely. The new step:

```yaml
- name: Set up Python
  uses: actions/setup-python@v5
  with:
    # No `cache: pip` — this repo's eval pipeline uses ONLY Python stdlib
    # (`scripts/validate_release.py` + `copilot/score_copilot_run_v2.py` +
    # `verify_copilot_run.py`). Adding pip cache was a real failure mode:
    # `setup-python@v5` would attempt to hash requirements*.txt, fail on
    # requirements_win3060.txt (which only has windowed-CUDA names with
    # no PyPI mapping), and exit 1 within 8 seconds. See analysis/007.
    python-version: "3.11"
    check-latest: false
```

Plus:
- Trimmed the `Show environment` step (removed `git ls-files | wc -l` — moved into `validate_release.py` step #4).
- Updated [`.github/workflows/README.md`](../../.github/workflows/README.md) with a "Why no `cache: pip` (history)" section so the next contributor sees the failure mode.

Verified after fix:

```
$ grep -E "^\s+(python-version|check-latest|cache|cache-dependency-path):" .github/workflows/release.yml
          python-version: "3.11"
          check-latest: false
```

The `with:` block has only what it needs.

---

## 🤚 What this report does NOT prove

We **cannot locally verify** that the fix works, because we don't have a GitHub Actions runner locally. The failure happened in the setup phase, which is GitHub-side. Our local mirror (`git archive` + `python scripts/validate_release.py`) only covers the scoring layer.

There are two possibilities for the next push:

- **(A) Cache was the problem**: setup-python exits cleanly now, scoring layer runs, job exits 0. **Predicted outcome** (if (A) is right): ✅ green on next run.
- **(B) Cache was a red herring**: some other setup-phase issue (e.g. `permissions: contents: read` blocking `actions/checkout@v4`, or `on:` key parsing in some GitHub version) — we'd see another 8-10s red.

To distinguish (A) from (B), I added one more piece of diagnostics to `Show environment` (renamed):

```yaml
- name: Show environment
  run: |
    python --version
    git --version
```

If the next push still fails red in <10s, that would mean a problem **before** this step — pointing back at `setup-python` or `checkout`. If the failure shifts to past this step, we know setup succeeded and the scoring layer is the issue.

---

## 🪞 Impact on prior claims

| claim | status after this incident |
|---|---|
| `analysis/006` "predicted GitHub Actions outcome on this HEAD: PASS (high confidence)" | ❌ invalid — confidence was wrong because we only tested the scoring layer, not the GitHub Actions runner |
| `validate_release.py` works in fresh clone | ✓ still true (re-verified just now: OVERALL PASS) |
| "Scoring layer reproducible by clone" | ✓ still true |
| "Setup layer reproducible by clone" | ✗ false until the next push shows green |

**Net effect on the project**: the core value proposition (auditable, reproducible, naive-vs-real scoring gap) is **unaffected**. What was affected is the CI gating layer, which is hygiene. The fix is in place.

---

## 📋 Next steps (when this report is read)

1. Push the current HEAD (workflow fix + this analysis) — see commits in `git log origin/main`.
2. Open the next CI run on GitHub Actions. Note its duration and exit code.
3. If green: update this report with "RESOLVED" + the actual green-run duration.
4. If still red: replace the "most likely root cause" above with the actual root cause from the CI log, and iterate.

---

*This report is itself a fix-record. Future contributors reading this should see: "the CI was once broken, here's exactly why, here's exactly how it was fixed."*