# llm-lab-copilot 下一步方案

> 当前基线：**v3.2 = 87.80%（108/123）**，report_summary 86%、eval_yaml 91%、reviewer_qa 90%、failure_diagnosis 88%、verifier_design 80%。

---

## 1. 剩余 gap 分析

| 任务 | 当前 | 满分 | 剩余可追 checks | 瓶颈类型 |
|---|---|---|---|---|
| eval_yaml_generation | 91.18% (31/34) | 34 | 3 | 次要（已 91%） |
| failure_diagnosis | 88.46% (23/26) | 26 | 3 | 中等 |
| verifier_design | 80.00% (16/20) | 20 | 4 | **最大弱项** |
| reviewer_qa | 90.48% (19/21) | 21 | 2 | 次要 |
| report_summary | 86.36% (19/22) | 22 | 3 | 中等 |
| **合计** | **108** | **123** | **15** | — |

提示工程仍有空间：**verifier_design 的 ~25% gap（4/20）**和 **failure_diagnosis 的 ~12% gap（3/26）**是最大目标。

---

## 2. 路径 A：v3.2.1 — 修复 verifier_design 单 check 回归

### 目标
挽回 v3.2 中 `verifier_005` 的 `must_check_reason_and_action` 回归（v3 pass → v3.2 fail），预期总分 +0.81pp → **88.62%（109/123）**。

### 怎么做
- Contract E 是 verifier_design 的对应段。将 Contract E 从 v3 的抽象描述改为 v3.2 风格的填空模板（同 B 的策略：保留编号结构、加格式示例、不引入新概念）。
- 从 v3.2 派生 few_shot_v3.2.1.jsonl（只改 E，B 保持 v3.2 不动）。
- 成本：改写 5 min + 跑 8-10 min + 打分验证。

### 风险
- 极低——只改 Contract E 且沿用 v3.2 的成功策略（编号结构 + 填空模板 + 零概念泄漏）。v3.2 已证明这种策略不会扩散污染其他任务。
- 但 verifier_design 的剩余 3 checks 可能跟模型能力天花板有关，不一定全能用提示修复。实际收益可能 <1pp。

### 建议
作为 M2 之前的"快速提分"，成本低、风险小、收益确定。即使只 +1 check 也是净赢。

---

## 3. 路径 B：M2 训练（3B QLoRA）

### 目标
用 few-shot 提示 + train_seed_200.jsonl 做监督微调，目标 beats **87.80%**。

### 技术方案

| 项 | 配置 |
|---|---|
| 基座模型 | `qwen2.5-coder:3b`（需 `ollama pull`，Q4_K_M ≈ 2GB）/ 备选 `qwen3:4b` |
| 微调方法 | QLoRA（4bit NF4），lora_r=16，lora_alpha=32，target_modules=q_proj,v_proj,k_proj,o_proj |
| 框架 | Unsloth + TRL SFTTrainer（与已有 `low-vram-llm-finetune` skill 一致） |
| 训练数据 | `datasets/llm_lab_copilot/train_seed_200.jsonl`（200 条）+ `hard_cases_50.jsonl`（50 条）= 250 条 |
| 提示格式 | v3.2 风格（Contract A-E + few-shot 前缀 + task） |
| seq_len | 2048（3B 舒适）/ 1024（7B 勉强） |
| batch_size | 4（3B）/ 1（7B） |
| epochs | 2-3 |
| GPU/VRAM | RTX 3060 6GB，3B 舒适（batch=4, seq_len=2048 ≈ 5GB）；7B 勉强（batch=1, seq_len=1024, OOM 风险） |

### 关键决策：用 3B 还是 7B？

- **3B 优先**（推荐）：基座必须同系列（qwen2.5-coder:3b），LoRA 后可 merge 或直接推理。eval 时用 3B+LoRA 与 3B few-shot baseline 对比（而非与 7B v3.2 对比），因为模型尺度不同。需先测 3B 的 zero-shot / few-shot v3.2 基线（预估比 7B 低 3-5pp），训练目标 beats 3B 的 few-shot 基线。
- **7B 替代**：直接在 `qwen2.5-coder:7b` 上做 QLoRA（batch=1, seq_len=1024, max_grad_accum=4）。eval 时直接对比 7B v3.2 基线 87.80%。但 6GB VRAM 紧张，需精确调参并接受较慢训练。

### 实验设计（eval-first，参照上一轮纪律）

