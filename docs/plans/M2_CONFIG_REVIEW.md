# M2（3B 训练）配置审查 —— 兼"审稿偏好 LoRA"数据路径定位

> 审查对象：`train/train_lora.py` 实际默认参数 vs 方案文档 `qwen25-3b-tmlr-finetune-plan.md` §3。
> 结论先行：**除 batch/seq 在 3060 上的自动降档外，超参配置与方案完全一致**；真正需要你决策的是"审稿偏好"数据的来源缺口（见 §3）。

---

## 1. 超参审计表（方案 vs 脚本 vs 评价）

| 参数 | 方案文档 §3 | `train_lora.py` 默认 | 评价 |
|---|---|---|---|
| 量化 | 4bit NF4 + 双量化 | `load_in_4bit=True`（Unsloth 默认双量化） | ✅ 一致 |
| `max_seq_length` | 4096 | argparse 默认 4096；**3060 被 low 档覆盖为 2048** | ⚠ 见 §2 |
| LoRA `r` | 32 | 32 | ✅ |
| LoRA `alpha` | 64 | `r*2`=64 | ✅ |
| LoRA `dropout` | 0.1 | 0.1 | ✅ |
| `target_modules` | 7 个线性层 | 7 个 | ✅ |
| `bias` | none | none | ✅ |
| `gradient_checkpointing` | unsloth | unsloth | ✅ |
| 优化器 | `paged_adamw_8bit` | `paged_adamw_8bit` | ✅ |
| `per_device_train_batch_size` | 4（"舒适区"） | 4；**3060 被 low 档覆盖为 2** | ⚠ 见 §2 |
| `gradient_accumulation_steps` | 4 | 4 | ✅ |
| `warmup_ratio` | 0.03 | 0.03 | ✅ |
| `num_train_epochs` | 2（方案由 3 下调） | 2 | ✅ |
| `learning_rate` | 1e-4（方案由 2e-4 下调） | 1e-4 | ✅ |
| `lr_scheduler_type` | cosine | cosine | ✅ |
| `bf16` / `fp16` | fp16（3060 无 bf16） | `fp16=True` 硬编码 | ✅ |
| `max_grad_norm` | 0.3 | 0.3 | ✅ |
| `logging_steps` | 10 | 10 | ✅ |
| 验证/早停 | 5% 验证 + 早停 | `eval-ratio=0.05` + `EarlyStoppingCallback(3)` + `load_best_model_at_end` | ✅ |
| HF 缓存 | — | 默认重定向 `F:/hf_cache`（避 C 盘） | ✅ 符合治本策略 |

**审计结论：** 量化、LoRA、优化器、学习率、早停、缓存重定向均与方案一致，无需改动。唯一偏差是 §2 的 batch/seq 降档。

---

## 2. 关键发现：3060 必触发"low 档"降批（已修复逻辑）

`train_lora.py` 的 `env_check()` 判定阈值：

```python
if total < 6.5 * 1024**3:   # 6.5 GiB
    return "low"
```

而 **RTX 3060 = 6.0 GiB < 6.5 GiB**，因此**任何 3060 运行都会进入 low 档**，旧逻辑无条件执行：

```python
args.batch = min(args.batch, 2)      # 方案期望的 4 被覆盖
args.seq_len = min(args.seq_len, 2048)  # 方案期望的 4096 被覆盖
```

这与方案文档"3B 舒适区 batch=4 / seq=4096"直接矛盾，且**即使你显式传 `--batch 4` 也会被 `min()` 抹掉**——你无法在 3060 上尝试方案的吞吐目标。

**已修复（本次）：** 降级仅作用于"用户未显式指定"的情况，保留安全默认的同时允许进阶覆盖：

```python
user_set_batch = "--batch" in sys.argv
user_set_seq   = "--seq-len" in sys.argv
if tier == "low":
    if not user_set_batch: args.batch   = min(args.batch, 2)
    if not user_set_seq:   args.seq_len = min(args.seq_len, 2048)
```

**影响与建议：**
- 默认运行（不传 `--batch/--seq-len`）：行为不变 → 3060 上 batch=2 / seq=2048，**安全优先**，每 epoch 步数约翻倍，训练更慢但零 OOM 风险。
- 首次跑通后若 `nvidia-smi` 显示峰值显存 < ~5.0GB、仍有余量，可尝试方案的吞吐目标：
  ```
  python train/train_lora.py --model Qwen/Qwen2.5-3B-Instruct \
         --data data/training_all.jsonl --out outputs/qwen25-3b-tmlr --merge \
         --batch 4 --seq-len 4096
  ```
  若报 CUDA OOM，立即回退到默认（删掉这两个 flag）或降到 `--batch 2 --seq-len 4096`。
- 想从 `run_all.py` 直接用方案目标，需给 M2 调用补 `--batch/--seq-len` 透传（当前 `run_all` 未透传这两个参数）；建议先单独跑 `train_lora.py` 调通后再改编排器。

---

## 3. "审稿偏好 LoRA"的数据缺口（核心决策点）

