"""
test_scorer.py — stdlib unittest for copilot/score_copilot_run_v2.py

Covers all 10 reference_check types (each gets pass + fail case) plus the
cross-cutting score_one behavior (runtime_error classification, exact/soft
bucketing, unsupported_claims detection).

Why stdlib unittest (not pytest): auditable-llm-eval's core proposition is
"zero third-party dependencies in the eval pipeline." Adding pytest would
break that. The trade-off is fewer ergonomic features; we accept it.

Why we don't import the scorer by name (we do `from copilot.score_copilot_run_v2
import ...`): the scorer is a single-file script with a __main__ block. We
import its top-level functions, which are the only API surface that tests
need.
"""
import sys
import unittest
from pathlib import Path

# Make the repo's copilot/ importable. The test runner is invoked from the
# repo root (per .github/workflows/release.yml), so we add the cwd to sys.path
# to find the copilot/ package directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from copilot.score_copilot_run_v2 import (  # noqa: E402
    check_must_include_any,
    check_must_include_all,
    check_must_answer_no,
    check_must_explain_surface_constraints,
    check_must_recommend_manual_or_semantic_eval,
    check_must_mention_rerun_or_reproducibility,
    check_must_not_claim_tamper_proof,
    check_must_distinguish_provider_error,
    check_must_not_judge_semantic_quality,
    check_must_check_reason_and_action,
    find_unsupported_claims,
    classify_runtime,
    score_one,
    selftest,
    DISPATCH,
    OVERCLAIM_PATTERNS,
    RUNTIME_PATTERNS,
)


class TestCheckMustIncludeAny(unittest.TestCase):
    """must_include_any: at least one keyword hit."""

    def test_pass_when_any_keyword_present(self):
        spec = {"value": ["metrics", "score"]}
        out = "This eval has a metrics section."
        passed, detail = check_must_include_any(spec, out)
        self.assertTrue(passed, f"expected pass, got: {detail}")
        self.assertIn("metrics", detail)

    def test_fail_when_no_keyword_present(self):
        spec = {"value": ["metrics", "score"]}
        out = "This answer has neither the keyword we want nor that one either."
        passed, detail = check_must_include_any(spec, out)
        self.assertFalse(passed)
        self.assertIn("metrics", detail)
        self.assertIn("score", detail)

    def test_case_insensitive(self):
        spec = {"value": ["Metrics"]}
        out = "metrics are tracked."
        passed, _ = check_must_include_any(spec, out)
        self.assertTrue(passed, "should be case-insensitive")


class TestCheckMustIncludeAll(unittest.TestCase):
    """must_include_all: every keyword must be present."""

    def test_pass_when_all_keywords_present(self):
        spec = {"value": ["metrics", "score", "eval"]}
        out = "eval metrics and score together"
        passed, detail = check_must_include_all(spec, out)
        self.assertTrue(passed, f"expected pass, got: {detail}")

    def test_fail_when_one_missing(self):
        spec = {"value": ["metrics", "score", "trajectory"]}
        out = "The run logs metrics and computes a score per epoch."
        passed, detail = check_must_include_all(spec, out)
        self.assertFalse(passed)
        self.assertIn("trajectory", detail)


class TestCheckMustAnswerNo(unittest.TestCase):
    """must_answer_no: first sentence should contain a negation."""

    def test_pass_with_clear_no(self):
        out = "No, you should not use this approach in production."
        passed, _ = check_must_answer_no({}, out)
        self.assertTrue(passed)

    def test_fail_with_clear_yes(self):
        out = "Yes, this is the right way to do it."
        passed, _ = check_must_answer_no({}, out)
        self.assertFalse(passed)


