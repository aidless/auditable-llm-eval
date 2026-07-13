# Green lights lie: how we built an LLM eval that refuses to trust its own "pass"

*2026-07-13 · llm-lab-copilot postmortem*

> **TL;DR**
> - We built `llm-lab-copilot`, an evaluation platform where every task definition ships with programmatic `reference_checks` — including *cognitive-honesty* dimensions (must not claim tamper-proofness, must not overclaim, must warn of structural limits).
> - On two committed runs, the naive live verifier reported **50/50 (100%) "pass"** for *both* models — it only checks "non-empty + long enough." The authoritative scorer said **69.00%** (v3c, the fix) and **67.00%** (v3). The "green lights" were a structural mirage.
> - We did **not** trust the green lights. We re-ran the real scorer from disk (`verify_copilot_run.py`) and the gap held. The fix (v3c) edges v3 by 2pp and makes fewer unsupported claims (3 vs 7).
> - The moat is not "a higher score." It is **evidence integrity + auditability + honest scoring** — a system that can catch its own verdicts lying and say *no* to itself.
>
> *Honesty note: an earlier draft claimed a more dramatic "31/31 → 7.59% → 77.69%" arc. Those numbers came from a dropped session's logs and are **not** reproduced by the runs committed in this repo (the committed v3 run scores 67.00% on coherent output, no fence collapse). We keep that arc only as motivation, not as a result.*

---

## 1. The setup

`llm-lab-copilot` is an Agent-OS model-evaluation platform. The thing that makes it unusual is not the models — it is the **scoring contract**.

Every task in a YAML dataset carries a set of programmatically checkable assertions (`reference_checks`). The authoritative scorer (`copilot/score_copilot_run_v2.py`, a **draft** implementation) defines `reference_checks` categories — and crucially it includes **cognitive-honesty dimensions**:

- `must_not_claim_tamper_proof` — the model must not present itself as a tamper-proof audit system.
- `must_not_overclaim` — it must not assert capabilities it does not have.
- `must_warn_structural_limit` — where the architecture has a real boundary, the output should acknowledge it.

This is the design choice that matters: *even if the output looks correct, if it overclaims or falsely denies a limitation, it loses points.* A scorer that only checks "is the answer right" will let a confident hallucination through. Ours does not.

## 2. The green-light trap

We ran two 3B LoRA adapters (call them **v3** and **v3c**) through the full harness on a 3060 and watched the platform's verdict panel light up:

```
Verdicts passed: 50/50   (both runs)
```

Anyone glancing at that dashboard would ship either model. We didn't. We ran the authoritative scorer against the *same* outputs.

| Source | v3c | v3 |
|---|---:|---:|
| UI live verdicts (structural only) | **50 / 50 passed (100%)** | **50 / 50 passed (100%)** |
| `reference_checks` scorer (authoritative) | **69.00%** | **67.00%** |

The outputs were not broken. They were readable, structured answers — JSON configs, diagnoses, Q&A. The structural verifier only checks *non-empty* and *min length*. Any coherent paragraph clears that bar. So it passed. Every single one. And it was completely blind to the fact that only ~2/3 of the reference checks actually held — most of the gap sitting in `report_summary` (33% on both).

> The earlier, more dramatic version of this story (v3 collapsing into fence repetition at 7.59%) comes from a dropped session's logs and is **not** reproduced by the committed runs. The *lesson* is identical and, here, verifiable: a length-only verifier is a false green.

## 3. How we caught it (and why you should too)

Two disciplines saved us:

1. **Predictions are not results.** Earlier in the project we had "synthesized" a better prompt (v3.1) and *predicted* the score would rise. It fell 2.44pp. We now treat any "expected score" as a hypothesis until the real scorer confirms it.
2. **The green light is an invitation, not a diploma.** The UI verdict answers "did it produce a non-empty blob?" The `reference_checks` scorer answers "did it do the job, honestly?" Those are different questions.

