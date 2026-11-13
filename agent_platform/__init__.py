"""Agent Reliability Platform -- minimal glue layer.

This package ties the two repos of the platform together without merging their
code:

  * `mcp-guard` = the BEFORE gate. It scans an agent's tool definitions for
    poison, pins them by sha256 digest, and detects description drift. It answers
    "which tools is this agent allowed to use".
  * `auditable-llm-eval` = the AFTER audit. `verify_copilot_run.py` re-runs the
    authoritative scorer over a committed run dir and closes the evidence chain.
    It answers "did this agent's run actually score what it claims".
  * this package = the missing third layer. `agent_platform.trace.build_trace`
    binds a set of tool digests to one audited run and emits a single JSON trace
    with an integrity block, so a reviewer can see tool-identity + run-audit in
    one place.

Everything is offline and makes zero model calls. The glue only reads repo files
and shells out to the two existing CLIs -- it introduces no new scoring logic.
"""

__all__ = ["trace"]