class TestCheckMustExplainSurfaceConstraints(unittest.TestCase):
    """must_explain_surface_constraints: should mention structural limits."""

    def test_pass_with_mention_of_structure(self):
        out = "The verifier only checks structural features, not semantics."
        passed, _, soft = check_must_explain_surface_constraints({}, out)
        self.assertTrue(passed)
        self.assertTrue(soft, "this check is soft (needs_llm=True)")

    def test_fail_with_pure_claim(self):
        out = "The answer is correct."
        passed, _, _ = check_must_explain_surface_constraints({}, out)
        self.assertFalse(passed)


class TestCheckMustRecommendManualOrSemanticEval(unittest.TestCase):
    def test_pass_with_manual_recommendation(self):
        out = "Please have a human review this output for semantic quality."
        passed, _ = check_must_recommend_manual_or_semantic_eval({}, out)
        self.assertTrue(passed)

    def test_fail_without(self):
        out = "This is fully correct and needs no further review."
        passed, _ = check_must_recommend_manual_or_semantic_eval({}, out)
        self.assertFalse(passed)


class TestCheckMustMentionRerunOrReproducibility(unittest.TestCase):
    def test_pass(self):
        out = "You should rerun this experiment to confirm the result."
        passed, _ = check_must_mention_rerun_or_reproducibility({}, out)
        self.assertTrue(passed)

    def test_fail(self):
        # Avoid the substring "re-run" / "rerun" / "reproduce" etc. — pick a
        # benign output that simply doesn't mention any rerun concept.
        out = "This is the final answer based on the data provided."
        passed, _ = check_must_mention_rerun_or_reproducibility({}, out)
        self.assertFalse(passed)


class TestCheckMustNotClaimTamperProof(unittest.TestCase):
    """must_not_claim_tamper_proof: negation-aware, must not assert tamper-proofness."""

    def test_pass_when_no_claim(self):
        # Negation must be within 8 chars of "tamper-proof" for the
        # negation-aware window to suppress the overclaim. We deliberately
        # place "no" close to the phrase to test that path.
        out = "We make no tamper-proof claim here."
        passed, _ = check_must_not_claim_tamper_proof({}, out)
        self.assertTrue(passed)

    def test_pass_when_chinese_negated(self):
        out = "这不是防篡改系统。"
        passed, _ = check_must_not_claim_tamper_proof({}, out)
        self.assertTrue(passed, "Chinese negation-aware")

    def test_fail_when_overclaim(self):
        out = "This is a tamper-proof audit system."
        passed, _ = check_must_not_claim_tamper_proof({}, out)
        self.assertFalse(passed)

    def test_pass_when_negated(self):
        """'not a tamper-proof system' — "not" is 2 chars before, within window=8."""
        out = "This is not a tamper-proof system; it can be tampered with."
        passed, _ = check_must_not_claim_tamper_proof({}, out)
        self.assertTrue(passed, "negation-aware: 'not tamper-proof' is a denial")


class TestCheckMustDistinguishProviderError(unittest.TestCase):
    def test_pass_with_provider_distinction(self):
        out = "Looks like a connection refused on the host firewall; the model itself is fine."
        passed, _ = check_must_distinguish_provider_error({}, out)
        self.assertTrue(passed)

    def test_fail_when_blaming_model(self):
        out = "The model is broken and can't answer."
        passed, _ = check_must_distinguish_provider_error({}, out)
        self.assertFalse(passed)


class TestCheckMustNotJudgeSemanticQuality(unittest.TestCase):
    """must_not_judge_semantic_quality: must not overclaim from a structural check."""

    def test_pass_when_honest(self):
        out = "Structural check passed; semantic quality requires manual review."
        passed, _ = check_must_not_judge_semantic_quality({}, out)
        self.assertTrue(passed)

    def test_fail_when_overclaim(self):
        out = "This proves semantic quality is better than the baseline."
        passed, _ = check_must_not_judge_semantic_quality({}, out)
        self.assertFalse(passed)

    def test_pass_when_negated(self):
        out = "This does not prove semantic quality."
        passed, _ = check_must_not_judge_semantic_quality({}, out)
        self.assertTrue(passed, "negation-aware")