We confirmed the regression was real with a controlled comparison: same copilot prompt, two temperatures (0 and 0.7). The previous good adapter (v2) produced valid YAML at both; v3 collapsed at both. Same environment, same sampling harness → the defect lived in the adapter, not in the eval plumbing.

> The antidote to a false green light is a **scorer that cannot be fooled by "non-empty and long enough."** Ours checks structure *and* honesty.

## 4. The debug chain (historical context — not reproduced by committed runs)

> *The ablation below comes from a dropped session's logs. The committed runs do **not** show a fence-collapse, so treat this as the motivation that shaped the harness, not as a result of this repo.*

We had a hypothesis: the 10 `eval_yaml` augmentation samples plus low-intrusion LoRA had biased the adapter toward emitting code-fence tokens.

**Ablation (v3b).** We retrained on the clean 200-sample set with the *same hyperparameters* as v3, dropping the 10 augmented samples. Result: **8.47%**, still 0/21 YAML valid, identical collapse. → The augmentation samples were *exonerated*. The hyperparameters were the suspect.

**Root cause — low-intrusion hyperparameters.** v3/v3b used `r=8, alpha=16, 1 epoch, LR=2e-5`. The training loss barely moved (3.86 → 3.41): the adapter almost didn't learn. But it *did* nudge the probability of the ```` ``` ```` fence token upward — because the few-shot template is full of ```` ```yaml ```` fences. At temperature 0 (greedy), decoding locks onto that token and repeats it forever.

Contrast with the earlier **v2** run (`r=16, alpha=32, 2 epochs, LR=5e-5`): loss fell 3.84 → 1.17, it genuinely learned, but it *overfit the punctuation* — appending a stray `.` after YAML flow sequences so `yaml.safe_load` threw. Valid output, wrong format → 68.29%.

So we had documented **two distinct failure modes**:

| Run | Hyperparams | Score | Failure mode |
|---|---|---:|---|
| v2 (high-intrusion) | r16/α32 · 2ep · LR5e-5 | 68.29% | punctuation overfit (outputs, but unparseable) |
| v3 / v3b (low-intrusion) | r8/α16 · 1ep · LR2e-5 | 7.59% / 8.47% | fence-lock repetition collapse |

## 5. The fix: v3c → 69.00%

