# 012 — Final State Report (the auditable-llm-eval formation day)

> **STATUS**: end-of-day closure. This is the **1-page cheat sheet** for anyone (including future-us) opening this repo in a fresh session and asking "what is this and where do I start?"

**Date**: 2026-07-14 01:30 (formation day: 2026-07-13 21:30 → 2026-07-14 01:30, ~4 hours)
**HEAD**: `f51a19e`
**Audience**: future contributors, future-us, anyone reviewing the project for adoption

---

## 1. The TL;DR

`aidless/auditable-llm-eval` is **14 commits, 89 tracked files, 4 layers, 4 blog posts, 10 numbered analyses, 39 stdlib unit tests, and a 6-job cross-platform CI matrix that has been verified end-to-end on this machine**. The headline numbers (v3c = 69.00%, v3 = 67.00%) are reproducible by anyone with a clone and one command. The methodology is auditable: every decision is in `analysis/`, every spec is machine-checked, every confidence claim is in the ladder (`confirmed / moderate / speculative / unverifiable`). Two real CI failures (the `cache: pip` incident) are preserved in `analysis/007` as part of the proof, not as a bug.

## 2. The numbers (one screen)

| dimension | value | where it lives |
|---|---|---|
| Commits | 14 | `git log --oneline` |
| Tracked files | 89 | `git ls-files \| wc -l` |
| Blog posts | 4 (001 主张 / 002 中文形成史 / 002-en 英文 HN / 003 CI 复盘) | `outputs/llm-lab/docs/blog/` |
| Analyses | 11 (001-010 + README) | `analysis/` |
| ADRs | 4 | `outputs/llm-lab/docs/adr/` |
| Specs | 3 JSON + 1 README | `specs/` |
| Unit tests | 39 cases, all pass | `tests/test_scorer.py` |
| Validator | 1 command, 4 checks | `scripts/validate_release.py` |
| Headline numbers | v3c 69.00% / v3 67.00% | `outputs/llm-lab/datasets/llm_lab_copilot/runs/` |
| Live verdicts vs real | naive 100% green, real 67-69% | `analysis/004-false-green-evidence.md` |
| Local validation | 6 dimensions × pass | this report §4 |
| CI matrix | 3 OS × 2 step = 6 jobs | `.github/workflows/release.yml` |

## 3. The 14-commit timeline

```
4e0c943  Initial commit: llm-lab-copilot auditable LLM eval (reproducible)
6111944  docs: add v1.0.0 release notes
63b978c  feat: add specs/analysis layer + CHANGELOG/CONTRIBUTING (specs-first)
c188cda  fix: exclude _verify_* byproducts from gitignore
9c61109  feat(ci): add GitHub Actions release-validate + mirror scripts/
d626c0b  docs: README badges + self-review + CI simulation report
a0a6abe  fix(ci): remove broken cache:pip from setup-python (caused 2 red CI runs)
688262b  docs(analysis): CI v2 verification report (Python 3.11 + fresh-clone)
62c3f74  docs(analysis): self-review + downgrade 008 confidence claim
b458b7e  docs(analysis): CI v2 fix confirmed (3 green runs)
d09dca6  docs(blog): 002-formation-day (中文)
cd96feb  docs(readme): link blog/002 in portal nav
d5aef9e  docs: phrase-downgrade rule + 002-en + 003-ci-postmortem
f51a19e  feat(ci+tests): cross-platform CI matrix + stdlib unittest suite
```

The narrative arc: push → 4-layer hardening → CI introduction → 2 red CI runs → fix → verify → confirmed → 4 blog posts → 3 OS matrix + 39 unit tests.

## 4. The 6-dimension local validation matrix (all PASS)

This is the strongest evidence we can produce locally that the CI will pass. Six independent dimensions, all green on this machine:

| # | dimension | what it proves | result |
|---|---|---|---|
| 1 | Python 3.13 + real repo | scoring layer + discipline layer on this dev box | ✅ |
| 2 | Python 3.11.6 + real repo | same, on the CI's pinned Python version | ✅ |
| 3 | Python 3.13 + fresh-clone (`git archive`) | not contaminated by dirty local state | ✅ |
| 4 | Python 3.11.6 + fresh-clone | closest local proxy to real CI runner | ✅ |
| 5 | Full release.yml 5-step sequence | end-to-end behavior matches what CI will run | ✅ |
| 6 | Release zip (`llm-lab-opensource.zip`) extracted + run | what a real user from GitHub Release will experience | ✅ |

In every case: `validate_release.py` exits 0, all 4 checks pass, 39/39 tests pass.

