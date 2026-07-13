# Architecture Decision Records — llm-lab-copilot

This directory records the load-bearing architecture decisions behind `llm-lab-copilot`,
the auditable model-evaluation platform. Each ADR captures **one decision**, the context
that forced it, the alternatives we rejected, and the trade-off we accepted.

These ADRs are written against the **real codebase**, not an aspirational design. Where an
earlier strategy document assumed features that do not exist (e.g. a `CompareResult` model,
337 tests, a `planner/` module, Langfuse-based tracing), these ADRs state what is actually
implemented. When the map and the territory disagree, the territory wins.

## Index

| ADR | Title | Decision in one line |
|---|---|---|
| [0001](0001-content-hashing-evidence.md) | Content-hashing evidence packages | sha256 every evidence artifact — *tamper-perceiving*, not tamper-proof |
| [0002](0002-sequential-synchronous-runner.md) | Sequential synchronous runner | single thread + atomic append + run-lock + resume; consistency > throughput |
| [0003](0003-local-jsonl-audit-trail.md) | Local JSONL audit trail | plain local JSONL files, not Langfuse / not a SQL server |
| [0004](0004-verifier-is-not-scorer.md) | The verifier is not the scorer | live verifier does structural checks only; `reference_checks` scorer is the authority |

## Status legend

- **Accepted** — implemented and in force.
- **Superseded** — replaced by a later ADR (linked).
- **Proposed** — under discussion, not yet implemented.

## The through-line

All four decisions serve one property: **evidence integrity**. An evaluation result is only
worth as much as your ability to prove what was measured and to replay it. Throughput,
fancy dashboards, and drop-in observability SaaS were all traded away wherever they
threatened that property. The postmortem in
[`../blog/001-auditable-llm-eval-no-green-lights.md`](../blog/001-auditable-llm-eval-no-green-lights.md)
shows why this matters in practice: a run once reported 31/31 green lights while the
authoritative scorer said 7.59%. These ADRs are the architecture that let us catch that.
