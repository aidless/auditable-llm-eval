# scripts/

One-shot automation that backs the disciplines codified in [`specs/`](../specs/) and [`analysis/`](../analysis/).

## `validate_release.py`

Run the full reproducible-release local validation gate:

```bash
python scripts/validate_release.py
```

Exits 0 only if all four checks pass:

1. `copilot/score_copilot_run_v2.py --selftest`
2. `specs/scoring-rules.json` ↔ code `DISPATCH` consistency (10 types / 10)
3. `verify_copilot_run.py` on every committed run under `outputs/llm-lab/datasets/llm_lab_copilot/runs/*/`
4. Git tracked-file sanity: no `.zip`, no model weights, no `.workbuddy/`

This is the same script invoked by [GitHub Actions](../.github/workflows/release.yml) on every push to `main` and every PR.

## Source of truth

This script is **mirrored** from the user-level skill:

- Skill canonical home: `~/.workbuddy/skills/reproducible-publish/scripts/validate_release.py`
- Repo mirror: `scripts/validate_release.py`

If the two diverge, the skill wins — please sync the repo copy back from the skill and re-run validation to confirm.

## Customizing

```bash
# different repo layout (e.g., your own scoring rules)
python scripts/validate_release.py \
  --repo-root . \
  --scorer path/to/your_scorer.py \
  --verifier path/to/your_verifier.py \
  --spec path/to/your/spec.json \
  --runs-glob "path/to/runs/*/" \
  --dataset path/to/test.jsonl
```

All four checks remain, only the paths change.