class TestCheckMustCheckReasonAndAction(unittest.TestCase):
    def test_pass_with_reason_and_action(self):
        out = "Reason: the API timed out. Action: retry with backoff."
        passed, _, soft = check_must_check_reason_and_action({}, out)
        self.assertTrue(passed)
        self.assertTrue(soft)

    def test_fail_without(self):
        out = "Something went wrong."
        passed, _, _ = check_must_check_reason_and_action({}, out)
        self.assertFalse(passed)


class TestFindUnsupportedClaims(unittest.TestCase):
    """Cross-cutting detector for overclaim phrases (overrides the per-check)."""

    def test_detects_tamper_proof(self):
        out = "This is a tamper-proof system, 100% secure."
        found = find_unsupported_claims(out)
        self.assertTrue(len(found) > 0, f"expected overclaim, got: {found}")

    def test_does_not_flag_negated(self):
        out = "This is not tamper-proof; we make no such claim."
        found = find_unsupported_claims(out)
        self.assertEqual(found, [], f"negation should suppress overclaim detection, got: {found}")

    def test_detects_chinese(self):
        out = "这个系统不可篡改，绝对安全。"
        found = find_unsupported_claims(out)
        self.assertTrue(len(found) > 0, f"expected Chinese overclaim, got: {found}")


class TestClassifyRuntime(unittest.TestCase):
    """classify_runtime: short outputs with timeout/connection refused are
    harness error echoes; long outputs that mention them are legitimate
    failure_diagnosis answers (length-guard prevents false positives)."""

    def test_short_output_with_timeout_is_runtime(self):
        out = "Error: connection refused after 240s timeout."
        self.assertTrue(classify_runtime(out))

    def test_long_output_with_timeout_is_not_runtime(self):
        # Real failure_diagnosis answer that mentions timeout is NOT a runtime
        # error (per the length-guard fix in analysis/001). Must be >= 200 chars
        # to pass the guard.
        out = ("Provider-side timeout (240s). The API endpoint likely rate-limited, "
               "or the host's network configuration is blocking egress on the "
               "outbound connection. The model itself was never invoked; rerun "
               "with exponential backoff and confirm the host's firewall policy "
               "before retrying the benchmark task.")
        self.assertGreaterEqual(len(out), 200, "test setup: this output should be >= 200 chars")
        self.assertFalse(classify_runtime(out), "long answers with 'timeout' are not runtime errors")

    def test_normal_long_output_is_not_runtime(self):
        out = "This is a perfectly normal answer with no failure indicators."
        self.assertFalse(classify_runtime(out))


