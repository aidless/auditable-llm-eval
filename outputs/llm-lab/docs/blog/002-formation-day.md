# One day, ten commits, two red CI runs: a repo that audits itself

*2026-07-13 · the auditable-llm-eval formation day*

> **TL;DR**
> - On a single calendar day we shipped `aidless/auditable-llm-eval` from a loose pile of scripts into a closed-loop, auditable, CI-gated open-source release: 7 commits, 85 tracked files, four-layer structure (specs / analysis / standardization / skill extraction), GitHub Actions CI, and a one-command local validator.
> - The headline numbers (v3c = **69.00%**, v3 = **67.00%**) are reproducible by anyone with a clone and one command (`python scripts/validate_release.py` → OVERALL PASS).
> - The CI went **red twice in a row** before going green — because we enabled `cache: pip` against a `requirements_win3060.txt` that has no PyPI mapping. We caught it on the third push, removed the cache config, and three subsequent runs are green (17s, 11s, 13s).
> - The most useful thing we did today was **not trust our own confidence claims**. We wrote "high confidence PASS" once, got bitten by reality, and have permanently downgraded that phrasing.

---

## 1. Where we started

At 21:30 on 2026-07-13, the repo `F:\test\2026-07-12-00-12-06` was a loose pile of scripts: a 3B QLoRA training pipeline (M0–M3), a draft scorer with 10 `reference_check` types, a discipline verifier, two committed runs (`v3c` at 69.00%, `v3` at 67.00%), and a chunk of root-level planning docs (`COPILOT_RETROSPECTIVE.md`, `EXECUTION_PLAN.md`, etc.). The headline numbers were reproducible, but the discipline layer was **decorative** — no enforced gate, no audit log, no contract between code and check semantics.

We had 23 hours of session time behind us and were at the edge of context. The user asked for **two things**:

1. Push the repo to GitHub as an open-source release.
2. Make the docs honest (a previous draft claimed "7.59% fence collapse" and "77.69% fix" — both unverifiable from any committed run; we downgraded to 67%/69% before pushing).

The push worked (initial commit, then a release notes commit). The honesty pass worked. Then the user said something that changed the trajectory:

> "按照 cow 工具栈做" — apply the cow/AGENT.md / RULE.md / WORKFLOW.md discipline to this repo.

That sentence turned a push into a layered, auditable, gated release.

---

## 2. The four layers

Cow's `WORKFLOW.md` codifies three laws: **spec-first**, **human-machine dual artifacts**, **preserve-then-verify-then-clean**. We translated them into four structural layers for `auditable-llm-eval`:

1. **Contract layer** — `specs/`. Three JSON files (`scoring-rules.json`, `eval.endpoints.json`, `test_50.schema.json`) paired with a one-line consistency check that fails if a new check type is added in code but not spec (or vice versa). 10/10 DISPATCH keys matched spec types on every run.
2. **Decision log** — `analysis/`. Numbered analyses (`001-…` through `009-…`) with `Trigger / Problem / Diagnosis / Fix / Verification / Lesson / Links`. Anyone can read why a decision was made, not just what.
3. **Standardization** — `CHANGELOG.md` (SemVer with source-doc appendix) + `CONTRIBUTING.md` (3-gate local validation policy before opening a PR). The original planning docs were preserved at the root for context.
4. **Skill extraction** — `~/.workbuddy/skills/reproducible-publish/` (mirrored to `scripts/validate_release.py` for CI). The full "open-source reproducible release" workflow becomes reusable for the next project.

This took four commits in roughly an hour.

---

## 3. The CI introduction

We added `.github/workflows/release.yml` with a single job that runs `python scripts/validate_release.py`. The workflow deliberately avoids Ollama / GPU — the verifier re-runs the scorer against committed `outputs.jsonl`, never against the live model. Anyone can re-derive the headline numbers in a CI sandbox.

We mirrored the validator script into the repo (`scripts/validate_release.py`) so CI can call it without depending on the user-level skill. We added a README badge.

Then we pushed. **Both runs went red in 8-10 seconds.** The `analysis/006-ci-simulation.md` prediction ("high confidence PASS") was wrong.

The root cause: I had enabled `cache: pip` with `cache-dependency-path: requirements*.txt` on `setup-python@v5`. The repo's only match was `requirements_win3060.txt` (Windows CUDA wheels, no PyPI mapping). `setup-python` couldn't compute a stable cache hash, exited 1 in the setup phase, never reached the `run:` blocks. The 8-10s timing was diagnostic — any failure past 30s would have been a scoring-layer issue; this was clearly setup-phase.

---

## 4. The fix

`analysis/007` recorded the incident (root cause inference, two qualifiers: "may exit 1" + "(B) cache was a red herring"). The fix removed `cache: pip` + `cache-dependency-path` entirely. The pipeline uses zero third-party imports — there's nothing to cache. After:

- YAML structural sanity verified locally.
- Python 3.11 compatibility verified locally (downloaded `cpython-3.11.6` from python-build-standalone).
- Fresh-clone + Python 3.11 ran `validate_release.py` to OVERALL PASS, exit 0.

`analysis/008` predicted "PASS ~30s wall time, **moderate confidence**" — deliberately downgraded from `analysis/006`'s "high confidence" because the same phrasing had just gotten bitten.

The fix commit landed at `a0a6abe`. Pushed. Waited.

---

## 5. The third push turned green

A screenshot from the user confirmed: **5 workflow runs** on the Actions page.

| # | commit | status | duration |
|---|---|---|---:|
| 1 | `9c61109` | ❌ | (cache era) |
| 2 | `d626c0b` | ❌ | 8s |
| 3 | `a0a6abe` | ✅ | **17s** |
| 4 | `688262b` | ✅ | **11s** |
| 5 | `62c3f74` | ✅ | **13s** |

