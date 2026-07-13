# ADR 0004 — The verifier is not the scorer

- **Status:** Accepted
- **Date:** 2026-07-13
- **Context tags:** honest scoring, false green lights, separation of concerns

## Context

The platform has two things that can say "this output is fine," and conflating them is the
single most dangerous mistake a user of this system can make:

1. The **live verifier** — a fast, structural gate that runs during a run. It checks things
   like *non-empty*, *min chars*, *max chars*. Its verdicts drive the UI's green/red panel.
2. The **`reference_checks` scorer** (`copilot/score_copilot_run_v2.py`, a **draft** implementation) — the authoritative,
   offline scorer. It runs 10 `reference_checks` categories (exact / soft / unsupported_claims / missing_required_points / score; heuristic, with `soft_checks` flagged `needs_llm=True`), parses YAML, validates schema, and — critically —
   enforces **cognitive-honesty** dimensions: `must_not_claim_tamper_proof`,
   `must_not_overclaim`, `must_warn_structural_limit`.

The postmortem shows exactly why this separation must be explicit: one run displayed
**31/31 verdicts passed** in the UI while the scorer reported **7.59%**. The outputs were
backtick repetition collapse — non-empty and long enough to pass the *structural* verifier,
and completely worthless. The green light was a structural mirage.

> **Draft-status note.** The scorer cited here is `copilot/score_copilot_run_v2.py`, a **self-described draft** (its docstring says it does not depend on a real repo to self-test). It is **not** the `scripts/score_copilot_run.py` path quoted in an earlier draft (that path does not exist in this repo). The 10 `reference_checks` categories are heuristic; `soft_checks` are flagged `needs_llm=True` and are not yet backed by an LLM judge. The copilot `runs/` that would hold real verdicts/evidence are **not committed** to this repo, so the 31/31-vs-7.59% gap is reported from session logs, not from shipped runs.

## Decision

We **formally separate** the two and designate the scorer as the sole authority:

- The **live verifier does structural checks only**. Its "pass" means *"produced a
  non-empty, length-bounded blob"* — nothing about correctness or honesty. It is a
  smoke-test / liveness signal, never a quality judgment.
- The **`reference_checks` scorer is the authority.** No result is considered evaluated until
  the scorer has run. The scorer **penalizes overclaiming** — an output that is correct-looking
  but asserts tamper-proofness, or fails to warn about a real structural limit, loses points.
- A live verifier "pass" is therefore an **invitation to score**, not a diploma.

This is deliberately encoded so the system can *fail itself*: a model cannot earn a good
score by being confidently wrong, and the platform cannot flatter itself with green lights.

## Alternatives considered

- **Make the live verifier smarter (fold scoring into it).** Rejected — a per-request,
  in-loop verifier can't safely run the full ~80-check scorer (including YAML parse + honesty
  checks) without slowing every run and coupling scoring to the runner. Keep them separate.
- **Trust the UI verdict panel as the score.** This *is* the bug the postmortem documents.
  Explicitly rejected.
- **Drop the honesty checks (score only correctness).** Rejected — it would let a confident
  hallucination pass. Honesty penalties are the moat, not a nicety.

## Consequences

- **Positive:** false green lights are structurally impossible to mistake for real scores;
  honest-claim discipline is enforced by code, not convention; the two components can evolve
  independently (fast liveness signal vs. thorough authority).
- **Negative:** users must run a second, offline step to get the real number — the UI alone
  is insufficient by design. This friction is intentional; see the postmortem for what
  happens when people skip it.
- **Discipline:** always score with `reference_checks`; always compare models on the *same
  dataset + same scorer*; never quote the UI pass rate as a result.