方案当前把 M2 定位为 **"TMLR 领域专家"**（懂方法/公式/实验）。你说的"审稿偏好 LoRA"隐含一个更具体的目标：**让模型模仿你的审稿视角与评判偏好**。这两者在数据层面并不等同，需明确：

### 3.1 当前管道实际喂给 M2 的数据
`training_all.jsonl` = `fulltext_cot_data.jsonl`（arXiv 领域理解 A/B/C/F）+ 可选 `manuscript_cot_data.jsonl`（你的稿件）。

其中 `convert_manuscript.py` 产出的是 **"作者侧"理解样本**（提炼方法、复现实验、解释公式）——它让模型**懂你的研究内容**，但**不产出"审稿人侧"样本**（给定一篇稿，输出你会质疑什么、看重什么）。

### 3.2 缺口
- **没有脚本生成"审稿偏好"样本**：当前没有任何环节把"你对论文的评判标准/审稿口吻"写进训练集。
- **你的独特资产未被充分利用**：#47–51 的 TMLR 投稿记录、你收到的审稿意见、你做 PC/审稿时的真实评语——这些才是"审稿偏好"的语料，但管道只用了**稿件正文**，没用**审稿视角**。

### 3.3 三条可选路径（按风险递增）

| 路径 | 做法 | 数据来源 | 风险/成本 |
|---|---|---|---|
| **A. 维持领域专家基线** | 直接跑通现有管道 | arXiv + 你的稿件 | 零新增；先拿到能用的领域专家，再迭代 |
| **B. 增"审稿偏好"数据轨**（已实现，推荐第二轮） | 生成器 `convert_reviews.py` 已实现：输入每行为 `{excerpt,review}`（针对片段的审稿意见）或 `{principles}`（审稿准则），输出 `review_cot_data.jsonl`；经 `run_all.py --reviews` 并入 `training_all.jsonl`；格式模板见 `review_corpus_TEMPLATE.jsonl`（示例，需替换为真实语料） | 你的审稿记录、对 #47–51 的复盘、偏好清单（如"重视消融/可复现/显著性检验"） | 中：需你提供语料（替换模板）；不动训练骨架 |
| **C. 复用稿件换模板** | 让 `convert_manuscript` 增加"审稿视角"模板（给定方法段→"作为审稿人我会质疑…"） | 你的稿件（无真实审稿语料） | 高：可能学到"伪审稿口吻"，偏好不真实 |

**建议（落地顺序）：**
1. **先用路径 A 跑通 M0→M3 全流程**，拿到领域专家基线（这是"按你的建议来"已铺好的步骤）。
2. 基线达标后，用**路径 B** 补"审稿偏好"数据做**第二轮 LoRA**（数据追加，脚本骨架不变）：
   - 把你的真实审稿语料按 `convert_reviews.py` 的输入格式整理：`{"excerpt":"<论文片段原文>","review":"<你的真实审稿意见>"}` 或 `{"principles":"<你最看重的审稿准则>"}`，每行一条，存 `review_corpus.jsonl`（先 `python data/convert_reviews.py --make-template review_corpus_TEMPLATE.jsonl` 看格式）。
   - 跑 `python run_all.py --papers 200 --manuscript "你的稿件.tex" --reviews "review_corpus.jsonl"`：脚本会生成 `review_cot_data.jsonl` 并并入 `training_all.jsonl`。
   - 第二轮训练建议 `lora_r` 保持 32、适当降 `learning_rate`（审稿语料少，易过拟合），或对新数据用独立 LoRA 适配器避免冲刷领域能力。

> 注：是否需要我现在就写 `convert_reviews.py` + 整理你的审稿语料模板？这取决于你手头是否有可提炼的审稿记录。若有，路径 B 可立刻启动。

---

## 4. 推荐的 M2 执行命令

**首轮（路径 A，安全默认）：**
```bash
python train/train_lora.py --model Qwen/Qwen2.5-3B-Instruct \
       --data data/training_all.jsonl --out outputs/qwen25-3b-tmlr --merge
```
预期：3060 上 batch=2 / seq=2048；启用 5% 验证 + 早停；产物 `outputs/qwen25-3b-tmlr-merged/`（~6GB fp16）。

**进阶（确认有余量后尝试方案吞吐目标）：** 在上条末尾加 `--batch 4 --seq-len 4096`（OOM 即回退）。

---

## 5. 与方案文档的待同步项
- `qwen25-3b-tmlr-finetune-plan.md` §3 的 batch/seq "舒适区"描述与 3060 实际降档行为存在张力，建议在文档中补一句："3060 默认进入 low 档（batch=2/seq=2048）；显存有余时可显式 `--batch 4 --seq-len 4096` 覆盖。"
- 若确定走"审稿偏好"路线，方案应新增 §2.4「审稿偏好数据来源与格式」。

---
*审查依据：`train/train_lora.py`、`qwen25-3b-tmlr-finetune-plan.md`、`run_all.py` 当前实现。Batch/seq 降档逻辑已于 2026-07-12 修复。*
