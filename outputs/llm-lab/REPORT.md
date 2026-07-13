# llm-lab-copilot：一次"假绿"的捕获、根因分析与修复全过程

> **Auditable LLM Evaluation: Capturing a "False Green", Root-Causing It, and the Fix**
> A bilingual (EN + 中文) field report. The reproducible core: a copilot eval harness whose naive live verifier reports **100% green (50/50)** on every run, while the authoritative `reference_checks` scorer reports **69.00% (v3c)** and **67.00% (v3)** on two committed runs — the gap is the point.

---

## TL;DR

**English.** We fine-tuned a 3B LLM into a "copilot" and built an *auditable* evaluation harness with **two independent scorers**: (1) a fast *live verifier* that only checks "output is non-empty and long enough", and (2) an authoritative *reference-check scorer* (`copilot/score_copilot_run_v2.py`) running 10 check categories including *cognitive-honesty* dimensions. On two real runs committed in this repo, the live verifier reports **50/50 (100%) pass** for both models, while the reference-check scorer reports **69.00%** (v3c, the fix) and **67.00%** (v3). Both numbers are computed from on-disk artifacts by `verify_copilot_run.py` and are **fully reproducible** with `eval/run_copilot_eval.py`. The gap between "UI says 100% green" and "scorer says ~67–69%" is the entire lesson: a length-only check is a false green. *(An earlier, more dramatic "31/31 → 7.59% → 77.69%" arc was reconstructed from session logs during a dropped session and is **not** reproduced by the committed runs — see §5. We keep it only as motivation.)*

**中文摘要.** 我们把一个 3B 模型微调成"copilot"，并围绕它搭了一套*可审计*评测框架，含**两套独立打分器**：①快*实时验证器*只查"非空+够长"；②权威*reference-check scorer*（`copilot/score_copilot_run_v2.py`）跑 10 类检查、含"认知诚实"维度。本仓库提交的两个真实 run 上，实时验证器对两个模型都报 **50/50（100%）通过**，而权威 scorer 报 **69.00%**（v3c 修复版）和 **67.00%**（v3）。两个数字都由 `verify_copilot_run.py` 从磁盘产物算出，用 `eval/run_copilot_eval.py` **可端到端复现**。落差（界面说 100% 绿 vs scorer 说 ~67–69%）正是核心教训：只查长度的验证器是"假绿"。*(更早一段更戏剧化的"31/31→7.59%→77.69%"弧线是在一段被丢弃的会话里依据会话日志重建的，提交 run 并未复现——见 §5，仅作动机保留。)*

---

## Table of Contents / 目录