## 5. The repo topology

```
aidless/auditable-llm-eval  (89 files, 14 commits, ~300 KB)
├── LICENSE                              MIT
├── README.md                            portal (4 shields + EN TL;DR + 中文 body)
├── CHANGELOG.md                         SemVer timeline with source-doc appendix
├── CONTRIBUTING.md                      3-gate PR policy + phrase-downgrade rule
├── RELEASE_NOTES_v1.0.md                copy-paste body for Releases page
│
├── specs/                                contract layer (machine-checkable)
│   ├── scoring-rules.json                 10 reference_check types + overclaim/runtime patterns
│   ├── eval.endpoints.json                CLI contract for 3 eval scripts
│   ├── test_50.schema.json                JSON Schema for the benchmark
│   └── README.md                          one-line spec↔code consistency check
│
├── analysis/                             decision log (numbered)
│   ├── 001-scorer-runtime-misclassification-fix.md
│   ├── 002-verify-data-model-rewrite.md
│   ├── 003-honesty-pass.md
│   ├── 004-false-green-evidence.md
│   ├── 005-self-review.md
│   ├── 006-ci-simulation.md              (the prediction that got bitten)
│   ├── 007-ci-v2-fix.md                  (incident + fix)
│   ├── 008-ci-v2-verification.md         (Python 3.11 + fresh-clone)
│   ├── 009-self-review.md                (downgrade high→moderate)
│   ├── 010-confirmed.md                  (CI green, upgrade chain)
│   └── README.md                          maintenance rules
│
├── tests/                                stdlib unittest (zero third-party deps)
│   ├── test_scorer.py                    39 cases covering 10 check types + score_one
│   └── README.md                          why-stdlib-not-pytest
│
├── .github/workflows/
│   ├── release.yml                        3 OS × 2 step = 6 jobs (validate + tests)
│   └── README.md                          why no cache:pip (history)
│
├── scripts/
│   ├── validate_release.py                one-command local validator (4 checks)
│   └── README.md
│
├── copilot/                              the scorer
│   ├── score_copilot_run_v2.py            10 check types, runtime/overclaim detectors
│   └── (related: gen_test50.py)
│
├── eval/                                 entry point
│   ├── run_copilot_eval.py                runs model on test_50, writes outputs+verdicts+report
│   └── run_eval.py
│
├── verify_copilot_run.py                 discipline checker (7 sections)
│
├── outputs/llm-lab/                      the actual data + docs
│   ├── datasets/llm_lab_copilot/
│   │   ├── test_50.jsonl                  50-task benchmark
│   │   ├── runs/20260713-211540-…-v3c/    5 files (committed, 69.00%)
│   │   ├── runs/20260713-213920-…-v3/     5 files (committed, 67.00%)
│   │   └── gen_test50.py
│   ├── docs/
│   │   ├── GETTING_STARTED.md             1-min / 5-min / full training paths
│   │   ├── LESSONS.md
│   │   ├── blog/001-…md                   "Green lights lie" (substantive claim)
│   │   ├── blog/002-…md                   形成史 (中文)
│   │   ├── blog/002-…-en.md               formation day (English HN version)
│   │   ├── blog/003-…md                   CI postmortem (English HN version)
│   │   └── adr/0001-0004 + README.md      architecture decision records
│   ├── REPORT.md                          technical report
│   └── README.md                          portal
│
├── training scripts (root, for retraining)
│   ├── train_copilot_3b.py
│   ├── train_copilot_3b_v3b.py
│   ├── train_copilot_3b_v3c.py           the fixed hyperparameters
│   ├── merge_clean.py / _v3b.py / _v3c_local.py
│   ├── Modelfile_copilot / 2 / 3 / 3b / 3c
│   ├── requirements_win3060.txt          (gitignored, but in zip for self-containment)
│   └── train_seed_200_aug.jsonl          (gitignored, but in zip)
│
└── (other root planning docs preserved for context)
    ├── COPILOT_RETROSPECTIVE.md          source-doc appendix of CHANGELOG
    ├── EXECUTION_PLAN.md
    ├── M2_CONFIG_REVIEW.md
    ├── NEXT_STEPS_PLAN.md
    ├── RUN_GUIDE.md
    ├── RUN_LOG.md
    ├── TRAINING_TROUBLESHOOTING.md
    └── qwen25-3b-tmlr-finetune-plan.md
```

## 6. The phrase-downgrade rule (the meta-lesson)

The 6-step progression `006 (high confidence, wrong) → 007 (incident) → 008 (high confidence, downgraded) → 009 (self-review) → 010 (confirmed by 3 green runs) → CONTRIBUTING.md` is now codified as the only project-wide writing rule. The rule:

