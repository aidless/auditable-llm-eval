# We shipped an auditable LLM eval in one day. The CI went red twice. That's the point.

*2026-07-13 · auditable-llm-eval formation day · English version of [002-formation-day.md](./002-formation-day.md)*

> **TL;DR** — In 8 hours we turned a loose pile of scripts into `aidless/auditable-llm-eval`: 85 tracked files, four-layer structure, GitHub Actions CI, and a one-command local validator. The headline numbers (v3c = 69.00%, v3 = 67.00%) are reproducible by anyone with a clone. The CI went red twice in a row because we enabled `cache: pip` against a `requirements_win3060.txt` with no PyPI mapping. Three subsequent runs are green (17s, 11s, 13s). The discipline is auditable, not the benchmark.

---

## 1. The thing we built

`aidless/auditable-llm-eval` is a reproducible LLM evaluation pipeline where every task ships with programmatic `reference_checks` — including *cognitive-honesty* dimensions. A model that confidently hallucinates passes the structural checks but fails the honesty checks. Two committed runs (a competent LoRA v3c and a less-trained v3) both show:

- Naive verdicts: **50/50 (100%) green** (only checks non-empty + length)
- Authoritative scorer: **69.00%** (v3c) and **67.00%** (v3)
- A **30-point deception zone** that any reader can re-derive with one command

The moat is not the score. It's that the methodology is auditable end-to-end.

## 2. The four layers (in 90 minutes)

We translated the cow/AGENT.md discipline (spec-first, human-machine dual artifacts, preserve-then-verify-then-clean) into four structural layers:

1. **`specs/`** — three JSON files (`scoring-rules.json`, `eval.endpoints.json`, `test_50.schema.json`) with a one-line spec↔code consistency check. The scorer has 10 check types, all in spec, all enforced.
2. **`analysis/`** — numbered decision logs with Trigger/Problem/Diagnosis/Fix/Verification/Lesson. Anyone can read *why* a decision was made, not just *what*.
3. **`CHANGELOG.md` + `CONTRIBUTING.md`** — SemVer timeline + 3-gate PR policy.
4. **Skill extraction** — the full "open-source reproducible release" workflow becomes reusable as `~/.workbuddy/skills/reproducible-publish/`.

This is auditable methodology, not just a benchmark. The benchmark numbers (69% / 67%) are reproducible by anyone with a clone and one command.

## 3. The CI went red. Twice.

We added `.github/workflows/release.yml` to enforce `python scripts/validate_release.py` on every push. We deliberately avoided Ollama / GPU — the verifier re-runs the scorer against committed `outputs.jsonl`, not against the live model. **Both first runs went red in 8-10 seconds.** The 8-10s timing was diagnostic: any failure past 30s would be a scoring-layer bug; this was clearly setup-phase.

Root cause: I had enabled `cache: pip` with `cache-dependency-path: requirements*.txt` on `setup-python@v5`. The repo's only match was `requirements_win3060.txt` — Windows CUDA wheels with no PyPI mapping. `setup-python` couldn't compute a stable cache hash, exited 1 in setup, never reached the `run:` blocks.

Lesson: **don't add `cache: pip` to CI steps in repos with no third-party deps.** Cargo-culting bites.

## 4. The fix, and the second bite

The fix removed the cache config entirely (nothing to cache, zero third-party imports). I wrote `analysis/008` to claim "predicted PASS, high confidence" — exactly the same phrasing that had just gotten bitten in `analysis/006`. A self-review pass caught it and downgraded to "moderate confidence" before the push.

Then we waited. A user-supplied screenshot of the Actions page confirmed: **3 green runs in a row after the fix.** The CI badge will turn green on the next GitHub cache refresh.

## 5. What the rule learned

The progression `006 (high confidence, wrong) → 008 (high confidence, downgraded) → 010 (confirmed by 3 green runs)` is now codified as a project-wide rule in [CONTRIBUTING.md § Confidence-phrasing rules](../../../../CONTRIBUTING.md). The rule: **moderate is the ceiling until external evidence exists**; "confirmed" requires real CI / user screenshot / measured data. A new verification dimension does not upgrade the phrasing.

## 6. What this proves

- A pipeline that catches its own false-green verdicts.
- A scorer that knows its check types are not the same as semantic quality.
- A discipline layer that re-derives committed numbers from raw outputs.
- A CI gate that prevents shipping if any of the above breaks.
- A history of decisions (in `analysis/006-010`) that anyone can audit.

The CI going red twice in a row is **part of the proof**, not a failure of it. A repo that says "100% reproducible" and then isn't is worse than a repo that **shows you the moment its discipline caught a problem and the fix**.

If you want to verify the claim: clone [aidless/auditable-llm-eval](https://github.com/aidless/auditable-llm-eval), run `python scripts/validate_release.py`, and read `analysis/006 → 010` to see what the discipline does when it catches its own bug.

— Posted from the formation day. Future failures will be in `analysis/011-…`, future postmortems will be in `blog/003-…`. The discipline is auditable methodology, not just a benchmark.