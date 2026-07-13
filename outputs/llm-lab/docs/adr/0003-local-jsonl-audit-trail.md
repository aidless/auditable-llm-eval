# ADR 0003 — Local JSONL audit trail

- **Status:** Accepted
- **Date:** 2026-07-13
- **Context tags:** auditability, local-first, portability

## Context

Every run must leave a complete, inspectable trail: inputs, outputs, verdicts, scores, and
timestamps. An earlier strategy document assumed this was built on **Langfuse** (a hosted
LLM observability SaaS). It is not — the real implementation writes plain **JSONL** files to
the local run directory. This ADR records why the local-file choice is correct, not an
accident to be "upgraded away."

The audit trail is also the substrate that [ADR 0001](0001-content-hashing-evidence.md)
hashes and that [ADR 0002](0002-sequential-synchronous-runner.md) appends to atomically, so
its format has to be dead simple and append-friendly.

## Decision

The audit trail is stored as **local JSONL** — one JSON object per line, one file per stream
(e.g. verdicts, evidence) inside the run directory. No external service, no database server.

Properties that make JSONL the right fit:

- **Append-only friendly** — a new record is one `write` of one line; pairs perfectly with
  the atomic-append runner (ADR 0002).
- **Diffable & greppable** — a human can `diff`, `grep`, and eyeball the trail with no tools.
- **Hashable & replayable** — a stable byte stream that ADR 0001 can sha256, and that any
  script can re-read to recompute scores independently.
- **Zero-dependency & portable** — the entire evidence of a run is a folder you can copy,
  archive, or hand to someone else; it works offline and on a locked-down Windows box.

## Alternatives considered

- **Langfuse (hosted observability).** Nice dashboards, but adds a network dependency,
  a data-egress/privacy surface, and couples our evidence of record to a third party's
  uptime and export format. Rejected — contradicts "prove and replay locally."
- **SQLite / embedded SQL.** Structured queries, but a binary file is harder to diff/grep,
  awkward to hash line-by-line, and adds schema-migration overhead. Rejected as fallback,
  not needed at current scale.
- **Cloud object store (S3, etc.).** Rejected for the same coupling/egress reasons as
  Langfuse; a run must be fully meaningful on the local disk that produced it.

## Consequences

- **Positive:** runs are self-contained, portable, offline-capable, human-inspectable, and
  trivially hashable/replayable; no vendor lock-in on the evidence of record.
- **Negative:** no built-in query engine or hosted UI — cross-run analytics require reading
  files (or a thin future indexer). Accepted; ad-hoc analysis over JSONL is cheap and the
  local-first guarantee is worth more than turnkey dashboards.
- **Future option:** an *optional*, additive exporter (to Langfuse/SQLite/etc.) could be
  layered on top **without** displacing local JSONL as the source of truth.
