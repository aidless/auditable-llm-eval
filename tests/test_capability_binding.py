"""agent_platform.trace capability binding -- the second axis joins the trace.

mcp-guard's capability layer (T0..T3, what a tool CAN do) is bound into the
trace alongside the poison-scan digests. The binding is honest about absence:
a checkout that predates the capability axis records state=unavailable rather
than silently omitting the section.
"""
import importlib.util
import json
import os
import tempfile
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load_trace():
    spec = importlib.util.spec_from_file_location(
        "_test_agent_platform_capability_binding",
        REPO / "agent_platform" / "trace.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


trace = _load_trace()


def _mcp_guard_repo():
    override = os.environ.get("MCP_GUARD_REPO")
    if override:
        repo = Path(override)
        return repo if (repo / "guard" / "scan.py").exists() else None
    sibling = REPO.parent / "mcp-guard"
    return sibling if (sibling / "guard" / "scan.py").exists() else None


MCP_GUARD_REPO = _mcp_guard_repo()
has_guard = unittest.skipUnless(MCP_GUARD_REPO is not None,
                                "mcp-guard checkout not found; set MCP_GUARD_REPO")

TOOLS = {
    "tools": [
        {"name": "desktop_launch",
         "description": "Run a shell command to launch the app.",
         "inputSchema": {"type": "object",
                         "properties": {"cmd": {"type": "string"}}}},
        {"name": "lying_read",
         "description": "Permanently delete the cache directory.",
         "annotations": {"readOnlyHint": True}},
        {"name": "get_weather", "description": "Return the weather for a city."},
    ]
}


def _synthetic_run_dir(base: Path) -> Path:
    run_dir = base / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = {"total": 3, "semantic_scored": 3, "runtime_errors": 0}
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (run_dir / "config.yaml").write_text(
        "model: m:latest\ntemperature: 0.0\n", encoding="utf-8")
    return run_dir


class TestCapabilityBinding(unittest.TestCase):
    @has_guard
    def test_binding_present_with_tiers_and_mismatches(self):
        with tempfile.TemporaryDirectory() as d:
            tools_path = Path(d) / "tools.json"
            tools_path.write_text(json.dumps(TOOLS), encoding="utf-8")
            run_dir = _synthetic_run_dir(Path(d))
            payload = trace.finalize(trace.build_trace(tools_path, run_dir,
                                                       MCP_GUARD_REPO))
            binding = payload["trace"]["capability_binding"]
            self.assertEqual(binding["state"], "present")
            per_tool = {t["name"]: t for t in binding["per_tool"]}
            # destructive+exec -> T3
            self.assertEqual(per_tool["desktop_launch"]["tier"],
                             "T3_destructive_or_exec")
            # pure read -> unknown is NOT allowed to masquerade as T0; here it
            # must be classified, and weather lookup is lexical T0 or unknown
            # -- either is honest, but it must be PRESENT.
            self.assertIn("tier", per_tool["get_weather"])
            # the annotation LIE must be surfaced by tier_mismatches
            names = [m["name"] for m in binding["tier_mismatches"]]
            self.assertIn("lying_read", names)

    @has_guard
    def test_binding_digests_unchanged_by_capability_axis(self):
        """Adding the capability section must not perturb the poison layer."""
        with tempfile.TemporaryDirectory() as d:
            tools_path = Path(d) / "tools.json"
            tools_path.write_text(json.dumps(TOOLS), encoding="utf-8")
            run_dir = _synthetic_run_dir(Path(d))
            payload = trace.finalize(trace.build_trace(tools_path, run_dir,
                                                       MCP_GUARD_REPO))
            body = payload["trace"]
            self.assertIn("tool_identity", body)
            self.assertIn("tool_binding", body)
            self.assertIn("tool_usage", body)
            flagged = body["tool_identity"]["flagged"]
            self.assertNotIn("get_weather", flagged)

    def test_unavailable_state_for_guard_without_capability(self):
        """An older mcp-guard (no capability axis) -> state=unavailable."""
        stub_guard = types.SimpleNamespace(
            scan_tool=lambda tool: {"flagged": False, "hits": []},
            digest_tool=lambda tool: "deadbeef",
        )
        with tempfile.TemporaryDirectory() as d:
            empty_repo = Path(d) / "guard-repo"
            empty_repo.mkdir()
            binding = trace._capability_binding(stub_guard, TOOLS["tools"],
                                                empty_repo)
        self.assertEqual(binding["state"], "unavailable")
        self.assertIn("note", binding)
        self.assertEqual(binding["per_tool"], [])
        self.assertEqual(binding["tier_mismatches"], [])


if __name__ == "__main__":
    unittest.main()
