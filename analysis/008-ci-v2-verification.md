# 008 — CI v2 Verification: Python 3.11 + fresh-clone local stand-in

> **STATUS**: post-fix verification, run on 2026-07-13 23:50 after fix landed at `a0a6abe`. Conclusion: scoring layer is **verified to PASS under Python 3.11 on a fresh clone**. Only the GitHub Actions setup layer (`actions/setup-python@v5` itself, `actions/checkout@v4`) remains unverified locally.

## Why this report exists

`analysis/007` recorded the incident (2 red CI runs) and the fix (remove `cache: pip`). The fix is now committed and pushed (`a0a6abe`). But the fix's effectiveness can only be **proven** by the next CI run on GitHub itself, which we cannot trigger locally without a Docker daemon and a usable GitHub Actions runner.

What we **can** do is verify everything **upstream and downstream** of `actions/setup-python@v5`:

1. ✅ **YAML structure**: the workflow file is parseable and has only `python-version: "3.11"` + `check-latest: false` in the `with:` block of setup-python (no `cache: pip`, no `cache-dependency-path`).
2. ✅ **Python 3.11 compatibility**: we have a real Python 3.11.6 binary now, and the entire `scripts/validate_release.py` pipeline runs cleanly under it.
3. ✅ **Fresh-clone equivalence**: a `git archive` mirror of HEAD runs the pipeline to OVERALL PASS on Python 3.11, exit 0.
4. ⚠ **GitHub Actions runner layer**: not locally verifiable — Docker daemon does not start on this machine (WSL2 backend not configured).

## What was tested

### Test 1 — Python 3.11 runs validate_release.py on real repo

```bash
PY311="C:\Users\Administrator\.workbuddy\scratch\python311\python\python.exe"
$PY311 --version
# Python 3.11.6

cd F:/test/2026-07-12-00-12-06
$PY311 scripts/validate_release.py
# ... [1] PASS [2] PASS [3] PASS × 2 runs [4] PASS
# OVERALL: PASS
```

This proves:
- Our Python code is **3.11-compatible** (not just 3.13)
- The `with: { python-version: "3.11" }` choice in setup-python is **safe** — we don't depend on any 3.13-only stdlib feature

### Test 2 — Python 3.11 on a fresh-clone mirror

```bash
git archive HEAD | tar -x -C /tmp/ci-simulation-v2/auditable-llm-eval
# mirrored 81 files
cd /tmp/ci-simulation-v2/auditable-llm-eval
$PY311 scripts/validate_release.py
# ... [1] PASS [2] PASS [3] PASS × 2 runs [4] WARN (no .git/) → treated PASS in summary
# OVERALL: PASS, exit 0
```

This proves:
- The 81 tracked files in HEAD are sufficient for a PASS — no hidden local-only state
- The exit code is 0 (the CI gate will pass if everything upstream is fine)
- Check #4 (`gitignore sanity`) correctly **downgrades to WARN** in a non-git directory rather than FAIL — proving the script handles this edge case gracefully

## What is still unverified

- **actions/setup-python@v5 actually succeeds** on `ubuntu-latest` with the simplified `with:` block
- **actions/checkout@v4** correctly fetches the 81 tracked files (we have no reason to doubt this, but it's unverified)
- **Runner filesystem paths** match what our scripts expect (we use `pathlib.Path` throughout, so this is essentially guaranteed, but untested)
- **GitHub-hosted `ubuntu-latest` has Python 3.11 available** (it does, per GitHub's runner images, but pinned-version behavior across runner versions is not tested)

## Predicted outcome on the next GitHub Actions run

**PASS, exit 0, ~30 seconds wall time.**

Why this is now a high-confidence prediction (upgraded from `analysis/006`'s claim, which was invalidated by the actual incident):

- ✅ YAML structure is sane
- ✅ Python 3.11 compatibility verified locally
- ✅ Fresh-clone + 3.11 = PASS verified locally
- ✅ The fix removed the cache config that was the **only identified failure mode** for the previous red runs
- ❌ The remaining unverified surface is the GitHub Actions runner itself — and it has been running thousands of similar workflows daily across millions of repos without action setup failures on the simplified config

## What to do if it still goes red

If the next push's CI still fails red, the failure mode will tell us which layer is broken:

| Failure duration | Likely layer | Next diagnostic |
|---|---|---|
| <10s | setup-python / checkout | `setup-python@v5` itself (regression in action version?); try v4 instead |
| ~30s | python --version step | Python install or PATH issue |
| >30s | validate_release.py step | Scoring layer regression — run locally to see exact output |
| Different | unknown | Fetch the CI log; that contains the exact step that failed |

## Reproducing this report

```bash
# 1. Get Python 3.11
mkdir -p /tmp/py311 && cd /tmp/py311
curl -sSL -o py311.tar.gz "https://github.com/indygreg/python-build-standalone/releases/download/20231002/cpython-3.11.6+20231002-x86_64-pc-windows-msvc-shared-install_only.tar.gz"
tar -xzf py311.tar.gz
PY311=/tmp/py311/python/python.exe

# 2. Real-repo test
cd /path/to/auditable-llm-eval
$PY311 scripts/validate_release.py

# 3. Fresh-clone test
git archive HEAD | tar -x -C /tmp/ci-simulation-v2/auditable-llm-eval
cd /tmp/ci-simulation-v2/auditable-llm-eval
$PY311 scripts/validate_release.py
```

Both should print `OVERALL: PASS` with `exit 0`.

---

*This report's role is to upgrade the post-`a0a6abe` confidence from "fixed, hope it works" to "verified to the limit of what a local environment without Docker can verify."*