1. [Background — 背景](#1-background)
2. [The reproducible result: 100% green vs 67–69% — 可复现结果](#2-the-reproducible-result)
3. [Historical context: the 7.59% / 77.69% arc — 历史背景](#3-historical-context)
4. [The Fix (v3c) — 修复](#4-the-fix)
5. [Results: the score chain — 分数链](#5-results)
6. [Why auditable: the four ADRs — 可审计的四项决策](#6-architecture)
7. [Lessons — 经验](#7-lessons)
8. [Reproduce & repo layout — 复现与仓库结构](#8-reproduce)
9. [Open-sourcing notes — 开源说明](#9-opensource)

---

## 1. Background

**English.** `llm-lab-copilot` evaluates domain-fine-tuned LLMs on a fixed 50-task "copilot" benchmark (`test_50.jsonl`, **committed in this repo**). Each task asks the model to output structured artifacts (config YAML, report summary, failure diagnosis, verifier design, reviewer Q&A). Two scorers exist:

- **Live verdicts** (what the UI shows): a light check — output is non-empty and above a length floor. Fast, but blind to *quality*. In this repo it is produced by `eval/run_copilot_eval.py` as `verdicts.jsonl` (`verdict: pass` iff non-empty + length ≥ 20).
- **`reference_checks` scorer** (`copilot/score_copilot_run_v2.py`): the authoritative grader. It runs 10 categories — `exact_checks` / `soft_checks` / `unsupported_claims` / `missing_required_points` / `score` — including *cognitive-honesty* dimensions (`must_not_claim_tamper_proof`, `must_not_overclaim`, `must_warn_structural_limit`). A model that *claims* to be tamper-proof auto-fails.

The discipline verifier (`verify_copilot_run.py`) re-runs the real scorer from disk artifacts and surfaces the gap between "verdict says pass" and "scorer says X%". That gap is the whole point of this report.

> **Status (2026-07-13): now reproducible.** This repo ships `test_50.jsonl`, both scorers, the discipline verifier, and two committed real runs (`runs/20260713-211540-copilot-3b-lora-v3c`, `runs/20260713-213920-copilot-3b-lora-v3`). The headline numbers below are computed from those runs by `verify_copilot_run.py` and can be regenerated with `eval/run_copilot_eval.py`. An earlier strategy doc assumed components that **do not exist in the code** (`CompareResult`, a 337-test suite, a `planner/` module, Langfuse telemetry) — dropped. The `yaml` / `EvalConfig` / `llm_lab run` / `runs/` references that appear in older drafts point to a *separate* general-purpose LLM-eval platform (llm-lab, openai/deepseek-backed) and are **not** part of the copilot draft; the copilot eval ships as scripts (`eval/run_copilot_eval.py`, `copilot/score_copilot_run_v2.py`).

**中文摘要.** `llm-lab-copilot` 用一个固定的 50 题"copilot"基准（`test_50.jsonl`，**已提交本仓库**）评估领域微调后的 LLM，每题要求输出结构化产物（配置 YAML、报告摘要、故障诊断、验证器设计、审稿问答）。存在两个打分器：**实时 verdicts**（界面显示的，只查非空+长度下限，快但看不见质量；本仓库由 `eval/run_copilot_eval.py` 产出 `verdicts.jsonl`，`verdict: pass` 当且仅当非空且长度≥20）；**`reference_checks` 权威 scorer**（`copilot/score_copilot_run_v2.py`，跑 10 类检查，含"认知诚实"维度——声称自己防篡改会直接挂）。纪律校验器 `verify_copilot_run.py` 用磁盘产物重跑真实 scorer，把"verdict 说通过"和"scorer 说 X%"的落差暴露出来——这落差正是本报告的主题。

> **状态（2026-07-13）：现已可复现。** 本仓库含 `test_50.jsonl`、两套 scorer、纪律校验器，以及两个提交的真实 run（`runs/20260713-211540-copilot-3b-lora-v3c`、`runs/20260713-213920-copilot-3b-lora-v3`）。下文头版数字由 `verify_copilot_run.py` 从这两个 run 算出，可用 `eval/run_copilot_eval.py` 重新生成。早先战略文档假设了代码中并不存在的组件（CompareResult / 337 测试套件 / planner / Langfuse），已剔除。旧草稿里的 `yaml` / `EvalConfig` / `llm_lab run` / `runs/` 指向**另一个**通用评测平台（llm-lab，对接 openai/deepseek），并非 copilot 草稿的一部分；copilot 评测以脚本形式存在。

---

## 2. The reproducible result: 100% green vs 67–69%

**English.** On a 3060 we ran both models through the full harness. The live verifier lit up **50/50 (100%) pass** for *each* — because every output is non-empty and ≥ 20 chars. Re-running the authoritative scorer against the *same* outputs told a different story:

| Run | Live verdicts (naive) | reference_checks scorer | Output character |
|---|---|---|---|
| v3c (the fix) | 50/50 (100% green) | **69.00%** | coherent; `report_summary` weak (33%) |
| v3 (regression candidate) | 50/50 (100% green) | **67.00%** | coherent; 7 unsupported tamper claims |

Neither run collapsed into repetition. Both produced readable, structured answers. Yet the authoritative scorer shows only ~2/3 of the reference checks actually pass — most of the gap sits in `report_summary` (33.33% on both) and, for v3, in `reviewer_qa` (65%). The naive verifier is blind to all of it. **That blindness is the false green.**

**中文摘要.** 在 3060 上我们把两个模型都跑完整个 harness。实时验证器对*每个*都亮起 **50/50（100%）通过**——因为每条输出都非空且≥20字。用权威 scorer 对*同一批*输出重跑，故事不同：v3c **69.00%**、v3 **67.00%**，且两个 run 都输出通顺、没有重复崩溃。但权威 scorer 显示只有约 2/3 的 reference check 真正通过——差距主要在 `report_summary`（两者都 33.33%）以及 v3 的 `reviewer_qa`（65%）。naive 验证器对这一切视而不见。**这种视而不见就是假绿。**

---

## 3. Historical context: the 7.59% / 77.69% arc (NOT reproduced by this repo)

**English.** An earlier draft of this report told a more dramatic story, reconstructed from session logs during a long session that was later dropped (proxy errors / background-task reclamation): the v3 adapter allegedly collapsed into fence repetition and scored **7.59%** under the live-verifier's 31/31 green, and the v3c fix allegedly recovered to **77.69%**. **These numbers are NOT reproduced by the runs committed in this repo.** The committed v3 run scores **67.00%** on *coherent* output (no fence collapse), and the committed v3c run scores **69.00%** — not 77.69%. We retain the arc only as the *motivation* that led to building this harness; it is not a result of this repository. The methodological lesson ("a length-only verifier is a false green") is fully demonstrated by the committed runs regardless.

**中文摘要.** 本报告的更早一版讲了一个更戏剧化的故事，是在一段后来被丢弃的会话里依据会话日志重建的：v3 适配器据称退化为围栏重复、在实时验证器 31/31 绿灯下只拿 **7.59%**，而 v3c 修复据称救回到 **77.69%**。**这些数字与本仓库提交的 run 不符**。提交的 v3 run 在*通顺*输出上拿 **67.00%**（无围栏崩溃），v3c run 拿 **69.00%**——不是 77.69%。我们仅把这段弧线作为*动机*保留，它并非本仓库的结果。方法学教训（"只查长度的验证器是假绿"）由提交的 run 充分实证，与旧数字无关。

---

## 4. The Fix

**English.** **v3c** kept v3's *capacity* (rank 16 / alpha 32 / 2 epochs) but used a **tempered LR 3e-5** (between v2's 5e-5 and v3's 2e-5) on `clean200 + 10aug` data. On the committed run it scores **69.00%** (3 borderline `unsupported_claims` flagged by the scorer, see §5) — i.e. it *approaches* but does not *beat* the few-shot 3B baseline (82.11% in the historical arc).

Two engineering pitfalls had to be cleared to even *produce* the number (kept as historical lessons, from session logs):

- **Merge hang (7–8 min, no output).** Root cause: `trust_remote_code=True` + a repo-id under a restricted network made HuggingFace *resolution* hang. Fix: **local snapshot absolute path** + `TRANSFORMERS_OFFLINE=1` + drop `trust_remote_code` (Qwen2.5-Coder-3B is a standard architecture). Merge ~30s. CPU fp16 clean merge avoids malformed tensors from 4-bit `merge_and_unload`.
- **No eval-config layer (corrected).** An earlier draft claimed a v3c *EvalConfig schema bug*. Mistake: the copilot eval ships as **scripts**, not yaml, and has **no `EvalConfig`**. `EvalConfig` / `llm_lab run` / `examples/*.yaml` belong to a *separate* platform. The real entry point is `eval/run_copilot_eval.py` (+ `copilot/score_copilot_run_v2.py`).

**中文摘要.** **v3c** 保留 v3 的*容量*（r16/α32/2epoch），但用**折中 LR 3e-5**（介于 v2 的 5e-5 与 v3 的 2e-5 之间），数据用 `clean200+10aug`。提交的 run 上拿 **69.00%**（scorer 标记 3 条边界性 `unsupported_claims`，见 §5），即*接近*但*未超越* few-shot 3B 基线（历史弧 82.11%）。

为拿到数字踩过的两个真坑（历史经验教训，来自会话日志）：**合并卡死 7–8 分钟无输出**——根因 `trust_remote_code=True`+受限网络下 HF 解析挂起；修复=本地快照绝对路径+`TRANSFORMERS_OFFLINE=1`+去掉 `trust_remote_code`，约 30s 完成；CPU fp16 干净合并避开 4bit 畸形张量。*(更正：原稿称"EvalConfig schema bug"，错误——copilot 评测以脚本存在、没有 EvalConfig；`EvalConfig`/`llm_lab run`/`examples/*.yaml` 属于另一个通用平台。真实入口是 `eval/run_copilot_eval.py`。)*

---

## 5. Results

**English.** Reproducible score chain — computed from the two committed runs by `verify_copilot_run.py` (all sections PASS, WARN ×0):

| Run (committed) | Live verdicts | reference_checks | by_task (eval_yaml / report_summary / failure_diag / verifier_design / reviewer_qa) | unsupported_claims |
|---|---|---|---|---|
| **v3c** (`runs/20260713-211540-copilot-3b-lora-v3c`) | 50/50 (100%) | **69.00%** | 0.60 / 0.3333 / 1.00 / 0.6667 / 0.85 | 3 |
| **v3** (`runs/20260713-213920-copilot-3b-lora-v3`) | 50/50 (100%) | **67.00%** | 0.70 / 0.3333 / 1.00 / 0.6667 / 0.65 | 7 |

**Verdict.** Both models look perfect to the naive verifier (100% green) but only clear ~2/3 of the authoritative reference checks. The reproducible lesson: separate *structural* pass from *quality* grade, and wire the gap into CI. v3c (the fix) edges v3 by 2pp and makes fewer unsupported claims (3 vs 7).

> Historical arc (session logs, **not reproduced here**, kept as motivation only): 7B few-shot 87.80% · 3B few-shot 82.11% · v3c *claimed* 77.69% · v2 68.29% · v3 *claimed* 7.59% (fence collapse) · v3b *claimed* 8.47%. Do not cite these as results of this repo.

**中文摘要.** 可复现分数链——由 `verify_copilot_run.py` 从两个提交 run 算出（全段 PASS，WARN ×0）：

| Run（已提交） | 实时 verdicts | reference_checks | 逐任务（eval_yaml / report_summary / failure_diag / verifier_design / reviewer_qa） | 过度声称 |
|---|---|---|---|---|
| **v3c** (`runs/20260713-211540-…`) | 50/50（100%） | **69.00%** | 0.60 / 0.3333 / 1.00 / 0.6667 / 0.85 | 3 |
| **v3** (`runs/20260713-213920-…`) | 50/50（100%） | **67.00%** | 0.70 / 0.3333 / 1.00 / 0.6667 / 0.65 | 7 |

**结论**：两个模型在 naive 验证器眼里都完美（100% 绿），但只有约 2/3 通过权威 reference check。可复现教训：把"结构通过"与"质量打分"分开，把落差写进 CI。v3c（修复版）比 v3 高 2pp、过度声称更少（3 vs 7）。

> 历史弧线（会话日志，**本仓库未复现**，仅作动机）：7B few-shot 87.80% · 3B few-shot 82.11% · v3c *据称* 77.69% · v2 68.29% · v3 *据称* 7.59%（围栏崩溃）· v3b *据称* 8.47%。请勿作为本仓库结果引用。

---

## 6. Architecture

**English.** Four Architecture Decision Records encode *why* this project is auditable. Each is deliberately humble about what it is **not**.

- **ADR-0001 Content-hashing evidence** — every evidence artifact carries a `sha256`. It is **tamper-*perceiving*, not tamper-*proof***. The scorer's `must_not_claim_tamper_proof` check enforces the same honesty in the model's own output.
- **ADR-0002 Sequential synchronous runner** — single-threaded + atomic append + run-lock + resume. Trade-off: **evidence consistency > throughput**. Escape hatch: parallelize *across* runs, never *within* one.
- **ADR-0003 Local JSONL audit trail** — explicitly *rejects* Langfuse / SQLite / S3. JSONL is `diff`/`grep`/`hash`/`replay`-able, works offline, and has zero vendor lock-in. An additive exporter is a future option, not a replacement.
- **ADR-0004 Verifier ≠ scorer** — the live verifier only does *structural* checks; the authoritative `reference_checks` scorer owns the *grade* (including cognitive-honesty penalties). The **50/50-green-vs-67–69%-scorer** episode (committed runs) is its living specimen; the earlier 31/31-vs-7.59% arc was the motivation.

Full text: [`docs/adr/`](docs/adr/README.md).

**中文摘要.** 四篇 ADR 记录了*为什么*本项目可审计，且都诚实地说明自己*不是*什么。**0001 内容哈希证据**——每份证据带 sha256，是"可篡改感知"而非"防篡改"；scorer 的 `must_not_claim_tamper_proof` 在模型输出上也强制同一诚实。**0002 顺序同步 runner**——单线程+原子追加+run-lock+resume，取舍是"证据一致性 > 吞吐"，逃生口=跨 run 并行而非 run 内并行。**0003 本地 JSONL 审计**——明确否定 Langfuse/SQLite/S3，JSONL 可 diff/grep/hash/replay、离线可用、无厂商锁定。**0004 verifier≠scorer**——实时验证器只做结构检查，权威分数归 `reference_checks`（含认知诚实惩罚），**50/50 绿 vs 67–69% scorer**（提交 run）是它的活标本；更早的 31/31 vs 7.59% 弧线是动机。全文见 [`docs/adr/`](docs/adr/README.md)。

---

## 7. Lessons

**English.**

1. **A green light is an invitation, not a diploma.** Any check that only confirms "non-empty + long enough" will celebrate a weak answer. Separate *structural* pass from *quality* grade. *(Reproduced: both runs hit 100% naive-green while scoring only 67–69% on the authoritative scorer.)*
2. **Two scorers, always.** A fast live verifier for UX; an authoritative scorer for truth. Wire the gap into your CI, not your hopes.
3. **Reproduce, don't trust the report.** `verify_copilot_run.py` recomputes the score from disk artifacts — the predicted number is never the result.
4. **Cognitive honesty is gradeable.** "I am tamper-proof" must be a *failing* answer. Encode epistemic humility into the scorer.
5. **Be honest about what you can't reproduce.** Numbers from dropped sessions (the 77.69% / 7.59% arc) were demoted to motivation, not results, the moment committed runs disagreed.

**中文摘要.** 1. **绿灯是邀请函，不是毕业证书**——只查"非空+够长"的检查会为弱答案鼓掌，必须把结构通过与质量打分分开。*(已复现：两个 run 都拿 100% naive 绿，但权威 scorer 只给 67–69%。)* 2. **永远两套打分器**——快验证器管体验，权威 scorer 管真相，把落差写进 CI 而非寄托于希望。3. **复现，别信报告**——`verify_copilot_run.py` 从磁盘重算分数，预测值永远不是结果。4. **认知诚实可打分**——"我防篡改"必须是*挂科*答案，把认知谦逊写进 scorer。5. **对不可复现的东西保持诚实**——被丢弃会话里的数字（77.69%/7.59% 弧线）一旦与提交 run 矛盾，就降级为动机而非结果。

> 这五条已独立成文档：[`docs/LESSONS.md`](docs/LESSONS.md)（中英双语，可单独阅读）。

---

## 8. Reproduce

**English.** Workflow (all scripts are in this repo root):

```bash
# 0) prerequisites: a local ollama serving the model (e.g. copilot-3b-lora-v3c:latest)
#    at http://localhost:11434

# 1) generate a run end-to-end (predictions + naive verdicts + authoritative score + config)
python eval/run_copilot_eval.py --model copilot-3b-lora-v3c:latest
#    -> outputs/llm-lab/datasets/llm_lab_copilot/runs/<run_id>/
#       outputs.jsonl  verdicts.jsonl  report.jsonl  summary.json  config.yaml

# 2) discipline check: re-run the REAL scorer from disk, surface the gap
python verify_copilot_run.py \
    --run-dir outputs/llm-lab/datasets/llm_lab_copilot/runs/<run_id> \
    --dataset outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl \
    --scorer  copilot/score_copilot_run_v2.py \
    --model-expected copilot-3b-lora-v3c:latest
#    -> exits 0 when every section PASSes; prints overall_reference_check_rate
```

The two runs cited in this report are **already committed** (fully reproducible without retraining):

- `runs/20260713-211540-copilot-3b-lora-v3c` — v3c, **69.00%**
- `runs/20260713-213920-copilot-3b-lora-v3` — v3, **67.00%**

> Note: `eval/run_copilot_eval.py` calls `ollama` over `http://localhost:11434` and **pins `temperature: 0`** in the committed `config.yaml`. The benchmark `test_50.jsonl` and the two `runs/` are committed, so the headline numbers are reproducible from this repo as shipped.

**Repo layout (what ships here):**

```
README.md                      # root: TMLR fine-tune project + §10 entry to this subproject
COPILOT_RETROSPECTIVE.md       # empirical source of truth (score chain to v2, historical)
COPILOT_NEXT_STEPS.md          # fix roadmap (historical)
verify_copilot_run.py          # discipline verifier (re-runs real scorer from disk)
eval/
  run_copilot_eval.py          # copilot eval entry point (predict + naive verdict + score + config)
  run_eval.py                  # separate TMLR 200-question harness (mc/open grading)
  build_eval_set.py            # 200-q eval set builder
  eval_questions.jsonl         # question bank
copilot/
  score_copilot_run_v2.py      # authoritative reference_checks scorer (10 categories)
outputs/llm-lab/
  README.md                    # subproject portal (this report's home context)
  REPORT.md                    # THIS document
  datasets/llm_lab_copilot/
    test_50.jsonl              # the 50-task benchmark (committed)
    runs/                      # committed real runs (v3c 69%, v3 67%)
  docs/
    adr/                       # ADR-0001..0004 + README index
    blog/
      001-auditable-llm-eval-no-green-lights.md   # HN-oriented blog
    LESSONS.md                 # five disciplines of auditable eval (EN+中文)
LICENSE                         # MIT (root of repo)
```

**中文摘要.** 复现流程：①本地 ollama 提供模型（如 `copilot-3b-lora-v3c:latest`）于 `http://localhost:11434`；② `python eval/run_copilot_eval.py --model ...` 一条命令产出 predictions + naive verdicts + 权威分 + config；③ `python verify_copilot_run.py --run-dir ...` 从磁盘重跑真实 scorer、暴露落差。本报告引用的两个 run **已提交**（无需重训即可复现）：v3c 69.00%、v3 67.00%。`test_50.jsonl` 与两个 `runs/` 均已提交，故头版数字可由本仓库端到端复现。`eval/run_copilot_eval.py` 通过 `localhost:11434` 调 ollama，并在提交的 `config.yaml` 中**钉死 `temperature: 0`**。

---

## 9. Open-sourcing notes

**English.**

- **What's included (now reproducible):** the benchmark `test_50.jsonl`, both scorers (`copilot/score_copilot_run_v2.py`, `verify_copilot_run.py`), the eval entry point `eval/run_copilot_eval.py`, two committed real runs (`runs/20260713-211540-…-v3c` = 69.00%, `runs/20260713-213920-…-v3` = 67.00%), all four ADRs, the blog, and this report. The headline scores are reproducible from this repo as shipped.
- **What's NOT claimed:** we do **not** claim a tamper-proof system, a 337-test suite, a `planner/`, or Langfuse integration — those appeared in an early strategy doc but are absent from the code. The ADRs describe what *is*. We also do **not** present the 77.69% / 7.59% arc as a result — those session-log numbers are contradicted by the committed runs.
- **Authoring transparency:** the ADR×4 + blog were first drafted in an earlier long session that was **dropped** (proxy errors / background-task reclamation) and never persisted to disk; they were **rebuilt from the empirical log** in a later session. The *current* headline results (69.00% / 67.00%) come from **committed runs** and are reproducible via `verify_copilot_run.py`.
- **License:** `LICENSE` (MIT) is included at repo root — replace the copyright holder (`llm-lab-copilot Contributors`) with your own name before publishing. This report and the docs are authored to be safely open-sourced.
- **Suggested repo tagline:** *"An auditable LLM eval harness that caught its own model's verdicts lying — 100% green, 67–69% real."*

**中文摘要.** **已包含（现可复现）**：基准 `test_50.jsonl`、两套 scorer、评测入口 `eval/run_copilot_eval.py`、两个提交的真实 run（v3c 69.00%、v3 67.00%）、四篇 ADR、博客、本报告；头版分数可由本仓库端到端复现。**不声称**：我们不声称有防篡改系统、337 测试套件、`planner/` 或 Langfuse 集成——这些出现在早先战略文档但代码中并不存在；我们也不把 77.69%/7.59% 弧线当结果（那些会话日志数字与提交 run 矛盾）。**作者透明度**：ADR×4+博客最早在一段被中断的长会话里起草但从未落盘，后来依据实证日志重建；*当前*头版结果（69.00%/67.00%）来自**提交 run**，可用 `verify_copilot_run.py` 复现。**许可证**：`LICENSE`（MIT）已置于仓库根目录——发布前把版权持有者改为你自己的名字即可。**建议仓库标语**："一套可审计 LLM 评测框架，抓到自己的模型 verdicts 撒谎——100% 绿，67–69% 真。"

---

*Report status (2026-07-13): written bilingual (EN + 中文), grounded in **committed, reproducible runs** (v3c 69.00%, v3 67.00%) verified by `verify_copilot_run.py`. Companion docs: [`docs/adr/`](docs/adr/README.md) · [`docs/blog/001-auditable-llm-eval-no-green-lights.md`](docs/blog/001-auditable-llm-eval-no-green-lights.md) · [`docs/LESSONS.md`](docs/LESSONS.md) · portal [`README.md`](README.md).*
