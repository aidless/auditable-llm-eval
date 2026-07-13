# ADR 0002 — Sequential, synchronous runner

- **Status:** Accepted
- **Date:** 2026-07-13
- **Context tags:** evidence consistency, concurrency, resumability

## Context

The eval runner drives N prompts through a model provider and records a verdict + evidence
for each. The obvious performance move is concurrency: a thread pool or `asyncio` fan-out to
run many prompts at once. But this platform's core value is **evidence integrity** (see
[ADR 0001](0001-content-hashing-evidence.md)), and concurrent writers make consistency hard:
interleaved appends, partially written records, and races that silently drop or duplicate a
verdict. A dropped verdict is exactly the kind of defect that produces a misleading "pass"
(the postmortem's 31/31 green-light trap).

> **Draft-status note.** This ADR records the *target* runner design for the copilot platform. The current copilot eval ships as draft scripts (`copilot/score_copilot_run_v2.py`, `verify_copilot_run.py`) and does **not** yet implement this sequential/synchronous runner. The design *is* implemented in a separate general-purpose platform (`llm-lab`, `llm_lab/runner.py`); it is cited here as the model to follow, not as shipped copilot code.

## Decision

The runner is **single-threaded and synchronous**. It processes prompts in order and writes
each result before moving to the next. The design has four load-bearing properties:

1. **Single thread** — no concurrent writers, so no interleaving or write races.
2. **Atomic append** — each verdict/evidence record is appended as one complete unit; there
   are no half-written records to confuse the scorer or the hasher.
3. **Run-lock** — a lock guards a run directory so two processes cannot write the same run
   concurrently and corrupt its evidence.
4. **Resume** — because writes are ordered and atomic, an interrupted run can be resumed
   from the last completed record without re-running or double-counting completed prompts.

## Alternatives considered

- **Thread pool.** Higher throughput, but concurrent appends threaten ordered, atomic
  evidence and complicate resume. Rejected: consistency > throughput for this tool.
- **`asyncio` fan-out.** Same consistency hazard plus more complex failure modes and harder
  debugging. Rejected for the same reason.
- **Concurrency + a write queue / DB transactions.** Would recover consistency, but adds a
  serialization point and infrastructure that contradicts the local-first stance of
  [ADR 0003](0003-local-jsonl-audit-trail.md). Rejected as premature.

## Consequences

- **Positive:** evidence is ordered, atomic, and internally consistent; runs are resumable
  after interruption; behavior is trivial to reason about and debug.
- **Negative:** wall-clock throughput is bounded by sequential execution — a large dataset
  against a slow provider is slow. Accepted deliberately; this is an evaluation tool where
  a correct, replayable result matters far more than fast completion.
- **Escape hatch:** if throughput ever becomes a hard requirement, parallelism can be added
  *across independent runs* (each with its own run-lock and directory) without touching the
  within-run ordering guarantee.
