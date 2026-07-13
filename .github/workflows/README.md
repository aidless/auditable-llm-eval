# GitHub Actions workflows

CI that gates every push to `main` and every PR on the reproducible-release discipline.

## `release.yml` — `release-validate`

Runs [`scripts/validate_release.py`](../../scripts/validate_release.py) on every push to `main`, every PR, and on manual dispatch. The script exits 0 only if all four checks pass:

1. **scorer selftest** (`copilot/score_copilot_run_v2.py --selftest`)
2. **spec ↔ code consistency** (`specs/scoring-rules.json` match `DISPATCH` keys, 10/10)
3. **verifier on every committed run** (`verify_copilot_run.py` × N runs)
4. **gitignore sanity** (no `.zip` / no weights / no `.workbuddy/` in tracked tree)

### Why no Ollama / GPU dependency

Check #3 runs the scorer against **committed `outputs.jsonl`**, not against the live model. So GitHub-hosted `ubuntu-latest` runners (no GPU) can verify the headline numbers without spinning up an Ollama server. Anyone can re-derive the result in a CI sandbox.

This is the headline property of the repo: **reproducibility tests should not require the model**.

### Badge

Add to README:

```markdown
[![release-validate](https://github.com/aidless/auditable-llm-eval/actions/workflows/release.yml/badge.svg)](https://github.com/aidless/auditable-llm-eval/actions/workflows/release.yml)
```

### What CI does NOT do

- ❌ Does not retrain models (too expensive for CI; intentional)
- ❌ Does not require a GPU runner
- ❌ Does not check Ollama-versioned model tags (those change on a different cadence)
- ❌ Does not push Release assets (no token in env; release creation is a manual UI step)

Those gaps are by design — the discipline layer catches spec / behavior drift. Model evolution is monitored via committed runs (each new run is a new verifiable artifact).

### Skipping CI

In a real emergency you can prefix a commit message with `[skip ci]` (GitHub Actions parses this). Don't do this casually — the discipline is what makes the headline numbers trustworthy.