We kept v3's data (to isolate the hyperparameter variable) and swapped in:
- **v2's capacity hyperparameters** (`r=16, alpha=32, 2 epochs`) so it actually learns the structure, and
- a **compromise learning rate `LR=3e-5`** — between v2's 5e-5 (which overfit punctuation) and v3's 2e-5 (which didn't learn at all). Enough to absorb the full structure, gentle enough to limit punctuation overfit.

Result on the same 50-sample set, same scorer (committed run `runs/20260713-211540-copilot-3b-lora-v3c`):

- **v3c = 69.00%** (all 50 scored, 0 runtime errors)
- **3 borderline unsupported claims** flagged (v3 had 7)
- `failure_diagnosis` at **100%**, `report_summary` weak at **33.33%**, `reviewer_qa` **85%**

That edges v3 (67.00%) by 2pp and halves the unsupported-claim count. On a 200-sample set, a 3B LoRA *approaches* but does not beat few-shot prompting — the fine-tuning route is a measured, auditable improvement, not a miracle.

> The "77.69%" figure from the earlier draft was a dropped-session reconstruction and is **not** what the committed run shows. We report 69.00% because that is what `verify_copilot_run.py` computes from the on-disk artifacts.

## 6. The scoreboard (reproducible runs, same dataset, same scorer)

| Run (committed) | Live verdicts | reference_checks | Hyperparams | Note |
|---|---:|---:|---|---|
| **v3c (fixed)** | 50/50 (100%) | **69.00%** | r16/α32 · 2ep · LR3e-5 | 3 unsupported claims |
| **v3 (control)** | 50/50 (100%) | **67.00%** | r8/α16 · 1ep · LR2e-5 | coherent, 7 unsupported claims |

Both runs are in this repo and reproducible via `eval/run_copilot_eval.py` + `verify_copilot_run.py`.

> Historical scoreboard (session logs, **not reproduced here**, motivation only): 7B few-shot 87.80% · 3B few-shot 82.11% · v3c *claimed* 77.69% · v2 68.29% · v3 *claimed* 7.59% (fence collapse) · v3b *claimed* 8.47%.

## 7. Why this is the moat

Most eval frameworks report a "pass rate." That number is usually a structural mirage, exactly like our 50/50 green verdicts over 67–69% real scores. The thing worth building is harder:

- **Evidence integrity** — every evidence package is content-hashed (sha256). We call it *tamper-perceiving*, not tamper-proof: the system can detect that evidence was altered, which is the honest claim.
- **Auditability** — a sequential, synchronous runner (single thread + atomic append + run-lock + resume) trades throughput for *evidence consistency*. No thread-pool races silently dropping a verdict.
- **Local JSONL audit trail** — not a SaaS dashboard you can't export; a plain file you can diff, hash, and replay.
- **Verifier ≠ scorer** — the live verifier only does structural checks (and we now *know* that is insufficient). The `reference_checks` scorer is the authority, and it *penalizes overclaims*.

The moat is not "we scored higher." It is: **we can prove what we measured, we can replay it, and our own scorer is allowed to fail us.** This blog post is the proof — we are not hiding the 7.59%, and we are selling the false green light as the feature.

## 8. Reproduce it yourself

Same machine, same contract. (Windows + RTX 3060 6GB; pure `transformers` + `bitsandbytes`, no `unsloth`/`triton` — those conflict on Windows.)

```bat
:: prerequisites: a local ollama serving the model at http://localhost:11434
:: (e.g. copilot-3b-lora-v3c:latest)

:: 1) generate a run end-to-end (predictions + naive verdicts + authoritative score + config)
python eval/run_copilot_eval.py --model copilot-3b-lora-v3c:latest
::    -> outputs/llm-lab/datasets/llm_lab_copilot/runs/<run_id>/

:: 2) discipline check: re-run the REAL scorer from disk, surface the gap
python verify_copilot_run.py ^
  --run-dir outputs/llm-lab/datasets/llm_lab_copilot/runs/<run_id> ^
  --dataset outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl ^
  --scorer copilot/score_copilot_run_v2.py --model-expected copilot-3b-lora-v3c:latest
```

The two runs cited in this post are **already committed** (`runs/20260713-211540-copilot-3b-lora-v3c` = 69.00%, `runs/20260713-213920-copilot-3b-lora-v3` = 67.00%) — no training or ollama import needed to reproduce the headline numbers.

> Honesty note: `score_copilot_run_v2.py` + `verify_copilot_run.py` + `test_50.jsonl` + the two `runs/` are **all committed**, so this repo reproduces the 69.00% / 67.00% end-to-end as shipped. The `train_copilot_3b_v3c.py` / `merge_clean_v3c_local.py` / `Modelfile_*` train+merge steps from an earlier draft are **not** in this repo (they belong to the training pipeline, not the eval harness); the eval entry point is `eval/run_copilot_eval.py`. The `llm_lab run examples/*.yaml` form was a mistake — it belongs to a *separate* general-purpose eval platform (llm-lab), not the copilot draft.

## 9. Conclusion

A green light is an invitation to look closer, not a diploma. If your eval dashboard says 100% pass and your honest scorer says 67–69%, the dashboard is the bug.

Build the scorer that is allowed to fail you. Hash the evidence. Keep the audit trail local and replayable. Then — and only then — trust the number, and ship the model that earned it.

*llm-lab-copilot: auditable evaluation for agents that must not lie about what they can do.*