1. **先测 3B 基线**（不训练）：
   - 3B zero-shot（50 条，无 few-shot 前缀）→ 预计 50-60%
   - 3B few-shot v3.2（50 条，与 v3.2 相同提示）→ 预计 75-82%
2. **训练**（仅当 3B few-shot 基线 < 87.80% 时训练才有意义）：
   - 用 v3.2 风格提示 + train_seed_200 训练 → 产出 LoRA adapter
   - 在 test_50 上 eval 3B+LoRA（few-shot v3.2 提示）
3. **成功标准**：3B+LoRA few-shot score > 3B few-shot 基线，且 gap ≥ 3pp。

### 风险
- 3B 尺度比 7B 小，即使微调后可能仍低于 7B v3.2 基线（87.80%）。这不是失败——3B+LoRA beats 3B few-shot 本身就有意义。
- 如果要在 7B 基数上做微调并以 87.80% 为目标，6GB VRAM 是一个硬约束（batch=1 勉强可以，但训练慢且不稳定）。

---

## 4. 推荐路线

```
v3.2 (87.80%) 
  │
  ├─ [P1, 立刻可做] v3.2.1: 填空模板改 Contract E → 预期 88.62% (109/123)
  │    成本: ~15min, 风险: 极低
  │
  └─ [M2, 需要准备] 3B QLoRA 训练
        ├─ 1. pull qwen2.5-coder:3b (5min)  
        ├─ 2. 测 3B zero-shot + few-shot 基线 (~20min run)
        ├─ 3. 审 train_seed_200 数据质量 + v3.2 风格对齐
        ├─ 4. 训练 (~30-60min on 3060)
        └─ 5. eval 3B+LoRA → 对比基线
```

**建议先做 P1，再做 M2。** P1 成本极低且几乎稳赢（同策略已验证），做完 P1 后拿到 v3.2.1 的分数（≈88.6%）再切 M2——那时基线更高、目标更明确。

---

## 5. 你只需确认

1. **先 P1 还是直跳 M2？**
2. 如果 M2：用 **qwen2.5-coder:3b**（更安全，同系列）还是 **qwen2.5-coder:7b**（直接对标 v3.2 基线但 VRAM 紧张）？
3. 训练数据：现有的 `train_seed_200.jsonl` 是否需要先用 v3.2 风格重刷一遍提示？

---

## 6. 实测结论（2026-07-12 收尾）：3B QLoRA 未 beats 基线

**eval 已全部完成（50/50，0 error）。实测结果（同一数据集 few_shot_v3.2.jsonl / 123 reference-checks / 同一 scorer）：**

| 模型 | micro | macro | YAML schema |
|---|---:|---:|---:|
| 3B few-shot v3.2 (run 152341) | 82.11% | 82.40% | 8/50 |
| 7B v3.2 基线 (run 140642) | 87.80% | 87.30% | 9/50 |
| **3B-LoRA-v2 (run 233918)** | **68.29%** | **72.32%** | **1/50** |

- ❌ **目标未达成**：LoRA 不升反降，比 3B few-shot 还低 14 分，比 7B v3.2 低 19.5 分。
- 回退集中在 `eval_yaml_generation`（76.5%→29.4%）；根因=QLoRA 让模型在 YAML 行内列表后多打标点（`[...].` 致语法错），27/50 解析失败。
- 避开了 live verdicts 的"假绿"（显示 100%，实际只过非空+长度检查）。

**新建议（替换原文 §4 的 M2 优先级）**：
- 对 3B 体量，**few-shot v3.2（82.11%）是当前最佳可行方案**，不要为了"微调"而微调。
- 若仍要微调路线：① 修 train_seed_200 的 YAML 格式（全过 yaml.safe_load）；② 把 eval_yaml 类任务显式纳入训练集；③ 降 LoRA 侵入度（r=8/α=16、1 epoch、更低 lr）缓解灾难性遗忘；④ 资源允许则上 7B/14B QLoRA + few-shot 更可能 beats 87.80%。
- v3.2.1（P1）当初未做——但它针对的是 7B 基线 87.80%，即使成功（≈88.6%）也仍低于本次 3B 微调的失败成本；**当前最高优先级是接受"3B few-shot 82.11% 为该体量 SOTA"，把微调当作未验证的高风险选项。**

详见 `reports/copilot_prompt_3b_lora_report.md`。