This is the moment a repo goes from "release-validate is decorative" to "release-validate is gating". Any future push that breaks any of the four checks will fail the gate.

`analysis/010-confirmed.md` records the upgrade chain: `006` (invalid) → `007` (inferred) → `008` (moderate) → `010` (confirmed by external evidence).

---

## 6. The things I got wrong

Honest accounting, because the project is about honesty:

- **`analysis/006` claimed "high confidence PASS" with only one verification dimension** (git-archive + scoring layer). The discipline caught it: 8 seconds later, CI went red. I have downgraded this phrasing class permanently in `~/.workbuddy/MEMORY.md`. The rule is now: **moderate is the ceiling until external evidence exists**; confirmed requires real CI / user screenshot / measured data.
- **I tried to install `act` (the local GitHub Actions runner) to verify locally, but Docker Desktop's daemon wouldn't start** (WSL2 backend missing on this Windows machine). The fallback was to install Python 3.11 standalone and verify there. That worked, but it required a second non-obvious step (download a 41MB tarball from python-build-standalone) — the kind of thing that doesn't generalize.
- **I added a `cache: pip` config to `setup-python@v5` without checking whether the repo had anything to cache.** This is the kind of cargo-culting that bites. Lesson: before adding cache to a CI step, ask "what will it cache, and is that worth caching?"
- **The light-self-review at one point called out `analysis/008` for the same "high confidence" phrasing I'd already gotten bitten for.** I fixed it in the same commit. The discipline catches its own failures.

---

## 7. The shape of the repo now

```
origin/main = b458b7e, 85 tracked files, 7 commits

LICENSE / README.md (badge + TL;DR)
├── .github/workflows/release.yml         (CI: validate_release.py, no GPU, no Ollama)
├── .github/workflows/README.md           (history of why we removed cache:pip)
├── specs/                                (machine-checkable contracts)
│   ├── scoring-rules.json                (10 reference_check types)
│   ├── eval.endpoints.json               (CLI contract for the 3 eval scripts)
│   ├── test_50.schema.json               (JSON Schema for the benchmark)
│   └── README.md                         (one-line spec↔code consistency check)
├── analysis/                             (numbered decision log)
│   ├── 001-scorer-runtime-misclassification-fix.md
│   ├── 002-verify-data-model-rewrite.md
│   ├── 003-honesty-pass.md
│   ├── 004-false-green-evidence.md
│   ├── 005-self-review.md                (light-self-review, post-1.0)
│   ├── 006-ci-simulation.md              (the prediction that got bitten)
│   ├── 007-ci-v2-fix.md                  (incident + fix)
│   ├── 008-ci-v2-verification.md         (Python 3.11 + fresh-clone)
│   ├── 009-self-review.md                (post-fix review, downgraded high→moderate)
│   └── 010-confirmed.md                  (CI green, upgrade chain)
├── CHANGELOG.md                          (SemVer timeline)
├── CONTRIBUTING.md                       (3-gate policy)
├── scripts/validate_release.py           (one-command local validator)
├── copilot/score_copilot_run_v2.py       (the authoritative scorer)
├── verify_copilot_run.py                 (discipline checker)
├── eval/run_copilot_eval.py              (entry point)
├── outputs/llm-lab/                      (the actual data + docs)
│   ├── datasets/llm_lab_copilot/test_50.jsonl
│   ├── datasets/llm_lab_copilot/runs/20260713-211540-…-v3c  (69.00%)
│   ├── datasets/llm_lab_copilot/runs/20260713-213920-…-v3   (67.00%)
│   ├── docs/blog/001-…                   (the green-lights-lie story)
│   ├── docs/blog/002-…                   (this post)
│   └── docs/GETTING_STARTED.md           (1-min / 5-min / full training paths)
└── RELEASE_NOTES_v1.0.md                 (copy-paste body for GitHub Releases)
```

---

## 8. What this proves

The repo's central claim is not "we trained a good model" (3B LoRA v3c is competent but not SOTA; few-shot 82.11% still beats it). The central claim is **methodology**:

- A pipeline that catches its own false-green verdicts.
- A scorer that knows its own check types are not the same as semantic quality.
- A discipline layer that re-derives committed numbers from raw outputs.
- A CI gate that prevents shipping if any of the above breaks.
- A history of decisions (in `analysis/`) that anyone can audit.

The CI going red twice in a row is **part of the proof**, not a failure of it. A repo that says "100% reproducible" and then turns out not to be is worse than a repo that **shows you the moment its discipline caught a problem and the fix**.

If you want to verify the claim: clone the repo, run `python scripts/validate_release.py`, and read `analysis/006 → 010` to see what the discipline does when it catches its own bug.

---

## 9. What we'd do differently next time

- **Don't add `cache: pip` to CI steps in repos with no third-party deps.** Even with the wrong glob, it shouldn't have been added.
- **Local CI simulation should run in the actual CI Python version**, not just whatever's locally installed. The Python 3.11 download saved us here, but the default test should be "use the CI's Python version by default".
- **The "high confidence" rule deserves to be in the project's CONTRIBUTING.md, not just in personal memory.** Future contributors (and future-us) will write that phrase without remembering why it bit.

---

*If you got this far, the repo's discipline layer is now enforceable and the CI badge will turn green on the next GitHub cache refresh (usually within 5 minutes). Future pushes that break `validate_release.py` will fail the gate — and `analysis/006 → 010` will be there to show what to do about it.*

— The auditable-llm-eval formation day, captured in 10 commits and one self-humbling discipline loop.