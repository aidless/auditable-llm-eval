"""Self-evolution loop: trace signals -> rule-coverage gap -> candidate case.

The platform learns from what it observes, but the learning is a *proposal*, not
an automatic edit. Nothing in this module writes to mcp-guard's cases.jsonl or
rules.py -- that is a human gate. It only:

  1. reads one or more traces (or a raw tool-definitions file) and aggregates
     per-tool signals;
  2. derives, per signal, which existing rule family it would belong to and
     whether that family is currently unflagged (a *coverage gap*);
  3. emits a schema-aligned candidate case + a proposal report, so a human can
     copy it into cases.jsonl, add the rule, and re-run the ablation gate.

Signal semantics (keep these precise -- the loop is only as good as its
classification):
  * tool_unflagged          -- a tool was scanned and NO rule fired. The main
                              miss shape; becomes a candidate case.
  * called_tool_unflagged   -- that unflagged tool was also ACTUALLY CALLED
                              (from tool_usage). Higher priority: it ran.
  * usage_unauthorized      -- a tool was called that is not even in the
                              allowlist. Out-of-policy, independent of rules.
  * binding_mismatch        -- the audited definition is not the allowlisted
                              one (rug-pull shape). Definition drift, not a
                              rule gap -- routed to review, not a candidate.

Usage:
    agent-evolve scan --trace t.json [--trace t2.json ...] [--out report.json]
    agent-evolve scan --tools tools.json [--out report.json]
    agent-evolve scan ... --fail-on-proposal   # CI gate: exit 1 while signals exist
    agent-evolve --version
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

__version__ = "0.1.0"


def load_guard(mcp_guard_repo: Path):
    """Import the mcp-guard `guard.scan` package (same loader as trace.py)."""
    repo = Path(mcp_guard_repo).resolve()
    if not (repo / "guard" / "scan.py").exists():
        raise SystemExit(f"mcp-guard not found at {repo} (missing guard/scan.py)")
    cleaned = False
    try:
        importlib.import_module("guard.scan")
    except ModuleNotFoundError:
        # A failed load can leave a fake `guard` (no __path__) in sys.modules.
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


# Rule families a NEW case would most plausibly extend, so the human sees where
# a candidate would land. Derived from mcp-guard's rule ids, not invented.
FAMILIES = ["imperative-tag", "secret-read", "exfil-param", "recipient-rewrite",
            "auth-url-exec", "encoded-exfil"]

# Two-tier triage. A label is only "confirmed" when the tool is already in
# mcp-guard's labeled set (cases.jsonl) -- otherwise the scanner has no idea
# whether an unflagged tool is a miss or simply benign, and promoting it to a
# candidate would flood the loop with get_weather-style noise.
CONFIRMED_SIGNALS = ("called_tool_unflagged", "tool_unflagged")
REVIEW_SIGNALS = ("usage_unauthorized", "binding_mismatch")


def load_labels(mcp_guard_repo: Path) -> tuple[set[str], set[str]]:
    """(poison_names, benign_names) from mcp-guard's labeled cases, if present.

    Reads tasks/cases.jsonl read-only. Missing file -> empty sets, which degrades
    every unflagged tool to "unseen" (review, not confirmed) rather than guessing.
    """
    cases = Path(mcp_guard_repo).resolve() / "tasks" / "cases.jsonl"
    poison: set[str] = set()
    benign: set[str] = set()
    if not cases.exists():
        return poison, benign
    for line in cases.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        (poison if row.get("label") == "poison" else benign).add(row.get("name", "?"))
    return poison, benign


def _tier(sig: dict, poison: set[str]) -> str:
    """confirmed = a known-labeled poison tool that fired no rule (a real miss)."""
    if sig["tool"] in poison and sig["signal"] in CONFIRMED_SIGNALS:
        return "confirmed"
    return "review"


def _load_input(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "trace_sha256" in data and "trace" in data:  # finalized trace
        return data["trace"]
    return data  # already a trace body, or a tools file -- caller disambiguates


def signals_from_trace(trace: dict) -> list[dict]:
    """Aggregate per-tool signals from a trace body. Deterministic ordering."""
    out: list[dict] = []
    identity = trace.get("tool_identity", {})
    usage = trace.get("tool_usage", {})
    binding = trace.get("tool_binding", {})

    flagged = set(identity.get("flagged", []))
    called = set(usage.get("tools_called", []) or [])
    unauthorized = set(usage.get("unauthorized", []) or [])

    for entry in identity.get("tools", []):
        name = entry.get("name", "?")
        evidence = {"source": "tool_identity", "rule_ids": entry.get("rule_ids", []),
                    "flagged": entry.get("flagged", False)}
        if entry.get("name") in unauthorized:
            out.append({"signal": "usage_unauthorized", "tool": name, "evidence": evidence,
                        "called": True})
        elif name not in flagged:
            out.append({"signal": "called_tool_unflagged" if name in called
                        else "tool_unflagged", "tool": name, "evidence": evidence,
                        "called": name in called})
    for name in sorted(unauthorized):
        if all(s["tool"] != name for s in out):
            out.append({"signal": "usage_unauthorized", "tool": name,
                        "evidence": {"source": "tool_usage"}, "called": True})
    for m in binding.get("mismatches", []):
        out.append({"signal": "binding_mismatch", "tool": m.get("name", "?"),
                    "evidence": {"source": "tool_binding", "why": m.get("why")},
                    "called": False})
    return out


def signals_from_tools(tools: list[dict], guard) -> list[dict]:
    """Scan a raw tools file and emit a `tool_unflagged` signal per clean tool.

    Used when there is no trace yet -- the raw discovery half of the loop.
    """
    out = []
    for tool in tools:
        name = tool.get("name", "?")
        result = guard.scan_tool(tool)
        if not result["flagged"]:
            out.append({"signal": "tool_unflagged", "tool": name,
                        "evidence": {"source": "scan", "rule_ids": [],
                                     "flagged": False}, "called": False})
    return out


def make_candidate(sig: dict, tools_path: str) -> dict:
    """Turn a signal into a schema-aligned candidate case (human-reviewable)."""
    name = sig["tool"]
    return {
        "name": name,
        "description": f"<PENDING HUMAN WRITE> adversarial description for '{name}' "
                       f"that today fires no rule. Derive it from the observed tool, "
                       f"then fill a real description and gold_rules.",
        "inputSchema": {"type": "object", "properties": {}},
        "label": "poison",
        "gold_rules": [],
        "proposal": {
            "signal": sig["signal"],
            "called": sig["called"],
            "candidate_families": FAMILIES,
            "source_tools_sha256_file": tools_path,
            "note": "candidate only -- appending to cases.jsonl requires human "
                    "confirmation; pick the family, write the description, set gold_rules",
        },
    }


def build_report(signals: list[dict], tools_path: str, poison: set[str],
                 seen: set[str] | None = None) -> dict:
    seen = seen or set()
    new = [s for s in signals if s["tool"] not in seen]
    for s in new:
        s["tier"] = _tier(s, poison)
    # Only CONFIRMED misses become actionable candidates; everything else is
    # routed to review so benign tools never masquerade as rule gaps.
    candidates = [make_candidate(s, tools_path) for s in new if s["tier"] == "confirmed"]
    # review = unflagged but NOT in the labeled set -> benign or unknown, i.e.
    # not promotable to a candidate. Unauthorized / mismatch signals are their
    # own categories and must not be described as "benign".
    review = sorted({s["tool"] for s in new if s["tier"] == "review"
                     and s["signal"] in CONFIRMED_SIGNALS})
    gaps = [s for s in new if s["signal"] == "called_tool_unflagged"]
    unauthorized = sorted({s["tool"] for s in new if s["signal"] == "usage_unauthorized"})
    mismatches = [s["tool"] for s in new if s["signal"] == "binding_mismatch"]
    return {
        "schema_version": 1,
        "tools_source": tools_path,
        "n_signals": len(new),
        "n_seen_suppressed": len(signals) - len(new),
        "tier": {
            "confirmed_misses": sorted({s["tool"] for s in new if s["tier"] == "confirmed"}),
            "review": review,
            "n_review_benign_or_unknown": len(review),
        },
        "rule_coverage_gap": {
            "n_tools_unflagged": sum(1 for s in new
                                     if s["signal"] in ("tool_unflagged", "called_tool_unflagged")),
            "n_called_but_unflagged": len(gaps),
            "n_usage_unauthorized": len(unauthorized),
            "n_binding_mismatch": len(mismatches),
            "usage_unauthorized_tools": unauthorized,
            "binding_mismatch_tools": mismatches,
            "candidates": candidates,
        },
        "next_step": ("human: triage candidates -> append reviewed case(s) to "
                      "mcp-guard tasks/cases.jsonl -> add/extend rule if needed -> "
                      "run scripts/measure_rule_ablation.py --check"),
    }


def main(argv: list[str] | None = None) -> int:
    default_mcp = os.environ.get("MCP_GUARD_REPO")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["scan"], help="aggregate signals -> proposal report")
    ap.add_argument("--trace", action="append", type=Path, default=[],
                    help="trace JSON (repeatable)")
    ap.add_argument("--tools", type=Path, help="raw tool-definitions JSON to scan directly")
    ap.add_argument("--mcp-guard-repo", default=default_mcp, type=Path,
                    help="mcp-guard checkout (or set MCP_GUARD_REPO)")
    ap.add_argument("--seen", type=Path, help="ledger of already-triaged tools (read+write)")
    ap.add_argument("--out", required=True, type=Path, help="proposal report JSON to write")
    ap.add_argument("--fail-on-proposal", action="store_true",
                    help="exit 1 while any CONFIRMED candidate is untriaged (CI gate)")
    ap.add_argument("--strict-review", action="store_true",
                    help="also exit 1 when unflagged tools are only in review "
                         "(off by default -- benign tools would otherwise redden the build)")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args(argv)

    # Only --tools needs the scanner; a trace already carries its signals, so it
    # can be aggregated without an mcp-guard checkout. Labels default to empty in
    # that case, which correctly degrades every unflagged tool to "review".
    guard = None
    poison: set[str] = set()
    benign: set[str] = set()
    if args.mcp_guard_repo:
        poison, benign = load_labels(args.mcp_guard_repo)

    signals: list[dict] = []
    tools_path = ""
    if args.tools:
        if guard is None:
            if not args.mcp_guard_repo:
                ap.error("--tools needs --mcp-guard-repo (or set MCP_GUARD_REPO)")
            guard = load_guard(args.mcp_guard_repo)
        raw = json.loads(args.tools.read_text(encoding="utf-8"))
        tools = raw.get("tools", [raw]) if isinstance(raw, dict) else raw
        tools_path = str(Path(args.tools).resolve())
        signals.extend(signals_from_tools(tools, guard))
    for tp in args.trace:
        body = _load_input(tp)
        tools_path = tools_path or str(Path(tp).resolve())
        signals.extend(signals_from_trace(body))
    if not signals and not args.seen:
        # Nothing observed is a valid, quiet report -- but say so explicitly.
        pass

    seen: set[str] = set()
    if args.seen and args.seen.exists():
        seen = set(json.loads(args.seen.read_text(encoding="utf-8")).get("seen", []))
    report = build_report(signals, tools_path, poison, seen)
    if args.seen:
        args.seen.parent.mkdir(parents=True, exist_ok=True)
        args.seen.write_text(json.dumps(
            {"seen": sorted(seen | {s["tool"] for s in signals})},
            sort_keys=True, ensure_ascii=False, indent=2), encoding="utf-8")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    gap = report["rule_coverage_gap"]
    tier = report["tier"]
    print(json.dumps({
        "n_signals": report["n_signals"],
        "n_seen_suppressed": report["n_seen_suppressed"],
        "confirmed_misses": tier["confirmed_misses"],
        "n_review": len(tier["review"]),
        "n_candidates": len(gap["candidates"]),
        "n_called_but_unflagged": gap["n_called_but_unflagged"],
        "n_usage_unauthorized": gap["n_usage_unauthorized"],
        "n_binding_mismatch": gap["n_binding_mismatch"],
        "out": str(args.out),
    }, ensure_ascii=False))
    # Gate on confirmed misses only: benign/unknown tools land in review and do
    # not redden the build, otherwise every clean tool would be a false alarm.
    if args.fail_on_proposal and tier["confirmed_misses"]:
        print("[evolve] confirmed misses untriaged -- triage then re-run, or extend --seen: "
              f"{tier['confirmed_misses']}", file=sys.stderr)
        return 1
    if args.fail_on_proposal and args.strict_review and tier["review"]:
        print(f"[evolve] {len(tier['review'])} tool(s) unflagged but not yet labeled "
              "(benign or unknown) -> review, not a confirmed miss", file=sys.stderr)
        return 1
    if tier["review"]:
        print(f"[evolve] note: {len(tier['review'])} unflagged tool(s) are benign/unknown "
              "(review); pass --strict-review to gate on these too")
    return 0


if __name__ == "__main__":
    sys.exit(main())