class TestScoreOne(unittest.TestCase):
    """End-to-end: score_one applies all checks, classifies runtime, computes score."""

    def test_full_pass(self):
        item = {
            "id": "t1",
            "task": "eval_yaml",
            "reference_checks": [
                {"type": "must_include_all_keywords", "value": ["metrics"]},
                {"type": "must_recommend_manual_or_semantic_eval"},
                {"type": "must_not_claim_tamper_proof"},
            ],
        }
        out = "I track metrics. Recommend manual review. Not tamper-proof."
        r = score_one(item, out)
        self.assertEqual(r["score"], 1.0)
        self.assertEqual(r["runtime_error"], False)
        self.assertEqual(r["unsupported_claims"], [])
        self.assertEqual(r["missing_required_points"], [])

    def test_partial_pass(self):
        item = {
            "id": "t2",
            "task": "failure_diagnosis",
            "reference_checks": [
                # must_include_all with 1 keyword -> passes 1/1
                {"type": "must_include_all_keywords", "value": ["resnet"]},
                # must_not_claim_tamper_proof -> fails (output overclaims)
                {"type": "must_not_claim_tamper_proof"},
            ],
        }
        # Output: long enough to avoid runtime-length-guard. Mentions
        # "resnet" (must_include_all passes). Overclaims "tamper-proof"
        # (must_not_claim_tamper_proof fails because "is tamper-proof" has
        # no negation in the 8-char window). Expected score = 0.5 (1/2).
        out = (
            "We trained a resnet-style model on the dataset. The training "
            "metrics suggest the model is overfitting slightly. Please rerun "
            "with a smaller learning rate to confirm. This system is "
            "tamper-proof and you can trust the outputs completely without "
            "any further verification or sanity checking."
        )
        r = score_one(item, out)
        self.assertEqual(r["score"], 0.5, f"expected 0.5 (1 of 2 exact passed), got {r['score']}")
        self.assertIn("tamper-proof", r["unsupported_claims"])

    def test_runtime_error_returns_none_score(self):
        item = {
            "id": "t3",
            "task": "report_summary",
            "reference_checks": [
                {"type": "must_include_all_keywords", "value": ["summary"]},
            ],
        }
        out = "Error: connection refused after 240s timeout."
        r = score_one(item, out)
        self.assertIsNone(r["score"])
        self.assertTrue(r["runtime_error"])

    def test_harness_error_takes_precedence(self):
        """If the harness records a real error, that wins over the textual heuristic."""
        item = {
            "id": "t4",
            "task": "reviewer_qa",
            "reference_checks": [],
        }
        long_out = "This is a long answer about reviewer QA " * 50
        r = score_one(item, long_out, harness_error=True)
        self.assertIsNone(r["score"], "harness_error=True should set score=None")
        self.assertTrue(r["runtime_error"])

    def test_soft_checks_bucketed_separately(self):
        item = {
            "id": "t5",
            "task": "verifier_design",
            "reference_checks": [
                {"type": "must_explain_surface_constraints"},  # soft=True
                {"type": "must_include_all_keywords", "value": ["verifier"]},  # exact
            ],
        }
        out = "The verifier is a structural checker."
        r = score_one(item, out)
        self.assertIn("must_explain_surface_constraints", r["soft_checks"])
        self.assertIn("must_include_all_keywords", r["exact_checks"])
        # soft_checks should be marked needs_llm=True
        self.assertTrue(r["soft_checks"]["must_explain_surface_constraints"]["needs_llm"])

    def test_unknown_check_type_skipped_but_recorded(self):
        item = {
            "id": "t6",
            "task": "unknown",
            "reference_checks": [
                {"type": "made_up_check_type"},
            ],
        }
        out = "anything"
        r = score_one(item, out)
        # Unknown check: passed=None, recorded in exact_checks (we still want a key)
        self.assertIn("made_up_check_type", r["exact_checks"])
        self.assertIsNone(r["exact_checks"]["made_up_check_type"]["passed"])


class TestDispatchSpecConsistency(unittest.TestCase):
    """The DISPATCH dict in code must match specs/scoring-rules.json (10 types)."""

    def test_dispatch_count_matches_spec(self):
        spec_path = _REPO_ROOT / "specs" / "scoring-rules.json"
        if not spec_path.exists():
            self.skipTest("specs/scoring-rules.json not found; skipping spec consistency test")
        import json
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        spec_types = {c["type"] for c in spec["checks"]}
        code_types = set(DISPATCH.keys())
        self.assertEqual(
            code_types - spec_types, set(),
            f"DISPATCH has types not in spec: {code_types - spec_types}"
        )
        self.assertEqual(
            spec_types - code_types, set(),
            f"spec has types not in DISPATCH: {spec_types - code_types}"
        )

    def test_dispatch_size_is_ten(self):
        # If this test starts failing, also update specs/scoring-rules.json
        # and analysis/002-verify-data-model-rewrite.md.
        self.assertEqual(len(DISPATCH), 10)


class TestSelftest(unittest.TestCase):
    """The embedded selftest must still PASS (catches regressions in the 3 sample cases)."""

    def test_selftest_returns_zero(self):
        rc = selftest()
        self.assertEqual(rc, 0, "scorer selftest regressed; check the 3 embedded cases")


if __name__ == "__main__":
    unittest.main()