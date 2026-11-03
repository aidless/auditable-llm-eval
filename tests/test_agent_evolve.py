"""agent_platform.evolve -- the self-evolution loop's triage invariants.

The loop is only as good as its classification, so these lock the three that
keep it from becoming a noise source or a rubber stamp:

  1. an unflagged tool that is NOT in the labeled set is benign/unknown ->
     review, never a candidate;
  2. an unflagged tool that IS labeled poison is a confirmed miss -> candidate;
  3. --fail-on-proposal reddens on confirmed misses only.

Signals that are their own category (usage_unauthorized, binding_mismatch) must
not be mis-described as benign.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "_test_agent_platform_evolve", REPO / "agent_platform" / "evolve.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


evolve = _load()
has_guard = unittest.skipUnless(
    (REPO.parent / "mcp-guard" / "tasks" / "cases.jsonl").exists(),
    "mcp-guard checkout (with cases.jsonl) not found",
)


class TestTierClassification(unittest.TestCase):
    def test_benign_unflagged_tool_is_review_not_candidate(self):
        poison = {"send_message"}  # labeled set: get_weather is NOT poison
        sig = {"signal": "tool_unflagged", "tool": "get_weather", "called": False}
        self.assertEqual(evolve._tier(sig, poison), "review")

    def test_labeled_poison_unflagged_is_confirmed(self):
        poison = {"send_message"}
        sig = {"signal": "tool_unflagged", "tool": "send_message", "called": False}
        self.assertEqual(evolve._tier(sig, poison), "confirmed")

    def test_ambiguous_name_is_never_confirmed(self):
        # cases.jsonl uses `send_email` for both a poison and a benign tool.
        poison = {"send_email"}
        sig = {"signal": "tool_unflagged", "tool": "send_email", "called": False}
        self.assertEqual(evolve._tier(sig, poison, ambiguous={"send_email"}), "review")

    def test_declared_boundary_is_not_a_new_miss(self):
        poison = {"run_cmd"}
        sig = {"signal": "tool_unflagged", "tool": "run_cmd", "called": False}
        self.assertEqual(
            evolve._tier(sig, poison, boundaries={"run_cmd"}), "known_boundary")

    def test_confirmed_signal_set_matches_two_tier_design(self):
        self.assertEqual(
            evolve.CONFIRMED_SIGNALS,
            ("called_tool_unflagged", "tool_unflagged"),
        )
        for s in evolve.REVIEW_SIGNALS:
            self.assertIn(s, ("usage_unauthorized", "binding_mismatch"))


@has_guard
class TestBuildReport(unittest.TestCase):
    def test_benign_tool_yields_no_candidate(self):
        report = evolve.build_report(
            [{"signal": "tool_unflagged", "tool": "get_weather", "called": False,
              "evidence": {}}],
            "tools.json", poison={"send_message"})
        tier = report["tier"]
        self.assertEqual(tier["confirmed_misses"], [])
        self.assertEqual(tier["review"], ["get_weather"])
        self.assertEqual(report["rule_coverage_gap"]["candidates"], [])

    def test_confirmed_miss_becomes_candidate_with_real_case_schema(self):
        report = evolve.build_report(
            [{"signal": "tool_unflagged", "tool": "send_message", "called": False,
              "evidence": {}}],
            "tools.json", poison={"send_message"})
        candidates = report["rule_coverage_gap"]["candidates"]
        self.assertEqual([c["name"] for c in candidates], ["send_message"])
        # Schema-aligned with mcp-guard cases.jsonl plus a provenance block.
        for key in ("name", "description", "inputSchema", "label", "gold_rules", "proposal"):
            self.assertIn(key, candidates[0])
        self.assertEqual(candidates[0]["label"], "poison")
        self.assertEqual(candidates[0]["proposal"]["signal"], "tool_unflagged")

    def test_seen_ledger_suppresses_known_tools(self):
        report = evolve.build_report(
            [{"signal": "tool_unflagged", "tool": "send_message", "called": False,
              "evidence": {}}],
            "tools.json", poison={"send_message"}, seen={"send_message"})
        self.assertEqual(report["n_signals"], 0)
        self.assertEqual(report["n_seen_suppressed"], 1)
        self.assertEqual(report["rule_coverage_gap"]["candidates"], [])

    def test_unauthorized_and_mismatch_are_not_review_or_candidates(self):
        report = evolve.build_report(
            [{"signal": "usage_unauthorized", "tool": "ghost_tool", "called": True,
              "evidence": {}},
             {"signal": "binding_mismatch", "tool": "get_weather", "called": False,
              "evidence": {}}],
            "tools.json", poison=set())
        gap = report["rule_coverage_gap"]
        self.assertEqual(gap["usage_unauthorized_tools"], ["ghost_tool"])
        self.assertEqual(gap["binding_mismatch_tools"], ["get_weather"])
        self.assertEqual(gap["candidates"], [])
        self.assertEqual(report["tier"]["review"], [])  # not described as benign

    def test_ambiguous_tool_reports_as_ambiguous_not_confirmed(self):
        report = evolve.build_report(
            [{"signal": "tool_unflagged", "tool": "send_email", "called": False,
              "evidence": {}}],
            "tools.json", poison={"send_email"}, ambiguous={"send_email"})
        self.assertEqual(report["tier"]["confirmed_misses"], [])
        self.assertEqual(report["tier"]["ambiguous_labels"], ["send_email"])
        self.assertEqual(report["rule_coverage_gap"]["candidates"], [])

    def test_boundary_tool_reports_as_boundary_not_confirmed(self):
        report = evolve.build_report(
            [{"signal": "tool_unflagged", "tool": "run_cmd", "called": False,
              "evidence": {}}],
            "tools.json", poison={"run_cmd"}, boundaries={"run_cmd"})
        self.assertEqual(report["tier"]["confirmed_misses"], [])
        self.assertEqual(report["tier"]["known_boundaries"], ["run_cmd"])
        self.assertEqual(report["rule_coverage_gap"]["candidates"], [])


@has_guard
class TestGates(unittest.TestCase):
    def _scan(self, out, tools=None, trace=None, fail=False, strict=False,
              seen=None):
        argv = ["scan"]
        if tools:
            argv += ["--tools", str(tools)]
        if trace:
            argv += ["--trace", str(trace)]
        argv += ["--mcp-guard-repo", str(REPO.parent / "mcp-guard"), "--out", str(out)]
        if fail:
            argv.append("--fail-on-proposal")
        if strict:
            argv.append("--strict-review")
        if seen:
            argv += ["--seen", str(seen)]
        return evolve.main(argv)

    def test_default_gate_passes_benign_example(self):
        tools = REPO.parent / "mcp-guard" / "examples" / "whatsapp_tools.json"
        with __import__("tempfile").TemporaryDirectory() as d:
            self.assertEqual(self._scan(Path(d) / "r.json", tools=tools, fail=True), 0)

    def test_default_gate_reddens_on_confirmed_miss(self):
        with __import__("tempfile").TemporaryDirectory() as d:
            tools = Path(d) / "miss.json"
            tools.write_text(json.dumps(
                {"tools": [{"name": "send_message", "description": "Just send.",
                            "inputSchema": {"type": "object", "properties": {}}}]}),
                encoding="utf-8")
            self.assertEqual(self._scan(Path(d) / "r.json", tools=tools, fail=True), 1)

    def test_strict_review_reddens_on_benign(self):
        tools = REPO.parent / "mcp-guard" / "examples" / "whatsapp_tools.json"
        with __import__("tempfile").TemporaryDirectory() as d:
            self.assertEqual(
                self._scan(Path(d) / "r.json", tools=tools, fail=True, strict=True), 1)

    def test_seen_ledger_closes_confirmed_miss(self):
        with __import__("tempfile").TemporaryDirectory() as d:
            tools = Path(d) / "miss.json"
            tools.write_text(json.dumps(
                {"tools": [{"name": "send_message", "description": "Just send.",
                            "inputSchema": {"type": "object", "properties": {}}}]}),
                encoding="utf-8")
            ledger = Path(d) / "seen.json"
            self.assertEqual(
                self._scan(Path(d) / "r1.json", tools=tools, fail=True, seen=ledger), 1)
            self.assertEqual(
                self._scan(Path(d) / "r2.json", tools=tools, fail=True, seen=ledger), 0)

    def test_crossrepo_gate_green_on_committed_cases(self):
        tools = REPO.parent / "mcp-guard" / "tasks" / "cases.jsonl"
        with __import__("tempfile").TemporaryDirectory() as d:
            rc = self._scan(Path(d) / "r.json", tools=tools, fail=True)
        self.assertEqual(rc, 0)

    def test_crossrepo_gate_reddens_on_a_new_miss(self):
        # Build a temp mcp-guard-like repo whose cases.jsonl gains a NEW poison
        # that fires no rule. The gate must redden -- that is its whole purpose.
        import shutil
        with __import__("tempfile").TemporaryDirectory() as d:
            fake_repo = Path(d) / "mcp-guard"
            shutil.copytree(REPO.parent / "mcp-guard" / "guard", fake_repo / "guard")
            (fake_repo / "tasks").mkdir(parents=True)
            new_case = {"name": "new_ghost", "description": "Do something harmless.",
                        "inputSchema": {"type": "object", "properties": {}},
                        "label": "poison", "gold_rules": ["imperative-tag"]}
            cases = fake_repo / "tasks" / "cases.jsonl"
            cases.write_text(json.dumps(new_case), encoding="utf-8")
            rc = evolve.main(["scan", "--tools", str(cases),
                              "--mcp-guard-repo", str(fake_repo),
                              "--out", str(Path(d) / "r.json"),
                              "--fail-on-proposal"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    sys.exit(unittest.main())
