# ADR 0001 — Content-hashing evidence packages

- **Status:** Accepted
- **Date:** 2026-07-13
- **Context tags:** evidence integrity, auditability, honest claims

## Context

An evaluation run produces evidence: model outputs, verdicts, scores, the resolved config,
and the dataset snapshot. For a result to be trustworthy, a reader must be able to detect
whether any of that evidence was altered after the fact — accidentally (a re-run that
overwrote a file) or deliberately (someone editing an output to make a score look better).

We needed a mechanism that (a) is cheap, (b) requires no external service, and (c) makes
tampering *detectable* — while being scrupulously honest about what it does **not** provide.

## Decision

Every evidence artifact is hashed with **sha256**, and the digests are recorded alongside
the run. Re-reading an artifact and recomputing its digest reveals any modification.

We describe this capability as **tamper-perceiving, not tamper-proof**. The system can
*detect* that evidence changed; it cannot *prevent* a determined actor with write access
from changing both the artifact and its recorded digest. This distinction is enforced in
the scorer itself: the `must_not_claim_tamper_proof` check **penalizes** any output that
describes the platform as tamper-proof. The architecture and the scoring contract agree —
we do not let ourselves overclaim.

## Alternatives considered

- **Cryptographic signing / append-only ledger.** Real tamper-*resistance*, but requires
  key management and/or an external trust anchor. Rejected as over-engineering for a
  single-founder, local-first tool; revisit if multi-party trust becomes a requirement.
- **No hashing, trust the filesystem.** Rejected — provides zero detectability and makes
  "prove what you measured" impossible.
- **Weaker digest (md5/crc).** Rejected — collision-cheap, undermines the one property we
  are buying.

## Consequences

- **Positive:** any post-hoc edit to evidence is detectable by recomputation; zero external
  dependencies; the honest framing ("tamper-perceiving") is baked into the scorer so the
  product cannot silently drift into overclaiming.
- **Negative / limits:** not tamper-*proof* — an actor who rewrites artifact + digest
  together defeats detection. This is an accepted limitation, stated openly rather than hidden.
- **Follow-on:** pairs with [ADR 0003](0003-local-jsonl-audit-trail.md) (the audit trail is
  the thing being hashed) and [ADR 0002](0002-sequential-synchronous-runner.md) (atomic,
  ordered writes keep the hashed evidence internally consistent).
