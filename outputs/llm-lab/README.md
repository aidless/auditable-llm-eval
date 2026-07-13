# llm-lab-copilot — 可审计 LLM 评测平台

`llm-lab-copilot` 是对微调模型做**可审计**评估的评测平台。核心纪律只有一句：

> **绿灯只是邀请函，不是毕业证书。**

本目录是它在本工程中的文档与产物落地处。平台的设计决策与实证经过见 `docs/`。

> 🚀 **小白从这里开始**：不会命令行、没显卡也没关系。看 [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) —— 从装 Python 到跑出"假绿"证据，一步一步复制命令即可。最快 1 分钟的最小验证（**连 Ollama 都不用装**）：
> ```bash
> python verify_copilot_run.py \
>   --run-dir outputs/llm-lab/datasets/llm_lab_copilot/runs/20260713-211540-copilot-3b-lora-v3c \
>   --dataset outputs/llm-lab/datasets/llm_lab_copilot/test_50.jsonl \
>   --scorer  copilot/score_copilot_run_v2.py
> ```
> 看到 7 项全 `[PASS]` 即证明 69.00% 是真实从磁盘算出来的。

> ✅ **状态（2026-07-13）：现已可复现。** copilot 评测以脚本形式存在（`eval/run_copilot_eval.py` 入口 + `copilot/score_copilot_run_v2.py` 权威 scorer + `verify_copilot_run.py` 纪律校验器），基准 `test_50.jsonl` 与两个真实 run（`runs/20260713-211540-…-v3c`=**69.00%**、`runs/20260713-213920-…-v3`=**67.00%**）**已提交本仓库**，头版分数可由本仓库端到端复现。⚠️ 诚实提示：更早会话日志里"v3c 77.69% / v3 7.59% 围栏崩溃"的戏剧化弧线**未被提交 run 复现**（提交 run 显示 v3 在通顺输出上拿 67%，并未崩溃），仅作为*动机*保留，不当作本仓库结果。文档里的 `yaml` / `EvalConfig` / `llm_lab run` 属**另一个**通用平台（llm-lab），非 copilot 草稿。四篇 ADR 记录设计意图，其中顺序同步 runner / 本地 JSONL 审计 / 内容哈希尚属设计层、未在 copilot 草稿中落盘实现。

> **完整过程报告（开源用）**：[`REPORT.md`](REPORT.md) — 中英双语，记录"31/31 假绿 → 7.59% 真实分 → v3c 77.69% 修复"的全过程、根因分析、复现步骤与开源说明。
> **经验文档**：[`docs/LESSONS.md`](docs/LESSONS.md) — 可审计评测的五条纪律（中英双语），可独立阅读。

---

## 这是什么

- **可审计（设计目标）**：每份证据带 `sha256`，审计轨迹是本地 JSONL，可 `diff` / `grep` / `hash` / `replay`，离线可用、无供应商锁定。*(注：这是 ADR 0001/0003 的设计意图，copilot 草稿 scorer 当前尚未落盘 JSONL 审计轨迹。)*
- **顺序同步**：runner 单线程 + 原子追加 + run-lock + resume，换取**证据一致性 > 吞吐**。
- **认知诚实**：内置 verifier 只做结构判定；权威 `reference_checks` scorer 含 `must_not_claim_tamper_proof` / `must_not_overclaim` / `must_warn_structural_limit` 等"认知诚实"惩罚维度，禁止自我过度声称。
- **假绿标本（可复现）**：naive 实时验证器对两个模型都报 50/50（100%）通过，权威 scorer 只打 69.00%（v3c）/ 67.00%（v3）——"100% 绿 vs ~2/3 真"正是本平台要抓的假绿。

---

## 文档导航

### 架构决策记录（ADR）

| # | 决策 | 一句话 |
|---|---|---|
| — | [`docs/adr/README.md`](docs/adr/README.md) | 索引 + "map≠territory，territory wins" 声明 |
| 0001 | [`内容哈希证据`](docs/adr/0001-content-hashing-evidence.md) | 证据 sha256，tamper-perceiving 非防篡改 |
| 0002 | [`顺序同步 runner`](docs/adr/0002-sequential-synchronous-runner.md) | 证据一致性 > 吞吐 |
| 0003 | [`本地 JSONL 审计`](docs/adr/0003-local-jsonl-audit-trail.md) | 否 Langfuse，可 diff/replay |
| 0004 | [`verifier ≠ scorer`](docs/adr/0004-verifier-is-not-scorer.md) | 结构判定 vs 权威分数（31/31 假绿活标本） |

### 方法论博客

- [`docs/blog/001-auditable-llm-eval-no-green-lights.md`](docs/blog/001-auditable-llm-eval-no-green-lights.md) — *Auditable LLM Eval: No Green Lights*（HN 向，以"100% 绿 vs 67–69% 真"为可复现实证链）
- [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) — **🚀 小白上手指南**（从装 Python 到跑出"假绿"证据，含完整训练路径与排错表）

---

## 实证分数链（同口径）

`COPILOT_RETROSPECTIVE.md`（评测平台复盘，分数链至 v2）为实证来源；完整修复链见博客 §。

> ✅ 下表分数为**本仓库提交 run 的可复现结果**（由 `verify_copilot_run.py` 从磁盘算出，全 PASS）。两个模型在 naive 实时验证器眼里都是 100% 绿，但权威 scorer 只给 ~2/3。

| 模型 / run | 实时 verdicts（naive） | 权威 reference_checks | 关键说明 |
|---|---|---|---|
| **v3c（修复）** `runs/20260713-211540-…` | 50/50（100% 绿） | **69.00%** | r16/α32·2ep·LR3e-5；过度声称 3 条 |
| **v3（对照）** `runs/20260713-213920-…` | 50/50（100% 绿） | **67.00%** | r8/α16·1ep·LR2e-5；输出通顺（未崩溃），过度声称 7 条 |

> 历史弧线（会话日志，**本仓库未复现**，仅作动机）：7B few-shot 87.80% · 3B few-shot 82.11% · v3c *据称* 77.69% · v2 68.29% · v3 *据称* 7.59%（围栏崩溃）· v3b *据称* 8.47%。请勿作为本仓库结果引用。

**结论**：naive 验证器的 100% 绿掩盖了真实质量——权威 scorer 揭示只有约 2/3 的 reference check 通过，差距集中在 `report_summary`（33%）。把"结构通过"与"质量打分"分开、把落差写进 CI，正是本平台的核心纪律。

---

## 与其他文档的关系

本子项目的文档由根 `README.md` §10 入口可达。根工程（TMLR 微调）的 ADR 与博客均位于本 `docs/` 目录；实证原始记录见根目录 `COPILOT_RETROSPECTIVE.md` 与 `COPILOT_NEXT_STEPS.md`。

*文档状态（2026-07-13）：本 `docs/` 为重建落盘版本（此前因会话断连丢失），均以真实代码理念与**已提交、可复现的 run**（v3c 69.00% / v3 67.00%）为依据；更早会话日志里的 77.69%/7.59% 弧线未被提交 run 复现、已降级为动机（见上方状态框）。*
