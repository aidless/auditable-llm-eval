# 下一步计划（Next-Step Plan）— 2026-07-12

> 依据：用户反思「few-shot 已证有效，但微调必要性未被证明 → 先补评估闭环，不贸然训练」。
> 范围：两条独立工作流（A=llm-lab-copilot 优先；B=TMLR 3B 管线，弹药就位、训练暂缓）。

---

## 0. 当前状态快照（实测）

| 项 | 状态 |
|---|---|
| M1 数据腿（TMLR） | 后台任务随会话重置丢失，`data/training_all.jsonl` = 0 字节；需重跑（依赖已修：arxiv 4.0.0 + build_dataset.py 容错） |
| llm-lab-copilot 代码 | **本机未找到**（score_copilot_run.py / test_50.jsonl / train_seed_50.jsonl 均缺失）→ 执行 A1 前的**阻塞项** |
| 战略决定 | 采纳用户反思：eval-first；训练动作被 eval-loop 结论门控，暂不扣扳机 |
| 已就绪弹药（TMLR） | 三件套脚本 + run_all.py 编排器 + convert_reviews.py（路径 B）+ 排错速查 + 技能包（11 条目，arxiv 已锁 4.0.0） |

---

## 1. 总体原则

- **两条工作流解耦**：A 是 copilot 的 eval-first 实验；B 是为 3B 采 TMLR 数据的管线。两者训练集不同、模型不同，可并行，但**两者的训练动作都暂缓**。
- **决策纪律（核心）**：先让评分器可信 + few-shot 效应被隔离/饱和，再决定是否 QLoRA。禁止「同时动 prompt 和 data 再训」——否则分不清是谁涨的。
- **成本视角（对你反思的延伸）**：微调必要性不是「FT vs Base」二选一，而是 **(FT+few 相对 Base+few 的增量) × (零/few-shot 推理的成本节省)**。高频调用的 copilot，若微调后能零-shot 达到 few-shot 水平，长期更省。
- **门槛的语义**：75% 等硬门槛的作用是「判断 few-shot 是否饱和」，不是「达标就永不训」。若 few-shot 仍涨→继续加示例；若封顶→那才是该训的信号。

---

## 2. 工作流 A：llm-lab-copilot eval-first（主线，优先）

### Phase A0 — 定位代码（阻塞项，需用户）
- 你提供 `llm-lab-copilot` 仓库路径，或挂到当前工作目录。
- 确认存在：`score_copilot_run.py`、`test_50.jsonl`(held-out)、`train_seed_50.jsonl`。

### Phase A1 — 升级评分器（优先级 #1）
- 补全 `reference_checks` 覆盖（当前缺）：
  `must_include_any_keywords` / `must_include_all_keywords` / `must_answer_no` /
  `must_explain_surface_constraints` / `must_recommend_manual_or_semantic_eval` /
  `must_mention_rerun_or_reproducibility` / `must_not_claim_tamper_proof` /
  `must_distinguish_provider_error` / `must_not_judge_semantic_quality` /
  `must_check_reason_and_action`
- 输出结构升级为：
  ```json
  {
    "exact_checks": {}, "soft_checks": {},
    "unsupported_claims": [], "missing_required_points": [], "score": 0.0
  }
  ```
- 理由：当前 `failure_diagnosis` / `verifier_design` / `reviewer_qa` 分数偏保守，**很可能含评分器混淆**；不先修这步，后面所有数字不可信。

### Phase A2 — few-shot v2 prompt
- 任务专用 system prompt（声明角色、禁止过度宣称结构验证=语义质量、强制区分 provider/verifier/config 错误）。
- 每类任务 2 个示例（共 10）：eval_yaml(2) / report_summary(2) / failure_diagnosis(2) / verifier_design(2) / reviewer_qa(2)。
- 三条硬规则视为输出约束：
  - `errors.jsonl / timeout / connection refused` → provider error
  - 有 output 但 verdict failed → verifier fail
  - YAML parse / path / provider 不合法 → config/dataset error
- **运行时与语义分离**：`summary_002` 类 240s timeout 计为 provider reliability，不计入 answer quality。