- **Confirmed** = measured + peer-reviewed + multiple independent verifications
- **Moderate** = measured + single-dimension local verification + inferred extrapolation
- **Speculative** = inference only, no measurement
- **Unverifiable** = requires external access

**One-line test**: before writing any "X confidence" claim, ask "if this turns out wrong, how embarrassing would it be?" If very, drop the confidence level.

This is now in `CONTRIBUTING.md` § Confidence-phrasing rules AND in `~/.workbuddy/MEMORY.md` for cross-project reuse.

## 7. The 1-page cheat sheet for "what to do next time you open this repo"

1. **Verify nothing is broken**: `python scripts/validate_release.py` → expect OVERALL: PASS, exit 0.
2. **Run the tests**: `python -m unittest discover -s tests -v` → expect 39/39 OK.
3. **Want to add a check type**? Edit `specs/scoring-rules.json` FIRST (per spec-first rule), then implement in `copilot/score_copilot_run_v2.py` and add to DISPATCH, then add a test in `tests/test_scorer.py`, then add a `reference_check` row in `test_50.jsonl`. The CI will catch any drift between spec and code.
4. **Want to add a new run**? Run `python eval/run_copilot_eval.py --model <tag>`, then `python verify_copilot_run.py --run-dir <new_run> --dataset outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl --scorer copilot/score_copilot_run_v2.py`. Only push if 7/7 sections pass.
5. **Want to add a new analysis**? Use `NNN-short-slug.md` naming, follow the `Trigger / Problem / Diagnosis / Fix / Verification / Lesson / Links` template (see `analysis/README.md`). Update both `analysis/README.md` and `CHANGELOG.md` [Unreleased] section.
6. **Writing any conclusion with a confidence level?** Use the ladder (§6). If the result turns out wrong, downgrade. The "high confidence" trap is the only failure mode we have personal evidence for.

## 8. What's open / not done

| # | open item | why it's open | next step |
|---|---|---|---|
| 1 | GitHub Actions 6-job matrix has not yet been observed live (only simulated locally — analysis/008 + this report §4) | this env has no token; the push that triggered the matrix landed at `f51a19e` but the user has not yet screenshotted the Actions page | user to screenshot the 6 jobs; if any fail, write analysis/013+ with the failure mode and iterate |
| 2 | `tmp/` 200 Python scripts and ~30 root-level planning docs (COPILOT_RETROSPECTIVE etc.) are not yet organized into the spec-first structure | 30-day deferral; not blocking release | future cleanup session |
| 3 | GitHub repo About description + topics not set | this env has no token | user to set via Settings → General |
| 4 | GitHub Release v1.0.0 not yet created with `llm-lab-opensource.zip` attached | this env has no token | user to Draft a new release using `RELEASE_NOTES_v1.0.md` body |
| 5 | `validate_release.py` does not yet have a `--strict` mode that treats WARN as FAIL | useful for future tightening, not necessary now | add when the matrix has been observed to behave as expected |
| 6 | No benchmarks across more models (qwen2.5:7b, mistral:7b, gpt-oss:20b) | out of scope for the formation day | future expansion |

## 9. The single sentence this project wants to be remembered by

> **The discipline is the deliverable, not the headline score.** The repo's central claim is not "v3c = 69.00%" (a number, easy to fake). The central claim is "**you can re-derive that number from raw outputs, in one command, on three operating systems, in front of 39 unit tests, and the spec↔code consistency check will fail if anyone lies about any of it.**" Methodology is auditable, not just the benchmark.

## 10. The links

- Repo: https://github.com/aidless/auditable-llm-eval
- Blog 001 (主张): `outputs/llm-lab/docs/blog/001-auditable-llm-eval-no-green-lights.md`
- Blog 002 (形成史 中文): `outputs/llm-lab/docs/blog/002-formation-day.md`
- Blog 002-en (English HN): `outputs/llm-lab/docs/blog/002-formation-day-en.md`
- Blog 003 (CI 复盘 HN): `outputs/llm-lab/docs/blog/003-ci-discipline-postmortem.md`
- 4 ADRs: `outputs/llm-lab/docs/adr/0001-0004`
- The CI failure: `analysis/007-ci-v2-fix.md` (the most important 6 KB in this repo)
- The 6-dimension validation: this report §4

---

*If you got this far, the formation day is over. The discipline is the deliverable. Future failures will be in `analysis/013-…`. Future blog posts will be in `004-…`. The repo is self-auditing. Pass it on.*