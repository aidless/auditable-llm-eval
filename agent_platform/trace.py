"""Build one auditable trace binding tool-identity to run-audit.

Reads only:
  * a tool-definitions JSON (same shape `mcp-guard-scan` accepts: a list, or
    `{"tools": [...]}`);
  * one committed run dir from auditable-llm-eval (uses the tracked
    `summary.json` + `config.yaml`; it does NOT invoke the scorer, so no file in
    the run dir is rewritten).

Writes only the trace JSON to `--out`. Zero model calls, stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path


def load_guard(mcp_guard_repo: Path):
    """Import `guard.scan` from an mcp-guard checkout as a real package.

    `guard.scan` uses a relative import (`from .rules import scan_text`), so it
    must load as part of the `guard` package. The repo path is added to
    `sys.path` only if `guard` is not already importable, then removed -- this
    keeps the cross-repo dependency explicit without permanently mutating the
    importer or shadowing a real installed `guard`.
    """
    repo = Path(mcp_guard_repo).resolve()
    if not (repo / "guard" / "scan.py").exists():
        raise SystemExit(f"mcp-guard not found at {repo} (missing guard/scan.py)")
    cleaned = False
    try:
        importlib.import_module("guard.scan")
    except ModuleNotFoundError:
        # A failed `spec_from_file_location` load leaves a fake `guard` in
        # sys.modules (a module, not a package). Drop it so the real package
        # can be imported; a genuine package carries `__path__`.
        stale = sys.modules.get("guard")
        if stale is not None and not hasattr(stale, "__path__"):
            del sys.modules["guard"]
            sys.modules.pop("guard.scan", None)
            cleaned = True
        sys.path.insert(0, str(repo))
        try:
            importlib.import_module("guard.scan")
        finally:
            if cleaned:
                try:
                    sys.path.remove(str(repo))
                except ValueError:
                    pass
    return importlib.import_module("guard.scan")


def load_tools(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("tools", [data])
    return data


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _capability_binding(guard, tools: list[dict], repo: Path) -> dict:
    """Bind the capability axis (what each tool CAN do) into the trace.

    mcp-guard grew a second, orthogonal axis: the poison scan asks "is the
    description lying to the model", the capability scan asks "what can this
    tool actually do" (T0 read .. T3 destructive/exec). A trace that pins only
    the first axis misses tools like run_cmd that carry no poisoning at all.

    Availability is decided by the CHECKOUT, not by ambient sys.modules: a
    checkout without guard/capability.py records state=unavailable -- the
    section is never silently dropped, and an unrelated installed `guard`
    package never answers for the pinned repo.
    """
    if not (repo / "guard" / "capability.py").exists():
        return {
            "state": "unavailable",
            "note": "mcp-guard checkout has no capability axis "
                    "(guard/capability.py missing); capability tier is not "
                    "bound in this trace",
            "per_tool": [],
            "tier_mismatches": [],
        }
    capmod = importlib.import_module("guard.capability")
    cap = getattr(guard, "scan_capability", None) or capmod.scan_capability
    mism_fn = getattr(guard, "tier_mismatches", None) or getattr(
        capmod, "tier_mismatches", None)
    results = [cap(tool) for tool in tools]
    mismatches = mism_fn(tools, results) if mism_fn is not None else []
    per_tool = []
    for tool, result in zip(tools, results):
        per_tool.append({
            "name": result.get("name", tool.get("name", "?")),
            "tier": result.get("tier"),
            "unknown": bool(result.get("unknown")),
            "n_hits": len(result.get("hits", [])),
            "rules": sorted({h["rule"] for h in result.get("hits", [])}),
        })
    return {
        "state": "present",
        "per_tool": per_tool,
        "tier_mismatches": mismatches,
    }


def build_trace(tools_path: Path, run_dir: Path, mcp_guard_repo: Path) -> dict:
    guard = load_guard(mcp_guard_repo)
    # Resolve before anything enters the trace body: a relative `--run-dir` or
    # `--tools` must not change the digest just because of the caller's cwd.
    tools_path = Path(tools_path).resolve()
    run_dir = Path(run_dir).resolve()
    tools = load_tools(tools_path)

    tool_ids = []
    flagged = []
    for tool in tools:
        name = tool.get("name", "?")
        result = guard.scan_tool(tool)
        entry = {
            "name": name,
            "digest": guard.digest_tool(tool),
            "flagged": bool(result["flagged"]),
            "rule_ids": sorted({h["rule"] for h in result["hits"]}),
        }
        tool_ids.append(entry)
        if result["flagged"]:
            flagged.append(name)

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    config = _read_config(run_dir / "config.yaml")

    tools_sha = sha256_file(tools_path)
    tool_binding = _bind_tools(run_dir, tools, tool_ids, tools_sha)
    tool_usage = _bind_usage(run_dir, tool_binding)

    return {
        "layer": {
            "before_gate": "mcp-guard (tool scan + digest pin)",
            "after_audit": "auditable-llm-eval (committed summary.json, scorer-derived)",
            "binding": "runner tool_manifest.json (tools this run was allowed to use)",
            "usage": "runner tool_calls.json (tools this run actually called)",
        },
        "tools_source": str(tools_path),
        "tool_identity": {
            "n_tools": len(tools),
            "flagged": flagged,
            "tools": tool_ids,
        },
        "capability_binding": _capability_binding(
            guard, tools, Path(mcp_guard_repo).resolve()),
        "tool_binding": tool_binding,
        "tool_usage": tool_usage,
        "run_audit": {
            "run_dir": str(run_dir),
            "model": config.get("model"),
            "temperature": config.get("temperature"),
            "total": summary.get("total"),
            "semantic_scored": summary.get("semantic_scored"),
            "runtime_errors": summary.get("runtime_errors"),
            "overall_reference_check_rate": summary.get("overall_reference_check_rate"),
            "by_task": summary.get("by_task"),
            "items_with_unsupported_claims": summary.get("items_with_unsupported_claims"),
        },
        "inputs": {
            "tools_sha256": tools_sha,
            "summary_sha256": sha256_file(run_dir / "summary.json"),
            "config_sha256": sha256_file(run_dir / "config.yaml"),
            "tool_calls_sha256": (sha256_file(run_dir / "tool_calls.json")
                                  if (run_dir / "tool_calls.json").exists() else None),
        },
    }


def _bind_usage(run_dir: Path, tool_binding: dict) -> dict:
    """Cross-check the OBSERVED tool calls against the declared allowlist.

    This is the layer that answers "did the agent actually call something it was
    not allowed to use". States:

      absent        -- no tool_calls.json supplied; nothing to assert.
      ok            -- every called tool is in the allowlist.
      unauthorized  -- at least one called tool is NOT in the allowlist.
      unverifiable  -- there is a call log but no allowlist to check it against.
    """
    calls_path = run_dir / "tool_calls.json"
    if not calls_path.exists():
        return {
            "state": "absent",
            "note": "run has no tool_calls.json (no --tool-calls); actual tool usage "
                    "is not recorded for this run",
            "n_calls": None,
            "tools_called": [],
            "unauthorized": [],
        }
    record = json.loads(calls_path.read_text(encoding="utf-8"))
    tools_called = record.get("tools_called", [])
    manifest = _read_manifest(run_dir)
    if manifest is None:
        return {
            "state": "unverifiable",
            "note": "call log present but no tool_manifest.json to check it against; "
                    "re-run with --tool-allowlist to make this checkable",
            "n_calls": record.get("n_calls"),
            "tools_called": tools_called,
            "unauthorized": [],
        }
    allowed = {t["name"]: t["digest"] for t in manifest}
    unauthorized = [t for t in tools_called if t not in allowed]
    return {
        "state": "ok" if not unauthorized else "unauthorized",
        "n_calls": record.get("n_calls"),
        "tools_called": tools_called,
        "unauthorized": unauthorized,
    }


def _read_manifest(run_dir: Path) -> list[dict] | None:
    manifest_path = run_dir / "tool_manifest.json"
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8")).get("tools", [])


def _bind_tools(run_dir: Path, tools: list[dict], tool_ids: list[dict],
                tools_sha: str) -> dict:
    """Bind the run's declared allowlist to the audited tool definitions.

    The runner (eval/run_copilot_eval.py) writes tool_manifest.json into the run
    dir when a `--tool-allowlist` was given, pinning the same digests the BEFORE
    gate uses. Cross-checking it against the external --tools file is what turns
    two independent reports into a single trace: a mismatch means the tools being
    audited are not the tools this run was allowed to use.

    states: "verified" | "mismatch" | "absent". "absent" is not an error -- the
    run simply did not declare an allowlist; it is reported, not asserted.
    """
    manifest_path = run_dir / "tool_manifest.json"
    if not manifest_path.exists():
        return {
            "state": "absent",
            "note": "run has no tool_manifest.json (no --tool-allowlist); "
                    "tool_identity below is from the external --tools file only",
            "manifest_tools": None,
            "mismatches": [],
        }
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_tools = manifest.get("tools", [])
    by_name = {t.get("name", "?"): t for t in tool_ids}
    mismatches = []
    for entry in manifest_tools:
        name = entry.get("name", "?")
        audited = by_name.get(name)
        if audited is None:
            mismatches.append({"name": name, "why": "in manifest but not in --tools file"})
        elif audited["digest"] != entry.get("digest"):
            mismatches.append({"name": name, "why": "digest differs from --tools file"})
    for name in by_name:
        if all(e.get("name") != name for e in manifest_tools):
            mismatches.append({"name": name, "why": "in --tools file but not in manifest"})
    return {
        "state": "verified" if not mismatches else "mismatch",
        "manifest_tools": len(manifest_tools),
        "manifest_digest_algo": manifest.get("digest_algo"),
        "mismatches": mismatches,
    }


def _read_config(path: Path) -> dict:
    """Minimal `key: value` reader for the flat run config (no yaml dependency)."""
    config = {}
    if not path.exists():
        return config
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        config[key.strip()] = value.strip()
    return config


def finalize(trace: dict) -> dict:
    """Attach the integrity block: hash the body, then pin it with its own hash.

    The body is deterministic (sorted keys, no timestamps), so the same inputs
    always give the same `trace_sha256` -- that is the replay handle.
    """
    body = json.dumps(trace, sort_keys=True, ensure_ascii=False, indent=2)
    trace_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return {"trace_sha256": trace_sha256, "trace": trace}


def main(argv: list[str] | None = None) -> int:
    default_mcp = os.environ.get("MCP_GUARD_REPO")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tools", required=True, type=Path, help="tool-definitions JSON")
    ap.add_argument("--run-dir", required=True, type=Path, help="committed auditable-llm-eval run dir")
    ap.add_argument("--mcp-guard-repo", default=default_mcp, type=Path,
                    help="mcp-guard checkout (or set MCP_GUARD_REPO)")
    ap.add_argument("--out", required=True, type=Path, help="trace JSON to write")
    ap.add_argument("--fail-on", choices=["none", "unauthorized", "mismatch", "any"],
                    default="none",
                    help="blocking semantics after the trace is written: exit 1 on "
                         "an out-of-policy call (unauthorized), a rug-pull-shaped "
                         "definition drift (mismatch), or either (any). Default none: "
                         "record the evidence, do not block.")
    args = ap.parse_args(argv)

    if not args.mcp_guard_repo:
        ap.error("--mcp-guard-repo is required (or set MCP_GUARD_REPO)")
    trace = build_trace(args.tools, args.run_dir, args.mcp_guard_repo)
    payload = finalize(trace)
    args.out.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    identity = trace["tool_identity"]
    audit = trace["run_audit"]
    binding = trace["tool_binding"]
    usage = trace["tool_usage"]
    print(json.dumps({
        "trace_sha256": payload["trace_sha256"],
        "n_tools": identity["n_tools"],
        "flagged": identity["flagged"],
        "binding": binding["state"],
        "usage": usage["state"],
        "overall_reference_check_rate": audit["overall_reference_check_rate"],
        "out": str(args.out),
    }, ensure_ascii=False))

    problems = []
    if usage["state"] == "unauthorized":
        problems.append("unauthorized:" + ",".join(usage["unauthorized"]))
    if binding["state"] == "mismatch":
        problems.append("mismatch:" + ",".join(m["name"] for m in binding["mismatches"]))
    triggered = {
        "none": False,
        "unauthorized": usage["state"] == "unauthorized",
        "mismatch": binding["state"] == "mismatch",
        "any": bool(problems),
    }[args.fail_on]
    if triggered:
        print("[agent-trace] BLOCK (" + args.fail_on + "): " + "; ".join(problems),
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