### Phase A3 — 跑 full 50：四组对照
```
A. base_zero_shot
B. base_few_shot_v1        (原 3 示例)
C. base_few_shot_v2        (A2 的 10 示例)
D. base_few_shot_v2 + improved scorer (A1)
```
- `test_50.jsonl` 保持 held-out 不动。
- 新增 `test_hard_50.jsonl`：专放易误判样本（provider timeout / partial run / structural pass 但明显不能证质量 / verifier 过严 / reviewer challenge），看鲁棒性。

### Phase A4 — 生成 `copilot_prompt_v2_report.md`
- 趋势对比 + 哪些检查仍 failing + unsupported_claims 来源 + 运行时 vs 语义分离后的真实分数。

### Phase A5 — 决策门（看 A3/A4 结果）
- **微调必要性下降**（暂缓训）：overall ≥75% 且 `eval.yaml ≥85%`、`failure_diagnosis ≥65%`。
- **进入 QLoRA**（保守）：弱项持续 `failure_diagnosis <60%` / `reviewer_qa <60%` / `verifier_design <60%`，且 few-shot 已封顶。

### Phase A6（仅当 A5 进入训练）— 扩数据 + QLoRA
- **扩 `train_seed` 到 200 放在「决定微调之后」**，不与 few-shot v2 同时变两量（否则无法分离 prompt vs data 贡献）。
- 比例：eval.yaml 60 / report_summary 40 / failure_diagnosis 45 / verifier_design 30 / reviewer_qa 25；重点补 hard cases（timeout 无 verdict、100% pass 不能证质量、all_keywords 过死、path 错、YAML 缩进错、provider 失败、counts 不一致）。
- 保守 QLoRA 配置（7B 在本机 6GB 很紧，先停 Ollama）：
  `4bit NF4 / max_seq_len 2048 / rank 8 / alpha 16 / dropout 0.05 / batch 1 / grad_accum 16 / epochs 2 / lr 2e-4`
  先用 50 条 smoke train 确认不 OOM，再上 200。
- 必须比较 `Base / Base+few / FT / FT+few`；判定标准是 **FT 是否超过 Base+few-shot**（非 FT 是否超过 Base）。

---

## 3. 工作流 B：TMLR 3B 管线（暂停训练，保留弹药）

- **M1 数据腿**：`training_all.jsonl` 空（后台任务丢失）。因训练暂缓，排期靠后；修复已就位（arxiv 4.0.0 + build_dataset.py 容错），随时可重跑：
  `python run_all.py --skip-m0 --skip-m2 --skip-m3 --papers 20`（受管 venv，arxiv 4.0.0）。
- **M2 训练**：暂停。等 copilot eval-loop 结论，或独立验证「3B 场景 few-shot 也够用」后再决定是否训。
- **路径 B（审稿偏好）**：待你提供真实 `review_corpus.jsonl`（#47–51 审稿意见 / PC 评语 / 偏好清单）后，再 `--reviews` 启动；模板勿当训练语料。
- 管线本身已是「可执行的选项」，不是必须立刻训——与 A 的纪律一致。

---

## 4. 成功标准（硬门槛，来自用户反思，作 gate 用）

| 指标 | 目标 |
|---|---:|
| overall reference check rate | ≥ 75% |
| eval.yaml generation | ≥ 85% |
| report_summary | ≥ 75% |
| failure_diagnosis | ≥ 70% |
| verifier_design | ≥ 65% |
| reviewer_qa | ≥ 65% |
| provider/config/semantic 错误区分 | ≥ 80% |
| unsupported claims | 下降 ≥ 30% |

若微调后未超过 Base+few-shot 至少 10 个百分点 → 不继续扩训。

---

## 5. 我需要你确认的两件事

1. **llm-lab-copilot 仓库路径**（执行 A1 前必须）→ 指给我，或把仓库挂到当前目录。
2. **是否把「eval-first / 证明必要性再训练」固化为长期协作纪律** → 跨项目都值钱，可写进 `~/.workbuddy/MEMORY.md`。

---

## 6. 若你说「按这个来」

- 我先等你给路径 → 从 **A1 评分器升级** 动手，严格不碰训练；
- 同时可并行重跑 B 的 M1 数据腿（不冲突，且是「数据先行」）；
- 每完成一 phase 即回报实际产出与数字，绝不越过 A5 决策门自行训练。
