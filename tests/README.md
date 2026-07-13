# tests/

Stdlib `unittest` tests for the auditable-llm-eval pipeline. **No third-party test dependencies** (no `pytest`, no `nose`, no `tox`) — keeping the project at zero third-party deps is part of its core proposition.

## How to run

```bash
# From the repo root:
python -m unittest discover -s tests -v

# Or as a one-liner from anywhere (the runner walks into the tests/ dir):
python -m unittest discover -s tests
```

A passing run looks like:

```
Ran 39 tests in 0.005s
OK
```

A failing run prints `FAIL: test_name (ClassName.test_method)` followed by a traceback.

## What is covered

`test_scorer.py` (39 cases, the only file in this directory for now):

| Test class | What it asserts |
|---|---|
| `TestCheckMustIncludeAny` | `must_include_any_keywords` check, including case-insensitivity |
| `TestCheckMustIncludeAll` | `must_include_all_keywords` check, including "one missing" failure path |
| `TestCheckMustAnswerNo` | `must_answer_no` first-sentence negation check |
| `TestCheckMustExplainSurfaceConstraints` | `must_explain_surface_constraints` soft check |
| `TestCheckMustRecommendManualOrSemanticEval` | `must_recommend_manual_or_semantic_eval` |
| `TestCheckMustMentionRerunOrReproducibility` | `must_mention_rerun_or_reproducibility` |
| `TestCheckMustNotClaimTamperProof` | `must_not_claim_tamper_proof` — including Chinese + English negation paths (window=8) |
| `TestCheckMustDistinguishProviderError` | `must_distinguish_provider_error` |
| `TestCheckMustNotJudgeSemanticQuality` | `must_not_judge_semantic_quality` — negation-aware |
| `TestCheckMustCheckReasonAndAction` | `must_check_reason_and_action` soft check |
| `TestFindUnsupportedClaims` | cross-cutting overclaim detector (Chinese + English) |
| `TestClassifyRuntime` | length-guard fix from `analysis/001` — short = harness echo, long = real answer |
| `TestScoreOne` | end-to-end: full pass / partial pass / runtime_error / harness_error / soft bucketing / unknown check |
| `TestDispatchSpecConsistency` | DISPATCH keys (10) match `specs/scoring-rules.json` (10) |
| `TestSelftest` | the embedded 3-case `selftest()` still returns 0 |

## What is **not** covered (deliberately)

- `verify_copilot_run.py` is a `__main__` script (no module API), so its
  tests would require `subprocess` plumbing that adds noise without much
  coverage value at this stage. The integration test that *does* exercise
  it is `scripts/validate_release.py` step #3 (run in CI on every push).
- `eval/run_copilot_eval.py` requires a live ollama instance. Not
  unit-tested; covered end-to-end by manual runs committed under
  `outputs/llm-lab/datasets/llm_lab_copilot/runs/`.

## CI integration

`scripts/validate_release.py` checks #1 runs `copilot/score_copilot_run_v2.py
--selftest` (3 embedded cases). The new `tests/` directory is a **second
gate**: `unittest discover` runs in CI on every push. If a contributor
breaks a check type, both gates must agree before green.

The CI step is in `.github/workflows/release.yml` as `Run unit tests`. It
is idempotent — if `tests/` is missing, the step skips (with a clear log
message) rather than failing. The pipeline still works without tests; it
just doesn't have a second gate.

## Why not pytest?

The auditable-llm-eval proposition is "zero third-party dependencies in
the eval pipeline" — the same proposition that caused the `cache: pip`
incident (analysis/007) when we added a non-existent pip cache. Adding
`pytest` would require `requirements-dev.txt` + `pip install pytest` in
CI + a third party trusted to keep working. Stdlib `unittest` is
sufficient for the cases we need to assert and adds zero new failure
surfaces. The ergonomic cost (less pretty output, no `parametrize`) is
acceptable for a project of this size.

If the test suite grows to > 100 cases, reconsider.