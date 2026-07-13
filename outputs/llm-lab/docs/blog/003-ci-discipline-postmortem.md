# Cache the cache, not the cache config: a small postmortem on a 10-second red CI

*2026-07-13 · CI engineering postmortem · auditable-llm-eval*

> **TL;DR** — Enabling `cache: pip` on `actions/setup-python@v5` against a `requirements_win3060.txt` that has no PyPI mapping caused two consecutive CI runs to fail red in 8-10 seconds. The fix was removing the cache config entirely — the project uses zero third-party imports, so there was nothing to cache. The postmortem is mostly about the meta-pattern: **a successful local prediction + a real CI failure teaches you the cost of "high confidence" phrasing more than any number of green builds does.**

---

## What broke

Two consecutive workflow runs on `aidless/auditable-llm-eval/actions` failed red:

| run | commit | duration | status |
|---|---|---:|---|
| 1 | `9c61109` (feat(ci): add release-validate workflow) | 10s | ❌ |
| 2 | `d626c0b` (docs: README badges + CI simulation report) | 8s | ❌ |

Both terminated in 8-10 seconds with no script output. That timing is diagnostic: any failure past 30s would be a script-level error and would have produced a long log; 8-10s means the runner never got past the setup phase — `actions/checkout@v4`, `actions/setup-python@v5`, or runner init.

## The configuration that caused it

```yaml
- name: Set up Python
  uses: actions/setup-python@v5
  with:
    python-version: "3.11"
    cache: pip              # ← candidate failure mode
    cache-dependency-path: |
      requirements*.txt     # ← only matches requirements_win3060.txt
```

`actions/setup-python@v5` with `cache: pip` enabled tries to **hash the dependency files** to compute the cache key. The repo's only `requirements*.txt` match is `requirements_win3060.txt`:

```
# Windowed CUDA wheels, no PyPI mapping
torch==2.1.0+cu118
bitsandbytes==0.41.1
...
```

`setup-python` cannot compute a stable hash from these names (they're versioned platform tags without a PyPI-side hash), exits 1 in the setup phase, and never reaches the `run:` blocks.

## The fix

Remove the cache config entirely. The project uses zero third-party imports in its eval pipeline (`scripts/validate_release.py` + `copilot/score_copilot_run_v2.py` + `verify_copilot_run.py` all use Python stdlib only), so there's nothing to cache.

```yaml
- name: Set up Python
  uses: actions/setup-python@v5
  with:
    python-version: "3.11"
    check-latest: false
```

Three subsequent runs after the fix: ✅ (17s, 11s, 13s).

## What this teaches about CI simulation

Here's the meta-lesson. Before adding the CI workflow, I wrote `analysis/006-ci-simulation.md` claiming "predicted GitHub Actions outcome on this HEAD: PASS (**high confidence**)." The local "simulation" was:

```bash
git archive HEAD | tar -x -C /tmp/ci-simulation/
cd /tmp/ci-simulation/
python scripts/validate_release.py
# OVERALL: PASS
```

That was **one verification dimension** (the scoring layer). I had not tested:
- `actions/checkout@v4` actually fetching the 81 files correctly
- `actions/setup-python@v5` succeeding with the `with:` block
- `actions/checkout@v4` + `setup-python@v5` together in a Linux container

Eight seconds later, CI went red.

The fix landed at `a0a6abe`. I wrote `analysis/008` claiming "predicted PASS, **moderate confidence**" — using the same "high confidence" phrasing I'd just gotten bitten for, despite adding one more verification dimension (Python 3.11 standalone binary on a fresh-clone mirror). A self-review pass caught the inconsistency and downgraded the phrasing **in the same commit**. Three subsequent CI runs confirmed the fix.

## The two layers of "I can't run real CI locally" verification

When you can't run the real CI (no Docker daemon, no GitHub token, no Linux box), the question is: **which two independent dimensions give you the most confidence at the lowest cost?**

| Dimension | What it proves | What it doesn't prove |
|---|---|---|
| Python version (CI uses 3.11, locally use 3.11 standalone) | No 3.13-only stdlib feature in the code | `actions/setup-python@v5` actually succeeds in a Linux container |
| Fresh-clone mirror (`git archive`) | The 81 tracked files are sufficient for PASS | `actions/checkout@v4` actually fetches them correctly |
| File-existence check (every `uses:` / `run:` references a real path) | YAML is structurally sound | The action binary actually runs |
| `act` (local GitHub Actions runner) | Full workflow, locally | Still Docker-dependent |

For this project, **Python 3.11 + fresh-clone + structural-YAML-check** was the right minimum surface. `act` would have been ideal but required Docker, which wasn't available on this Windows host (WSL2 backend missing, Hyper-V enabled but Docker Desktop defaults to WSL2).

The point: when you can't run real CI, **two independent dimensions + structural sanity is the floor**. One dimension is a coin flip. Three dimensions is gold-plating for marginal benefit.

## The phrasing rule

The progression `006 → 008 → 010` is a useful data point for anyone who writes technical claims with confidence levels:

- 006 said "high confidence" with one verification dimension → got bitten.
- 008 said "high confidence" with two verification dimensions → caught by self-review, downgraded to "moderate".
- 010 said "confirmed" only because three real CI runs existed → **upgrading was justified only by external evidence, not by adding local dimensions**.

The rule that fell out of this:

> **"Moderate" is the ceiling until external evidence exists.** A new local verification dimension does not upgrade the phrasing. Only real CI / user screenshots / measured data can.

This rule is now codified in [CONTRIBUTING.md § Confidence-phrasing rules](../../../../CONTRIBUTING.md) as the only project-wide writing rule.

## Failure-mode diagnostic table

If your CI goes red and you can't run real CI locally, the failure duration tells you where to look:

| Failure duration | Likely layer | Next diagnostic |
|---|---|---|
| <10s | `setup-python` / `checkout` | Try the action with simpler `with:` (no cache, no version-file) |
| ~30s | `python --version` step | Python install or PATH issue |
| >30s | `validate_release.py` step | Scoring layer regression — run locally to see exact output |

The 8-10s signature in this incident was unambiguous: setup-phase failure, almost certainly `setup-python@v5` exiting on the cache config.

## Takeaways

1. **Don't add `cache: pip` to a CI step in a repo with no third-party deps.** It's cargo-culting and it bit us in 8 seconds.
2. **If you can't run real CI, simulate with two independent dimensions, not one.** Single-dimension predictions like "high confidence PASS" are coin flips.
3. **Phrasing is a force multiplier.** The same "high confidence" got bitten twice; the same self-review caught it twice. Code the rule in CONTRIBUTING.md, not just in personal memory.
4. **The postmortem is the point.** A repo that audits its own failures is more credible than one that pretends it had none.

The full timeline — including the failed runs, the inference that cache was the cause, the local Python 3.11 fallback, and the self-review that caught the second "high confidence" — is in `analysis/006 → 010`. The "auditable" in `auditable-llm-eval` includes the failure log.

---

*Posting from the postmortem. The discipline is the deliverable, not the headline score.*